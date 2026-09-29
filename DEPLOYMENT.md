# Docker 部署指南

本指南部署完整的 AnimeScore：评分网站、API、Bangumi 登录、映射管理、模型审核、每小时评分采集及每日 Filmarks 自动映射。

## 1. 准备环境

- 安装 Docker Engine 和 Docker Compose **2.30 或更高版本**；Windows/macOS 可使用 Docker Desktop 的 Linux 容器模式。
- 公网部署准备一个域名，将 DNS 指向服务器，并开放 TCP 80、443。使用已有反向代理时无需新增 Caddy。
- 服务器需要访问 GitHub/bangumi-data、各评分平台、Bangumi OAuth 及所配置的模型接口。
- 运行期间保留一个应用实例、一个 API worker。SQLite 数据卷不要通过网络文件系统在多台机器间共享。

```bash
docker version
docker compose version
git clone https://github.com/facjxzdt/AnimeScore.git
cd AnimeScore
cp .env.example .env
chmod 600 .env
```

下列终端示例使用 Linux/macOS Shell。Windows PowerShell 使用 `Copy-Item .env.example .env` 创建配置文件。

## 2. 填写配置

编辑 `.env`，配置值不要加外围引号。Compose 的 `env_file` 使用 `format: raw`，服务会收到原始值，包含 `$` 的密钥也不会在服务环境中被替换。不要将 `.env` 提交到 Git 或写进 Dockerfile。

```dotenv
# 公网访问域名，不带协议或路径；仅内置 Caddy 使用此项。
ANIMESCORE_DOMAIN=anime.example.com

BGM_CLIENT_ID=你的应用ID
BGM_CLIENT_SECRET=你的应用密钥
BGM_REDIRECT_URI=https://anime.example.com/api/v1/auth/bangumi/callback
BGM_ADMIN_IDS=你的数字UID或自定义用户名

# 基础地址需要 /v1 时包含 /v1，不要包含 /chat/completions。
LLM_BASE_URL=https://模型服务域名/v1
LLM_API_KEY=你的模型密钥
LLM_MODEL=模型名称

BANGUMI_DATA_AUTO_UPDATE=1
SCORE_AUTO_UPDATE=1
FILMARKS_AUTO_MAP=1
```

