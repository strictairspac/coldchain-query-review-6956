# 冷链结算 SQL 复核台

为澄港冷链结算组保存 SQL 基准样本、独立候选改写和实库执行证据。原生 HTML/CSS/JS 前端，Python 后端执行解析、只读查询和多重集合比对。

## 真实工作场景

澄港冷链结算组共 18 人，每天从运费账单中按客户、路线、温控合格条件汇总结算。目前通过邮件传递 `coldchain-settlement.sql` 和表格复核，三个痛点是版本难定位、口径变动容易漏查、单次查询截图无法还原执行计划。上游是冷链计费账单，本站替代 SQL 改写复核和证据归档，下游是结算复核人。演示数据固定 600 条账单、3 客户、2 路线，字段与页面说明一致。

## 业务模块

1. 样本库：登记名称、口径说明与原始 SELECT，防止重名；提供温控合格、路线费用、异常温控三个起始样本。
2. SQL 复核：选择基准，编辑候选，校验后创建独立批次并入 Redis 队列。
3. 运行历史：跟踪 queued/running/passed/different/failed，失败也保留证据；显示受理与执行原因。
4. 证据详情：真实 EXPLAIN ANALYZE、两侧结果行、SHA-256 摘要、遗漏/新增行和 JSON 下载；显示证据实际使用的客户范围。
5. 客户授权：管理员为各专员逐客户授权，未授权默认无数据；授权变更对排队批次即时生效。
6. 管理员操作审计：记录写请求、执行账号和 HTTP 结果，包括拒绝请求。

| 角色 | 主要页面 | 权限与典型动作 |
|---|---|---|
| admin 管理员 | 全部页面、客户授权、审计 | 配置专员可查客户、创建样本/批次、查看/导出全部结果、查看写操作审计 |
| operator 操作员 | 四个业务页面 | 在获授权客户内登记 SQL、提交后台复核、查看/导出自己的结果；不可配置授权或查看审计 |
| viewer 观察员 | 四个业务页面 | 在获授权客户内只读与导出；API 层拒绝所有业务写请求 |

管理员默认覆盖全部客户；其他账号只有管理员显式勾选的客户。未配置授权的账号查询一律返回空数据而不是全量数据。批次状态与原因对管理员、创建者本人以及客户范围仍在当前授权内的同组专员可见（仅元数据，不含账单）。证据与下载遵循同一客户范围：证据记录的客户范围必须非空且完全落在访问者当前授权内，否则返回 403；授权收窄后旧证据归管理员。

## 快速启动

```bash
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
# 启动自动 seed；手动重跑不新增且不覆盖用户修改
docker compose exec -T backend python -m scripts.seed_demo
```

