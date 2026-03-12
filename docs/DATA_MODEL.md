# 伏羲（Fuxi）— 数据模型设计文档

> 版本：v0.4
> 最后更新：2026-03-12

---

## 一、整体 ER 关系

```
sim_tasks ──< sim_worldlines ──< sim_worldline_events
    │               │
    │         (graph_namespace)
    │               │
    ├──< sim_agents  │
    │               │
    ├──< sim_checkpoints
    │               │
    ├──< sim_event_injections
    │               │
episodes ──< entities ──< entity_edges
                            (temporal: valid_at / expired_at)

sim_tasks ──< sim_reports
sim_worldlines ──< sim_reports
```

---

## 二、Memory 模块表结构

### 2.1 `episodes` — 原始输入记录

每一次用户上传的文档块、Agent 的行动记录都是一个 Episode。

```sql
CREATE TABLE episodes (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id    VARCHAR     NOT NULL,   -- 图谱命名空间（世界线隔离用）
    thread_id   UUID        NOT NULL,   -- 对话/任务线索 ID
    role        VARCHAR     NOT NULL,   -- user | assistant | system | agent
    content     TEXT        NOT NULL,   -- 原始文本内容
    source_type VARCHAR     DEFAULT 'message',  -- message | document | agent_action | injection
    valid_at    TIMESTAMPTZ NOT NULL,   -- 事件发生时间（非入库时间）
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_episodes_group    ON episodes (group_id);
CREATE INDEX idx_episodes_thread   ON episodes (thread_id);
CREATE INDEX idx_episodes_valid_at ON episodes (group_id, valid_at);
```

**`source_type` 取值说明：**

| 值 | 含义 |
|----|------|
| `document` | 用户上传的文档（种子材料） |
| `agent_action` | Agent 推演过程中产生的事实行动 |
| `injection` | 外部事件注入（用户手动 / 联网 / 历史库） |
| `message` | 普通对话消息 |

---

### 2.2 `entities` — 知识图谱节点

```sql
CREATE TABLE entities (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id            VARCHAR     NOT NULL,   -- 图谱命名空间
    name                VARCHAR     NOT NULL,   -- 归一化名称（小写）
    display_name        VARCHAR,                -- 原始名称（展示用）
    entity_type         VARCHAR     NOT NULL,   -- person | organization | location | concept | event
    summary             TEXT,                   -- LLM 生成的实体摘要
    summary_embedding   VECTOR(1536),           -- 摘要向量（用于语义检索）
    metadata            JSONB       DEFAULT '{}', -- 扩展属性（角色、职位、立场等）
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_entities_group      ON entities (group_id);
CREATE INDEX idx_entities_name       ON entities (group_id, name);
CREATE INDEX idx_entities_type       ON entities (group_id, entity_type);
CREATE INDEX idx_entities_embedding  ON entities
    USING hnsw (summary_embedding vector_cosine_ops);
```

---

### 2.3 `entity_edges` — 时序关系边（核心）

每一条边代表一个在特定时间段内有效的"事实"。这是时序推演的核心存储。

```sql
CREATE TABLE entity_edges (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id            VARCHAR     NOT NULL,
    source_entity_id    UUID        NOT NULL REFERENCES entities(id),
    target_entity_id    UUID        NOT NULL REFERENCES entities(id),
    predicate           VARCHAR     NOT NULL,   -- 关系类型（sanctions, controls, opposes...）
    fact                TEXT        NOT NULL,   -- 自然语言事实描述
    fact_embedding      VECTOR(1536),           -- 事实向量（用于语义检索）

    -- 时序字段（核心）
    valid_at            TIMESTAMPTZ NOT NULL,   -- 事实开始生效时间
    expired_at          TIMESTAMPTZ,            -- NULL = 当前仍有效；非 NULL = 已过期

    -- 溯源
    episode_ids         UUID[]      NOT NULL DEFAULT '{}',
    
    -- 推演溯源
    generated_by        VARCHAR,                -- 'extraction' | 'agent_action' | 'blackswan' | 'injection' | 'bootstrap'
    confidence          FLOAT       DEFAULT 1.0, -- 置信度（0-1）

    created_at          TIMESTAMPTZ DEFAULT now()
);

-- 当前有效事实（最高频查询）
CREATE INDEX idx_edges_active ON entity_edges (group_id, source_entity_id)
    WHERE expired_at IS NULL;

-- 时间范围查询（时光机）
CREATE INDEX idx_edges_temporal ON entity_edges (group_id, valid_at, expired_at);

-- 向量检索
CREATE INDEX idx_edges_embedding ON entity_edges
    USING hnsw (fact_embedding vector_cosine_ops);
```