在 [Bangumi 开发者应用](https://bgm.tv/dev/app) 注册应用，回调地址必须与 `BGM_REDIRECT_URI` 完全一致，包括协议、域名、端口及路径。公网回调需要 HTTPS；HTTP 只允许 `localhost`、`127.0.0.1` 等回环地址。

`BGM_ADMIN_IDS` 支持数字 UID、自定义用户名，以及 `https://bgm.tv/user/用户名` 等主页链接；多人用英文逗号分隔。自定义用户名是个人主页 `/user/` 后的标识，不是显示昵称。**在首位管理员第一次登录之前配置此项。**账号已存在时，修改此项不会改写其角色；应通过已有管理员在后台调整，或临时配置 `ANIMESCORE_ADMIN_TOKEN` 作为运维入口。

模型需兼容 Chat Completions、JSON object 输出、`temperature` 和 `max_tokens` 参数。密钥只供后端使用。留空 OAuth 或模型配置时，相应功能显示未配置，公开评分查询仍可使用。每人每天五次确定判错，正确映射、上游错误及无法确定不扣次数；历史和错误账本保存在数据卷中。

## 3. 拉取镜像

主要镜像地址：`ghcr.io/facjxzdt/animescore:latest`。发布流程构建 `linux/amd64` 和 `linux/arm64`，并提供 `sha-<七位提交号>` 标签供固定版本部署。`latest` 跟随通过测试的 `master` 版本。

```bash
docker compose pull animescore
```

若 GHCR 返回 `denied`，先确认镜像发布流程已成功。如果包为私有，在 GitHub Packages 设置中开放包可见性，或使用具有 `read:packages` 权限的 GitHub 凭据登录后再拉取：

```bash
docker login ghcr.io -u YOUR_GITHUB_USERNAME
```

密码提示处填写 GitHub Token，不是 GitHub 账号密码。不要将 Token 写在命令参数、代码或部署文档里。原有 Docker Hub 凭据配置齐全时，Actions 同时更新 `facjxzdt/animescore` 镜像。

## 4. 选择启动方式

### 方式 A：本机使用或已有反向代理

```bash
docker compose config --quiet
docker compose up -d --no-build
docker compose ps
docker compose logs --tail=100 animescore
```

默认访问 `http://127.0.0.1:5001/`，后台为 `/admin`，API 文档为 `/docs`。端口只绑定服务器回环地址。远程服务器上的 `127.0.0.1` 指服务器自身，不是你浏览器所在的电脑。

本机登录的回调应设置为 `http://127.0.0.1:5001/api/v1/auth/bangumi/callback`，并在 Bangumi 应用中注册同一个地址。必须用 `127.0.0.1` 访问，避免与 `localhost` 混用导致 Cookie 或同源校验失败。

端口冲突时，在 `.env` 设置 `ANIMESCORE_PORT=5003`，同时修改回调地址。已有 Nginx/Caddy 等反向代理时，将域名的 HTTPS 请求转发至 `http://127.0.0.1:5001`，保留原始 Host，并设置 `X-Forwarded-Proto`。所有页面及 `/api/v1/` 都使用同一域名。

### 方式 B：使用内置 Caddy 提供公网 HTTPS

确认 `.env` 中已设置域名和 HTTPS 回调，DNS 已生效，80/443 没有被其他服务占用，然后执行：

```bash
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml pull
docker compose -f compose.yaml -f compose.https.yaml up -d --no-build
docker compose -f compose.yaml -f compose.https.yaml ps
docker compose -f compose.yaml -f compose.https.yaml logs --tail=100 caddy
```

访问 `https://anime.example.com/`。Caddy 自动申请和续期证书；此模式移除应用的宿主机 5001 端口映射，仅通过 Caddy 访问应用。证书使用独立数据卷保存。后续的 `up`、`pull`、`down` 等命令继续使用这两个 `-f` 参数。

### 从源码构建

不使用已发布镜像时，在 `.env` 设置 `ANIMESCORE_IMAGE=animescore:local`，然后执行：

```bash
docker compose build --pull animescore
docker compose up -d --no-build
```

HTTPS 模式为第二条命令追加前述两个 `-f` 参数。宿主机无需安装 Python 或 Node.js。镜像内以 UID/GID `10001:10001` 运行，前端在构建阶段打包；密钥、下载目录、SQLite、本地测试输出和 `node_modules` 不会打入镜像。

## 5. 首次启动检查

```bash
curl -fsS http://127.0.0.1:5001/api/v1/health/
curl -fsS http://127.0.0.1:5001/api/v1/catalog/
curl -fsS http://127.0.0.1:5001/api/v1/auth/me
```

HTTPS 部署将上面的基础地址换成你的 `https://域名`。

- `/auth/me` 在未登录时返回 `user: null`；配置有效时 `login_enabled`、`review_enabled` 为 `true`。这两个标志表示配置完整，不代表外部凭据已经验证成功。
- 首次启动会下载 bangumi-data。评分随后分批获取，完整当季采集可能需要数分钟。各平台失败互不影响已有结果。
- Docker 的 `healthy` 表示 HTTP 服务可响应；`/health/` 里的 `degraded` 可能表示目录下载失败或过期。首次没有目录时，搜索和榜单返回 503，应检查容器联网。
- 登录后访问 `/admin`，确认管理员角色。启用 OAuth 后匿名本机管理关闭；仅输入 UID 不会建立登录会话。
- 趋势图从部署后的首次采集开始积累，不会凭空生成过去 7 天、30 天或一年的数据。

部署验证无需调用付费模型。需要验证实际审核时，使用已登录账号提交一个真实缺失映射；模型审核通过后才保存映射和署名，再获取评分。

## 6. 数据持久化与迁移

Compose 默认项目名为 `animescore`，数据卷为 `animescore_data`，挂载到 `/app/data/cache`。其中主要包括：

| 文件 | 内容 |
| --- | --- |
| `bangumi-data.json` | 上游动画目录 |
| `ratings.sqlite3` | 评分缓存、历史、人工映射、用户角色、会话、投稿、错误次数及任务状态 |

重新构建镜像、更新镜像、重建容器都保留该卷。不要执行 `docker compose down -v`，它会删除数据卷。多套部署应使用不同的 `docker compose -p 项目名`，并在后续命令中保持一致。

导入本机已有的数据时，先停止原本写入这些文件的 AnimeScore 进程，并创建目标容器：

```bash
docker compose create animescore
docker compose cp ./data/cache/bangumi-data.json animescore:/app/data/cache/bangumi-data.json
docker compose cp ./data/cache/ratings.sqlite3 animescore:/app/data/cache/ratings.sqlite3
docker compose run --rm --no-deps --user 0 --cap-add CHOWN --entrypoint chown animescore -R 10001:10001 /app/data/cache
docker compose up -d --no-build
```

没有旧数据库时跳过数据库复制。若旧数据库存在同名 `-wal`、`-shm` 或 `-journal` 文件，应在原服务正常关闭后整目录备份并迁移，不能仅复制仍在写入的主数据库。旧版本容器创建的 root 所有数据卷，也需要先备份，再执行上面的所有者修正命令。

只有目录下载受阻时，可导入已下载的 `bangumi-data/dist/data.json`，或通过 `BANGUMI_DATA_URL` 指定可信镜像。不要把其他站点的任意 JSON 当成 bangumi-data。

## 7. 备份、升级和回滚

### 一致性备份

以下操作只短暂停止应用，保证 SQLite 和任务状态完整：

```bash
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "backups/$stamp"
chmod 700 backups
docker compose stop animescore
docker compose cp animescore:/app/data/cache/. "backups/$stamp/"
docker compose start animescore
```

如果复制失败，先处理磁盘或权限问题，再执行 `docker compose start animescore`。数据库备份包含登录会话和用户记录，应与密钥配置分开妥善保管；`.env` 另做私密备份，不要上传公开仓库。`backups/` 已排除在 Git 和 Docker 构建上下文之外。

### 更新版本

先备份数据，并记录当前镜像 ID 或 digest。然后在项目目录执行：

```bash
docker compose images
git pull --ff-only
docker compose pull animescore
docker compose up -d --no-build
docker compose ps
```

公网 HTTPS 部署更新时使用 `docker compose -f compose.yaml -f compose.https.yaml ...`。修改 `.env` 后同样执行 `up -d --force-recreate --no-build`；仅执行 `restart` 不会重新载入容器环境变量。

固定版本时，在 `.env` 设置 `ANIMESCORE_IMAGE=ghcr.io/facjxzdt/animescore:sha-提交号前七位`，或使用 `ghcr.io/facjxzdt/animescore@sha256:实际摘要`，再拉取和重建容器。不要把示例提交号当成真实标签。

### 恢复备份

先停止应用并备份当前卷，再将选定备份目录恢复到已创建的容器；目标若包含更新版本生成的 SQLite journal/WAL 文件，应使用新的空数据卷恢复，避免新旧数据库文件混用。恢复后将文件所有者设为 `10001:10001`，再启动对应版本的镜像。**回滚镜像并不自动回滚数据库结构**；遇到不兼容迁移，应恢复升级前的整份数据卷备份。

## 8. 排查常见问题

| 现象 | 检查方法 |
| --- | --- |
| `denied`，无法拉取 GHCR | 检查 Actions 是否已发布、包可见性以及 `docker login ghcr.io` |
| `Permission denied` / SQLite 无法写入 | 检查数据卷或挂载目录的 UID/GID 是否为 10001；不要把缓存目录挂成只读 |
| 登录未配置 | 检查三个 OAuth 配置项、回调格式，并重建容器 |
| 授权失败或状态过期 | 核对注册回调、浏览器地址的域名/协议，重新发起登录；避免在不同标签页混用授权流程 |
| 登录成功但不是管理员 | 初次登录前是否设置了 UID；自定义用户名是否与 OAuth 返回值一致；由现有管理员或运维令牌调整角色 |
| 模型审核暂不可用 | 检查基础地址、Key、模型名及 JSON object 支持；查看服务端日志，失败不扣用户错误次数 |
| 搜索/榜单 503 | 检查 `/api/v1/catalog/` 和 GitHub raw 连通性，必要时导入目录 |
| 有映射但无评分 | 站点可能无评分、限流或不可达；映射存在不等于评分采集成功 |
| Docker 健康但页面没数据 | 健康检查只检测 HTTP；继续检查目录状态和采集进度 |
| HTTPS 证书失败 | 检查域名 DNS、TCP 80/443、防火墙和 Caddy 日志 |

使用 `docker compose logs --tail=100 animescore` 查看应用日志。不要公开粘贴 `.env`、`docker inspect` 的完整环境变量或展开后的 `docker compose config`；校验 Compose 文件时使用 `config --quiet`。

## 9. GitHub 自动发布

工作流位于 [docker-build.yml](.github/workflows/docker-build.yml)。推送 `master`、`v*` 标签或手动运行后，依次执行 Python 3.11/3.12 测试、前端构建、容器页面与 API 检查、重启持久化检查，成功后发布 GHCR 多架构镜像。

GHCR 使用仓库内置 `GITHUB_TOKEN`，只授予发布任务 `packages: write` 权限，无需上传你的本地模型密钥或 Bangumi 密钥。已有 `DOCKERHUB_USERNAME` 和 `DOCKERHUB_TOKEN` 时保留 Docker Hub 同步发布。GitHub 新建的包可能默认私有，可在仓库关联的 Packages 页面检查可见性。

本地可复用容器检查，测试使用独立临时卷，不读取 `.env`，不联网采集评分或调用模型：

```bash
docker build -t animescore:ci-test .
python scripts/container_smoke.py --image animescore:ci-test
```

配置细节依据 [Docker Compose env_file 文档](https://docs.docker.com/reference/compose-file/services/#env_file)、[Compose 覆盖规则](https://docs.docker.com/reference/compose-file/merge/#reset-value)、[Caddy 反向代理文档](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) 和 [GitHub 镜像发布文档](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)。
