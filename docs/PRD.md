# 伏羲（Fuxi）— 产品需求文档（PRD）

> 版本：v0.4
> 状态：草稿
> 最后更新：2026-03-12

---

## 一、产品定位

**伏羲** 是一个基于多智能体仿真的**未来推演平台**。

用户输入种子材料（文档、事件、背景资料）和推演目标，平台自动提取关键要素，构建知识图谱，然后让多个 AI Agent 基于各自的身份、立场、历史行为在时间轴上自主演化，最终产出多条平行的"世界线"预测，并给出好坏评估。

**一句话**：给定一个初始世界，推演它在未来的所有可能走向。

**核心机制**：事实驱动推演（Fact-driven Simulation）。Agent 的每次行动不产生文章或帖子，而是产生**改变世界状态的事实**，直接写入知识图谱，驱动下一轮所有 Agent 的决策。

---

## 二、目标用户

| 用户类型 | 使用场景 | 付费意愿 |
|---------|---------|---------|
| C 端个人用户 | 小说/剧本世界线推演、历史假设推演、个人决策辅助 | 按次付费 / 月订阅 |
| B 端企业用户 | 舆情预测、政策影响评估、战略沙盘、金融风险推演 | 团队订阅 / 私有化部署 |
| 游戏/内容创作者 | NPC 行为推演、剧情分支生成 | 月订阅 |

---

## 三、核心产品流程（4 步骤）

### 步骤 1：要素提取 + 关系图谱渲染

**用户输入：**
- 种子材料（文档、新闻、事件描述）
- 推演目标（用自然语言描述，如"分析中美贸易战对半导体产业的影响"）
- 时间范围（起止时间，如 2025年 → 2030年）
- 世界线数量（默认 3 条）
- 场景类型（geopolitics / finance / novel / celebrity / general）

**系统自动完成：**
1. 解析上传文档（PDF / 文本）
2. 以推演目标为导向，定向提取：
   - **人物**（Person）：姓名、职位、所属组织、历史行为倾向
   - **组织**（Organization）：性质、实力、利益诉求
   - **事件**（Event）：时间、影响范围、关联人物
   - **关键概念**（Concept）：政策、技术、市场等
3. 构建关系图谱（节点 + 带时态的关系边）
4. 为每个 Agent 生成三层画像（见"Agent 画像结构"）
5. 前端渲染可交互的关系图

**前端展示：**
- 可缩放的关系图（节点着色区分类型，边显示关系描述）
- 用户可手动添加/修改节点和关系
- 点击节点查看详情（已知事实列表 + Agent 画像）

---

### 步骤 2：人物身份分析 + 推演分支设定

**系统自动完成：**
1. 分析关键人物的身份动态（历史上的角色变化轨迹）
2. 识别"关键决策节点"（哪些节点的选择会导致分叉）
3. 为每个 Agent 构建完整画像：
   - 静态画像：基本身份、利益诉求、历史行为模式
   - 动态行为参数：活跃度、影响力权重、情感偏向、立场
   - 场景扩展字段：根据 `scene_type` 注入场景特定属性（含信息权限）
4. 世界线初始化（`WorldlineBootstrap`）：LLM 生成 N 个差异化初始假设，克隆图谱，注入各自初始事实

**用户可操作：**
- 查看/编辑 Agent 画像（含场景扩展字段和信息权限）
- 手动调整 Agent 的 `influence_weight`（模拟势力变化）
- 手动指定某个 Agent 的立场（强制约束）
- 标记"关键节点"（推演时重点分析的时间点）

---

### 步骤 3：时间轴推演 + 黑天鹅事件

**推演机制（事实驱动）：**

