"""
意图识别链 - 使用 LLM 进行意图识别

负责：
- 基于 LLM 的意图识别
- 槽位提取
- 置信度评估
"""
from typing import Optional, Dict, Any, List
import json
import re

from app.services.llm_service import LLMService


INTENT_RECOGNITION_PROMPT = """你是一个智能客服意图识别助手。请分析用户输入，识别用户的意图和需要的信息。

用户输入: {user_input}

当前会话上下文:
- 当前主题: {current_topic}
- 当前任务: {current_task}
- 待补槽位: {pending_slot}
- 最近对话: {recent_messages}

请输出 JSON 格式的分析结果:
{{
    "main_intent": "意图类型，可选: refund_execute(退款执行) | refund_consult(退款咨询) | refund_explain(退款解释) | logistics_consult(物流咨询) | presale_consult(售前咨询) | general_question(通用问题)",
    "topic": "主题，可选: refund | logistics | presale | order | unknown",
    "task": "任务类型，可选: execute(执行) | consult(咨询) | explain(解释) | chat(闲聊)",
    "user_goal": "用户目标描述",
    "issue_desc": "问题描述",
    "order_id": "提取的订单号，如果没有则为 null",
    "confidence": "置信度 0-1",
    "need_followup": "是否需要追问 true/false",
    "missing_slots": ["缺失的槽位名称，如 order_id"],
    "is_topic_shift": "是否发生主题切换 true/false",
    "is_task_shift": "是否发生任务切换 true/false",
    "sentiment": "用户情绪: positive(积极) | neutral(中性) | negative(消极)",
    "urgency": "紧急程度: high(高) | medium(中) | low(低)"
}}

识别规则:
1. 退款执行意图关键词: "帮我退款"、"我要退款"、"申请退款"、"发起退款"、"给我退了"
2. 退款咨询意图关键词: "能不能退"、"可以退吗"、"退款规则"、"怎么退"、"多久到账"
3. 退款解释意图关键词: "为什么不能退"、"为什么失败"、"什么原因"、"为什么不能"
4. 物流咨询关键词: "物流"、"快递"、"发货"、"到哪里了"、"什么时候到"
5. 售前咨询关键词: "运费"、"包邮"、"价格"、"优惠"、"活动"

注意:
- 必须输出有效的 JSON 格式
- 如果用户表达模糊，confidence 应该较低
- 如果用户同时提到多个问题，优先识别最紧急/最重要的
"""


