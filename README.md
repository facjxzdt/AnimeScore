# AnimeScore

使用 [bangumi-data](https://github.com/bangumi-data/bangumi-data) 作为番剧目录，按站点 ID 聚合 Bangumi、MyAnimeList、AniList、Filmarks、Anikore 评分的 Web 应用与 FastAPI 服务。

基础数据和评分分开管理：标题、译名、类型、开播日期、播放站点、跨站 ID 来自 bangumi-data；评分从对应平台获取，统一为十分制。不再依赖 Bangumi 日历、逐站标题猜测或 `mapping/anime_map.json` 构建默认目录。

## 快速开始

需要 Python 3.11 或 3.12，以及 Node.js 22 或更新版本（仅构建前端时使用）。

```bash
git clone https://github.com/facjxzdt/AnimeScore.git
cd AnimeScore
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m scripts.sync_catalog
cd frontend
npm ci
npm run build
cd ..
python start_api.py
```

- Web 界面：<http://localhost:5001/>
- API 文档：<http://localhost:5001/docs>
- 数据源状态：<http://localhost:5001/api/v1/catalog/>
- 健康检查：<http://localhost:5001/api/v1/health/>
- Windows 也可运行 `run.ps1` 或 `run.bat`。

启动时会检查并更新目录；已有缓存的有效期默认是 24 小时。运行期间每小时检查一次过期情况。更新经过完整格式校验，再原子替换本地文件；下载或校验失败时继续使用上次有效数据。第一次运行且没有有效数据时，目录接口返回 503，健康检查返回 `degraded`。

## Bangumi 登录与用户投稿

网站通过 [Bangumi OAuth 授权码流程](https://github.com/bangumi/api/blob/master/docs-raw/How-to-Auth.md) 登录，不接收 Bangumi 密码。后端交换授权码，再通过 `/v0/me` 核验 UID；Bangumi Token 不交给浏览器、不存入数据库。本站会话使用 HttpOnly、SameSite=Lax Cookie，HTTPS 下启用 Secure，最长七天。写操作需会话 CSRF 校验；退出会撤销服务端会话。OAuth 状态绑定浏览器、十分钟过期且只能使用一次。

在项目根目录 `.env` 或进程环境变量中设置以下项目，模板见 `.env.example`；进程环境变量优先，修改后重启后端：

| 变量 | 内容 |
| --- | --- |
| `BGM_CLIENT_ID` | Bangumi 开发者应用的 App ID |
| `BGM_CLIENT_SECRET` | 应用密钥，仅供后端使用 |
| `BGM_REDIRECT_URI` | 与应用注册值完全一致，如 `http://127.0.0.1:5002/api/v1/auth/bangumi/callback`；使用 5001 时修改端口 |
| `BGM_ADMIN_IDS` | 初始管理员的数字 UID、自定义用户名或个人主页链接，多个用逗号分隔；只在该账号首次登录本站时生效 |
| `LLM_BASE_URL` | OpenAI 兼容接口的基础地址，服务商需要时包含 `/v1`；程序追加 `/chat/completions` |
| `LLM_API_KEY` | 模型服务密钥，仅供后端使用 |
| `LLM_MODEL` | 服务商提供的模型名称，需支持 JSON object 输出 |

公网回调必须使用 HTTPS，HTTP 仅允许本机回环地址。模型接口同样要求 HTTPS，本地模型可使用回环 HTTP。未配置 OAuth 或模型时，对应功能明确显示未配置，不会模拟登录或伪造审核结果。`.env` 已排除在 Git 和 Docker 构建上下文之外；容器使用 `--env-file` 注入配置。

例如 `BGM_ADMIN_IDS=123456,custom_username,https://bgm.tv/user/another_user`。自定义用户名按 OAuth 返回的 `username` 精确匹配，不使用可重复的昵称；纯数字仅匹配数字 UID。主页链接支持 `bgm.tv`、`bangumi.tv` 和 `chii.in` 的 `/user/...` 路径。所有账号仍须完成 Bangumi 授权，不能通过自填 UID 登录。

管理员可在 `/admin` 的“用户与投稿管理”中搜索已登录的用户并设置角色；无法移除最后一位管理员。角色变更立即影响现有会话，并记录审计。`ANIMESCORE_ADMIN_TOKEN` 仍可作为运维管理入口；启用 OAuth 后关闭匿名本机管理，普通登录用户也无法借本机模式进入后台。若账号已先以普通用户登录，再添加 `BGM_ADMIN_IDS` 不会改写其角色，应由已有管理员或管理令牌进入后台调整。

普通用户在动画详情点击“补充缺失 ID”，可提交五个已接入评分站点的 ID 或作品链接。后端先检查格式、已有映射和重复 ID，再从固定的站点接口/作品页取资料，模型只核对标题、译名、季度、类型、首播日期等公开元数据。不会向模型发送用户信息、登录凭据或完整评论页面；模型无法调用工具，也不能改写待审核的 ID。只有结构完整、三项核对均通过且置信分达到 0.95 的 `match` 决定才会自动保存；置信分不是准确率保证，不确定结果进入人工审核。

通过后原子保存正式映射、提交者 Bangumi UID 和提交时用户名，并安排该站评分采集、历史记录与后续每小时更新。动画列表和详情下方显示小字署名，链接到稳定 UID；管理员改动为不同 ID 或删除映射时移除旧署名。采集失败不撤销正确映射，保留状态并由每小时任务重试。

每日错误限额按**提交时的北京时间自然日**计算：每个 UID 五次确定判错，达到五次后当天不能提交新审核；正确映射不扣次数。格式错误、重复/冲突、站点错误、模型超时/非法输出及无法确定均不扣次数。同一用户同一天重复错误 ID 只记一次；已有审核结果复用缓存，不重复调用模型。每人同时只能有一项待审投稿，提交间隔至少 30 秒。正确/错误决定缓存七天，不确定决定缓存一天；目录资料或模型配置变更会使用新的决定缓存键。单次模型调用最多 800 输出 Token，不自动重试付费调用。

投稿队列、错误账本、会话、审核依据及署名存入 SQLite。排队任务可以续跑；已开始却中断的审核标记失败并允许用户重试，不自动重复调用模型。管理员可查看依据后采纳未确定、失败或误判的投稿；纠正误判时退回相应日期的错误次数，同时保留原提交者署名。客户端“我的投稿”可查看状态及理由。

## 评分看板

首页直接显示当季榜单，支持中日英文搜索、年份与季度切换、类型筛选、平台覆盖及评分人次筛选。详情提供海报、简介、分站评分、评分人次、来源链接、综合评分与历史 CSV。数据观察页显示评分分布、平台覆盖和采集状态；收藏与个人权重保存在当前浏览器。

Web 默认权重为 **Bangumi 5、MyAnimeList 2**，AniList、Filmarks、Anikore 默认关闭。每站都有参与综合分的开关及 0–100 的权重；关闭后保留分站展示，重新开启恢复该站上次权重。旧浏览器保存的三站权重会自动迁移。权重仅影响当前用户的排名和历史综合分，不修改原始数据。缺失平台不计入分母；全零权重不允许。综合分仅代表已接入平台，评分人次跨平台未去重，未进行样本量校正。

后端启动后自动采集当季番剧和查看过详情的作品，每小时执行一次。SQLite 保存缓存、评分人数、真实小时快照、采集进度和调度时间；刷新网页只读取缓存，不触发整季联网。进程间通过带续期的数据库租约避免重复批量采集。采集时服务需要持续运行，重新启动会接续到期任务。

趋势支持 **7d / 30d / 90d / 1y**：前两档显示每小时末次真实记录，后两档显示每天（UTC）末次记录，保留 400 天。历史从首次成功采集时开始积累，不回填旧分数，不虚构曲线；失败平台的分数和人数留空。修改个人权重会根据原始分站快照重算整段历史。

需要提前重试一轮采集时，可运行 `python -m scripts.collect_scores`；它与自动采集共用租约、缓存和限流，并输出本轮状态。首次采集可能需要数分钟；平台异常会单独标记，不影响其他平台显示。

## 映射管理后台

访问 `/admin` 管理全部五个评分站点的 ID。支持按标题、译名或 ID 搜索，筛选缺失站点、查看人工修改、填写修改备注及导出映射 JSON。编辑器支持三种状态：跟随 bangumi-data、人工指定、禁用此映射。可直接粘贴作品链接，Filmarks 必须填写 `系列 ID/季度 ID`，例如 `1431/6089`，避免把同系列不同季混在一起。

“校验”读取该 ID 对应的作品名称、评分和评价人数，遵守评分缓存与站点限速；校验不自动保存。“保存映射”立即影响后续查询并将作品加入每小时跟踪；“采集已保存映射”补充当前映射下的评分。未保存的输入不参与采集。

人工映射、版本号、修改记录保存在同一个 SQLite 数据库中，独立于上游 JSON。目录重新同步不会覆盖人工值；恢复“跟随目录”会移除该站人工覆盖。后台会拒绝重复站点 ID 和过期版本的并发写入。修改站点 ID 后，旧 ID 对应的历史评分不会混入新映射的曲线，其他平台历史仍保留。

管理 API 支持 Bangumi 管理员会话或 `ANIMESCORE_ADMIN_TOKEN`，并校验同源请求。只有两者都未配置时才允许匿名本机回环管理。使用令牌时，在后台输入后才能读写；令牌仅存于当前标签页的会话存储。远程部署应使用 HTTPS。普通评分查询无需登录。

Filmarks 和 Anikore 采用作品页的五星均分乘二，Anikore 的百分制综合热度不作为评分。两站默认请求间隔三秒，受访问限制或页面结构变化时保留缓存并标记不可用。本次实测 Filmarks 可用，Anikore 对本机返回 HTTP 202 访问限制页，未绕过该限制。

### Filmarks 自动映射

后台可按季度或全部缺失条目启动批量任务，每批 1–250 部，支持仅查候选、自动保存确定匹配、停止任务及查看进度。系统先建立 Filmarks 季度目录索引，再使用原名、别名及缩短的检索词补查，最后核对同系列的其他季度。日文汉字期数、罗马数字、全半角和标点差异会规范化；仅有季数字样相似的无关作品会被过滤。目录解析兼容普通作品链接和通过页面点击属性导航的条目，不执行页面脚本。

自动保存要求：作品页 canonical ID 正确、规范化名称与原名或别名一致、开播日期相差不超过 31 天、只有一个符合条件的候选。Filmarks 的站内 `seasonNumber` 不等同于动画第几季，不据此匹配。电影条目、日期缺失、相似标题和多候选结果留待人工确认；不自动覆盖任何已有映射或人工禁用。后台可筛选“待确认”等状态，查看来源、名称及日期证据，把候选填入编辑器后保存。

部分年份的 Filmarks 季度目录不存在，返回 404/410 时按空目录缓存 24 小时，并继续按名称和别名搜索；搜索正常完成但无候选时显示“未找到”。作品页失效、搜索接口错误、403/429 限流和服务器错误仍按原规则处理，不会被当作空目录。

自动映射与人工映射共用版本冲突检测和修改记录，来源分别为 `auto` / `manual`；已有数据库会自动迁移。目录更新不覆盖这些映射。批量任务、候选、页面解析结果均持久化到 SQLite，任务中断可续跑，多进程共用任务租约。网络请求与 Filmarks 评分采集共用进程内限速；目录及候选缓存 24 小时，失败决策缓存一小时。遇到访问限制会停止任务并保留已完成进度。

服务默认每天补全当季缺失映射，成功后立即将作品页评分写入缓存与真实历史，并加入每小时评分跟踪。`FILMARKS_AUTO_MAP=0` 可停用每日自动任务，后台手动批量匹配仍可使用。命令行与后台共用任务：

```bash
python -m scripts.map_filmarks --year 2026 --season summer
python -m scripts.map_filmarks --all --limit 100 --review-only
python -m scripts.map_filmarks --year 2024 --season spring --force
```

重复执行全目录批次优先处理尚未检查的条目。`--force` 重新评估候选决策，仍复用未过期的页面缓存。

## 查询与评分

```text
GET /api/v1/search/?q=葬送的芙莉莲
GET /api/v1/search/?q=Frieren&include_scores=true
GET /api/v1/anime/?year=2026&month=7&limit=20
GET /api/v1/anime/season/2026/summer
GET /api/v1/anime/season/current
GET /api/v1/anime/400602
GET /api/v1/anime/400602?include_scores=false
```

默认搜索只读取本地目录及已有评分缓存。`include_scores=true` 会按目录中的 ID 获取评分；详情接口默认启用。列表、季度、统计和导出均读取评分缓存，避免一次请求触发全量外站抓取。无站点映射时不猜测 ID；缺失评分返回 `null`。`score_status` 区分未抓取、无映射、无评分、可用、过期和请求失败。

评分缓存在 SQLite 中，按平台和 ID 隔离，默认有效期一小时；失败后至少一分钟内不重复请求，HTTP 429 尊重更长的 `Retry-After`，有旧分数时继续返回并标记 `stale`。每个平台独立限速，AniList 默认间隔 2.2 秒。原有目录 API 的综合分继续使用 `data/config.py` 的 `weights` 配置；Web 使用独立的查询参数计算个人权重。

MAL 优先读取官方作品页的作品级均分、评价人数和排名，校验页面 canonical ID 后入库。官方页连接失败、限流或结构异常时自动回退 Jikan；两个来源分别限速（默认至少两秒）并遵守各自的 `Retry-After`，单个来源冷却不会阻塞另一个来源。双方失败时保留旧分数和原采集时间，不把失败伪装成无评分。`score_status.mal.source` 标识 `myanimelist` 或 `jikan`，`source_errors` 提供双方失败的诊断。

限速和并发合并在每个 API 工作进程内生效，多个进程共享 SQLite 结果；部署多个工作进程时需按平台配额控制请求总量。

批量刷新当季或历史季度评分：

```bash
python -m scripts.sync_catalog --scores
python -m scripts.sync_catalog --scores --year 2023 --season fall
python -m scripts.sync_catalog --force
```

`python -m apps.onekey` 和旧调度入口 `web_api.deamon.updata_score()` 也使用上述新流程。评分部分失败时保存成功结果，命令以非零状态退出，便于调度系统发现故障。

## 数据与时间约定

- 季度按 UTC+8 的开播时间计算：1–3 月为 winter，4–6 月为 spring，7–9 月为 summer，10–12 月为 fall。
- 周几优先取 `broadcast` 的起始日期，缺失时使用 `begin`；返回 1–7，表示周一至周日。
- “当季”包含该季度首播的所有类型，包括尚未开播的作品。“在播”限于已开播的 TV/web：有 `end` 时按实际区间判断；缺少 `end` 时只将当季首播作品列入在播，历史作品返回 `is_airing=null`。长期连载且缺少完结日期的作品可能不在在播列表中。
- 保留同名条目及没有 Bangumi ID 的条目。`catalog_id` 由原名、开播时间、类型和语言生成；上游修改这些字段时该 ID 会改变，跨版本关联优先使用站点 ID。
- 番剧级 URL、地区限制优先于站点模板；保留全部译名和站点信息。TMDB ID 保留 `tv/…`、`movie/…` 前缀。
- bangumi-data 不提供海报、简介、制作公司、监督和评分。采集时从评分平台补充可用的海报、简介、集数、制作公司、投票数与站内排名；没有采集到的字段保留为空。旧 `source=precise` / `source=bangumi` 搜索仍可显式使用。

## 配置与离线运行

可将 `.env.example` 中需要的变量导出到环境，或配置项目根目录的 `.env`。Web 服务启动时会读取 `.env`，已设置的环境变量优先；命令行同步和采集脚本使用环境变量。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `BANGUMI_DATA_URL` | 上游 `master/dist/data.json` 的 raw URL | 可配置镜像或固定版本的 JSON URL |
| `BANGUMI_DATA_PATH` | 项目内 `data/cache/bangumi-data.json` | 数据文件位置 |
| `BANGUMI_DATA_AUTO_UPDATE` | `1` | 启动和运行期间自动更新目录 |
| `BANGUMI_DATA_MAX_AGE_HOURS` | `24` | 缓存有效时长 |
| `SCORE_CACHE_PATH` | 项目内 `data/cache/ratings.sqlite3` | 评分缓存位置 |
| `SCORE_AUTO_UPDATE` | `1` | 后端每小时自动采集评分；设为 `0` 停用 |
| `FILMARKS_AUTO_MAP` | 跟随 `SCORE_AUTO_UPDATE` | 每日自动补全当季 Filmarks 映射；设为 `0` 停用自动任务 |
| `ANIMESCORE_ADMIN_TOKEN` | 无 | 可选运维管理令牌；也可通过 Bangumi 管理员会话访问后台 |
| `API_WORKERS` | `1` | API 工作进程数 |

导入已下载的上游 `dist/data.json`，无需安装 Node.js：

```bash
python -m scripts.sync_catalog --file /path/to/data.json
```

之后设置 `BANGUMI_DATA_AUTO_UPDATE=0`、`SCORE_AUTO_UPDATE=0`，查询时使用 `include_scores=false`（Web API 为 `refresh=false`），即可离线读取缓存。详情页会尝试更新单部作品，离线失败时保留已有缓存。同步工具与服务使用相同的数据文件，已运行的服务会在下次读取时识别文件更新。

## Docker

完整的 Compose、HTTPS、Bangumi/模型配置、数据迁移、备份与回滚步骤见 **[Docker 部署指南](DEPLOYMENT.md)**。发布镜像：`ghcr.io/facjxzdt/animescore:latest`，支持 amd64/arm64；每次成功发布同时提供 `sha-<七位提交号>` 标签。

项目提供 `compose.yaml`，可使用 `docker compose pull` 和 `docker compose up -d --no-build` 启动。默认只绑定 `127.0.0.1:5001`；公网 HTTPS 配置见指南。

```bash
docker build -t animescore:latest .
docker run -d -p 5001:5001 --name animescore \
  -v animescore-data:/app/data/cache animescore:latest
```

镜像使用 Node.js 阶段构建前端，由 FastAPI 同端口提供页面和 API。缓存卷保存目录、评分和历史，升级时应保留该卷。容器首次启动需要访问数据源，也可先向卷中导入数据。镜像不包含本机下载的缓存。

Docker 端口转发不视为容器内回环访问。使用后台时，通过 `--env-file` 配置 Bangumi OAuth 和初始管理员 UID，或通过 `-e ANIMESCORE_ADMIN_TOKEN` 传入运维管理令牌。

## 结构与验证

```text
services/catalog.py       上游模型、目录索引、检索、时间规则、缓存与同步
services/ratings.py       ID 评分查询、限速、SQLite 缓存、综合分
services/analytics.py     历史快照、个人加权、排名、采集租约
services/collector.py     每小时当季与已跟踪作品采集
services/providers.py     五站定义、ID 与作品链接校验
services/scrapers.py      Filmarks / Anikore 作品总评分解析
services/mappings.py      独立人工映射、版本控制和修改记录
frontend/src/             Web 看板、ECharts 图表、Lucide 图标
frontend/src/admin.*      映射管理后台
web_api/api_v1/           查询、详情、统计、导出、健康状态
scripts/sync_catalog.py   在线同步、离线导入、季度评分刷新
scripts/collect_scores.py 手动执行完整评分采集及状态记录
apis/                    旧客户端及显式 precise / bangumi 搜索兼容
tests/                   无网络回归测试
```

历史 `web/`、`next/`、旧评分 JSON 与爬虫工具保留，未作为新 API 的目录来源。订阅接口兼容 `data/jsons/sub_score_sorted.json`，存在目录记录时按 Bangumi ID 关联。新流程不再更新历史 `score_sorted.json`、`score.csv`，请通过 API 导出当前视图。

```bash
pip install -r requirements-dev.txt
python -m pytest -q
# 前端构建
cd frontend
npm ci
npm run build
# 启动服务并完成首次当季采集后，执行浏览器交互测试
# 默认连接 http://127.0.0.1:5001，Windows 使用已安装的 Edge
# 可用 WEB_TEST_URL 指定自己的服务地址；其他系统先运行 npx playwright install chromium
npm test
cd ..
# Linux / macOS 完整发布检查
bash scripts/release_check.sh
```

完整接口、迁移变化和错误语义见 [API_V1.md](API_V1.md)。GitHub Actions 在 Python 3.11、3.12 上运行无网络回归检查，并独立验证前端构建。浏览器测试会覆盖桌面与手机视口，生成截图；真实站点数据与网络状态可能影响首次详情采集。

## 数据署名

番剧基础数据来自 [bangumi-data/bangumi-data](https://github.com/bangumi-data/bangumi-data)，采用 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 许可。AnimeScore 对字段进行了转换、索引和派生时间计算，数据集本身不包含平台评分。JSON 导出和目录状态接口包含来源与许可信息；代码继续遵循仓库的 MIT 许可。