```
时间步 T（初始世界状态）
    ↓
每个 Agent（按 influence_weight 排序）：
  1. 感知：从图谱检索与自己相关的有效事实（按 information_access 权限过滤）
           + 接收上一步高影响力事件的待响应通知
  2. 决策：LLM 基于 Agent 画像 + 当前事实 + 待响应事件 → 输出结构化行动
     行动格式：{ action_type, description, new_facts[], confidence }
  3. 写回：new_facts 通过 temporal_upsert 写入图谱
     自动检测矛盾 → 旧事实 expired_at 标记过期
  4. 广播：高影响力事件（impact_score >= 0.7）推送给相关 Agent，触发优先响应
    ↓
步末：WeightModifier 根据新事实动态调整所有 Agent 的 influence_weight 等参数
    ↓
保存断点检查点（崩溃恢复 / 暂停续跑用）
    ↓
时间步 T+1（图谱状态已更新，所有 Agent 可感知新事实）
    ↓
重复，直至达到目标时间
```

**Agent 行动类型（按场景注册）：**

| 场景 | 行动类型示例 |
|------|------------|
| `geopolitics` | 发布政策、实施制裁、结成同盟、军事行动 |
| `finance` | 买入、卖出、做空、发布财报、融资 |
| `novel` | 表白、背叛、逃跑、揭秘、结盟 |
| `celebrity` | 回应、否认、沉默、反击、发声明 |
| `general` | 决策、合作、对抗、观望、谈判 |

**外部事件注入（插件化）：**

用户可随时向推演中的世界线注入外部事件，作为新的初始事实写入图谱：

| 注入来源 | 描述 |
|---------|------|
| 手动注入 | 用户输入"假设发生了X"，直接写入指定时间点 |
| 联网搜索 | 按推演时间自动拉取真实新闻（P2） |
| 历史事件库 | 按 sim_time 匹配历史上真实发生的事件（P2） |
| 定时数据源 | 财经 API / 新闻 RSS 定期推送（P2） |

**分支产生机制（多世界线）：**
- 推演开始时，LLM 生成 N 个不同初始假设（乐观/中性/悲观），各自独立演化
- 不同世界线之间完全隔离（独立的 `graph_namespace`）

**黑天鹅事件：**
- 每个时间步有概率触发随机低概率高影响事件
- 事件库：自然灾害、技术突破、政治变局、突发危机等
- 用户可设定黑天鹅触发概率（关闭 / 低 / 中 / 高）
- 黑天鹅发生后，当前世界线自动分叉

**推演暂停/续跑：**
- 用户可随时暂停推演（状态变为 `paused`）
- 暂停后可注入新的约束事件或修改 Agent 参数
- 恢复时从最近检查点继续，图谱状态完全保留

**时间滑块：**
- 用户可拖动时间滑块查看任意时间点的世界状态
- 底层支持：`get_entity_facts_at(point_in_time)` 时光机查询
- 显示该时间点下所有 Agent 的状态、关系图谱快照

---

### 步骤 4：多世界线结果展示

**世界线评分系统：**

每条世界线在推演结束时，由 LLM 评估以下维度（维度随 `scene_type` 动态调整）：

| 场景 | 评估维度 |
|------|---------|
| `geopolitics` | 目标达成度、权力稳定性、联盟格局、黑天鹅暴露 |
| `finance` | 投资组合收益率、夏普比率、系统性风险暴露 |
| `novel` | 情节张力、主角目标达成率、情感弧完整度 |
| `celebrity` | 知名度保持、商业价值、丑闻控制力、黑天鹅暴露 |
| `general` | 目标达成度、稳定性、关键人物走向、黑天鹅风险 |

**综合评分** → 0-100 分，以 **50 分为分水岭**（可通过 `scene_config.verdict_threshold` 自定义），分为"水上"（≥ 阈值，正向）和"水下"（< 阈值，负向）两大类。

**展示形式：**

```
水上（好的未来）
  ├── 世界线 A（乐观演化）    评分: 87  [查看详情]
  └── 世界线 C（稳健演化）    评分: 72  [查看详情]
──────────────────────── 水面 ────────────────────────
水下（不利的未来）
  ├── 世界线 B（悲观演化）    评分: 34  [查看详情]
  └── 世界线 D（黑天鹅冲击）  评分: 18  [查看详情]
```

每条世界线详情页包含：
- 时间轴事件流（关键事实变更按时间排列，含外部注入事件标记）
- 图谱演化动画（关系如何随时间变化）
- 关键转折点分析（是什么事实变更导致了分叉）
- Agent 权重变化历史（`influence_weight` 随时间的变化曲线）
- 可下载的完整推演报告（Markdown）

