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
from app.prompts import get_prompt


# 意图识别 Prompt - 从 prompts.md 加载
# 如需修改，请编辑 backend/app/prompts/prompts.md
INTENT_RECOGNITION_PROMPT_TEMPLATE = get_prompt('意图识别') or """你是智能客服系统的意图理解引擎。请深度分析用户输入的语义，准确识别用户真实意图。

用户输入: {user_input}

当前会话状态:
- 当前主题: {current_topic}
- 当前任务: {current_task}
- 待补槽位: {pending_slot}
- 最近对话历史: {recent_messages}

请基于语义理解（而非关键词匹配）分析用户意图，输出 JSON 格式:
{{
    "main_intent": "意图类型: refund_execute(申请退款/办理退款) | refund_consult(咨询退款规则/资格) | refund_explain(询问退款失败原因) | logistics_consult(查询物流/订单状态) | presale_consult(售前咨询) | general_question(其他问题)",
    "topic": "主题: refund(退款) | logistics(物流) | presale(售前) | order(订单) | unknown(未知)",
    "task": "任务: execute(执行操作) | consult(咨询信息) | explain(解释说明) | chat(闲聊)",
    "user_goal": "用户核心诉求的简洁描述",
    "issue_desc": "用户遇到的具体问题",
    "order_id": "提取的订单号(8-20位数字或字母+数字)，没有则为 null",
    "confidence": "置信度 0.0-1.0，基于语义清晰度",
    "need_followup": "是否需要追问 true/false",
    "missing_slots": ["缺失的必要信息，如 order_id"],
    "is_topic_shift": "是否切换了话题主题 true/false",
    "is_task_shift": "是否切换了任务类型 true/false",
    "sentiment": "情绪: positive(积极) | neutral(中性) | negative(消极/不满)",
    "urgency": "紧急程度: high(高/很急) | medium(中) | low(低)"
}}

意图识别指南（基于语义理解）:

1. **refund_execute** - 用户明确想要执行退款操作
   - 语义特征: 有明确的行动诉求，希望立即处理退款
   - 示例: "我要退款"、"帮我退一下"、"这个订单给我退了"、"我想申请退款"

2. **refund_consult** - 用户咨询退款相关信息
   - 语义特征: 询问可能性、规则、流程、时效，不一定立即执行
   - 示例: "这个能退吗"、"退款规则是什么"、"多久能到账"、"怎么退款"

3. **refund_explain** - 用户询问退款失败/被拒的原因
   - 语义特征: 针对已有退款申请的疑问，寻求解释
   - 示例: "为什么不能退"、"退款失败了是什么原因"、"为什么审核不通过"

4. **logistics_consult** - 用户查询订单物流信息
   - 语义特征: 关注物流状态、配送进度、订单查询
   - 示例: "我的货到哪里了"、"帮我查一下订单"、"快递什么时候到"

5. **presale_consult** - 售前咨询
   - 语义特征: 下单前的疑问，了解商品/服务信息
   - 示例: "包邮吗"、"多久发货"、"有什么优惠"、"支持七天无理由吗"

6. **general_question** - 其他问题
   - 无法归入以上类别的通用问题

话题切换检测规则 (is_topic_shift / is_task_shift):
- **true**: 用户明显切换了话题或任务意图，如：问候语("你好"/"在吗")、开始询问新问题、突然改变诉求
- **false**: 用户在继续当前话题，如：补充信息、回答追问、追问细节
- 示例1: 上一轮在问退款，用户突然说"你好" → is_topic_shift=true
- 示例2: 上一轮在问退款，用户说"订单号是12345" → is_topic_shift=false
- 示例3: 机器问"请提供订单号"，用户说"我想咨询别的" → is_topic_shift=true

重要原则:
- **语义优先**: 理解用户真实意图，不要机械匹配关键词
- **上下文感知**: 结合对话历史理解当前输入，检测话题切换
- **订单号提取**: 仔细识别用户提到的订单号（8-20位数字）
- **置信度评估**: 表达越模糊，confidence 越低
- **追问判断**: 如果关键信息缺失（如订单号），设置 need_followup=true

请确保输出有效的 JSON 格式。
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
        
        prompt = INTENT_RECOGNITION_PROMPT_TEMPLATE.format(
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

            # 如果提取到订单号，从 missing_slots 中移除 order_id
            if result.get("order_id") and "order_id" in result.get("missing_slots", []):
                result["missing_slots"] = [slot for slot in result["missing_slots"] if slot != "order_id"]

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
