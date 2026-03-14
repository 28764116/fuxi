"""Scene registry for simulation scenarios.

每个场景配置包含：
  - action_types: Agent 可执行的行动类型列表
  - prompt_prefix: 注入 LLM prompt 的场景背景前缀
  - scoring_metrics: 评分维度及权重
  - weight_modifier_rules: 影响力权重修正规则（MVP 暂不执行，预留结构）
"""

from typing import Any

# ---------------------------------------------------------------------------
# 场景配置字典
# key = scene_type 字符串（与 SimTask.scene_type 对应）
# ---------------------------------------------------------------------------

SCENE_REGISTRY: dict[str, dict[str, Any]] = {

    # ------------------------------------------------------------------
    # 1. 地缘政治 / 国际关系
    # ------------------------------------------------------------------
    "geopolitics": {
        "display_name": "地缘政治",
        "prompt_prefix": (
            "你正在参与一场地缘政治博弈推演。"
            "各方行为体代表国家、国际组织或重要政治力量，"
            "决策受国家利益、外交惯例与国内政治约束。"
            "请基于你的立场和信息视野做出合理决策。"
        ),
        "action_types": [
            "diplomatic_statement",   # 外交声明
            "economic_sanction",      # 经济制裁
            "military_posture",       # 军事姿态调整
            "alliance_negotiation",   # 联盟/协议谈判
            "information_operation",  # 舆论/信息战
            "concession",             # 让步/妥协
            "escalation",             # 升级对抗
            "observe",                # 观望，暂不行动
        ],
        "scoring_metrics": {
            "stability":        {"weight": 0.30, "desc": "地区稳定性"},
            "power_balance":    {"weight": 0.25, "desc": "大国力量均衡度"},
            "economic_impact":  {"weight": 0.25, "desc": "经济连锁影响"},
            "escalation_risk":  {"weight": 0.20, "desc": "冲突升级风险（逆向）"},
        },
        "weight_modifier_rules": [
            # MVP 不执行，仅预留结构
            # {"condition": "action_type == 'escalation'", "modifier": 1.2, "target": "influence_weight"},
        ],
    },

    # ------------------------------------------------------------------
    # 2. 金融市场 / 宏观经济
    # ------------------------------------------------------------------
    "finance": {
        "display_name": "金融市场",
        "prompt_prefix": (
            "你正在参与一场金融市场压力测试推演。"
            "参与者包括中央银行、大型金融机构、主权基金与监管机构，"
            "各方基于私有信息与市场信号做出资产配置和政策决定。"
        ),
        "action_types": [
            "buy",                  # 增持/买入
            "sell",                 # 减持/卖出
            "hold",                 # 持仓观望
            "policy_announcement",  # 政策声明（央行/监管）
            "rate_adjustment",      # 利率调整
            "market_intervention",  # 市场干预
            "hedge",                # 对冲操作
            "default",              # 违约/爆雷
        ],
        "scoring_metrics": {
            "market_stability":   {"weight": 0.30, "desc": "市场稳定性"},
            "systemic_risk":      {"weight": 0.30, "desc": "系统性风险（逆向）"},
            "liquidity":          {"weight": 0.20, "desc": "流动性充裕度"},
            "policy_credibility": {"weight": 0.20, "desc": "政策公信力"},
        },
        "weight_modifier_rules": [],
    },

    # ------------------------------------------------------------------
    # 3. 供应链 / 产业
    # ------------------------------------------------------------------
    "supply_chain": {
        "display_name": "供应链博弈",
        "prompt_prefix": (
            "你正在参与一场全球供应链压力推演。"
            "参与者包括原材料供应商、制造商、物流商与终端客户，"
            "需在成本、交期与风险之间进行权衡。"
        ),
        "action_types": [
            "source_alternative",   # 寻找替代供应商
            "stockpile",            # 战略备货
            "reduce_capacity",      # 缩减产能
            "expand_capacity",      # 扩大产能
            "renegotiate_contract", # 重新谈判合同
            "exit_market",          # 退出特定市场
            "form_consortium",      # 组建联盟/集采
            "observe",              # 观望
        ],
        "scoring_metrics": {
            "supply_continuity":  {"weight": 0.35, "desc": "供应连续性"},
            "cost_efficiency":    {"weight": 0.25, "desc": "成本效率"},
            "resilience":         {"weight": 0.25, "desc": "抗冲击韧性"},
            "concentration_risk": {"weight": 0.15, "desc": "集中度风险（逆向）"},
        },
        "weight_modifier_rules": [],
    },

    # ------------------------------------------------------------------
    # 4. 公众舆论 / 社会事件
    # ------------------------------------------------------------------
    "public_opinion": {
        "display_name": "舆论演化",
        "prompt_prefix": (
            "你正在参与一场舆论演化推演。"
            "参与者包括媒体机构、意见领袖、政府发言人与普通公众，"
            "信息在社交网络中传播并影响公众认知。"
        ),
        "action_types": [
            "publish_content",      # 发布内容
            "amplify",              # 转发/放大
            "rebut",                # 反驳/辟谣
            "silence",              # 沉默/撤稿
            "frame_narrative",      # 重新建构叙事
            "leak_information",     # 爆料/泄露
            "mobilize_followers",   # 动员支持者
            "observe",              # 观望
        ],
        "scoring_metrics": {
            "narrative_coherence": {"weight": 0.30, "desc": "主流叙事连贯性"},
            "trust_level":         {"weight": 0.30, "desc": "公众信任度"},
            "polarization":        {"weight": 0.20, "desc": "社会极化程度（逆向）"},
            "information_quality": {"weight": 0.20, "desc": "信息质量"},
        },
        "weight_modifier_rules": [],
    },

    # ------------------------------------------------------------------
    # 5. 企业竞争 / 商业博弈
    # ------------------------------------------------------------------
    "business": {
        "display_name": "商业竞争",
        "prompt_prefix": (
            "你正在参与一场商业竞争博弈推演。"
            "参与者包括竞争企业、投资机构、监管方与关键客户，"
            "各方基于市场信号、竞争压力与资源约束做出商业决策。"
        ),
        "action_types": [
            "price_cut",            # 降价竞争
            "product_launch",       # 新品/新服务发布
            "acquire",              # 并购
            "partner",              # 结盟合作
            "lobby_regulator",      # 游说监管
            "invest_rd",            # 加大研发投入
            "layoff",               # 裁员收缩
            "observe",              # 观望
        ],
        "scoring_metrics": {
            "market_share":       {"weight": 0.30, "desc": "市场份额变化"},
            "innovation_pace":    {"weight": 0.25, "desc": "创新速度"},
            "financial_health":   {"weight": 0.25, "desc": "财务健康度"},
            "regulatory_risk":    {"weight": 0.20, "desc": "监管风险（逆向）"},
        },
        "weight_modifier_rules": [],
    },
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def get_scene(scene_type: str) -> dict[str, Any]:
    """获取场景配置，未知场景返回 geopolitics 作为默认值。"""
    return SCENE_REGISTRY.get(scene_type, SCENE_REGISTRY["geopolitics"])


def list_scenes() -> list[dict[str, str]]:
    """返回所有场景的简要信息（供前端选择用）。"""
    return [
        {"scene_type": k, "display_name": v["display_name"]}
        for k, v in SCENE_REGISTRY.items()
    ]


def get_action_types(scene_type: str) -> list[str]:
    """获取场景的合法 action 类型列表。"""
    return get_scene(scene_type)["action_types"]


def get_scoring_metrics(scene_type: str) -> dict[str, dict]:
    """获取场景的评分维度配置。"""
    return get_scene(scene_type)["scoring_metrics"]


def get_prompt_prefix(scene_type: str) -> str:
    """获取场景的 prompt 前缀。"""
    return get_scene(scene_type)["prompt_prefix"]