---

## 四、Agent 画像结构

每个 Agent 画像由三层组成：

```json
{
  "// 第一层：静态画像（所有场景通用）": "",
  "name": "某角色",
  "role": "国务院副总理",
  "organization": "中国国务院",
  "behavior_pattern": "强硬、数据驱动、倾向单边行动",
  "interests": ["维护经济增长", "扩大技术自主"],

  "// 第二层：动态行为参数（来自 MiroFish 设计，直接复用）": "",
  "activity_level": 0.8,
  "influence_weight": 2.5,
  "stance": "opposing",
  "sentiment_bias": -0.3,
  "response_delay_min": 5,
  "response_delay_max": 30,

  "// 第三层：场景扩展（由 scene_type 动态注入）": "",
  "scene_type": "geopolitics",
  "scene_metadata": {
    "information_access": "global",
    "authority_level": 8,
    "controlled_resources": ["外汇储备", "稀土出口配额"],
    "coalition": ["俄罗斯", "伊朗"]
  }
}
```

**`information_access` — 信息权限字段（新增）：**

| 值 | 适用场景 | 含义 |
|----|---------|------|
| `global` | 国家元首、情报机构 | 可感知图谱内所有事实 |
| `local` | 普通决策者（默认） | 仅感知与自身直接相关的事实 |
| `restricted` | 小说人物、情报受限角色 | 仅能看到明确授权给自己的事实 |

---

## 五、场景注册表（Scene Registry）

场景注册表定义每个场景的行动类型和 LLM 提示词前缀，是实现"引擎通用、场景配置化"的核心机制。

