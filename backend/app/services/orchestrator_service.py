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
from sqlalchemy import select
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import uuid
import json

from app.services.memory_service import MemoryService
from app.models.message import Message
from app.services.rule_service import RuleService, RuleDecision
from app.services.ticket_service import TicketService
from app.services.tool_service import ToolService
from app.services.session_service import SessionService
from app.services.user_service import UserService
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.chains.intent_chain import IntentRecognizer
from app.models.session import Session


class OrchestratorService:
    """对话编排服务"""
    
    def __init__(self, db: AsyncSession, tool_service=None):
        self.db = db
        self.memory_service = MemoryService(db)
        self.rule_service = RuleService()
        self.ticket_service = TicketService(db)
        self.tool_service = tool_service if tool_service else ToolService(db)
        self.session_service = SessionService(db)
        self.user_service = UserService(db)
        self.llm_service = LLMService()
        self.rag_service = RAGService()
        self.intent_recognizer = IntentRecognizer(self.llm_service)
    
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

        print(f"[DEBUG] === New Message ===")
        print(f"[DEBUG] user_content: {user_content}")
        print(f"[DEBUG] working_memory: {working_memory}")
        
        if not session:
            return self._error_response("会话不存在", trace_id)
        
        # 2. 获取用户信息
        user = await self.user_service.get_user_by_id(session.anonymous_user_id)
        if not user:
            return self._error_response("用户不存在", trace_id)
        
        # 3. 获取当前会话状态
        pending_slot = working_memory.get("pending_slot")
        current_topic = working_memory.get("current_topic", "unknown")
        current_task = working_memory.get("current_task", "chat")

        print(f"[DEBUG] pending_slot={pending_slot}, current_topic={current_topic}, current_task={current_task}")

        # 4. 先进行 LLM 意图识别（无论是否有 pending_slot，都需要判断用户是否切换话题）
        intent_result = None
        try:
            llm_intent = await self.intent_recognizer.recognize(
                user_input=user_content,
                current_topic=current_topic,
                current_task=current_task,
                pending_slot=pending_slot,
                recent_messages=working_memory.get("recent_messages", [])
            )

            # 转换为内部格式
            intent_result = {
                "topic": llm_intent.get("topic", "unknown"),
                "task": llm_intent.get("task", "consult"),
                "intent": llm_intent.get("main_intent", "general_question"),
                "missing_slots": llm_intent.get("missing_slots", []),
                "confidence": llm_intent.get("confidence", 0.5),
                "order_id": llm_intent.get("order_id"),
                "is_topic_shift": llm_intent.get("is_topic_shift", False),
                "is_task_shift": llm_intent.get("is_task_shift", False),
                "user_rejection": llm_intent.get("user_rejection", False)
            }

            print(f"[DEBUG] LLM intent: topic={intent_result['topic']}, task={intent_result['task']}, "
                  f"is_topic_shift={intent_result['is_topic_shift']}, is_task_shift={intent_result['is_task_shift']}")

        except Exception as e:
            print(f"[ERROR] LLM 意图识别失败: {e}")
            # LLM 失败时返回通用咨询意图
            intent_result = {
                "topic": "unknown",
                "task": "consult",
                "intent": "general_question",
                "missing_slots": [],
                "confidence": 0.3,
                "order_id": self._extract_order_id(user_content),
                "is_topic_shift": False,
                "is_task_shift": False,
                "user_rejection": False
            }

        # 5. 检查是否有 pending_slot 且用户没有切换话题
        if pending_slot and not intent_result.get("is_topic_shift") and not intent_result.get("is_task_shift"):
            # 用户正在补槽，使用之前的任务上下文
            # 从用户输入中提取槽位值（如订单号）
            slot_value = user_content.strip()

            print(f"[DEBUG] Filling slot: {pending_slot}={slot_value}, topic={current_topic}, task={current_task}")

            # 更新工作记忆，清除 pending_slot，保存订单号、topic 和 task
            await self.memory_service.update_working_memory(
                session,
                topic=current_topic if current_topic != "unknown" else "refund",
                task=current_task if current_task != "chat" else "execute",
                order_id=slot_value if pending_slot == "order_id" else None,
                pending_slot=""  # 使用空字符串清除 pending_slot
            )

            # 继续之前的任务，但保留已提取的槽位信息
            intent_result = {
                "topic": current_topic if current_topic != "unknown" else "refund",
                "task": current_task if current_task != "chat" else "execute",
                "missing_slots": [],
                "confidence": 0.9,
                "slot_filled": {pending_slot: slot_value},
                "order_id": slot_value if pending_slot == "order_id" else intent_result.get("order_id")
            }

            print(f"[DEBUG] Slot filled, intent result: topic={intent_result['topic']}, task={intent_result['task']}")
        else:
            # 无 pending_slot，或用户切换了话题
            if pending_slot and (intent_result.get("is_topic_shift") or intent_result.get("is_task_shift")):
                print(f"[DEBUG] Topic/task shift detected, clearing pending_slot")
                # 清除 pending_slot，让用户的新意图生效
                await self.memory_service.update_working_memory(
                    session,
                    pending_slot=""
                )

            # 如果 LLM 识别到订单号，更新会话
            if intent_result.get("order_id") and not session.current_order_id:
                await self.memory_service.update_working_memory(
                    session,
                    order_id=intent_result["order_id"]
                )

            # 检查是否需要触发工单兜底
            should_ticket, ticket_reason = await self._should_trigger_ticket(
                session, working_memory, user_content, intent_result.get("confidence", 0.5)
            )

            if should_ticket:
                # 生成工单摘要
                username = user.username if user else "用户"
                ticket_summary = f"用户{username}咨询：{user_content}。触发原因：{ticket_reason}"

                try:
                    ticket_result = await self.ticket_service.create_ticket(
                        session_id=session.session_id,
                        anonymous_user_id=session.anonymous_user_id,
                        summary=ticket_summary,
                        fallback_reason=ticket_reason
                    )

                    if ticket_result:
                        return self._ticket_card_response(
                            session, trace_id,
                            title="建议提交跟进请求",
                            description="当前问题机器人暂时无法直接处理，已为你记录跟进请求。",
                            summary=ticket_summary
                        )
                except Exception as e:
                    print(f"[ERROR] Failed to create ticket: {e}")
        
        # 4. 漂移检测
        shift_type = self.memory_service.classify_shift_type(
            working_memory.get("current_topic", "unknown"),
            intent_result.get("topic", "unknown"),
            working_memory.get("current_task", "chat"),
            intent_result.get("task", "chat")
        )
        
        # 强漂移或消息过多时压缩上下文
        if shift_type == "strong" or len(working_memory.get("recent_messages", [])) > 10:
            # 触发上下文压缩
            compressed_summary = await self.memory_service.compress_context_if_needed(
                session,
                message_count_threshold=10,
                token_estimate_threshold=5000
            )
            
            if compressed_summary:
                # 重新加载压缩后的工作记忆
                working_memory = await self.memory_service.get_compressed_working_memory(
                    session_id,
                    max_recent_messages=4
                )
                print(f"[DEBUG] 上下文已压缩，使用摘要: {compressed_summary.summary_text[:50]}...")
        
        # 5. 槽位判断（补槽场景已处理，这里不会再触发）
        followup_result = self.rule_service.check_followup_required(
            intent_result.get("missing_slots", []),
            None  # pending_slot 已在上一步处理
        )
        
        if followup_result.decision == RuleDecision.ALLOW:
            # 需要补槽，返回追问消息
            # 同时保存 topic 和 task，以便补槽时能正确恢复上下文
            followup_topic = intent_result.get("topic", "unknown")
            followup_task = intent_result.get("task", "chat")
            return await self._handle_followup(
                session, user, working_memory,
                followup_result.missing_fields[0] if followup_result.missing_fields else "order_id",
                trace_id,
                topic=followup_topic,
                task=followup_task
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
            # 检查是否是进度查询（当存在活跃任务时）
            active_order_id = session.current_order_id or working_memory.get('current_order_id')
            tool_status = session.tool_status or working_memory.get('tool_status')

            # 如果用户问进度相关，且有活跃订单，优先处理为进度查询
            if active_order_id and self._is_progress_query(user_content):
                return await self._handle_progress_query(
                    session, user, active_order_id, tool_status, trace_id
                )

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
            # 检查是否是进度查询（当存在活跃任务时）
            active_order_id = session.current_order_id or working_memory.get('current_order_id')
            tool_status = session.tool_status or working_memory.get('tool_status')

            print(f"[DEBUG] Checking progress query: order_id={active_order_id}, tool_status={tool_status}, is_progress={self._is_progress_query(user_content)}")

            # 如果用户问进度相关，且有活跃订单，处理为进度查询
            if active_order_id and self._is_progress_query(user_content):
                print(f"[DEBUG] Routing to progress query handler")
                return await self._handle_progress_query(
                    session, user, active_order_id, tool_status, trace_id
                )

            # 通用知识答疑
            return await self._handle_knowledge_answer(
                session, user, user_content, intent_result, working_memory, trace_id
            )
    
    async def _handle_followup(
        self,
        session: Session,
        user,
        working_memory: Dict[str, Any],
        pending_slot: str,
        trace_id: str,
        topic: Optional[str] = None,
        task: Optional[str] = None
    ) -> Dict[str, Any]:
        """处理补槽追问"""
        # 更新会话状态，保存 pending_slot、topic 和 task
        await self.memory_service.update_working_memory(
            session,
            topic=topic if topic and topic != "unknown" else None,
            task=task if task and task != "chat" else None,
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
        # 1. 提取订单号（优先从 slot_filled 获取，其次从消息中提取）
        slot_filled = intent_result.get("slot_filled", {})
        extracted_from_content = self._extract_order_id(user_content)
        order_id = slot_filled.get("order_id") or extracted_from_content or session.current_order_id

        print(f"[DEBUG] _handle_refund_execute: slot_filled={slot_filled}, extracted={extracted_from_content}, session_order_id={session.current_order_id}, final_order_id={order_id}")

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
            # 规则校验不通过，返回不可执行卡片
            return self._tool_result_response(
                session, trace_id,
                title="当前暂不支持退款",
                description=rule_result.reason or "该订单当前不满足退款条件，可能原因：超过售后申请时效、商品影响二次销售等。",
                status="not_allowed",
                actions=[
                    {"label": "了解退款规则", "action": "show_refund_rules"},
                    {"label": "提交跟进请求", "action": "create_ticket", "reason": "退款申请被拒绝"}
                ]
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

        # 5. 根据工具结果返回不同格式的卡片
        username = user.username if user else "用户"
        
        if tool_result.status == "success":
            # 退款成功
            return self._tool_result_response(
                session, trace_id,
                title="退款申请已提交",
                description=f"订单 {order_id} 的退款申请已提交成功，预计 1-3 个工作日到账。退款将原路返回至您的支付账户。",
                status="success",
                actions=[
                    {"label": "查询其他订单", "action": "query_another"},
                    {"label": "继续咨询", "action": "continue_chat"}
                ]
            )
        elif tool_result.status == "need_more_info":
            # 需要更多信息
            return self._tool_result_response(
                session, trace_id,
                title="需要补充信息",
                description=tool_result.message or "退款申请需要补充相关信息，请提供完整的退款原因。",
                status="need_more_info",
                actions=[
                    {"label": "补充信息", "action": "provide_info"},
                    {"label": "提交跟进请求", "action": "create_ticket", "reason": "需要补充退款信息"}
                ]
            )
        else:
            # 工具调用失败，触发工单兜底
            ticket_summary = f"用户{username}申请退款失败，订单号：{order_id}，失败原因：{tool_result.message}"
            
            # 尝试创建工单
            try:
                ticket_result = await self.ticket_service.create_ticket(
                    session_id=session.session_id,
                    anonymous_user_id=session.anonymous_user_id,
                    summary=ticket_summary,
                    order_id=order_id,
                    fallback_reason="退款工具调用失败"
                )
                
                if ticket_result:
                    return self._ticket_card_response(
                        session, trace_id,
                        title="退款处理未完成",
                        description=f"系统暂时无法处理订单 {order_id} 的退款申请。已为你记录跟进请求，客服将尽快联系你。",
                        summary=ticket_summary
                    )
            except Exception as e:
                print(f"[ERROR] Failed to create ticket: {e}")
            
            # 工单创建失败，仍返回工具失败卡片
            return self._tool_result_response(
                session, trace_id,
                title="本次处理未完成",
                description=f"系统暂时无法处理订单 {order_id} 的退款申请，请稍后重试或联系客服。",
                status="fail",
                actions=[
                    {"label": "稍后重试", "action": "retry"},
                    {"label": "提交跟进请求", "action": "create_ticket", "reason": "退款工具调用失败"}
                ]
            )
    
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
        working_memory: Dict[str, Any],
        trace_id: str
    ) -> Dict[str, Any]:
        """处理通用知识答疑链路 - 使用 RAG"""
        username = user.username if user else "用户"

        # 1. 首先尝试 RAG 检索
        try:
            rag_result = await self.rag_service.answer(
                question=user_content,
                username=username,
                top_k=3
            )
            
            if rag_result.get("hit") and rag_result.get("answer"):
                # RAG 命中，使用检索结果
                print(f"[DEBUG] RAG 命中，使用知识库回答")
                return self._text_response(
                    session, trace_id,
                    rag_result["answer"],
                    message_type="bot_knowledge"
                )
            else:
                print(f"[DEBUG] RAG 未命中: {rag_result.get('message')}")
        except Exception as e:
            print(f"[ERROR] RAG 检索失败: {e}")

        # 2. RAG 未命中或失败，降级到 LLM 直接回答
        # 构建上下文 - 从数据库读取历史消息
        context = []
        try:
            result = await self.db.execute(
                select(Message)
                .where(Message.session_id == session.session_id)
                .order_by(Message.created_at.desc())
                .limit(10)
            )
            messages = result.scalars().all()
            # 按时间正序排列
            for msg in reversed(messages):
                if msg.sender == "user":
                    context.append({"role": "user", "content": msg.content})
                elif msg.sender == "bot" and msg.message_type not in ["bot_greeting"]:
                    # 不包含首问问候语，避免干扰
                    context.append({"role": "assistant", "content": msg.content})
            # 只保留最近5轮对话
            context = context[-10:]  # 10条消息 = 5轮对话
        except Exception as e:
            print(f"[DEBUG] Failed to load message history: {e}")

        print(f"[DEBUG] Building context with {len(context)} messages for LLM")

        # 3. 构建运行时业务上下文（Grounded LLM）
        runtime_context = self._build_runtime_context(
            session=session,
            user=user,
            intent_result=intent_result,
            working_memory=working_memory,
            rag_result=rag_result if 'rag_result' in locals() else None
        )
        print(f"[DEBUG] Runtime context built with keys: {list(runtime_context.keys())}")

        # 调用 LLM，注入运行时上下文
        llm_response = await self.llm_service.chat(
            user_content=user_content,
            username=username,
            context=context if context else None,
            runtime_context=runtime_context
        )

        return self._text_response(
            session, trace_id,
            llm_response.content,
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

    def _build_runtime_context(
        self,
        session: Session,
        user,
        intent_result: Dict[str, Any],
        working_memory: Dict[str, Any],
        rag_result: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        构建运行时业务上下文（Grounded LLM）

        将可信状态数据注入 LLM，让模型基于事实生成回复，而非猜测。
        这是实现 Salesforce Agentforce 式 grounded business data 的关键。

        Args:
            session: 当前会话
            user: 用户对象
            intent_result: 意图识别结果
            working_memory: 工作记忆
            rag_result: RAG 检索结果

        Returns:
            运行时上下文字典
        """
        context = {
            "conversation_summary": self._generate_conversation_summary(session, working_memory, intent_result),
            "known_user_profile": {
                "user_id": session.anonymous_user_id,
                "username": user.username if user else "用户",
                "is_returning_user": self._is_returning_user(session.anonymous_user_id)
            },
            "known_context": {
                "active_order_id": session.current_order_id,
                "active_issue_type": intent_result.get("topic", "unknown"),
                "active_task": intent_result.get("task", "consult"),
                "last_resolution": session.tool_status,
                "pending_slot": working_memory.get("pending_slot")
            },
            "available_tools": ["refund_apply", "refund_status_query", "ticket_create"],
            "tool_call_policy": {
                "refund_apply_requires": ["order_id"],
                "refund_status_query_requires": ["order_id"],
                "ticket_create_requires": []
            }
        }

        # 添加知识库结果（如果有）
        if rag_result and rag_result.get("hit"):
            context["knowledge_results"] = [{
                "hit": True,
                "question": rag_result.get("question", ""),
                "answer": rag_result.get("answer", "")
            }]
        else:
            context["knowledge_results"] = []

        return context

    def _generate_conversation_summary(
        self,
        session: Session,
        working_memory: Dict[str, Any],
        intent_result: Dict[str, Any]
    ) -> str:
        """生成会话摘要"""
        parts = []

        # 用户身份
        if session.current_order_id:
            parts.append(f"用户正在咨询订单 {session.current_order_id} 的相关问题")

        # 当前主题/任务
        topic = intent_result.get("topic", "unknown")
        task = intent_result.get("task", "consult")
        if topic != "unknown":
            topic_map = {"refund": "退款", "logistics": "物流", "presale": "售前", "order": "订单"}
            task_map = {"execute": "执行", "consult": "咨询", "explain": "解释"}
            parts.append(f"当前问题类型：{topic_map.get(topic, topic)}-{task_map.get(task, task)}")

        # 处理状态
        if session.tool_status:
            status_map = {
                "success": "已成功处理",
                "pending": "处理中",
                "fail": "处理失败",
                "need_more_info": "需要更多信息"
            }
            parts.append(f"上一步处理结果：{status_map.get(session.tool_status, session.tool_status)}")

        # 待补充信息
        pending = working_memory.get("pending_slot")
        if pending:
            parts.append(f"等待用户补充：{pending}")

        return "；".join(parts) if parts else "新会话，用户问题待识别"

    def _is_returning_user(self, anonymous_user_id: str) -> bool:
        """判断是否为回访用户（简化实现）"""
        # 实际应该查询用户历史会话记录
        # 这里简化处理：如果有 current_order_id 说明是继续跟进
        return False  # TODO: 实现真实回访用户检测

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

    def _tool_result_response(
        self,
        session: Session,
        trace_id: str,
        title: str,
        description: str,
        status: str,
        actions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        生成工具结果卡片响应
        
        Args:
            title: 卡片标题
            description: 卡片描述
            status: 状态 - success/not_allowed/fail/need_more_info
            actions: 操作按钮列表 [{"label": "", "action": ""}]
        """
        return {
            "type": "bot_message",
            "message_id": f"msg_{uuid.uuid4()}",
            "session_id": session.session_id,
            "trace_id": trace_id,
            "payload": {
                "message_type": "tool_result_card",
                "content": title,
                "card": {
                    "title": title,
                    "description": description,
                    "status": status,
                    "actions": actions or []
                }
            }
        }

    def _ticket_card_response(
        self,
        session: Session,
        trace_id: str,
        title: str = "建议提交跟进请求",
        description: str = "当前问题机器人暂时无法直接完成处理",
        summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成工单引导卡片响应
        
        Args:
            title: 卡片标题
            description: 卡片描述
            summary: 问题摘要
        """
        actions = [
            {"label": "提交跟进请求", "action": "create_ticket", "summary": summary},
            {"label": "继续提问", "action": "continue_chat"}
        ]
        
        return {
            "type": "bot_message",
            "message_id": f"msg_{uuid.uuid4()}",
            "session_id": session.session_id,
            "trace_id": trace_id,
            "payload": {
                "message_type": "ticket_card",
                "content": title,
                "card": {
                    "title": title,
                    "description": description,
                    "status": "ticket_suggested",
                    "summary": summary,
                    "actions": actions
                }
            }
        }

    def _check_user_rejection(self, user_content: str) -> bool:
        """
        检测用户是否不接受当前结果
        
        检测关键词：不接受、不满意、不行、不对、有误、错误、投诉、人工、客服
        """
        rejection_keywords = [
            "不接受", "不满意", "不行", "不对", "有误", "错误",
            "投诉", "人工", "找客服", "转人工", "不认可", "不合理"
        ]
        content = user_content.lower()
        return any(kw in content for kw in rejection_keywords)

    async def _should_trigger_ticket(
        self,
        session: Session,
        working_memory: Dict[str, Any],
        user_content: str,
        intent_confidence: float
    ) -> Tuple[bool, str]:
        """
        判断是否应触发工单兜底
        
        Returns:
            (是否触发, 触发原因)
        """
        # 1. 检查连续识别失败（3轮低置信度）
        recent_messages = working_memory.get("recent_messages", [])
        low_confidence_count = 0
        for msg in recent_messages[-6:]:  # 检查最近6条消息（3轮）
            if msg.get("type") == "bot_followup" or msg.get("type") == "error_message":
                low_confidence_count += 1
        
        if low_confidence_count >= 3:
            return True, "连续多轮无法识别用户意图"
        
        # 2. 检查用户是否不接受结果
        if self._check_user_rejection(user_content):
            return True, "用户不接受当前处理结果"
        
        # 3. 检查意图置信度是否过低
        if intent_confidence < 0.3:
            return True, "无法识别用户意图"

        return False, ""

    def _is_progress_query(self, user_content: str) -> bool:
        """检查用户是否在查询进度"""
        progress_keywords = [
            "怎么样了", "到哪了", "进度", "状态", "处理完了吗",
            "有结果了吗", "现在呢", "如何了", "好了吗", "完成了吗",
            "什么进度", "处理到哪", "现在什么状态", "有进展了吗",
            "那个退款", "昨天那个", "刚才那个", "之前那个"
        ]
        content = user_content.lower()
        return any(kw in content for kw in progress_keywords)

    async def _handle_progress_query(
        self,
        session: Session,
        user,
        order_id: str,
        tool_status: Optional[str],
        trace_id: str
    ) -> Dict[str, Any]:
        """处理进度查询"""
        username = user.username if user else "用户"

        # 根据工具状态返回不同的进度信息
        if tool_status == "success":
            progress_content = (
                f"关于订单{order_id}的退款申请：\n"
                f"当前状态：退款申请已提交成功\n"
                f"处理进度：正在处理中，预计 1-3 个工作日到账\n"
                f"退款将原路返回至您的支付账户，请耐心等待。"
            )
        elif tool_status == "processing":
            progress_content = (
                f"关于订单{order_id}的退款申请：\n"
                f"当前状态：处理中\n"
                f"最新进度：正在审核处理，暂时还没有最终结果。\n"
                f"预计 1-3 个工作日内完成，到账后会有通知。"
            )
        elif tool_status == "not_allowed":
            progress_content = (
                f"关于订单{order_id}的退款申请：\n"
                f"当前状态：暂不符合退款条件\n"
                f"原因可能是超过售后时效或商品影响二次销售。\n"
                f"如需进一步处理，可以提交跟进请求。"
            )
        else:
            progress_content = (
                f"关于订单{order_id}：\n"
                f"当前状态：处理中\n"
                f"我已帮你查看了最新情况，暂时还没有最终结果。\n"
                f"如有更新会第一时间通知你。"
            )

        return self._text_response(
            session, trace_id,
            progress_content,
            message_type="bot_progress"
        )