**时光机查询语义：**

```sql
-- 查询某时间点 T 的所有有效事实
SELECT * FROM entity_edges
WHERE group_id = :namespace
  AND valid_at  <= :T
  AND (expired_at IS NULL OR expired_at > :T);
```

---

## 三、Simulation 模块表结构

### 3.1 `sim_tasks` — 推演任务

```sql
CREATE TABLE sim_tasks (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id        VARCHAR     NOT NULL,       -- 用户/租户 ID

    -- 用户输入
    title           VARCHAR     NOT NULL,
    seed_content    TEXT        NOT NULL,       -- 种子材料原文
    seed_type       VARCHAR     DEFAULT 'text', -- text | document
    goal            TEXT        NOT NULL,       -- 推演目标（自然语言）

    -- 场景配置
    scene_type      VARCHAR     DEFAULT 'general', -- geopolitics | finance | novel | celebrity | general
    scene_config    JSONB       DEFAULT '{}',   -- 场景专用配置（覆盖 SCENE_REGISTRY 默认值）

    -- 时间配置
    sim_start_time  TIMESTAMPTZ NOT NULL,       -- 推演起始时间（现实时间轴）
    sim_end_time    TIMESTAMPTZ NOT NULL,       -- 推演结束时间
    time_step_unit  VARCHAR     DEFAULT 'month', -- day | week | month | year

    -- Agent 配置
    num_agents      INTEGER     DEFAULT 10,
    num_timelines   INTEGER     DEFAULT 3,      -- 并行世界线数量

    -- 黑天鹅配置
    blackswan_enabled   BOOLEAN DEFAULT TRUE,
    blackswan_prob      FLOAT   DEFAULT 0.05,   -- 每时间步触发概率

    -- 任务状态（扩展了 paused 状态）
    status          VARCHAR     DEFAULT 'pending',
    -- pending | extracting | simulating | paused | scoring | completed | failed
    progress        INTEGER     DEFAULT 0,
    status_message  TEXT,
    error           TEXT,

    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
```

**`status` 状态机：**

```
pending → extracting → simulating ⇌ paused → scoring → completed
    ↓          ↓           ↓           ↓         ↓
  failed    failed      failed      failed    failed
```

任何阶段均可转入 `failed`（LLM 调用失败、Worker 崩溃等）。

**`scene_config` JSONB 示例（覆盖默认场景配置）：**

```json
{
  "extra_action_types": ["embargo", "covert_ops"],
  "custom_prompt_suffix": "本次推演重点关注能源领域的博弈。",
  "scoring_weights": {
    "goal_achievement": 0.4,
    "power_stability": 0.3,
    "blackswan_exposure": 0.3
  },
  "weight_modifier_rules": [
    {
      "predicate": "impose_sanctions",
      "subject_delta": {"influence_weight": 0.1},
      "object_delta": {"influence_weight": -0.15}
    }
  ]
}
```

---

### 3.2 `sim_agents` — Agent 画像（初始模板）

每个推演任务的 Agent 画像，三层结构：静态画像 + 动态行为参数初始值 + 场景扩展。

**重要设计决策：** `sim_agents` 只存储 **任务级别** 的初始画像模板（`task_id` 维度），不区分世界线。各世界线在推演过程中产生的动态参数变化（如 `influence_weight` 被 WeightModifier 修改）存储在 `sim_checkpoints.agent_states` 中（`worldline_id` 维度）。推演引擎在每步开始时，从最新 checkpoint 读取当前世界线下该 Agent 的实时参数；如果没有 checkpoint（第一步），则使用 `sim_agents` 中的初始值。

