"""
对话编排服务 - 核心编排中枢

负责：
- 用户消息统一入口
- 当前链路判定
- 补槽判断
- 漂移控制
- 调用 AI / RAG / 规则 / Tool
- 统一生成 reply plan

这是整个系统的核心编排层，协调各服务完成对话处理。
"""
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import uuid
import json

from app.services.memory_service import MemoryService
from app.services.rule_service import RuleService, RuleDecision
from app.services.ticket_service import TicketService
from app.services.tool_service import ToolService
from app.services.session_service import SessionService
from app.services.user_service import UserService
from app.models.session import Session


class OrchestratorService:
    """对话编排服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.memory_service = MemoryService(db)
        self.rule_service = RuleService()
        self.ticket_service = TicketService(db)
        self.tool_service = ToolService(db)
        self.session_service = SessionService(db)
        self.user_service = UserService(db)
    
    async def process_user_message(
        self,
        session_id: str,
        user_content: str,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理用户消息 - 核心入口
        
        流程：
        1. 加载工作记忆
        2. 漂移检测
        3. 历史检索（如需要）
        4. 意图识别（简化版：关键词 + 规则）
        5. 槽位判断
        6. 路由到对应链路
        7. 生成回复
        8. 更新记忆
        """
        trace_id = trace_id or str(uuid.uuid4())
        
        # 1. 加载工作记忆
        working_memory = await self.memory_service.load_working_memory(session_id)
        session = await self.session_service.get_session(session_id)
        
        if not session:
            return self._error_response("会话不存在", trace_id)
        
        # 2. 获取用户信息
        user = await self.user_service.get_user_by_id(session.anonymous_user_id)
        if not user:
            return self._error_response("用户不存在", trace_id)
        
        # 3. 检查是否有 pending_slot（补槽场景）
        pending_slot = working_memory.get("pending_slot")
        current_topic = working_memory.get("current_topic", "unknown")
        current_task = working_memory.get("current_task", "chat")
        
        print(f"[DEBUG] pending_slot={pending_slot}, current_topic={current_topic}, current_task={current_task}")
        
        if pending_slot:
            # 用户正在补槽，使用之前的任务上下文
            # 从用户输入中提取槽位值（如订单号）
            slot_value = user_content.strip()
            
            print(f"[DEBUG] Filling slot: {pending_slot}={slot_value}, topic={current_topic}, task={current_task}")
            
            # 更新工作记忆，清除 pending_slot，设置订单号
            await self.memory_service.update_working_memory(
                session,
                order_id=slot_value if pending_slot == "order_id" else None,
                pending_slot=None
            )
            
            # 继续之前的任务
            intent_result = {
                "topic": current_topic if current_topic != "unknown" else "refund",
                "task": current_task if current_task != "chat" else "execute",
                "missing_slots": [],
                "confidence": 0.9,
                "slot_filled": {pending_slot: slot_value}
            }
            
            print(f"[DEBUG] Intent result: topic={intent_result['topic']}, task={intent_result['task']}")
        else:
            # 正常意图识别
            intent_result = self._simple_intent_recognition(
                user_content,
                working_memory
            )
        
        # 4. 漂移检测
        shift_type = self.memory_service.classify_shift_type(
            working_memory.get("current_topic", "unknown"),
            intent_result.get("topic", "unknown"),
            working_memory.get("current_task", "chat"),
            intent_result.get("task", "chat")
        )
        
        # 强漂移时压缩旧上下文
        if shift_type == "strong":
            # TODO: 触发会话摘要生成
            pass
        
        # 5. 槽位判断（补槽场景已处理，这里不会再触发）
        followup_result = self.rule_service.check_followup_required(
            intent_result.get("missing_slots", []),
            None  # pending_slot 已在上一步处理
        )
        
        if followup_result.decision == RuleDecision.ALLOW:
            # 需要补槽，返回追问消息
            return await self._handle_followup(
                session, user, working_memory,
                followup_result.missing_fields[0] if followup_result.missing_fields else "order_id",
                trace_id
            )
        
        # 6. 路由到对应链路
        task = intent_result.get("task", "consult")
        topic = intent_result.get("topic", "unknown")
        
        if task == "execute" and topic == "refund":
            # 退款执行链路
            return await self._handle_refund_execute(
                session, user, user_content, intent_result, trace_id
            )
        
        elif task == "explain" and topic == "refund":
            # 退款解释链路
            return await self._handle_refund_explain(
                session, user, user_content, intent_result, working_memory, trace_id
            )
        
        elif task == "consult" and topic == "refund":
            # 退款咨询链路
            return await self._handle_refund_consult(
                session, user, user_content, intent_result, trace_id
            )
        
        elif topic in ["logistics", "order"]:
            # 物流/订单咨询
            return await self._handle_logistics_consult(
                session, user, user_content, intent_result, trace_id
            )
        
        elif topic == "presale":
            # 售前咨询
            return await self._handle_presale_consult(
                session, user, user_content, intent_result, trace_id
            )
        
        else:
            # 通用知识答疑
            return await self._handle_knowledge_answer(
                session, user, user_content, intent_result, trace_id
            )
    
    def _simple_intent_recognition(
        self,
        user_content: str,
        working_memory: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        简化版意图识别（Demo 阶段）
        
        基于关键词 + 规则进行意图识别
        TODO: 后续接入 LLM 进行更准确的识别
        """
        content = user_content.lower()
        
        # 退款相关
        refund_execute_keywords = ["帮我退款", "我要退款", "发起退款", "申请退款", "给我退了"]
        refund_explain_keywords = ["为什么不能退", "为什么失败", "为什么不行", "什么原因"]
        refund_consult_keywords = ["能不能退", "可以退吗", "多久到账", "退款规则", "怎么退", "如何退款"]
        
        # 检查执行意图
        for kw in refund_execute_keywords:
            if kw in content:
                return {
                    "topic": "refund",
                    "task": "execute",
                    "intent": "refund_execute",
                    "missing_slots": ["order_id"],
                    "confidence": 0.9
                }
        
        # 检查解释意图
        for kw in refund_explain_keywords:
            if kw in content:
                return {
                    "topic": "refund",
                    "task": "explain",
                    "intent": "refund_explain",
                    "missing_slots": ["order_id"],
                    "confidence": 0.9
                }
        
        # 检查咨询意图
        for kw in refund_consult_keywords:
            if kw in content:
                return {
                    "topic": "refund",
                    "task": "consult",
                    "intent": "refund_consult",
                    "missing_slots": [],
                    "confidence": 0.8
                }
        
        # 物流/订单相关
        logistics_keywords = ["物流", "快递", "发货", "订单", "配送", "什么时候到"]
        for kw in logistics_keywords:
            if kw in content:
                return {
                    "topic": "logistics",
                    "task": "consult",
                    "intent": "logistics_consult",
                    "missing_slots": ["order_id"],
                    "confidence": 0.7
                }
        
        # 售前相关
        presale_keywords = ["运费", "包邮", "多久发货", "配送范围"]
        for kw in presale_keywords:
            if kw in content:
                return {
                    "topic": "presale",
                    "task": "consult",
                    "intent": "presale_consult",
                    "missing_slots": [],
                    "confidence": 0.7
                }
        
        # 默认：知识答疑
        return {
            "topic": "unknown",
            "task": "consult",
            "intent": "general_question",
            "missing_slots": [],
            "confidence": 0.5
        }
    
    async def _handle_followup(
        self,
        session: Session,
        user,
        working_memory: Dict[str, Any],
        pending_slot: str,
        trace_id: str
    ) -> Dict[str, Any]:
        """处理补槽追问"""
        # 更新会话状态
        await self.memory_service.update_working_memory(
            session,
            pending_slot=pending_slot
        )
        
        # 生成追问话术
        if pending_slot == "order_id":
            followup_content = "我先帮你看下，请把订单号发给我。"
        else:
            followup_content = f"为了更好帮你处理，请补充{pending_slot}相关信息。"
        
        return {
            "type": "bot_message",
            "message_id": f"msg_{uuid.uuid4()}",
            "session_id": session.session_id,
            "trace_id": trace_id,
            "payload": {
                "message_type": "bot_followup",
                "content": followup_content,
            },
        }
    
    async def _handle_refund_execute(
        self,
        session: Session,
        user,
        user_content: str,
        intent_result: Dict[str, Any],
        trace_id: str
    ) -> Dict[str, Any]:
        """处理退款执行链路"""
        # 1. 提取订单号（简化：从消息中提取）
        order_id = self._extract_order_id(user_content)
        
        if not order_id:
            # 需要补槽 - 先设置会话状态
            await self.memory_service.update_working_memory(
                session,
                topic="refund",
                task="execute",
                pending_slot="order_id"
            )
            
            print(f"[DEBUG] Set pending_slot: topic=refund, task=execute, pending_slot=order_id")
            
            # 返回追问消息
            return {
                "type": "bot_message",
                "message_id": f"msg_{uuid.uuid4()}",
                "session_id": session.session_id,
                "trace_id": trace_id,
                "payload": {
                    "message_type": "bot_followup",
                    "content": "我先帮你看下，请把订单号发给我。",
                },
            }
        
        # 2. 规则校验
        rule_result = self.rule_service.check_refund_execution_allowed(
            order_id=order_id,
            intent_confirmed=True
        )
        
        if rule_result.decision == RuleDecision.DENY:
            return self._text_response(
                session, trace_id,
                f"抱歉，{rule_result.reason}"
            )
        
        # 3. 调用退款工具
        tool_result = await self.tool_service.apply_refund(
            session_id=session.session_id,
            anonymous_user_id=session.anonymous_user_id,
            order_id=order_id,
            reason="用户申请退款"
        )
        
        # 4. 更新会话状态
        await self.memory_service.update_working_memory(
            session,
            topic="refund",
            task="execute",
            order_id=order_id,
            tool_status=tool_result.status
        )
        
        # 5. 返回卡片消息
        card_payload = self.tool_service.result_to_card_payload(
            tool_result, session.session_id
        )
        
        return {
            "type": "bot_message",
            "message_id": f"msg_{uuid.uuid4()}",
            "session_id": session.session_id,
            "trace_id": trace_id,
            "payload": card_payload,
        }
    
    async def _handle_refund_explain(
        self,
        session: Session,
        user,
        user_content: str,
        intent_result: Dict[str, Any],
        working_memory: Dict[str, Any],
        trace_id: str
    ) -> Dict[str, Any]:
        """处理退款解释链路"""
        # 1. 提取订单号
        order_id = self._extract_order_id(user_content) or working_memory.get("current_order_id")
        
        if not order_id:
            return await self._handle_followup(
                session, user, working_memory,
                "order_id",
                trace_id
            )
        
        # 2. 查询主题记忆
        topic_memory = await self.memory_service.get_topic_memory(
            session.anonymous_user_id, order_id
        )
        
        # 3. 生成解释
        if topic_memory and topic_memory.last_conclusion:
            explain_content = (
                f"关于订单{order_id}的退款问题：\n"
                f"{topic_memory.last_conclusion}\n\n"
                f"如还有其他疑问，可以继续问我。"
            )
        else:
            # 模拟解释
            explain_content = (
                f"关于订单{order_id}的退款问题，当前不满足退款条件。\n"
                f"可能原因：超过售后申请时效、商品影响二次销售等。\n\n"
                f"如需进一步处理，可以提交跟进请求。"
            )
        
        # 4. 更新主题记忆
        await self.memory_service.upsert_topic_memory(
            session.anonymous_user_id, order_id,
            topic="refund",
            task="explain",
            last_status="not_allowed",
            last_conclusion=explain_content,
        )
        
        return self._text_response(
            session, trace_id,
            explain_content,
            message_type="bot_explain"
        )
    
    async def _handle_refund_consult(
        self,
        session: Session,
        user,
        user_content: str,
        intent_result: Dict[str, Any],
        trace_id: str
    ) -> Dict[str, Any]:
        """处理退款咨询链路"""
        # 1. 判断是否是个单资格咨询
        order_id = self._extract_order_id(user_content)
        
        if order_id:
            # 个单资格咨询
            topic_memory = await self.memory_service.get_topic_memory(
                session.anonymous_user_id, order_id
            )
            
            if topic_memory and topic_memory.last_conclusion:
                consult_content = (
                    f"关于订单{order_id}的退款资格：\n"
                    f"{topic_memory.last_conclusion}"
                )
            else:
                consult_content = (
                    f"订单{order_id}的退款资格需要核实订单状态。\n"
                    f"通常情况下，7 天内可申请退款，商品需保持完好。"
                )
        else:
            # 纯规则咨询
            consult_content = (
                "退款规则说明：\n"
                "1. 签收后 7 天内可申请退款\n"
                "2. 商品需保持完好，不影响二次销售\n"
                "3. 退款申请后 1-3 个工作日处理\n"
                "4. 退款原路返回，到账时间视银行而定\n\n"
                "如有具体订单问题，可以提供订单号帮你查询。"
            )
        
        return self._text_response(
            session, trace_id,
            consult_content,
            message_type="bot_knowledge"
        )
    
    async def _handle_logistics_consult(
        self,
        session: Session,
        user,
        user_content: str,
        intent_result: Dict[str, Any],
        trace_id: str
    ) -> Dict[str, Any]:
        """处理物流咨询链路"""
        order_id = self._extract_order_id(user_content)
        
        if not order_id:
            return await self._handle_followup(
                session, user,
                await self.memory_service.load_working_memory(session.session_id),
                "order_id",
                trace_id
            )
        
        # 模拟物流查询
        logistics_content = (
            f"订单{order_id}的物流信息：\n"
            f"已发货，运输中...\n"
            f"预计 2-3 天送达。\n\n"
            f"如需详细物流轨迹，请查看订单详情页。"
        )
        
        return self._text_response(
            session, trace_id,
            logistics_content,
            message_type="bot_knowledge"
        )
    
    async def _handle_presale_consult(
        self,
        session: Session,
        user,
        user_content: str,
        intent_result: Dict[str, Any],
        trace_id: str
    ) -> Dict[str, Any]:
        """处理售前咨询链路"""
        # 售前问题一般不需要订单号
        presale_content = (
            "售前服务说明：\n"
            "1. 全场满 99 元包邮\n"
            "2. 一般下单后 24 小时内发货\n"
            "3. 支持 7 天无理由退换\n"
            "4. 质量问题我们承担运费\n\n"
            "如有其他问题，欢迎继续咨询。"
        )
        
        return self._text_response(
            session, trace_id,
            presale_content,
            message_type="bot_knowledge"
        )
    
    async def _handle_knowledge_answer(
        self,
        session: Session,
        user,
        user_content: str,
        intent_result: Dict[str, Any],
        trace_id: str
    ) -> Dict[str, Any]:
        """处理通用知识答疑链路"""
        # TODO: 后续接入 RAG 服务
        # 暂时返回一个通用回复
        answer_content = (
            f"收到你的问题：{user_content}\n\n"
            "我正在学习中，稍后会给你更准确的回复。\n"
            "你也可以尝试问我：\n"
            "- 退款多久到账\n"
            "- 运费怎么算\n"
            "- 订单物流查询"
        )
        
        return self._text_response(
            session, trace_id,
            answer_content,
            message_type="bot_text"
        )
    
    def _extract_order_id(self, content: str) -> Optional[str]:
        """
        从内容中提取订单号
        
        Demo 简化：查找类似订单号的字符串
        """
        import re
        # 匹配常见订单号格式：字母 + 数字，8-20 位
        pattern = r'[A-Za-z]?\d{8,20}'
        matches = re.findall(pattern, content)
        
        if matches:
            return matches[0]
        return None
    
    def _text_response(
        self,
        session: Session,
        trace_id: str,
        content: str,
        message_type: str = "bot_text"
    ) -> Dict[str, Any]:
        """生成文本回复"""
        return {
            "type": "bot_message",
            "message_id": f"msg_{uuid.uuid4()}",
            "session_id": session.session_id,
            "trace_id": trace_id,
            "payload": {
                "message_type": message_type,
                "content": content,
            },
        }
    
    def _error_response(
        self,
        error_message: str,
        trace_id: str
    ) -> Dict[str, Any]:
        """生成错误回复"""
        return {
            "type": "bot_message",
            "message_id": f"msg_{uuid.uuid4()}",
            "session_id": "",
            "trace_id": trace_id,
            "payload": {
                "message_type": "error_message",
                "content": f"系统错误：{error_message}",
            },
        }
