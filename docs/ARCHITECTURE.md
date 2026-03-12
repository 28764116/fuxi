# 伏羲（Fuxi）— 技术架构设计文档

> 版本：v0.4
> 最后更新：2026-03-12

---

## 一、整体架构

```
┌──────────────────────────────────────────────────────────┐
│                        前端层                             │
│   关系图谱渲染  │  时间滑块  │  世界线展示  │  进度面板   │
│              React + TypeScript + Vite                   │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP / WebSocket
┌──────────────────────────▼───────────────────────────────┐
│                      API 网关层                           │
│              FastAPI (uvicorn, async)                    │
│         API Key 鉴权  │  CORS  │  路由分发                │
└────┬──────────────────────────────────────┬──────────────┘
     │                                      │
┌────▼────────────┐                ┌────────▼──────────────┐
│   Memory 模块   │                │   Simulation 模块      │
│  知识图谱管理   │                │   推演任务管理          │
│  /memory/*      │                │   /simulation/*        │
│  时光机查询     │                │   WebSocket 进度推送    │
└────┬────────────┘                └────────┬──────────────┘
     │                                      │
     └──────────────┬───────────────────────┘
                    │ Celery Task（异步）
┌───────────────────▼──────────────────────────────────────┐
│                    任务队列层                             │
│                  Celery + Redis                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ memory      │  │ simulation  │  │  reporter       │  │
│  │ Worker      │  │ Worker      │  │  Worker         │  │
│  │ (三元组抽取) │  │ (多世界线   │  │ (评分+报告生成) │  │
│  │             │  │  推演循环)  │  │                 │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
└───────────────────────────┬──────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────┐
│                       数据层                             │
│  PostgreSQL + pgvector  │  Redis (队列 + Pub/Sub)        │
│  entities / entity_edges（时序图谱）                      │
│  sim_tasks / sim_agents / sim_worldlines / sim_reports   │
│  sim_checkpoints / sim_event_injections / episodes       │
└──────────────────────────────────────────────────────────┘
```

---

## 二、核心模块说明

### 2.1 Memory 模块（知识图谱 + 时序记忆）

**职责：** 世界状态的存储、更新和查询。这是推演引擎的"状态数据库"。

**核心能力：**

| 能力 | 实现 | 状态 |
|------|------|------|
| 文档解析 | `file_parser.py`（PDF/文本，重叠分块） | ✅ 已实现 |
| 三元组抽取 | `extractor.py`（LLM 定向提取） | ✅ 已实现，需扩展目标导向 |
| 向量化 | `embedder.py`（MiniMax embo-01，1536维） | ✅ 已实现 |
| 时序冲突检测 | `temporal.py`（temporal_upsert）| ✅ 已实现 |
| 语义检索 | `service.search_edges/search_entities` | ✅ 已实现 |
| 时光机查询 | `service.get_entity_facts_at(t)` | ✅ 已实现 |
| 图谱全量查询 | 图谱节点/边列表接口 | ⚠️ 需要补充 |

**时序事实生命周期：**

```
Episode（原始输入）
    ↓ Celery 异步
LLM 抽取三元组 (subject, predicate, object, fact)
    ↓
temporal_upsert：
  ├── 检索同主体+谓语的当前有效事实
  ├── LLM 判断是否矛盾
  ├── 矛盾 → 旧事实 expired_at = t_new
  └── 写入新事实 (valid_at = t, expired_at = NULL)
```

---

### 2.2 Simulation 模块（推演引擎）

**职责：** 驱动多 Agent 在时间轴上基于事实演化，产生多条并行世界线。

**核心原则：事实驱动（Fact-driven）**

```
Agent 的每次行动 ≠ 发帖/评论
Agent 的每次行动 = 产生改变世界状态的事实（写入图谱的时序边）
```

**目标推演循环（engine.py）：**