```python
SCENE_REGISTRY = {
    "geopolitics": {
        "action_types": ["announce_policy", "impose_sanctions", "form_alliance", "military_action", "negotiate"],
        "agent_prompt_prefix": "你是国际政治中的决策者，你的行动以国家/组织利益为核心驱动，决策考量包括：权力平衡、经济利益、意识形态。",
        "scoring_metrics": ["goal_achievement", "power_stability", "alliance_health", "blackswan_exposure"],
        "weight_modifier_rules": {
            "impose_sanctions": {"subject": {"influence_weight": +0.1}, "object": {"influence_weight": -0.15}},
            "form_alliance":    {"object": {"influence_weight": +0.2}},
            "military_action":  {"subject": {"activity_level": +0.3}, "object": {"activity_level": +0.2}}
        }
    },
    "finance": {
        "action_types": ["buy", "sell", "short", "hold", "announce_earnings", "raise_capital", "default"],
        "agent_prompt_prefix": "你是金融市场参与者，你的行动基于价格信号、持仓成本和市场情绪，决策考量包括：风险收益比、流动性、对手盘行为。",
        "scoring_metrics": ["portfolio_return", "sharpe_ratio", "drawdown", "systemic_risk"],
        "weight_modifier_rules": {
            "raise_capital": {"subject": {"influence_weight": +0.2}},
            "default":       {"subject": {"influence_weight": -0.4}}
        }
    },
    "novel": {
        "action_types": ["confess", "betray", "escape", "reveal_secret", "form_bond", "confront", "sacrifice"],
        "agent_prompt_prefix": "你是小说中的人物，你的行动基于情感状态和隐藏动机，决策考量包括：情感驱动、人物关系、隐藏目标。",
        "scoring_metrics": ["plot_tension", "goal_achievement", "emotional_arc", "narrative_coherence"],
        "weight_modifier_rules": {
            "betray":      {"subject": {"sentiment_bias": -0.3}, "object": {"activity_level": +0.4}},
            "form_bond":   {"subject": {"sentiment_bias": +0.2}, "object": {"sentiment_bias": +0.2}}
        }
    },
    "celebrity": {
        "action_types": ["respond", "deny", "go_silent", "counter_attack", "release_statement", "expose_other"],
        "agent_prompt_prefix": "你是娱乐圈人物，你的行动基于流量和商业利益，决策考量包括：公众形象、商业价值、粉丝情绪。",
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

---

## 六、功能优先级（MVP 范围）

### P0（核心，MVP 必须有）

- [ ] 文档上传 + 要素提取 + 图谱渲染
- [ ] 基于图谱的多 Agent 状态感知推演（事实驱动，图谱状态传递）
- [ ] Agent 三层画像生成（静态 + 行为参数 + 场景扩展，含 `information_access`）
- [ ] 世界线初始化（LLM 生成假设 + 图谱克隆 + 假设事实注入）
- [ ] 多世界线并行推演（至少 2-3 条）
- [ ] 时间滑块查询任意时间点的世界状态
- [ ] 世界线评分与水上/水下展示
- [ ] WebSocket 实时进度推送

### P1（重要，MVP 后第一批）

- [ ] Agent 画像查看与手动编辑（含 `influence_weight` 调整）
- [ ] WeightModifier：Agent 权重随图谱事实动态更新
- [ ] 推演暂停/续跑（断点检查点机制）
- [ ] 用户手动注入外部事件（`ManualEventInjector`）
- [ ] 高影响力事件广播 → 相关 Agent 优先响应
- [ ] 关键节点标记
- [ ] 黑天鹅事件注入（可配置概率）
- [ ] 世界线详情页 + 时间轴事件流
- [ ] 推演报告导出（PDF/Markdown）
- [ ] 场景类型选择（Scene Registry 完整支持）

### P2（增强功能）

- [ ] 外部联网事实接入（新闻/搜索/历史库/定时 API）
- [ ] 世界线对比视图（两条世界线并排对比）
- [ ] 用户自定义场景（自定义 action_types 和 prompt）
- [ ] Agent 权重变化历史曲线（前端可视化）
- [ ] 图谱演化动画
- [ ] 多租户 / 企业账号体系
- [ ] 计费系统

---

## 七、非功能需求

| 指标 | 要求 |
|------|------|
| 推演响应时间 | 10 Agent × 10 时间步，全流程 < 5 分钟 |
| 并发任务 | 支持同时运行 10 个推演任务 |
| 数据隔离 | `group_id` 行级隔离，不同用户数据完全隔离 |
| 实时进度 | WebSocket 每步进度更新延迟 < 1s |
| 可追溯性 | 所有图谱事实均记录来源（extraction/agent_action/injection/bootstrap） |
| 崩溃恢复 | Worker 崩溃后可从最近检查点恢复，最多损失 1 个时间步 |

---

## 八、关键概念定义

| 术语 | 定义 |
|------|------|
| **种子材料** | 用户上传的初始背景资料，是世界状态的原始数据来源 |
| **推演目标** | 用户用自然语言描述的关注焦点，引导要素提取和评估方向 |
| **世界状态** | 某一时间点下知识图谱中所有有效事实的集合 |
| **Agent** | 图谱中的关键人物/组织，具备独立的三层画像和决策能力 |
| **事实** | Agent 行动的输出单元，是一条写入图谱的时序关系边 |
| **信息权限** | Agent 感知图谱的范围（global/local/restricted），模拟信息不对称 |
| **场景注册表** | 定义不同场景的行动类型、LLM 提示词、评估维度和权重修改规则的配置字典 |
| **WeightModifier** | 每步推演后根据新事实动态调整 Agent 行为参数的插件 |
| **EventInjector** | 向图谱注入外部事件的插件接口，支持手动/联网/历史/API 多种来源 |
| **WorldlineBootstrap** | 世界线初始化模块，克隆基础图谱并注入差异化初始假设 |
| **世界线** | 一条从初始状态到目标时间的完整推演路径，与其他世界线平行独立 |
| **关键节点** | 世界线发生分叉的时间点，通常对应重大决策或事件 |
| **黑天鹅事件** | 低概率、高影响的随机外生冲击，触发后当前世界线分叉 |
| **时光机查询** | 查询任意历史时间点的世界状态（已有技术实现） |
| **断点检查点** | 每步推演完成后保存的状态快照，用于崩溃恢复和暂停续跑 |
| **水上/水下** | 对推演结果的直观评价分层，水上 = 正向结果，水下 = 负向结果 |
