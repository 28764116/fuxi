# 伏羲（Fuxi）— API 接口设计文档

> 版本：v0.4
> 最后更新：2026-03-12
> Base URL：`http://localhost:8000`  
> 鉴权：`X-API-Key: <your_key>`（dev 模式可留空）

---

## 一、接口总览

### Memory 模块 `/memory/*`

| 方法 | 路径 | 描述 | 状态 |
|------|------|------|------|
| `POST` | `/memory/episodes` | 写入新 Episode，异步触发三元组抽取 | ✅ 已有 |
| `POST` | `/memory/upload` | 上传文档，自动分块 ingest | ✅ 已有 |
| `GET` | `/memory/context/{thread_id}` | 获取组装好的 LLM 上下文 | ✅ 已有 |
| `GET` | `/memory/search` | 语义检索事实边 | ✅ 已有 |
| `GET` | `/memory/search/entities` | 语义检索实体 | ✅ 已有 |
| `GET` | `/memory/entities` | 列出实体（分页） | ✅ 已有 |
| `GET` | `/memory/entities/{id}` | 获取单个实体 | ✅ 已有 |
| `GET` | `/memory/entities/{id}/edges` | 获取实体所有关系边 | ✅ 已有 |
| `GET` | `/memory/facts/{id}` | 获取实体当前有效事实 | ✅ 已有 |
| `GET` | `/memory/facts/{id}/at` | 时光机：查询某时间点的事实 | ✅ 已有 |
| `GET` | `/memory/graph` | **获取图谱全量节点/边（前端渲染用）** | ❌ 待新增 |

### Simulation 模块 `/simulation/*`

| 方法 | 路径 | 描述 | 状态 |
|------|------|------|------|
| `POST` | `/simulation/tasks` | 创建推演任务（含 scene_type/scene_config） | ⚠️ 需扩展字段 |
| `GET` | `/simulation/tasks` | 列出任务 | ✅ 已有 |
| `GET` | `/simulation/tasks/{id}` | 获取任务详情 | ✅ 已有 |
| `GET` | `/simulation/tasks/{id}/status` | 获取任务进度 | ✅ 已有 |
| `POST` | `/simulation/tasks/{id}/pause` | **暂停推演** | ❌ 待新增 |
| `POST` | `/simulation/tasks/{id}/resume` | **恢复推演（从断点）** | ❌ 待新增 |
| `GET` | `/simulation/tasks/{id}/worldlines` | **获取任务的所有世界线** | ❌ 待新增 |
| `GET` | `/simulation/worldlines/{id}` | **获取单条世界线详情** | ❌ 待新增 |
| `GET` | `/simulation/worldlines/{id}/snapshot` | **时间快照：某时刻的图谱状态** | ❌ 待新增 |
| `GET` | `/simulation/worldlines/{id}/events` | **世界线事件流（时间轴）** | ❌ 待新增 |
| `POST` | `/simulation/worldlines/{id}/inject_event` | **外部事件注入** | ❌ 待新增 |
| `GET` | `/simulation/tasks/{id}/agents` | **获取 Agent 列表** | ❌ 待新增 |
| `PATCH` | `/simulation/agents/{id}` | **更新 Agent 画像 / 权重** | ❌ 待新增 |
| `GET` | `/simulation/tasks/{id}/reports` | 获取报告列表 | ✅ 已有 |
| `GET` | `/simulation/reports/{id}` | 获取单份报告 | ✅ 已有 |
| `WS` | `/simulation/ws/{task_id}` | WebSocket 实时进度 | ✅ 已有 |

---

## 二、关键接口详细设计

### 2.1 创建推演任务（扩展版）

**`POST /simulation/tasks`**

**Request Body：**
```json
{
  "group_id": "user_123",
  "title": "中美科技脱钩对半导体产业的影响推演",
  "seed_content": "...",
  "seed_type": "text",
  "goal": "分析未来5年中美科技脱钩背景下，中国半导体产业的发展走向",

  "scene_type": "geopolitics",
  "scene_config": {
    "extra_action_types": ["embargo", "covert_ops"],
    "custom_prompt_suffix": "本次推演重点关注能源领域的博弈。",
    "scoring_weights": {
      "goal_achievement": 0.4,
      "power_stability": 0.3,
      "blackswan_exposure": 0.3
    }
  },

  "sim_start_time": "2025-01-01T00:00:00Z",
  "sim_end_time": "2030-01-01T00:00:00Z",
  "time_step_unit": "month",

  "num_agents": 10,
  "num_timelines": 3,

  "blackswan_enabled": true,
  "blackswan_prob": 0.05
}
```

**Response（201）：**
```json
{
  "id": "uuid",
  "group_id": "user_123",
  "title": "...",
  "goal": "...",
  "scene_type": "geopolitics",
  "sim_start_time": "2025-01-01T00:00:00Z",
  "sim_end_time": "2030-01-01T00:00:00Z",
  "num_timelines": 3,
  "status": "pending",
  "progress": 0,
  "created_at": "..."
}
```