```python
for timeline in worldlines:
    # 从最新 checkpoint 恢复 Agent 动态参数（无 checkpoint 则用 sim_agents 初始值）
    agent_states = load_agent_states(timeline)

    for t in time_steps:
        # 按 influence_weight 排序，高影响力 Agent 先行动
        for agent in sorted(active_agents, key=lambda a: -agent_states[a.id].influence_weight):
            
            # 1. 感知：按信息权限检索图谱中与该 Agent 相关的当前有效事实
            facts = search_edges(
                query=agent.profile_summary,
                group_id=timeline.graph_namespace,
                t=t,
                limit=20,
                access_level=agent.scene_metadata.get("information_access", "local")
                # global: 可见所有事实; local: 仅直接相关; restricted: 仅明确授权
            )
            
            # 2. 决策：LLM 基于三层画像 + 当前事实 → 输出结构化行动
            prompt = build_prompt(agent, facts, t, scene_registry[task.scene_type])
            action = llm_decide(prompt)
            # action = { action_type, description, new_facts[], confidence }
            
            # 3. 写回：new_facts 通过 temporal_upsert 更新图谱
            for triplet in action.new_facts:
                temporal_upsert(triplet, valid_at=t, group_id=timeline.graph_namespace)
            
            # 4. 记录事件流（用于前端时间轴展示）
            event = save_worldline_event(timeline.id, t, action)
            
            # 5. 高影响力事件推送：触发相关 Agent 优先响应
            if event.impact_score >= 0.7:
                notify_affected_agents(event, active_agents, timeline)
        
        # 步末：WeightModifier —— 根据本步新事实动态调整 Agent 权重（更新 agent_states）
        weight_modifier.update_all(agent_states, timeline.graph_namespace, t)
        
        # 黑天鹅检查
        if task.blackswan_enabled and random() < task.blackswan_prob:
            blackswan = inject_blackswan_event(timeline, t)
            fork_new_timeline(timeline, blackswan, fork_at=t)
        
        # 检查点：持久化当前时间步进度
        save_checkpoint(task.id, timeline.id, t)
        
        publish_progress(task.id, timeline.id, t)
```

---

### 2.3 Scene Registry（场景注册表）

**职责：** 定义不同场景的行动类型、LLM 提示词和评估维度。是实现"引擎通用、场景配置化"的核心。

**文件位置：** `backend/simulation/scene_registry.py`

```python
SCENE_REGISTRY = {
    "geopolitics": {
        "action_types": [
            "announce_policy", "impose_sanctions", "form_alliance",
            "military_action", "negotiate", "withdraw_support"
        ],
        "agent_prompt_prefix": (
            "你是国际政治中的决策者，你的行动以国家/组织利益为核心驱动，"
            "决策考量包括：权力平衡、经济利益、意识形态。"
        ),
        "scoring_metrics": ["goal_achievement", "power_stability", "alliance_health", "blackswan_exposure"],
        "weight_modifier_rules": {
            "impose_sanctions": {"subject": {"influence_weight": +0.1}, "object": {"influence_weight": -0.15}},
            "form_alliance":    {"object": {"influence_weight": +0.2}},
            "military_action":  {"subject": {"activity_level": +0.3}, "object": {"activity_level": +0.2}}
        }
    },
    "finance": {
        "action_types": ["buy", "sell", "short", "hold", "announce_earnings", "raise_capital", "default"],
        "agent_prompt_prefix": (
            "你是金融市场参与者，你的行动基于价格信号、持仓成本和市场情绪，"
            "决策考量包括：风险收益比、流动性、对手盘行为。"
        ),
        "scoring_metrics": ["portfolio_return", "sharpe_ratio", "drawdown", "systemic_risk"],
        "weight_modifier_rules": {
            "raise_capital": {"subject": {"influence_weight": +0.2}},
            "default":       {"subject": {"influence_weight": -0.4}}
        }
    },
    "novel": {
        "action_types": ["confess", "betray", "escape", "reveal_secret", "form_bond", "confront", "sacrifice"],
        "agent_prompt_prefix": (
            "你是小说中的人物，你的行动基于情感状态和隐藏动机，"
            "决策考量包括：情感驱动、人物关系、隐藏目标。"
        ),
        "scoring_metrics": ["plot_tension", "goal_achievement", "emotional_arc", "narrative_coherence"],
        "weight_modifier_rules": {
            "betray":      {"subject": {"sentiment_bias": -0.3}, "object": {"activity_level": +0.4}},
            "form_bond":   {"subject": {"sentiment_bias": +0.2}, "object": {"sentiment_bias": +0.2}}
        }
    },
    "celebrity": {
        "action_types": ["respond", "deny", "go_silent", "counter_attack", "release_statement", "expose_other"],
        "agent_prompt_prefix": (
            "你是娱乐圈人物，你的行动基于流量和商业利益，"
            "决策考量包括：公众形象、商业价值、粉丝情绪。"
        ),
        "scoring_metrics": ["fame_preservation", "commercial_value", "scandal_containment"],
        "weight_modifier_rules": {
            "expose_other":    {"object": {"influence_weight": -0.3, "activity_level": +0.5}},
            "go_silent":       {"subject": {"influence_weight": -0.1}}
        }
    },
    "general": {
        "action_types": ["decide", "cooperate", "oppose", "observe", "negotiate", "withdraw"],
        "agent_prompt_prefix": "你是现实世界中的决策者，基于当前信息和自身利益作出判断。",
        "scoring_metrics": ["goal_achievement", "stability", "key_agent_outcomes", "blackswan_exposure"],
        "weight_modifier_rules": {}
    }
}
```

