# AnimeScore API v1

前缀为 `/api/v1`，返回 JSON；交互文档位于 `/docs`。基础数据源为 [bangumi-data](https://github.com/bangumi-data/bangumi-data)，许可为 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。评分由各平台独立提供。

示例：`GET /api/v1/search/?q=Frieren`，`GET /api/v1/dashboard/ranking?bgm=5&mal=2&anilist=0`。

## 路由

| 路径 | 用途 |
| --- | --- |
| `GET /health/` | API、目录可用性和新鲜度；退化时仍返回 200，可读 `status` |
| `GET /health/ping` | 进程存活 |
| `GET /catalog/` | 来源、许可、条目总数、更新时间、过期状态、同步错误 |
| `GET /anime/` | 全目录筛选与分页 |
| `GET /anime/airing` | 当前在播 |
| `GET /anime/subscribed` | 兼容旧订阅文件 |
| `GET /anime/season/current` | 当前季度首播作品 |
| `GET /anime/season/{year}/{season}` | 历史季度首播作品 |
| `GET /anime/{bgm_id}` | 目录详情与评分 |
| `GET /search/`, `POST /search/` | 多语言检索 |
| `GET /export/json`, `GET /export/csv` | 当前目录和评分缓存视图 |
| `GET /stats/` | 完整目录总数、在播数量、订阅数量、目录年份分布 |
| `GET /stats/score-distribution` | 在播作品已有综合分的分布 |
| `GET /stats/studio-ranking` | 已知制作公司统计；目录本身无该字段，因此可能为空 |
| `GET /dashboard/ranking` | 个人权重榜单、搜索、过滤与汇总 |
| `GET /dashboard/status` | 采集进度、下次执行时间、目录状态 |
| `GET /dashboard/anime/{catalog_id}` | Web 详情、加入每小时跟踪 |
| `GET /dashboard/anime/{catalog_id}/history` | 分站评分、总分及人数历史 |
| `GET /dashboard/anime/{catalog_id}/history.csv` | UTF-8 BOM 历史 CSV |
| `GET /admin/status` | 后台认证模式和站点定义 |
| `GET /admin/mappings` | 搜索、缺失 ID 筛选、人工修改筛选 |
| `GET /admin/mappings/export` | 导出人工及自动映射备份 JSON |
| `GET /admin/mappings/{catalog_id}` | 上游值、有效映射、覆盖值、版本及修改记录 |
| `PUT /admin/mappings/{catalog_id}` | 原子更新一个作品的映射 |
| `POST /admin/validate` | 按站点 ID 校验作品名称、评分及人数 |
| `POST /admin/mappings/{catalog_id}/collect` | 按已保存映射采集单部作品 |
| `GET /admin/filmarks/job` | 自动映射任务进度、统计和最近结果 |
| `POST /admin/filmarks/job` | 启动 Filmarks 批量匹配任务 |
| `POST /admin/filmarks/job/cancel` | 当前条目处理后停止任务 |
| `POST /admin/filmarks/discover/{catalog_id}` | 检索单部作品候选，供人工确认，不自动保存映射 |

## Web 看板

`/dashboard/ranking` 默认为当季，支持 `year`、`season`、`anime_type`、`min_platforms`（0–5）、`min_votes`（各平台评分人次之和）、`limit`（1–100）、`offset`。非空 `q` 在整个目录搜索，忽略年份和季度。列表只读取缓存，不联网。

所有榜单、详情、历史与历史导出接口均接受 `bgm=5&mal=2&anilist=0&filmarks=0&anikore=0` 权重参数，范围 0–100，至少一项非零。0 表示关闭该站综合分权重，但仍显示和采集分站数据。综合分对有评分且权重为正的平台归一化，保留三位小数；排序同分并列，显示时可保留两位。个人权重不会写入共享数据。`summary` 包含收录量、有综合分的数量、平均分、分布、平台覆盖与评分人次。

Web 详情使用 `catalog_id`，即使作品没有 Bangumi ID 也可查询。`refresh=true` 为默认，按缓存有效期补分；`refresh=false` 只读缓存。访问详情会加入一年内的每小时跟踪范围。后台自动采集始终包含当季番剧。

历史参数 `period=7d|30d|90d|1y`，默认 `7d`（CSV 默认 `30d`）。返回 `points`（包含 `timestamp`、`scores`、`votes`）、`collected_since`、`resolution`、`from`、`to` 和当前 `weights`。7d/30d 为小时快照，90d/1y 为 UTC 每日末次快照；所有时间为 ISO 8601。缺失值为 `null`，没有采集记录时返回空数组，不回填和插值。平台失败后的旧缓存仅用于当前列表，不作为新历史分数或人数。

`/dashboard/status` 的 `collection` 包括 `running`、`completed`、`total`、`failures`、`last_started`、`last_finished`、`next_run`、`observations`、`collected_since`。`failures` 表示本轮异常的平台请求数；`enabled` 表示是否启用后台每小时采集。

## 映射管理

管理 API 支持 Bangumi 管理员会话或 `Authorization: Bearer <ANIMESCORE_ADMIN_TOKEN>`；OAuth 和令牌均未配置时才允许匿名本机回环访问，浏览器请求还需同源。Cookie 会话的写操作需要 `X-CSRF-Token`。管理列表接受 `q`（标题、译名或完整站点 ID）、`missing=filmarks` 等站点键、`edited=true`、`limit`、`offset`。

保存示例（PUT `/api/v1/admin/mappings/{catalog_id}`）：

```json
{
  "revision": 0,
  "changes": {
    "filmarks": {"mode": "manual", "id": "https://filmarks.com/animes/1431/6089", "note": "已核对季度"},
    "anikore": {"mode": "disabled", "note": "映射待确认"}
  }
}
```

`mode=catalog` 删除该站人工覆盖，`manual` 使用规范化 ID，`disabled` 停用该作品在此站的映射。只修改 `changes` 中的站点。`revision` 使用详情返回的版本；版本冲突或重复 ID 返回 409，非法站点、ID 或 URL 返回 422。验证接口请求体为 `{"provider":"filmarks","id":"1431/6089"}`，返回规范 ID、作品名称、十分制评分、人数及采集状态；请求失败不会自动保存映射。

历史快照保留源 ID，映射修正后不将旧条目记录当成新条目的数据。人工覆盖不修改原始 bangumi-data 文件。导出的人工映射 JSON 不包含管理员令牌。

Filmarks 匹配任务示例：

```json
{"scope":"season","year":2026,"season":"summer","limit":100,"apply":true,"force":false}
```

`scope=missing` 覆盖全目录缺失映射，优先处理未检查条目；`limit` 为 1–250。`apply=false` 只查候选，`force=true` 重新评估决策（仍复用有效页面缓存）。同一时间只接受一个批量任务，否则返回 409。任务状态为 `idle / queued / running / completed / cancelled / failed`，返回进度、结果计数和最近条目；关闭浏览器不会取消任务。

候选包含 `id`、作品名、作品链接、发布日期、检索方法、名称相似度、核对依据、`verified` 和 `eligible`。相似度是文本匹配指标，不是准确率概率。结果状态为 `unchecked / matched / applied / review / not_found / error / conflict / skipped`。管理列表可传入 `filmarks_status=review` 筛选待确认项，详情包含 `filmarks_match`。自动映射在 `mapping_sources` 和覆盖值 `source` 中标记 `auto`，人工保存为 `manual`；人工禁用仍为 `disabled`。自动流程只补缺失值，不覆盖现有值，导出包含两类来源。

## 搜索

默认 `source=bangumi-data`，匹配原名和所有译名。GET 查询参数与 POST 请求体使用相同字段：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `q` | 必填 | 非空关键词 |
| `source` | `bangumi-data` | 可选 `precise`、`bangumi` 兼容旧在线搜索 |
| `year` / `month` | 无 | 开播年/月；月份 1–12 |
| `anime_type` | 无 | `tv`、`web`、`movie`、`ova`，用于目录检索 |
| `match_mode` | `normal` | `normal` 包含匹配，`strict` 规范化后完整名称匹配，`recall` 增加相似度匹配 |
| `limit` / `offset` | `10` / `0` | 数量 1–50，偏移非负 |
| `include_scores` | `false` | 目录结果是否实时补充各平台评分；只抓取本页 |
| `studio` / `director` / `source_type` | 无 | 仅旧 `precise` 搜索支持；`source_type` 不再与 `source` 共用别名 |
| `extra_scores` / `debug_scores` | `false` | 旧 `precise` 搜索的站外评分及调试开关 |

对目录搜索传入其不支持的制作信息过滤或 `extra_scores=true` 会返回 400，不会静默忽略。

```json
{
  "q": "Frieren",
  "source": "bangumi-data",
  "include_scores": true,
  "limit": 5,
  "offset": 0
}
```

响应保留 `query`、`source`、`results`、`total`、`filters_applied`。目录搜索的 `total` 是分页前全部命中数；旧在线源的 `total` 是本次上游返回的候选数，不表示其完整数据库命中数。

## 番剧与季度

`/anime/` 支持 `year`、`month`、`anime_type`、`limit`（默认 50，最大 100）、`offset`、`sort_by`（默认 `time`）。

`/anime/airing` 和 `/anime/subscribed` 支持 `limit`（不传则返回全部）、`offset`、`sort_by`（默认 `score`）。排序可选 `score`、`name`、`time`；综合分、开播时间按降序，名称按升序。排序基于已有缓存，不自动刷新全目录评分。

季度可选 `winter`、`spring`、`summer`、`fall`，分别对应 UTC+8 下的 1–3、4–6、7–9、10–12 月。季度响应保留 `season`、`anime_list`、`total`、`updated_at`；最后更新时间为目录同步时间。

详情接口的 `include_scores` 默认 `true`，离线时显式设为 `false`。缺少 Bangumi ID 的作品仍出现在目录、季度和搜索结果中。

在播仅考虑 TV/web，有起止时间时判断时间区间。无完结时间时，只将当季已开播作品列入在播；早期未知完结时间的作品 `is_airing=null`，不会被误判为永久在播。周几以 `broadcast` 起始日期优先、`begin` 次之，1–7 表示周一至周日。

## 字段与评分

原有 `name`、`name_cn`、`name_en`、`ids`、`scores`、`time`、`poster` 等字段保留。目录扩展字段：

- `catalog_id`：由原名、开始时间、类型和语言派生的条目键；上游修改上述字段会改变该值。
- `data_source`：`bangumi-data`。
- `titles`：各语言完整译名数组。
- `type`、`language`、`official_site`、`begin`、`end`、`broadcast`、`comment`。
- `sites`：完整站点 ID、展开后的 URL、站点类型、地区限制和放送信息；条目显式 URL 和地区限制优先。
- `score_status`：每个平台的状态、更新时间、错误类别、可用的 `http_status`。MAL 另外包含 `source`（`myanimelist` 官方作品页或 `jikan`）、`source_url`，双方失败时提供 `source_errors`。
- `votes`、`platform_ranks`：每个平台的投票数、站内排名（未提供则为空）。
- `episodes`：评分平台补充的总集数。

`ids` 包含 `bgm_id`、`mal_id`、`anilist_id`、`anidb_id`、`tmdb_id`、`bili_id` 等可用映射。只有上游提供时才填充，不按相似标题补 ID。

`scores.bgm`、`scores.mal`、`scores.anilist` 均为十分制。AniList 同时有平均分和均分时，沿用原客户端的两者平均算法。综合分 `scores.total` 使用 `data/config.py` 现有权重，对有效平台权重归一化；有效值不足时为 `null`，不会写入 `"None"` 字符串。

| 状态 | 含义 |
| --- | --- |
| `unmapped` | 目录缺少该站 ID |
| `not_fetched` | 有映射，尚无评分缓存 |
| `ok` | 有有效评分 |
| `no_score` | 平台暂未提供评分 |
| `stale` | 返回过期评分，或更新失败后保留的旧评分 |
| `unavailable` | 请求失败且没有旧评分 |

列表和导出不会自动联网抓分。后台每小时刷新当季与已查看的作品，也可通过详情、`include_scores=true` 搜索或 `python -m scripts.sync_catalog --scores` 预热缓存。海报、简介、集数和制作公司在评分采集时从上游补充，缺少的字段保持为空。

## 导出与迁移

导出参数 `type=airing|subscribed|all`，默认 `airing`。JSON 返回 `{ "source": { ... }, "items": [ ... ], "total": ... }`；CSV 含 UTF-8 BOM 和数据源列，避免表格软件将以公式字符开头的标题作为公式执行。

此次迁移保留 API v1 路径与主要对象字段，但以下行为已改变：

- 默认搜索源由 `precise` 改为 `bangumi-data`，默认不联网补分。
- 列表和导出从当前目录与评分缓存生成，不再读取仓库附带的旧在播评分文件；JSON 导出由标题字典改为带署名的列表对象。
- `stats.total_anime` 改为完整目录条目数；目录年份分布也基于完整目录。
- 空列表返回 200 和空数组；数据源缺失返回 503，未知条目返回 404。
- 搜索参数与 `sort_by` 等枚举不合法时返回 422；目录不支持的过滤返回 400。
- `MAP_AUTO_UPDATE`、`ANIME_MAP_URL` 等旧映射下载配置不再使用，改用 README 中的 `BANGUMI_DATA_*` 配置。

错误响应示例：`{ "detail": "Anime with bgm_id 123 not found" }`。单个平台评分失败不使番剧详情返回 500，详情通过 `score_status` 表示局部失败。

## 登录、权限与用户投稿

| 路由 | 用途 |
| --- | --- |
| `GET /auth/me` | 当前用户、CSRF token、登录/审核是否已配置、今日错误额度；响应禁止缓存 |
| `GET /auth/bangumi/login?return_to=/` | 发起 OAuth；返回位置只接受 `/` 或 `/admin` |
| `GET /auth/bangumi/callback` | 核验 state、交换授权码并设置本站会话 Cookie |
| `POST /auth/logout` | 撤销当前会话 |
| `POST /contributions` | 提交缺失 ID，返回 202 和投稿记录 |
| `GET /contributions?catalog_id=...&offset=0` | 本人投稿，每页最多 50 条 |
| `GET /contributions/{id}` | 本人单条投稿与最新额度，可用于轮询 |
| `GET /admin/users?q=...&offset=0` | 搜索已登录用户，每页 50 条 |
| `PUT /admin/users/{uid}/role` | 管理员设置 `{"role":"user"}` 或 `{"role":"admin"}` |
| `GET /admin/contributions?offset=0` | 管理员查看全部投稿、理由及核对资料 |
| `POST /admin/contributions/{id}/approve` | 管理员采纳不确定、失败或误判投稿，保留署名，误判退回原日期额度 |

普通用户接口必须有 `animescore_session` Cookie；不能用后台管理令牌冒充投稿者。Cookie 会话的 POST/PUT 操作必须携带 `/auth/me` 返回的 `X-CSRF-Token`，并满足同源检查。后台支持具有 `admin` 角色的会话或既有 Bearer 管理令牌；OAuth 启用后匿名本机模式停用。

投稿请求为 `{"catalog_id":"目录返回的20位ID","provider":"filmarks","id":"1431/6089"}`，也可使用对应站点作品链接。只接受五个已接入站点；禁止自填用户名、角色、署名或模型结论。格式错误返回 422，未登录返回 401，CSRF/权限失败返回 403，映射已存在/被禁用/ID 重复/已有待审返回 409，五次错误耗尽或提交间隔不足返回 429，模型未配置返回 503。

投稿状态：`queued / reviewing / accepted / rejected / uncertain / error / conflict`。只有确定的 `rejected` 计入每日五次错误账本；按提交时的北京时间计算，同一用户同一天的同一候选只记一次。`quota` 包含 `limit / errors / remaining / day / resets_at / pending`。审核通过先返回 `accepted` 与 `score_status=pending`，随后变为 `collecting / ok / no_score / unavailable` 等采集状态。不得把 `uncertain` 当成映射已确认。

正式条目增加 `mapping_sources[provider]="community"` 和 `mapping_contributors[provider]={"bgm_id":123,"username":"name","profile_url":"https://bgm.tv/user/123"}`。署名来自通过 OAuth 核验的会话，并与正式 ID 同事务写入；修改为不同 ID 会清除旧署名。
