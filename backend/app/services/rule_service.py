"""
规则服务 - 业务约束判断

负责：
- 是否需订单号
- 是否可执行 Tool
- 是否该兜底工单
- 退款资格判断

规则层不直接负责自然语言回复，只做业务约束判定。
"""
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class RuleDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEED_MORE_INFO = "need_more_info"


@dataclass
class RuleResult:
    """规则判断结果"""
    decision: RuleDecision
    reason: str
    missing_fields: list = None
    extra_context: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.missing_fields is None:
            self.missing_fields = []
        if self.extra_context is None:
            self.extra_context = {}


class RuleService:
    """规则判断服务"""
    
    # ========== 订单号规则 ==========
    
    def check_order_id_required(
        self,
        topic: str,
        task: str,
        issue_type: Optional[str] = None
    ) -> RuleResult:
        """
        判断是否需要订单号
        
        规则：
        - 售前问题：否
        - 退款执行：是
        - 规则解释（个单相关）：是
        - 物流/订单咨询：是
        """
        # 售前咨询不需要订单号
        if topic == "presale":
            return RuleResult(
                decision=RuleDecision.DENY,
                reason="售前咨询不需要订单号"
            )
        
        # 退款执行必须有订单号
        if task == "execute" and topic == "refund":
            return RuleResult(
                decision=RuleDecision.ALLOW,
                reason="退款执行需要订单号"
            )
        
        # 物流/订单咨询需要订单号
        if topic in ["logistics", "order"]:
            return RuleResult(
                decision=RuleDecision.ALLOW,
                reason="订单/物流咨询需要订单号"
            )
        
        # 售后相关一般需要订单号
        if topic in ["aftersale", "refund"]:
            return RuleResult(
                decision=RuleDecision.ALLOW,
                reason="售后咨询需要订单号"
            )
        
        # 默认不需要
        return RuleResult(
            decision=RuleDecision.DENY,
            reason="当前场景不需要订单号"
        )
    
    # ========== 退款执行规则 ==========
    
    def check_refund_execution_allowed(
        self,
        order_id: Optional[str],
        intent_confirmed: bool,
        topic_memory: Optional[Dict[str, Any]] = None
    ) -> RuleResult:
        """
        判断是否允许执行退款
        
        必须同时满足：
        1. 订单号有效
        2. 用户执行意图明确
        3. 资格校验通过（基于 topic_memory）
        """
        # 1. 检查订单号
        if not order_id:
            return RuleResult(
                decision=RuleDecision.NEED_MORE_INFO,
                reason="缺少订单号",
                missing_fields=["order_id"]
            )
        
        # 2. 检查意图确认
        if not intent_confirmed:
            return RuleResult(
                decision=RuleDecision.NEED_MORE_INFO,
                reason="用户执行意图未确认",
                missing_fields=["intent_confirmation"]
            )
        
        # 3. 检查历史状态（如有 topic_memory）
        if topic_memory:
            last_status = topic_memory.get("last_status")
            
            # 如果上次明确不可退款，需要额外确认
            if last_status == "not_allowed":
                return RuleResult(
                    decision=RuleDecision.DENY,
                    reason="该订单上次已判定不可退款",
                    extra_context={"last_status": last_status}
                )
        
        # 通过检查
        return RuleResult(
            decision=RuleDecision.ALLOW,
            reason="满足退款执行条件"
        )
    
    # ========== 退款资格判断规则 ==========
    
    def check_refund_eligibility(
        self,
        order_id: str,
        order_status: Optional[str] = None,
        days_since_delivery: Optional[int] = None
    ) -> RuleResult:
        """
        判断订单是否满足退款资格
        
        Demo 阶段简化规则：
        - 订单存在
        - 订单状态允许退款
        - 未超过售后有效期（7 天）
        """
        # 模拟订单状态检查
        # TODO: 实际场景应查询订单服务
        
        if order_status == "completed":
            # 已完成订单，检查时效
            if days_since_delivery is not None:
                if days_since_delivery > 7:
                    return RuleResult(
                        decision=RuleDecision.DENY,
                        reason="已超过 7 天售后申请时效",
                        extra_context={
                            "days_since_delivery": days_since_delivery,
                            "max_days": 7
                        }
                    )
        
        # 默认允许（Demo 阶段）
        return RuleResult(
            decision=RuleDecision.ALLOW,
            reason="满足退款资格"
        )
    
    # ========== 工单兜底规则 ==========
    
    def check_ticket_fallback_required(
        self,
        consecutive_failures: int = 0,
        knowledge_hit: bool = True,
        tool_failed: bool = False,
        user_not_accept: bool = False,
        topic_shift_confused: bool = False
    ) -> RuleResult:
        """
        判断是否需要工单兜底
        
        触发条件：
        - 连续补槽失败 >= 3 轮
        - 知识未命中且无法收敛
        - 工具失败
        - 用户不接受当前结果
        - 问题超边界
        """
        reasons = []
        
        # 连续失败
        if consecutive_failures >= 3:
            reasons.append(f"连续{consecutive_failures}轮处理失败")
        
        # 知识未命中
        if not knowledge_hit:
            reasons.append("知识库未命中")
        
        # 工具失败
        if tool_failed:
            reasons.append("工具调用失败")
        
        # 用户不接受
        if user_not_accept:
            reasons.append("用户不接受当前结果")
        
        # 有任意原因则触发工单
        if reasons:
            return RuleResult(
                decision=RuleDecision.ALLOW,
                reason="；".join(reasons),
                extra_context={
                    "consecutive_failures": consecutive_failures,
                    "knowledge_hit": knowledge_hit,
                    "tool_failed": tool_failed,
                    "user_not_accept": user_not_accept
                }
            )
        
        # 不需要工单
        return RuleResult(
            decision=RuleDecision.DENY,
            reason="当前不需要工单兜底"
        )
    
    # ========== 意图判断规则 ==========
    
    def classify_refund_intent(
        self,
        user_input: str,
        main_intent: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        区分退款咨询 vs 退款执行
        
        返回：(intent_type, confidence_reason)
        
        咨询特征词：
        - 能不能退、可以提现吗、多久到账、规则是什么
        
        执行特征词：
        - 帮我退款、我要退款、发起退款、给我退了
        """
        # 执行特征词（优先级高）
        execute_keywords = [
            "帮我退款", "我要退款", "发起退款", "申请退款",
            "给我退了", "立即退款", "马上退款", "办理退款"
        ]
        
        # 咨询特征词
        consult_keywords = [
            "能不能退", "可以退吗", "多久到账", "退款规则",
            "怎么退", "如何退款", "退款流程", "退款时效"
        ]
        
        # 解释特征词
        explain_keywords = [
            "为什么不能退", "为什么失败", "为什么不行",
            "什么原因", "怎么回事"
        ]
        
        # 检查执行意图
        for kw in execute_keywords:
            if kw in user_input:
                return ("refund_execute", f"命中执行关键词：{kw}")
        
        # 检查解释意图
        for kw in explain_keywords:
            if kw in user_input:
                return ("refund_explain", f"命中解释关键词：{kw}")
        
        # 检查咨询意图
        for kw in consult_keywords:
            if kw in user_input:
                return ("refund_consult", f"命中咨询关键词：{kw}")
        
        # 如果已有模型识别结果，参考
        if main_intent == "refund_execute":
            return ("refund_execute", "模型识别为执行意图")
        
        if main_intent == "refund_explain":
            return ("refund_explain", "模型识别为解释意图")
        
        # 默认按咨询处理（保守策略）
        return ("refund_consult", "默认按咨询处理")
    
    # ========== 追问规则 ==========
    
    def check_followup_required(
        self,
        missing_slots: list,
        current_pending_slot: Optional[str] = None
    ) -> RuleResult:
        """
        判断是否需要追问补槽
        
        规则：
        - 有缺失槽位则需要追问
        - 一次只追一个关键字段
        - 已有 pending_slot 时优先补全
        """
        if not missing_slots and not current_pending_slot:
            return RuleResult(
                decision=RuleDecision.DENY,
                reason="无需补槽"
            )
        
        # 有待补槽位
        if current_pending_slot:
            return RuleResult(
                decision=RuleDecision.ALLOW,
                reason=f"待补槽位：{current_pending_slot}",
                missing_fields=[current_pending_slot]
            )
        
        # 有缺失槽位
        if missing_slots:
            # 只返回第一个（一次只追一个）
            return RuleResult(
                decision=RuleDecision.ALLOW,
                reason=f"缺失槽位：{missing_slots[0]}",
                missing_fields=[missing_slots[0]]
            )
        
        return RuleResult(
            decision=RuleDecision.DENY,
            reason="无需补槽"
        )
    
    # ========== 售前/售后区分规则 ==========
    
    def classify_presale_aftersale(
        self,
        topic: str,
        has_order_id: bool = False,
        issue_type: Optional[str] = None
    ) -> str:
        """
        区分售前 vs 售后
        
        规则：
        - 有订单号 → 售后
        - 运费/发货/规则咨询 → 售前
        - 退款/物流/订单问题 → 售后
        """
        # 有订单号一般是售后
        if has_order_id:
            return "aftersale"
        
        # 明确的主题
        if topic == "presale":
            return "presale"
        
        if topic in ["refund", "logistics", "aftersale"]:
            return "aftersale"
        
        # 售前典型问题
        presale_keywords = ["运费", "发货", "多久发货", "包邮", "配送范围"]
        if issue_type:
            for kw in presale_keywords:
                if kw in issue_type:
                    return "presale"
        
        # 默认按售前处理（保守策略）
        return "presale"