**LLM Prompt 构造逻辑（`engine.py` 中）：**

```
[场景前缀]
你是 {agent.display_name}，职位：{agent.role}，所属：{agent.organization}。
你的立场：{agent.stance}，行为模式：{agent.behavior_pattern}。
你的核心利益：{agent.interests}。
{scene_metadata_description}   ← 由 scene_metadata 动态生成

当前时间：{sim_time}

你当前知道的事实：
{facts_list}                   ← 来自图谱的有效事实（按信息权限过滤）

最近发生的高影响力事件（需优先响应）：
{pending_reactions}            ← 由 notify_affected_agents 推入的待响应队列

你可以采取的行动类型：{action_types}  ← 来自 SCENE_REGISTRY

请输出你的决策（JSON格式）：
{
  "action_type": "...",
  "description": "...",
  "new_facts": [ { "source": ..., "predicate": ..., "target": ..., "fact": ..., "valid_at": ... } ],
  "confidence": 0.0-1.0
}
```

---

### 2.4 Agent 画像生成器（profile_generator.py）

**职责：** 从图谱节点自动生成三层 Agent 画像，存入 `sim_agents` 表。

```
图谱 entities（LLM 提取的节点）
    ↓
profile_generator.generate(entity, task)
    ├── 第一层：从 entity.metadata 提取静态画像字段
    ├── 第二层：LLM 推断行为参数初始值（activity_level, influence_weight, stance...）
    └── 第三层：按 task.scene_type 注入场景扩展字段（scene_metadata）
              ├── information_access: global | local | restricted
              └── 其他场景特定字段（holdings, authority_level, emotional_state...）
    ↓
写入 sim_agents 表（任务级初始模板，动态参数在推演中由 sim_checkpoints.agent_states 承载）
```

---

### 2.5 EventInjector（外部事件注入插件）

**职责：** 将现实世界事件或用户假设作为"种子事实"注入到指定世界线的图谱中，打断推演或修正前提。

**文件位置：** `backend/simulation/event_injector.py`

**注入来源（插件化接口）：**

```python
class EventInjectorBase:
    """所有事件注入来源实现此接口"""
    def fetch(self) -> list[InjectedEvent]: ...

class ManualEventInjector(EventInjectorBase):
    """用户手动输入：假设某事件发生"""
    # POST /simulation/worldlines/{id}/inject_event

class NewsSearchInjector(EventInjectorBase):
    """联网搜索注入：自动拉取最新新闻"""
    def fetch(self): return search_news(query=self.goal, date=self.sim_time)

class HistoricalDataInjector(EventInjectorBase):
    """历史事件库：按 sim_time 自动匹配历史上真实发生的事件"""
    def fetch(self): return query_historical_events(date=self.sim_time)

class ScheduledAPIInjector(EventInjectorBase):
    """定时数据源：财经API、新闻RSS等定期拉取"""
    def fetch(self): return pull_from_api(self.api_config)
```