---

### 2.2 获取所有世界线

**`GET /simulation/tasks/{task_id}/worldlines`**

**Response（200）：**
```json
[
  {
    "id": "uuid-a",
    "task_id": "uuid",
    "name": "乐观演化",
    "timeline_type": "normal",
    "initial_assumption": "中美达成部分协议，技术管制范围有限",
    "graph_namespace": "task_xxx_tl_optimistic",
    "status": "completed",
    "score": 87.5,
    "score_detail": {
      "goal_achievement": 90,
      "power_stability": 85,
      "alliance_health": 88,
      "blackswan_exposure": 10,
      "overall": 87,
      "summary": "目标高度达成，产业结构基本稳定，关键企业完成自主化转型。"
    },
    "verdict": "above_water",
    "current_sim_time": "2030-01-01T00:00:00Z"
  },
  {
    "id": "uuid-b",
    "name": "悲观演化",
    "score": 32.0,
    "verdict": "below_water"
  }
]
```

---

### 2.3 时间快照（时间滑块核心接口）

**`GET /simulation/worldlines/{worldline_id}/snapshot?t=2027-06-01T00:00:00Z`**

返回该时间点下的图谱状态（节点 + 边），前端直接渲染关系图。

**Request Params：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `t` | ISO8601 datetime | 是 | 查询的时间点 |
| `entity_types` | string (comma-sep) | 否 | 过滤实体类型，如 `person,organization` |
| `limit` | int | 否 | 最多返回多少个节点，默认 50 |

**Response（200）：**
```json
{
  "snapshot_time": "2027-06-01T00:00:00Z",
  "worldline_id": "uuid",
  "nodes": [
    {
      "id": "entity-uuid",
      "name": "华为",
      "display_name": "华为技术有限公司",
      "entity_type": "organization",
      "summary": "中国领先的电信设备制造商...",
      "metadata": {
        "stance": "自主创新",
        "influence_score": 0.92
      }
    }
  ],
  "edges": [
    {
      "id": "edge-uuid",
      "source": "entity-uuid-1",
      "target": "entity-uuid-2",
      "predicate": "competes_with",
      "fact": "华为与高通在5G芯片市场存在直接竞争",
      "valid_at": "2026-03-01T00:00:00Z",
      "expired_at": null,
      "confidence": 0.95,
      "generated_by": "agent_action"
    }
  ]
}
```

---

### 2.4 世界线事件流

**`GET /simulation/worldlines/{worldline_id}/events`**

返回该世界线的关键事件时间轴，用于前端事件流展示。

**Request Params：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `from_time` | ISO8601 | 否 | 开始时间 |
| `to_time` | ISO8601 | 否 | 结束时间 |
| `event_type` | string | 否 | `agent_action` \| `blackswan` \| `injection` \| `state_change` |

**Response（200）：**
```json
[
  {
    "id": "uuid",
    "event_time": "2026-03-15T00:00:00Z",
    "event_type": "agent_action",
    "action_type": "impose_sanctions",
    "title": "美国商务部扩大芯片出口管制范围",
    "description": "美国商务部宣布新一轮出口管制，将更多中国半导体企业列入实体清单...",
    "entity_ids": ["entity-uuid-1"],
    "impact_score": 0.88
  },
  {
    "id": "uuid",
    "event_time": "2027-01-10T00:00:00Z",
    "event_type": "injection",
    "title": "【注入事件】美国大选结果改变对华政策方向",
    "description": "用户注入：2027年1月新政府上台，对华政策明显转向...",
    "impact_score": 0.90
  },
  {
    "id": "uuid",
    "event_time": "2027-08-01T00:00:00Z",
    "event_type": "blackswan",
    "title": "【黑天鹅】台积电宣布暂停向中国大陆供货",
    "description": "受地缘政治压力影响，台积电宣布暂停向中国大陆晶圆代工订单...",
    "impact_score": 0.95
  }
]
```

---

### 2.5 外部事件注入

**`POST /simulation/worldlines/{worldline_id}/inject_event`**

向指定世界线（或所有世界线）注入一个外部事件，作为新事实写入图谱。

