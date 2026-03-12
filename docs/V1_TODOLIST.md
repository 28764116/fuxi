# 伏羲（Fuxi）— v1.1 + v2.0 Todolist

> 前置：MVP 已完成（推演跑通 + 评分报告可查）  
> v1.1 目标：让推演结果更可信、更可控  
> v2.0 目标：让产品能给真实用户用

---

## v1.1 — 推演质量提升

### 1. WeightModifier（事实权重动态调整）

- [ ] 新建 `backend/simulation/weight_modifier.py`
  - 定义插件接口 `WeightModifierBase.update(event, graph_namespace) → List[WeightUpdate]`
  - 实现 `SceneRuleModifier`：读取 `scene_registry` 里的 `weight_modifier_rules`，按 predicate 分类（冲突型/和解型）触发权重升降
  - `engine.py` 推演步末调用 `weight_modifier.update_all()`
- [ ] `scene_registry.py` 补充每个场景的 `weight_modifier_rules`（predicate → 权重系数映射）

### 2. EventInjector 插件体系（手动 + 黑天鹅）

- [ ] 新建 `backend/simulation/event_injector.py`
  - 定义接口 `EventInjectorBase.inject(task_id, worldline_id, sim_time) → Optional[Event]`
  - 实现 `ManualEventInjector`：监听 Redis Pub/Sub channel `fuxi:inject:{task_id}`，实时消费注入事件
  - 实现 `BlackSwanInjector(EventInjectorBase)`：按 `blackswan_prob` 在每步随机触发，从 `scene_registry.blackswan_pool` 抽取事件类型，LLM 生成具体内容
- [ ] `worldline_worker` 在每步调用所有已注册的 injector
- [ ] `POST /simulation/worldlines/{id}/inject_event` API：向指定世界线注入事件（推入 Redis channel）
- [ ] `sim_tasks` 启用 `blackswan_enabled` 和 `blackswan_prob` 字段

### 3. 暂停 / 续跑

- [ ] `POST /simulation/tasks/{id}/pause`：设 `status=paused`，向 Celery 发 revoke（soft）
- [ ] `POST /simulation/tasks/{id}/resume`：从最新 `sim_checkpoints` 恢复，重新入队
- [ ] `worldline_worker` 每步开始前检查 `task.status`，若 `paused` 则 raise `PausedSignal` 退出循环
- [ ] `sim_checkpoints` 确保记录 `pending_reactions`（各 Agent 待响应队列），使续跑无状态丢失

### 4. Agent 手动编辑

- [ ] `PATCH /simulation/agents/{id}`：允许修改 `stance`、`influence_weight`、`information_access`、`scene_metadata` 任意字段
  - 限制：只能在 `task.status=pending` 或 `paused` 时编辑
- [ ] `GET /simulation/tasks/{id}/agents/{agent_id}` — 单 Agent 详情（含三层画像全字段）

### 5. 推演内部并发优化

- [ ] `engine.py` 同一步内、同一 `information_access` 级别且互不依赖的 Agent，改为 `asyncio.gather` 并发调用 LLM
- [ ] `agent_runtime.py` 的 LLM 调用加超时（默认 30s），超时则该 Agent 本步 `action_type=skip`

---

## v1.1 完成标志

- 推演过程中可暂停，重新 resume 后事件流连续，无重复/遗漏
- 手动注入一个突发事件，事件出现在后续事件流中，相关 Agent 有响应记录
- 黑天鹅触发后，世界线评分出现明显分歧（与未触发世界线对比）
- 同一步内多 Agent LLM 调用耗时 ≤ 单次串行耗时的 1.5 倍

---
---

## v2.0 — 商业化基础

### 1. 用户系统

- [ ] 新增 `users` 表：`id, email, password_hash, display_name, created_at, status(active/suspended)`
- [ ] 新增 `api_keys` 表：`id, user_id, key_hash, name, last_used_at, expires_at, is_active`
- [ ] `POST /auth/register` — 注册（邮箱 + 密码）
- [ ] `POST /auth/login` — 登录，返回 JWT（access_token + refresh_token）
- [ ] `POST /auth/refresh` — 刷新 token
- [ ] `POST /auth/logout`
- [ ] `POST /users/api-keys` — 创建 API Key
- [ ] `DELETE /users/api-keys/{id}` — 吊销 API Key
- [ ] `GET /users/me` — 当前用户信息 + 配额使用情况
- [ ] FastAPI 依赖注入：`get_current_user`，支持 JWT 和 API Key 两种认证方式

### 2. 多租户隔离

- [ ] 所有表（`sim_tasks`、`sim_agents`、`sim_worldlines`、`entity_edges` 等）加 `user_id` 字段
- [ ] 所有查询接口加 `user_id` 过滤，禁止跨用户访问数据
- [ ] `group_id` 改为由系统生成（`{user_id}:{task_id}`），不再由前端传入
- [ ] Celery Worker 任务签名加 `user_id`，日志和监控按 `user_id` 维度聚合

### 3. 配额与计费

- [ ] 新增 `user_quotas` 表：`user_id, plan(free/pro/enterprise), monthly_tasks, monthly_agents, monthly_steps, reset_at`
- [ ] 新增 `usage_records` 表：`user_id, task_id, task_count, agent_count, step_count, llm_tokens, created_at`
- [ ] 任务提交前校验配额：超出则返回 `402 Payment Required`
- [ ] 推演结束后写 `usage_records`，更新 `user_quotas.used_*` 计数
- [ ] `GET /users/me/usage` — 当月用量 + 配额详情
- [ ] Free 套餐默认限制：每月 5 次任务 / 每次最多 10 Agent / 最多 20 时间步

### 4. 管理员后台 API

- [ ] `GET /admin/users` — 用户列表（含用量，分页）
- [ ] `PATCH /admin/users/{id}/quota` — 手动调整用户配额（发 Pro 兑换码用）
- [ ] `PATCH /admin/users/{id}/status` — 封号/解封
- [ ] `GET /admin/tasks` — 全量任务列表（运维监控用）
- [ ] `GET /admin/usage/stats` — 系统级用量统计（每日/每月）
- [ ] 所有 `/admin/*` 接口需要 `role=admin` 的 JWT

### 5. 安全加固

- [ ] 所有 API 接口加 Rate Limit（`slowapi` 中间件）：默认 60 req/min/IP
- [ ] `seed_content` 最大长度限制（10,000 字），超出拒绝
- [ ] `num_timelines` 最大值校验（Free ≤ 3，Pro ≤ 10）
- [ ] LLM 输出加 JSON Schema 校验，非法输出触发 retry（最多3次），3次失败则任务 `failed`
- [ ] API Key 存储只保存 hash（`bcrypt`），创建时明文只返回一次

---

## v2.0 完成标志

- 用户可注册登录，使用 API Key 调用推演接口
- Free 用户超配额时收到明确错误，不会继续消耗资源
- 两个不同用户的数据完全隔离，任意接口均无法跨用户读写
- 管理员可查看全量用户和用量，可手动调整配额
- 所有接口通过 Rate Limit 防止滥用