**注入流程：**

```
InjectedEvent
  ├── source_type: manual | news | historical | api
  ├── fact: 自然语言事实描述
  ├── entity_names: 涉及的实体名称列表
  ├── valid_at: 事件时间
  └── inject_to: worldline_id（null = 注入所有世界线）
    ↓
temporal_upsert → 写入 entity_edges（generated_by = 'injection'）
    ↓
记录到 sim_event_injections 表（用于审计和溯源）
    ↓
触发推演循环感知刷新（相关 Agent 在下一时间步优先响应此事件）
```

---

### 2.6 WeightModifier（Agent 权重动态调整插件）

**职责：** 每个时间步结束后，根据图谱中新增的事实，自动重新计算 Agent 的动态行为参数，反映现实中地位变化。

**文件位置：** `backend/simulation/weight_modifier.py`

**机制：**

```python
class WeightModifierBase:
    """所有权重修改规则实现此接口"""
    def apply(self, agent: SimAgent, new_facts: list[EntityEdge]) -> dict: ...
    # 返回需要更新的字段 {"influence_weight": new_val, "activity_level": new_val, ...}

class SceneWeightModifier(WeightModifierBase):
    """按场景注册表定义的规则修改权重"""
    # 例：geopolitics 场景
    # - 触发 form_alliance → 被结盟方 influence_weight += 0.2
    # - 触发 impose_sanctions → 制裁方 influence_weight += 0.1，被制裁方 influence_weight -= 0.15
    # - 触发 military_action → 相关 Agent activity_level 上升
    
class CustomRuleWeightModifier(WeightModifierBase):
    """用户自定义权重规则（scene_config 中配置）"""
```

**示例规则表：**

*geopolitics 场景：*

| 触发事实谓语 | 主体变化 | 客体变化 |
|------------|---------|---------|
| `impose_sanctions` | `influence_weight += 0.1` | `influence_weight -= 0.15` |
| `form_alliance` | — | `influence_weight += 0.2` |
| `military_action` | `activity_level += 0.3` | `activity_level += 0.2`（防御态势） |

*finance 场景：*

| 触发事实谓语 | 主体变化 | 客体变化 |
|------------|---------|---------|
| `raise_capital` | `influence_weight += 0.2` | — |
| `default`（违约） | `influence_weight -= 0.4` | — |

---

### 2.7 WorldlineBootstrap（世界线初始化）

**职责：** 在推演开始前，从基础图谱克隆出多条世界线，并向每条注入不同的初始假设事实。

**文件位置：** `backend/simulation/worldline_bootstrap.py`

```python
def bootstrap_worldlines(task: SimTask, base_graph_namespace: str) -> list[SimWorldline]:
    """
    1. 用 LLM 基于 task.goal 生成 N 个不同的初始假设（乐观/中性/悲观/...）
    2. 为每个假设创建独立的 graph_namespace
    3. 克隆基础图谱数据到各 namespace（深拷贝 entity_edges）
    4. 将各自的初始假设事实通过 temporal_upsert 写入对应 namespace
    """
    assumptions = llm_generate_assumptions(task.goal, task.num_timelines)
    # 例：
    # - 乐观：中美达成部分协议，技术管制有限
    # - 中性：维持现状，摩擦持续但无重大升级
    # - 悲观：全面技术脱钩，双边贸易大幅萎缩
    
    worldlines = []
    for assumption in assumptions:
        wl = create_worldline(task.id, assumption)
        clone_graph(base_graph_namespace, wl.graph_namespace)
        inject_assumption_facts(assumption, wl.graph_namespace, valid_at=task.sim_start_time)
        worldlines.append(wl)
    
    return worldlines
```

---

### 2.8 断点续跑机制（Checkpoint）

**职责：** 每完成一个时间步保存检查点，支持 Worker 崩溃后从断点恢复，支持用户暂停推演后注入新约束再继续。

**状态机扩展：**

```
pending → extracting → simulating ⇌ paused → scoring → completed
    ↓          ↓           ↓           ↓         ↓
  failed    failed      failed      failed    failed
```