**Request Body：**
```json
{
  "title": "美国大选结果改变对华政策方向",
  "description": "2027年1月新政府上台，对华政策明显转向，暂停部分出口管制。",
  "inject_time": "2027-01-20T00:00:00Z",
  "source_type": "manual",
  "entity_names": ["美国政府", "中国商务部"],
  "inject_to_all": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `inject_time` | ISO8601 | 事件注入到推演时间轴的哪个时间点 |
| `source_type` | string | `manual` \| `news_search` \| `historical` |
| `inject_to_all` | bool | `true` = 注入所有世界线，`false` = 仅当前世界线 |

**Response（200）：**
```json
{
  "injection_id": "uuid",
  "status": "applied",
  "generated_edge_ids": ["edge-uuid-1", "edge-uuid-2"],
  "message": "事件已成功注入，相关 Agent 将在下一时间步优先响应。"
}
```

---

### 2.6 Agent 列表与权重调整

**`GET /simulation/tasks/{task_id}/agents`**

返回任务的所有 Agent 画像列表。

**Response（200）：**
```json
[
  {
    "id": "agent-uuid",
    "display_name": "美国商务部",
    "role": "政策制定机构",
    "organization": "美国政府",
    "activity_level": 0.85,
    "influence_weight": 3.2,
    "stance": "opposing",
    "scene_metadata": {
      "information_access": "global",
      "authority_level": 9
    },
    "is_active": true
  }
]
```

**`PATCH /simulation/agents/{agent_id}`**

更新 Agent 的动态参数或场景扩展字段。支持在推演暂停期间调整。

**Request Body（部分更新）：**
```json
{
  "influence_weight": 2.0,
  "stance": "neutral",
  "scene_metadata": {
    "authority_level": 6
  }
}
```

**Response（200）：** 返回更新后的完整 Agent 对象。

---

### 2.7 推演暂停/恢复

**`POST /simulation/tasks/{task_id}/pause`**

暂停正在运行的推演任务。Celery Worker 完成当前时间步后停止，保存检查点。

**Response（200）：**
```json
{
  "task_id": "uuid",
  "status": "paused",
  "paused_at_time": "2027-06-01T00:00:00Z",
  "checkpoint_id": "uuid",
  "message": "推演已暂停，可修改 Agent 参数或注入外部事件后恢复。"
}
```

**`POST /simulation/tasks/{task_id}/resume`**

从最近检查点恢复推演。

**Response（200）：**
```json
{
  "task_id": "uuid",
  "status": "simulating",
  "resume_from_time": "2027-06-01T00:00:00Z",
  "message": "推演已从检查点恢复。"
}
```

---

### 2.8 图谱全量查询（关系图渲染用）

**`GET /memory/graph?group_id=xxx&entity_type=person,organization&limit=100`**

**Request Params：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `group_id` | string | 是 | 图谱命名空间 |
| `entity_type` | string | 否 | 过滤类型 |
| `include_expired` | bool | 否 | 是否包含已过期的边，默认 false |
| `limit` | int | 否 | 节点数量上限，默认 100 |

**Response（200）：** 同 `/snapshot` 的 nodes + edges 结构。

---

### 2.9 WebSocket 进度（多世界线扩展）

**`WS /simulation/ws/{task_id}`**

消息格式（扩展后）：
```json
{
  "task_status": "simulating",
  "task_progress": 45,
  "worldlines": [
    {
      "id": "uuid-a",
      "name": "乐观演化",
      "status": "running",
      "current_sim_time": "2027-03-01T00:00:00Z",
      "progress_pct": 40
    },
    {
      "id": "uuid-b",
      "name": "悲观演化",
      "status": "running",
      "current_sim_time": "2026-09-01T00:00:00Z",
      "progress_pct": 32
    }
  ],
  "latest_event": {
    "worldline_id": "uuid-a",
    "event_type": "agent_action",
    "title": "中国商务部宣布反制裁措施",
    "impact_score": 0.82
  },
  "message": "正在推演第 2/3 条世界线，时间步 2027-03..."
}
```

---

## 三、错误码规范

| HTTP 状态码 | 含义 |
|------------|------|
| `400` | 请求参数错误（字段缺失、格式错误） |
| `401` | API Key 无效 |
| `404` | 资源不存在 |
| `409` | 状态冲突（如对非运行中任务执行 pause） |
| `422` | Pydantic 数据验证失败 |
| `500` | 服务内部错误（含错误详情） |

**统一错误响应格式：**
```json
{
  "detail": "Task not found",
  "error_code": "TASK_NOT_FOUND"
}
```

---

## 四、接口实现优先级

| 优先级 | 接口 | 说明 |
|--------|------|------|
| P0 | `POST /simulation/tasks`（扩展） | 增加 scene_type/scene_config、goal、时间范围、世界线配置 |
| P0 | `GET /simulation/tasks/{id}/worldlines` | 世界线列表 + 评分 |
| P0 | `GET /simulation/worldlines/{id}/snapshot` | 时间滑块核心接口 |
| P0 | `WS /simulation/ws/{task_id}`（扩展） | 多世界线进度推送 + 最新事件 |
| P1 | `GET /simulation/worldlines/{id}/events` | 时间轴事件流（含 injection 类型） |
| P1 | `POST /simulation/worldlines/{id}/inject_event` | 外部事件手动注入 |
| P1 | `GET /simulation/tasks/{id}/agents` | Agent 列表 |
| P1 | `PATCH /simulation/agents/{id}` | Agent 权重/画像调整 |
| P1 | `POST /simulation/tasks/{id}/pause` | 推演暂停 |
| P1 | `POST /simulation/tasks/{id}/resume` | 推演恢复 |
| P1 | `GET /memory/graph` | 图谱全量查询 |
| P2 | `GET /simulation/worldlines/{id}` | 单条世界线详情 |