```sql
CREATE TABLE sim_agents (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID        NOT NULL REFERENCES sim_tasks(id),
    entity_id       UUID        NOT NULL REFERENCES entities(id), -- 对应图谱节点

    -- 第一层：静态画像（不随推演变化）
    display_name    VARCHAR     NOT NULL,
    role            VARCHAR,                    -- 职位/角色
    organization    VARCHAR,                    -- 所属组织
    behavior_pattern TEXT,                      -- 历史行为模式描述
    interests       TEXT[],                     -- 核心利益诉求列表

    -- 第二层：动态行为参数初始值（推演过程中的实时值存在 sim_checkpoints.agent_states）
    activity_level      FLOAT   DEFAULT 0.5,    -- 整体活跃度（0-1）
    influence_weight    FLOAT   DEFAULT 1.0,    -- 影响力权重（决定行动顺序和传播强度）
    stance              VARCHAR DEFAULT 'neutral', -- supportive | opposing | neutral | observer
    sentiment_bias      FLOAT   DEFAULT 0.0,    -- 情感偏向（-1.0 悲观 ～ 1.0 乐观）
    response_delay_min  INTEGER DEFAULT 0,      -- 对事件最短反应步数
    response_delay_max  INTEGER DEFAULT 3,      -- 对事件最长反应步数

    -- 第三层：场景扩展（由 scene_type 决定结构，初始值由 profile_generator 生成）
    scene_metadata  JSONB       DEFAULT '{}',   -- 场景特定属性（含 information_access）

    -- 生成信息
    generated_by    VARCHAR     DEFAULT 'llm',  -- llm | manual
    is_active       BOOLEAN     DEFAULT TRUE,

    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_sim_agents_task     ON sim_agents (task_id);
CREATE INDEX idx_sim_agents_entity   ON sim_agents (entity_id);
```

**推演时 Agent 参数的读取优先级：**

```
1. sim_checkpoints.agent_states[agent_id]  (当前世界线最新检查点)
2. sim_agents 表中的初始值                   (无检查点时的 fallback)
```

这样设计的好处：
- Agent 画像定义只存一份，不随世界线数量膨胀
- 不同世界线中同一 Agent 的动态参数可以独立演化（通过各自的 checkpoint）
- 用户在推演前编辑 `sim_agents` = 修改所有世界线的初始条件
- 用户在推演暂停后编辑 checkpoint = 只修改特定世界线的当前状态

**`scene_metadata` JSONB 示例（按 `scene_type` 不同）：**

```json
// geopolitics — 包含 information_access
{
  "information_access": "global",      // global | local | restricted
  "authority_level": 8,
  "military_strength": 0.7,
  "controlled_resources": ["外汇储备", "稀土出口配额"],
  "coalition": ["俄罗斯", "伊朗"]
}

// finance
{
  "information_access": "local",
  "holdings": {"AAPL": 1000, "TSLA": 500},
  "capital": 10000000,
  "risk_tolerance": 0.7,
  "leverage": 2.0
}

// novel
{
  "information_access": "restricted",
  "emotional_state": "绝望",
  "hidden_secret": "知道凶手是谁",
  "relationship_map": {"男主": "暗恋", "闺蜜": "信任"}
}

// celebrity
{
  "information_access": "local",
  "fame_level": 8,
  "scandal_sensitivity": 0.9,
  "management_company": "某娱乐",
  "relationships": {"某明星": "恋人(隐藏)", "经纪人": "利益绑定"}
}
```

**`information_access` 取值说明：**

| 值 | 含义 | 感知范围 |
|----|------|---------|
| `global` | 全局信息访问权限 | 可见 graph_namespace 内所有有效事实 |
| `local` | 本地信息权限（默认） | 仅检索与自身直接相关的事实（向量相似度 top-K） |
| `restricted` | 受限信息权限 | 仅能看到明确被分配给自己的事实（角色扮演/情报受限场景） |

---

### 3.3 `sim_worldlines` — 世界线

```sql
CREATE TABLE sim_worldlines (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID        NOT NULL REFERENCES sim_tasks(id),

    -- 世界线标识
    name            VARCHAR     NOT NULL,       -- '乐观演化' | '中性演化' | '悲观演化' | '黑天鹅分叉'
    timeline_type   VARCHAR     DEFAULT 'normal', -- normal | blackswan_fork
    parent_id       UUID        REFERENCES sim_worldlines(id), -- 分叉来源（黑天鹅）
    fork_at_time    TIMESTAMPTZ,                -- 从哪个时间点分叉

    -- 图谱命名空间（隔离不同世界线的图谱状态）
    graph_namespace VARCHAR     NOT NULL UNIQUE, -- e.g. "task_xxx_tl_a"

    -- 初始假设（各世界线的不同出发点，由 WorldlineBootstrap 生成）
    initial_assumption  TEXT,                   -- 该世界线的初始前提假设

    -- 运行状态
    status          VARCHAR     DEFAULT 'pending', -- pending | running | paused | completed | failed
    current_sim_time TIMESTAMPTZ,               -- 当前推演到哪个时间点

    -- 评分（推演完成后）
    score           FLOAT,                      -- 综合评分（0-100）
    score_detail    JSONB,                      -- 各维度评分明细
    verdict         VARCHAR,                    -- 'above_water' | 'below_water'

    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_worldlines_task ON sim_worldlines (task_id);
```