任何阶段均可转入 `failed`（LLM 调用失败、Worker 崩溃等）。

**检查点数据（存入 `sim_checkpoints` 表）：**

```python
{
    "task_id": ...,
    "worldline_id": ...,
    "checkpoint_time": "2027-03-01",   # 已推演到哪个时间步
    "agent_states": {                   # 所有 Agent 此时的动态参数快照
        "agent_uuid_1": {"influence_weight": 2.8, "activity_level": 0.9, ...},
        ...
    },
    "pending_reactions": {...}          # 待响应的高影响力事件队列
}
```

**恢复逻辑：**

```python
def resume_from_checkpoint(task_id, worldline_id):
    ckpt = get_latest_checkpoint(task_id, worldline_id)
    # 图谱状态无需恢复（entity_edges 已持久化）
    # 只需恢复 Agent 动态参数 + 从 ckpt.checkpoint_time 的下一步继续
    restore_agent_states(ckpt.agent_states)
    run_simulation(task_id, worldline_id, start_from=ckpt.checkpoint_time + 1_step)
```

---

### 2.9 世界线（WorldLine）管理

**分支数据模型：**

每条世界线持有一个独立的 `graph_namespace`，初始时由 `WorldlineBootstrap` 克隆，之后独立演化。

```
SimTask
  └── WorldLine A (乐观)   graph_namespace = "task_xxx_tl_optimistic"
  └── WorldLine B (中性)   graph_namespace = "task_xxx_tl_neutral"
  └── WorldLine C (悲观)   graph_namespace = "task_xxx_tl_pessimistic"
       └── WorldLine C1 (黑天鹅分叉) graph_namespace = "task_xxx_tl_pessimistic_fork1"
```

**状态快照机制：**

图谱事实自带 `valid_at` / `expired_at`，天然支持任意时间点查询，不需要额外存储快照。时间滑块直接调用 `get_entity_facts_at(t)` 即可。

---

## 三、数据流图

### 3.1 创建推演任务

```
用户上传文档 + 设定目标 + 选择场景类型
    │
    ▼
POST /simulation/tasks
    │ 创建 SimTask（含 scene_type, scene_config）
    ▼
Celery: simulation.run_pipeline(task_id)
    │
    ├── Phase 1: 要素提取（0%-20%）
    │   └── file_parser → extractor（目标导向）→ temporal_upsert → 基础图谱初始化
    │
    ├── Phase 2: Agent 画像生成（20%-30%）
    │   └── profile_generator（三层画像，含 information_access）→ sim_agents 表
    │
    ├── Phase 3: 世界线初始化（30%-35%）
    │   └── worldline_bootstrap → LLM生成初始假设 → 克隆图谱 → 注入初始假设事实
    │
    ├── Phase 4: 世界线并行推演（35%-85%）
    │   └── 为每条世界线启动独立 Celery 子任务
    │       └── 时间步循环：
    │           → Agent 按信息权限感知图谱
    │           → LLM 决策（含待响应事件队列）
    │           → temporal_upsert
    │           → WeightModifier 更新动态参数
    │           → save_checkpoint（断点）
    │
    └── Phase 5: 评分 + 报告（85%-100%）
        └── scorer（按 scene_type 评估维度）→ sim_reports
```

### 3.2 Agent 推演单步

```
Agent（按 influence_weight 排序）
    │
    ├── 感知：search_edges(agent画像, graph_namespace, t, access_level)
    │         ↓ 返回按信息权限过滤的有效事实（最多20条）
    │         ↓ + 待响应的高影响力事件（由上一步推入）
    │
    ├── 决策：LLM(场景前缀 + agent三层画像 + 事实列表 + 待响应事件 + action_types)
    │         ↓ 输出结构化 JSON { action_type, description, new_facts[] }
    │
    ├── 写回：for fact in new_facts → temporal_upsert(fact, t, graph_namespace)
    │         ↓ 检测矛盾 → 旧事实 expired_at 标记 → 新事实写入
    │         ↓ 记录 sim_worldline_events（用于前端时间轴）
    │
    └── 广播：if impact_score >= 0.7 → notify_affected_agents(event)
              ↓ 将高影响力事件推入相关 Agent 的待响应队列
```