class IntentRecognizer:
    """意图识别器 - 基于 LLM"""
    
    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service
    
    async def recognize(
        self,
        user_input: str,
        current_topic: str = "unknown",
        current_task: str = "chat",
        pending_slot: Optional[str] = None,
        recent_messages: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        识别用户意图
        
        Args:
            user_input: 用户输入文本
            current_topic: 当前主题
            current_task: 当前任务
            pending_slot: 待补槽位
            recent_messages: 最近消息历史
            
        Returns:
            意图识别结果字典
        """
        # 构建 prompt
        recent_msgs_str = self._format_recent_messages(recent_messages) if recent_messages else "无"
        
        prompt = INTENT_RECOGNITION_PROMPT.format(
            user_input=user_input,
            current_topic=current_topic,
            current_task=current_task,
            pending_slot=pending_slot or "无",
            recent_messages=recent_msgs_str
        )
        
        try:
            # 调用 LLM
            response = await self.llm_service.chat(
                user_content=prompt,
                username="system",
                context=None
            )
            
            # 解析 JSON 结果
            result = self._parse_llm_response(response.content)
            
            # 后处理：提取订单号
            if not result.get("order_id"):
                result["order_id"] = self._extract_order_id(user_input)
            
            # 后处理：检测用户不接受
            if self._check_rejection(user_input):
                result["sentiment"] = "negative"
                result["user_rejection"] = True
            
            return result
            
        except Exception as e:
            print(f"[IntentRecognizer] LLM 调用失败: {e}")
            # 降级到关键词匹配
            return self._fallback_recognition(user_input)
    
    def _format_recent_messages(self, messages: List[Dict]) -> str:
        """格式化最近消息"""
        formatted = []
        for msg in messages[-4:]:  # 只取最近4条
            role = "用户" if msg.get("role") == "user" else "机器人"
            content = msg.get("content", "")[:50]  # 限制长度
            formatted.append(f"{role}: {content}")
        return "\n".join(formatted)
    
    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """解析 LLM 响应为结构化数据"""
        try:
            # 尝试直接解析 JSON
            result = json.loads(content)
            return self._normalize_result(result)
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    return self._normalize_result(result)
                except json.JSONDecodeError:
                    pass
            
            # 解析失败，返回默认结果
            print(f"[IntentRecognizer] JSON 解析失败: {content[:100]}")
            return self._default_result()
    
    def _normalize_result(self, result: Dict) -> Dict[str, Any]:
        """规范化识别结果"""
        # 确保所有必要字段存在
        normalized = {
            "main_intent": result.get("main_intent", "general_question"),
            "topic": result.get("topic", "unknown"),
            "task": result.get("task", "consult"),
            "user_goal": result.get("user_goal", ""),
            "issue_desc": result.get("issue_desc", ""),
            "order_id": result.get("order_id"),
            "confidence": float(result.get("confidence", 0.5)),
            "need_followup": bool(result.get("need_followup", False)),
            "missing_slots": result.get("missing_slots", []),
            "is_topic_shift": bool(result.get("is_topic_shift", False)),
            "is_task_shift": bool(result.get("is_task_shift", False)),
            "sentiment": result.get("sentiment", "neutral"),
            "urgency": result.get("urgency", "medium"),
            "user_rejection": result.get("user_rejection", False)
        }
        return normalized
    
    def _default_result(self) -> Dict[str, Any]:
        """默认识别结果"""
        return {
            "main_intent": "general_question",
            "topic": "unknown",
            "task": "consult",
            "user_goal": "",
            "issue_desc": "",
            "order_id": None,
            "confidence": 0.3,
            "need_followup": True,
            "missing_slots": [],
            "is_topic_shift": False,
            "is_task_shift": False,
            "sentiment": "neutral",
            "urgency": "medium",
            "user_rejection": False
        }
    
    def _extract_order_id(self, content: str) -> Optional[str]:
        """从内容中提取订单号"""
        # 匹配常见订单号格式：字母 + 数字，8-20 位
        pattern = r'[A-Za-z]?\d{8,20}'
        matches = re.findall(pattern, content)
        if matches:
            return matches[0]
        return None
    
    def _check_rejection(self, content: str) -> bool:
        """检测用户是否不接受"""
        rejection_keywords = [
            "不接受", "不满意", "不行", "不对", "有误", "错误",
            "投诉", "人工", "找客服", "转人工", "不认可", "不合理"
        ]
        content_lower = content.lower()
        return any(kw in content_lower for kw in rejection_keywords)
    
    def _fallback_recognition(self, user_input: str) -> Dict[str, Any]:
        """降级识别 - 关键词匹配"""
        content = user_input.lower()
        
        # 退款执行
        if any(kw in content for kw in ["帮我退款", "我要退款", "申请退款", "发起退款"]):
            return {
                "main_intent": "refund_execute",
                "topic": "refund",
                "task": "execute",
                "confidence": 0.8,
                "need_followup": "order_id" not in content,
                "missing_slots": ["order_id"] if "order_id" not in content else [],
                "order_id": self._extract_order_id(user_input)
            }
        
        # 退款咨询
        if any(kw in content for kw in ["能不能退", "可以退吗", "退款规则", "怎么退"]):
            return {
                "main_intent": "refund_consult",
                "topic": "refund",
                "task": "consult",
                "confidence": 0.8,
                "need_followup": False,
                "missing_slots": []
            }
        
        # 退款解释
        if any(kw in content for kw in ["为什么不能退", "为什么失败", "什么原因"]):
            return {
                "main_intent": "refund_explain",
                "topic": "refund",
                "task": "explain",
                "confidence": 0.8,
                "need_followup": "order_id" not in content,
                "missing_slots": ["order_id"] if "order_id" not in content else [],
                "order_id": self._extract_order_id(user_input)
            }
        
        # 默认
        return self._default_result()