**`verdict` 判定规则：**

| 条件 | verdict | 含义 |
|------|---------|------|
| `score >= 50.0` | `above_water` | 正向/可接受的未来 |
| `score < 50.0` | `below_water` | 负向/不利的未来 |

阈值 50 为默认值，可通过 `sim_tasks.scene_config.verdict_threshold` 覆盖（如金融场景可设为 60）。

---

### 3.4 `sim_worldline_events` — 世界线事件流

记录每条世界线推演过程中产生的关键事实变更，用于前端时间轴展示。

```sql
CREATE TABLE sim_worldline_events (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    worldline_id    UUID        NOT NULL REFERENCES sim_worldlines(id),

    event_time      TIMESTAMPTZ NOT NULL,       -- 事件发生的推演时间
    event_type      VARCHAR     NOT NULL,       -- 'agent_action' | 'blackswan' | 'injection' | 'state_change'
    action_type     VARCHAR,                    -- 对应 SCENE_REGISTRY 的 action_types（如 'impose_sanctions'）
    title           VARCHAR     NOT NULL,       -- 事件标题（1行摘要）
    description     TEXT,                       -- 事件详细描述
    entity_ids      UUID[],                     -- 涉及的 Entity ID 列表（对应 entities.id）
    new_facts       JSONB       DEFAULT '[]',   -- 产生的新事实摘要（用于前端展示）
    impact_score    FLOAT       DEFAULT 0.5,    -- 该事件的影响力（0-1）

    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_wl_events_worldline ON sim_worldline_events (worldline_id, event_time);
```

---

### 3.5 `sim_checkpoints` — 断点检查点（新增）

记录每个时间步完成后的推演状态，支持崩溃恢复和暂停续跑。

```sql
CREATE TABLE sim_checkpoints (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID        NOT NULL REFERENCES sim_tasks(id),
    worldline_id    UUID        NOT NULL REFERENCES sim_worldlines(id),

    -- 检查点位置
    checkpoint_time TIMESTAMPTZ NOT NULL,       -- 已完成推演到哪个时间步

    -- Agent 动态状态快照（仅动态参数，图谱无需快照）
    agent_states    JSONB       NOT NULL DEFAULT '{}',
    -- 格式: { "agent_uuid": { "influence_weight": 2.8, "activity_level": 0.9, ... }, ... }

    -- 待响应事件队列
    pending_reactions JSONB     DEFAULT '[]',
    -- 格式: [ { "event_id": ..., "target_agent_id": ..., "priority": ... }, ... ]

    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_checkpoints_worldline ON sim_checkpoints (worldline_id, checkpoint_time DESC);
-- 取最新检查点只需: ORDER BY checkpoint_time DESC LIMIT 1
```

---

### 3.6 `sim_event_injections` — 外部事件注入记录（新增）

记录所有外部注入的事件，用于审计、溯源和前端展示。

```sql
CREATE TABLE sim_event_injections (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID        NOT NULL REFERENCES sim_tasks(id),
    worldline_id    UUID        REFERENCES sim_worldlines(id), -- NULL = 注入所有世界线

    -- 注入来源
    source_type     VARCHAR     NOT NULL,
    -- manual | news_search | historical | scheduled_api

    -- 注入内容
    title           VARCHAR     NOT NULL,
    description     TEXT,
    inject_time     TIMESTAMPTZ NOT NULL,       -- 注入到推演时间轴的哪个时间点
    entity_ids      UUID[]      DEFAULT '{}',  -- 涉及的 Entity ID 列表（对应 entities.id）
    entity_names    VARCHAR[],                  -- 涉及的实体名称（冗余，用于展示和未匹配实体）

    -- 状态
    status          VARCHAR     DEFAULT 'pending', -- pending | applied | rejected
    rejection_reason TEXT,
    
    -- 溯源：生成了哪些 entity_edges
    generated_edge_ids UUID[]   DEFAULT '{}',

    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_injections_task ON sim_event_injections (task_id);
CREATE INDEX idx_injections_worldline ON sim_event_injections (worldline_id);
```

---

### 3.7 `sim_reports` — 推演报告

```sql
CREATE TABLE sim_reports (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID        NOT NULL REFERENCES sim_tasks(id),
    worldline_id    UUID        REFERENCES sim_worldlines(id), -- NULL = 任务总报告

    title           VARCHAR     NOT NULL,
    content         TEXT        NOT NULL,       -- Markdown 格式报告
    report_type     VARCHAR     DEFAULT 'summary', -- summary | worldline | comparison

    created_at      TIMESTAMPTZ DEFAULT now()
);
```