### 3.3 外部事件注入（推演中）

```
POST /simulation/worldlines/{id}/inject_event
    │
    ▼
EventInjector.inject(event, worldline_id)
    │
    ├── temporal_upsert → entity_edges（generated_by = 'injection'）
    ├── 记录 sim_event_injections（来源、时间、内容）
    └── 如果任务处于 paused 状态 → 自动恢复推演（resume_from_checkpoint）
```

### 3.4 时间滑块查询

```
用户拖动滑块到时间 T
    │
    ▼
GET /simulation/worldlines/{id}/snapshot?t=2027-06-01
    │
    ▼
service.get_graph_snapshot(graph_namespace, t)
    │ SELECT * FROM entity_edges
    │ WHERE group_id = graph_namespace
    │   AND valid_at <= T
    │   AND (expired_at IS NULL OR expired_at > T)
    ▼
返回节点列表 + 边列表（前端渲染图谱快照）
```

---

## 四、技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| Web 框架 | FastAPI | 异步原生，自动生成 OpenAPI 文档 |
| 任务队列 | Celery + Redis | 多世界线可并行，任意阶段可重试，支持 revoke/resume |
| 数据库 | PostgreSQL + pgvector | 关系型 + 向量检索一体，无需引入 Neo4j |
| 实时通信 | WebSocket + Redis Pub/Sub | 替代轮询，多世界线进度统一推送 |
| LLM | MiniMax（OpenAI 协议兼容） | 当前默认，架构支持切换任意 OpenAI 兼容模型 |
| Embedding | MiniMax embo-01（1536维） | 与 LLM 同厂，降低延迟 |
| 向量索引 | pgvector HNSW | 相比 IVFFlat 查询更稳定，无需训练 |
| 前端 | React + TypeScript + Vite | 生态成熟，组件库选择多 |

---

## 五、部署结构

```yaml
# docker-compose 服务
services:
  api:          # FastAPI (uvicorn)
  worker:       # Celery worker
  postgres:     # PostgreSQL + pgvector
  redis:        # Redis（队列 + Pub/Sub）
  frontend:     # React 静态文件（Nginx）
```

**启动顺序：** postgres → redis → api → worker → frontend

---

## 六、待实现模块清单

| 优先级 | 模块 | 改动描述 |
|--------|------|---------|
| P0 | `simulation/scene_registry.py` | 新文件：场景注册表（action_types + prompt + scoring_metrics） |
| P0 | `simulation/models.py` | 新增 `SimAgent`、`SimCheckpoint`、`SimEventInjection` 表，`scene_type`/`scene_config` 字段 |
| P0 | `simulation/engine.py` | 完全重写：图谱感知（含信息权限）→ 三层画像决策 → temporal_upsert → WeightModifier → 检查点 |
| P0 | `simulation/profile_generator.py` | 新文件：三层 Agent 画像自动生成，含 `information_access` 字段 |
| P0 | `simulation/worldline_bootstrap.py` | 新文件：世界线初始化（LLM生成假设 + 图谱克隆 + 假设事实注入） |
| P0 | `simulation/tasks.py` | 多世界线并行子任务编排，支持 paused/resume 状态 |
| P0 | `simulation/router.py` | 新增世界线接口、图谱快照接口、事件注入接口、Agent 权重调整接口 |
| P0 | `memory/extractor.py` | 扩展为"目标导向"的定向抽取（传入 goal 参数） |
| P1 | `simulation/event_injector.py` | 新文件：EventInjector 插件接口 + Manual/News/Historical 实现 |
| P1 | `simulation/weight_modifier.py` | 新文件：WeightModifier 插件接口 + SceneWeightModifier 实现 |
| P1 | `simulation/scorer.py` | 新文件：世界线多维评分逻辑（按 scene_type 加载评估维度） |
| P1 | `simulation/blackswan.py` | 新文件：黑天鹅事件库 + 触发机制 |
| P1 | `memory/router.py` | 新增图谱全量查询接口（用于前端关系图渲染） |
| P2 | `app/main.py` | 统一日志配置、错误处理中间件 |