访问 [前端](http://localhost:18240)、[后端 OpenAPI](http://localhost:19240/docs)。数据库映射端口 17740。项目的日志、截图、测试脚本在批次根目录 `test-artifacts/gb-4101/`，不放入源码。

演示账号邮箱为 `admin@chenggang.test`、`operator@chenggang.test`、`viewer@chenggang.test`，统一密码 `ColdChain!17`。这些是本地固定演示凭据，上线前应修改 `.env` 和账号密码。演示授权为 operator 可查两个客户、viewer 可查一个客户；未列出的账号默认无数据，管理员可在“客户授权”页调整。

```bash
# 仅清理本项目及其演示数据
docker compose down -v --remove-orphans
```

## 一天工作剧本

1. 09:00 operator 登录，打开“低温结算汇总”样本。
2. 09:05 查看原始 SQL：按客户执行两处相关 SUM 子查询，过滤温度不高于 8 度的运费。
3. 09:10 创建 `shift-20261117` 批次，候选改写为下面的单次分组查询。
4. 09:15 提交到 worker，在运行历史刷新查看状态。
5. 09:20 打开证据，确认两侧的行数与摘要相同、结果一致（operator 获授权两个客户，故为 2 行）；展开真实计划比较循环次数与代价。
6. 09:25 把候选条件改为 `temperature > 8`，用新批次执行并查看新增/遗漏行。
7. 09:30 下载 `review-<批次号>.json` 给结算复核人；证据记录实际客户范围。
8. 09:40 viewer 登录复核，API 创建样本返回 403，读取 operator 证据返回 403；10:00 admin 查看审计与客户授权。

```sql
SELECT customer, SUM(amount) AS total
FROM invoices
WHERE temperature <= 8
GROUP BY customer
HAVING SUM(amount) > 100
ORDER BY customer
```

## 算法、输入与口径

输入是原始/候选单条 SELECT。sqlglot 解析 AST，仅准许 invoices 表、指定业务字段和 SUM/COUNT/AVG/MIN/MAX/ROUND/COALESCE/CAST。禁止多语句、INTO、锁、CTE、跨表、schema 和任意函数。解析后重新生成 PostgreSQL SQL，执行在 READ ONLY 事务中，切换 NOLOGIN `query_reader` 角色；该角色仅有 invoices 的 SELECT 权限。每条 statement 超时 2500ms，最多返回 1000 行，AST 最多 250 节点，候选 SQL 最多 6000 字符，最多 20 个排队/运行任务。

客户范围在两处同时强制：其一，重写每个 invoices 表引用为 `customer IN (授权客户)` 的子查询，相关子查询、自连接和改写条件都只能看到授权行；其二，`query_reader` 受行级安全策略约束，事务内以 `set_config('app.allowed_customers', …, true)` 设置范围，未设置或范围为空时默认无数据，事务结束即失效，连接池复用不会串用上一客户范围。原始与候选 SQL 使用同一范围，证据的 `scope` 记录实际使用的客户；若排队期间授权被撤，worker 执行时按最新授权复核，剔除已撤权客户，全部撤销则拒绝执行并留下仅管理员可读的拒绝证据。

两侧均实际执行 `EXPLAIN (ANALYZE, FORMAT JSON, BUFFERS)` 与 SELECT。结果每行按列位置规范为数据库文本值，`Counter` 统计行的重复次数；列数相同且计数集合相同即 equivalent。忽略行顺序及列别名、保留重复行，NULL 保留为空值。按有序的“规范行/计数”生成 SHA-256。数值不同文本表示（如 1 与 1.0）会判不同；这是明确的保守口径。不能据固定数据集通过证明所有可能输入上的 SQL 语义等价；一次耗时不能证明优化收益。

失败态包括语法/白名单失败（提交前 422）、缺少样本（404）、重名（409）、任务配额（429）、无客户授权（403）、数据库超时/运行错误（批次 failed，保存 error）、执行时撤权（批次 failed，原因记录为拒绝并留管理员证据）。正常差异是 different，不当成异常。

## 技术栈、结构与本地开发

| 部分 | 实现 |
|---|---|
| frontend | 原生 ES modules、CSS、Nginx 1.27，olive paper 风格 |
| backend | Python 3.11、FastAPI、SQLAlchemy、sqlglot、PyJWT |
| worker | 独立 Python 进程，Redis BLPOP + DB 状态恢复队列，心跳文件 |
| db / cache | PostgreSQL 16、Redis 7 |
| auth | JWT 8 小时有效，PBKDF2 SHA-256 加盐密码 |

`backend/src/` 按 config/models/schemas/services/controllers/routes/middlewares/utils/constants 分工；`backend/scripts/seed_demo.py` 管理幂等初始化；`backend/migrations/README.md` 说明 schema v2。`frontend/src/` 按 api/stores/types/components/common/hooks/pages/router/utils/constants 分工。实体链分别为 sample、batch、evidence，各自有模型、schema、服务、路由、API、store 和页面；客户授权是独立实体，挂在 users 上。

后端本地：创建虚拟环境并安装 `backend/requirements.txt`，先用 Compose 启动 db/redis，设置本地可达的 DATABASE_URL/REDIS_URL/JWT_SECRET，进入 backend 执行 `uvicorn src.main:app --reload`；worker 需 `/artifacts` 可写目录并执行 `python -m src.worker`。最省事的开发方式是修改源码后 `docker compose up -d --build`。前端通过 Nginx 的 `/api/` 去前缀代理访问后端，禁止双重 `/api/api`。

环境变量：COMPOSE_PROJECT_NAME（容器命名）、FRONTEND_PORT/BACKEND_PORT/DB_PORT（宿主端口）、POSTGRES_PASSWORD（演示库密码）、JWT_SECRET（签名密钥）、SEED_DEMO（默认 true）。后端容器另接收 DATABASE_URL 和 REDIS_URL。5 个服务均有 healthcheck；数据库、Redis、共享证据各自使用命名卷。

共享枚举位置：角色与任务状态在 `backend/src/constants/enums.py` 和 `frontend/src/constants/enums.js`；模型/鉴权服务/worker 消费后端值，状态标签与前端权限消费前端值。源数据 invoice status 为账单业务值 settled/pending，与任务状态独立。

## 已知边界

- 小型工作流没有样本删除和版本编辑；新口径新建样本/批次，旧记录保持独立。
- 使用固定业务数据和单实例 worker；不对接生产数据库，不部署生产高可用。
- 只允许受限 SQL 子集；不支持 CTE、窗口、跨表联接和用户自定义函数。
- 查询会执行两次（一次 EXPLAIN ANALYZE，一次取结果）；数据源固定只读，避免两次间口径变化。
- 后端迁移/seed 角色为本地数据库管理员；执行用户 SQL 时强制切换受限只读角色。生产应拆分独立迁移凭据。
- 客户授权来自 `customer_access` 表；SPA 载入时刷新 `/auth/me` 的客户范围。授权变更无需重启，但已签发的 JWT 不会主动失效，权限判断每次请求都查库。
- `seed_demo` 为 invoices 建立行级安全策略并将 `query_reader` 纳入；若手工改库，需保留该策略与 `GRANT SELECT`，否则第二层防护会失效（AST 层仍生效，但缺少纵深防御）。
- Web 字体来自 Google Fonts，离线会使用 serif/monospace 回退；不影响功能。

License: MIT，见 LICENSE。
