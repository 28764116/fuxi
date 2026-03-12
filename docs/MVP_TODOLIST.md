# 伏羲（Fuxi）— MVP Todolist

> 目标：跑通一次完整推演（种子输入 → 图谱 → 多世界线推演 → 评分报告）  
> 原则：P1 功能一律推后，能 hardcode 的先 hardcode，能跑通比能配置更重要

---

## 阶段一：基础设施打通（2-3天）

### 数据库
- [ ] 新增 `sim_agents` 表（三层画像，含 `entity_id` 外键、`scene_metadata` JSONB）
- [ ] 新增 `sim_worldlines` 表（`graph_namespace`、`initial_assumption`、`status`、`score`）
- [ ] 新增 `sim_worldline_events` 表（事件流，用于前端时间轴）
- [ ] 新增 `sim_checkpoints` 表（Agent 动态状态快照 + 待响应队列）
- [ ] `sim_tasks` 扩展字段：`goal`、`scene_type`、`scene_config`、`sim_start_time`、`sim_end_time`、`time_step_unit`、`num_timelines`、`blackswan_enabled/prob`
- [ ] 更新 `sim_tasks.status` 状态机，加入 `paused`、`scoring`（任何阶段均可 → `failed`）
- [ ] `entity_edges` 新增字段：`generated_by`（VARCHAR）、`confidence`（FLOAT）
- [ ] `entities` 新增字段：`display_name`（VARCHAR）、`metadata`（JSONB）

### 场景注册表
- [ ] 新建 `backend/simulation/scene_registry.py`，写入5个场景配置（action_types、prompt_prefix、scoring_metrics、weight_modifier_rules）

---

## 阶段二：种子拆分重构（3-4天）

### Phase 1：要素提取（改造现有）
- [ ] `memory/extractor.py` 扩展：接受 `goal` 参数，做目标导向定向提取（在 prompt 中注入推演目标）
- [ ] `tasks._run_extraction`：写 `episodes`/`entities`/`entity_edges` 时，`group_id` 字段填入基础图谱的 `graph_namespace`（如 `task_{id}_base`），而非用户级 `group_id`，以便后续世界线克隆时按 namespace 隔离

### Phase 2：Agent 画像生成（新建）
- [ ] 新建 `backend/simulation/profile_generator.py`
  - 从 `entities` 表读取已提取的节点
  - LLM 推断三层画像（静态 + 动态参数 + `scene_metadata` 含 `information_access`）
  - 写入 `sim_agents`，`entity_id` 绑定到对应图谱节点

### Phase 3：世界线初始化（新建）
- [ ] 新建 `backend/simulation/worldline_bootstrap.py`
  - LLM 根据 `task.goal` 生成 N 条差异化初始假设（乐观/中性/悲观）
  - 为每条创建 `sim_worldlines` 记录，分配独立 `graph_namespace`
  - `clone_graph(base_namespace, wl_namespace)`：深拷贝 `entity_edges`
  - 将各自初始假设通过 `temporal_upsert` 写入对应 namespace（`generated_by='bootstrap'`）

---

## 阶段三：推演引擎重构（4-5天）

### Agent 单步执行（新建）
- [ ] 新建 `backend/simulation/agent_runtime.py`
  - `run_agent_step(agent, facts, pending_reactions, scene_config, sim_time) → AgentAction`
  - 构建 prompt（场景前缀 + 三层画像 + 事实列表 + 待响应事件 + action_types）
  - 调用 LLM，返回结构化 `{ action_type, description, new_facts[], confidence }`

### 推演主循环（重写 engine.py）
- [ ] `engine.py` 改写为编排层
  - 按 `influence_weight` 排序 Agent
  - 按 `information_access` 过滤图谱事实调用 `search_edges`
  - 调用 `agent_runtime.run_agent_step`
  - `new_facts` 通过 `temporal_upsert` 写回图谱（`generated_by='agent_action'`）
  - 写 `sim_worldline_events` 记录事件流
  - 高影响力事件（`impact_score >= 0.7`）：推入相关 Agent 的待响应队列
  - 步末保存 `sim_checkpoints`