---

## 四、完整数据模型关系图

```
sim_tasks (1)
  │
  ├──(N) sim_agents
  │         └── entity_id → entities
  │
  ├──(N) sim_worldlines
  │         │
  │         ├── graph_namespace → entities (group_id = namespace)
  │         │                         └──< entity_edges (时序事实)
  │         │                                   └── episode_ids → episodes
  │         │
  │         ├──(N) sim_worldline_events (事件流)
  │         │
  │         ├──(N) sim_checkpoints (断点状态)
  │         │
  │         └── parent_id → sim_worldlines (黑天鹅分叉)
  │
  ├──(N) sim_event_injections (外部注入记录)
  │
  └──(N) sim_reports
```

---

## 五、`group_id` / `graph_namespace` 命名规范

### 概念区分

| 概念 | 字段 | 含义 | 所在表 |
|------|------|------|--------|
| **用户隔离** | `sim_tasks.group_id` | 标识数据所属的用户/租户，用于多租户数据隔离 | `sim_tasks` |
| **图谱隔离** | `sim_worldlines.graph_namespace` | 标识世界线的独立图谱命名空间 | `sim_worldlines` |
| **图谱归属** | `entities.group_id` / `entity_edges.group_id` | 标识图谱数据属于哪个命名空间 | `entities`、`entity_edges`、`episodes` |

**关键设计决策：** `entities` / `entity_edges` / `episodes` 表中的 `group_id` 字段在推演场景下存储的是 `graph_namespace`（世界线级别隔离），**而非**用户级别的 `group_id`。这是因为同一个任务的不同世界线需要各自独立的图谱数据。

用户级别的隔离通过 `sim_tasks.group_id` 实现，查询用户的所有数据时先查 `sim_tasks`，再通过 `sim_worldlines.graph_namespace` 关联到图谱数据。

### 命名规则

```
用户/租户隔离:   sim_tasks.group_id = "user_{user_id}"  或  "org_{org_id}"
基础图谱命名:    graph_namespace = "task_{task_id}_base"        (提取阶段的基础图谱)
世界线图谱命名:  graph_namespace = "task_{task_id}_tl_{short_id}"

示例:
  - graph_namespace = "task_a1b2c3_base"                      (基础图谱，提取阶段使用)
  - graph_namespace = "task_a1b2c3_tl_optimistic"             (乐观世界线)
  - graph_namespace = "task_a1b2c3_tl_pessimistic"            (悲观世界线)
  - graph_namespace = "task_a1b2c3_tl_pessimistic_fork1"      (黑天鹅分叉)
```

图谱数据的隔离查询只需在 WHERE 条件中使用 `group_id = :graph_namespace`，天然实现世界线之间的完全数据隔离。

---

## 六、推演行动数据结构（LLM 输出格式）

Agent 每一步的 LLM 输出为结构化 JSON，直接驱动图谱更新：

```json
{
  "action_type": "impose_sanctions",
  "description": "美国财政部宣布对中国半导体企业实施新一轮出口管制",
  "confidence": 0.85,
  "new_facts": [
    {
      "source": "美国财政部",
      "predicate": "sanctions",
      "target": "中芯国际",
      "fact": "美国财政部于2026年6月对中芯国际实施出口管制，禁止14nm以下制程设备出口",
      "valid_at": "2026-06-01",
      "expires_fact_id": null
    },
    {
      "source": "中芯国际",
      "predicate": "faces_restriction",
      "target": "先进制程扩产计划",
      "fact": "受制裁影响，中芯国际2026年先进制程扩产计划被迫延期",
      "valid_at": "2026-06-01",
      "expires_fact_id": "uuid-of-old-expansion-plan-fact"
    }
  ]
}
```

**`expires_fact_id` 字段说明：**

事实过期有两种机制，优先级从高到低：

| 机制 | 触发方式 | 说明 |
|------|---------|------|
| **显式过期** | LLM 在 `new_facts` 中指定 `expires_fact_id` | Agent 明确知道某条旧事实被新事实取代（如"扩产计划被迫延期"取代"扩产计划进行中"） |
| **自动冲突检测** | `temporal_upsert` 检索同主体+谓语的现有事实，LLM 判断是否矛盾 | 兜底机制，当 Agent 未显式指定时由系统自动处理 |

当 `expires_fact_id` 非空时，`temporal_upsert` 直接将指定事实标记 `expired_at = valid_at`，跳过自动冲突检测步骤。当 `expires_fact_id` 为 `null` 时，走正常的自动冲突检测流程。
```