### Celery 任务编排（改造 tasks.py）
- [ ] `tasks.py` 改为5阶段 pipeline
  - Phase 1（0%-20%）：要素提取 → 基础 `graph_namespace`
  - Phase 2（20%-30%）：`profile_generator` 生成 Agent
  - Phase 3（30%-35%）：`worldline_bootstrap` 初始化世界线
  - Phase 4（35%-85%）：`chord` 并行启动每条世界线的推演子任务，全部完成后进 Phase 5
  - Phase 5（85%-100%）：`scorer` 评分 → `sim_reports`
- [ ] 新增 `worldline_worker` Celery 任务：单条世界线完整推演循环

---

## 阶段四：评分 + 报告（2天）

- [ ] 新建 `backend/simulation/scorer.py`
  - 按 `scene_type` 加载 `scoring_metrics`
  - LLM 对每条世界线评分（0-100），输出各维度明细
  - 写回 `sim_worldlines.score`、`score_detail`、`verdict`（above_water / below_water）
- [ ] `reporter.py` 升级：按世界线生成详情报告 + 任务总报告（横向对比）
  - 报告含：事件流摘要、关键转折点、各 Agent 走向、评分依据

---

## 阶段五：API 扩展（2天）

- [ ] `POST /simulation/tasks` 接受扩展字段（`goal`、`scene_type`、`sim_start_time` 等）
- [ ] `GET /simulation/tasks/{id}/worldlines` — 返回任务下所有世界线列表（含评分）
- [ ] `GET /simulation/worldlines/{id}/events` — 世界线事件流（时间轴数据）
- [ ] `GET /simulation/worldlines/{id}/snapshot?t=` — 时间快照（图谱快照）
- [ ] `GET /simulation/tasks/{id}/agents` — Agent 列表
- [ ] `GET /memory/graph?group_id=` — 图谱全量节点/边（前端渲染用）
- [ ] WebSocket 消息格式补全 `worldline_id`、`latest_event` 字段

---

## 非阶段：贯穿全程

- [ ] `sim_tasks.status` 的 `scoring` 阶段接入进度推送（WebSocket）
- [ ] 所有 `temporal_upsert` 调用中 `group_id` 参数传入世界线的 `graph_namespace`（非用户级 `group_id`），确保世界线隔离（参见 DATA_MODEL.md 第五章命名规范）
- [ ] `entity_edges.generated_by` 正确标记来源（extraction / agent_action / bootstrap）

---

## MVP 范围内不做（推后）

> 以下功能即使文档已设计，MVP 阶段跳过，不要在 MVP 代码中预埋骨架

- WeightModifier（`weight_modifier.py`）
- EventInjector 插件体系（`event_injector.py`）
- 暂停/续跑（pause/resume API + checkpoint 恢复逻辑）
- 黑天鹅事件（`blackswan.py` / `BlackSwanInjector`）
- Agent 手动编辑接口（`PATCH /simulation/agents/{id}`）
- 联网/历史事件注入（P2）
- 前端（单独阶段）

---

## 完成标志

跑通以下场景视为 MVP 完成：

1. 上传一段中美贸易战背景资料 + 目标 + `scene_type=geopolitics`
2. 自动提取图谱（节点 + 边可通过 `/memory/graph` 查到）
3. 自动生成 10 个 Agent（`/simulation/tasks/{id}/agents` 可查）
4. 自动初始化 N 条世界线（由 `num_timelines` 参数决定，默认3条，乐观/中性/悲观）
5. 推演完成，每条世界线有事件流（`/worldlines/{id}/events`）
6. 评分完成，可区分水上/水下
7. 生成3份世界线报告 + 1份总报告
