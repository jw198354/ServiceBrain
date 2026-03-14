"""
记忆服务 - 管理上下文隔离、摘要、检索、意图漂移

负责：
- Working Memory 加载与更新
- Session Summary 生成
- Topic Memory 更新
- User Profile 更新
- 历史摘要检索
- 漂移判断辅助
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

from app.models.memory import SessionSummary, TopicMemory, UserProfileMemory
from app.models.session import Session
from app.models.message import Message


class MemoryService:
    """记忆管理服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ========== Working Memory ==========
    
    async def load_working_memory(
        self,
        session_id: str,
        limit_messages: int = 6
    ) -> Dict[str, Any]:
        """
        加载工作记忆
        
        包含：
        - 最近 N 轮对话
        - 当前会话状态
        - 待补槽位
        - 当前主题/任务
        """
        # 获取会话
        session_result = await self.db.execute(
            select(Session)
            .options(selectinload(Session.messages))
            .where(Session.session_id == session_id)
        )
        session = session_result.scalar_one_or_none()
        
        if not session:
            return self._empty_working_memory(session_id)
        
        # 获取最近消息
        messages_result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit_messages)
        )
        recent_messages = messages_result.scalars().all()
        recent_messages = list(reversed(recent_messages))
        
        return {
            "session_id": session_id,
            "anonymous_user_id": session.anonymous_user_id,
            "current_topic": session.current_topic or "unknown",
            "current_task": session.current_task or "chat",
            "pending_slot": session.pending_slot,
            "current_order_id": session.current_order_id,
            "recent_messages": [
                {
                    "role": msg.sender,
                    "type": msg.message_type,
                    "content": msg.content,
                    "timestamp": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in recent_messages
            ],
            "tool_status": session.tool_status,
        }
    
    def _empty_working_memory(self, session_id: str) -> Dict[str, Any]:
        """返回空工作记忆"""
        return {
            "session_id": session_id,
            "anonymous_user_id": None,
            "current_topic": "unknown",
            "current_task": "chat",
            "pending_slot": None,
            "current_order_id": None,
            "recent_messages": [],
            "tool_status": None,
        }
    
    async def update_working_memory(
        self,
        session: Session,
        topic: Optional[str] = None,
        task: Optional[str] = None,
        pending_slot: Optional[str] = None,
        order_id: Optional[str] = None,
        tool_status: Optional[str] = None,
    ) -> Session:
        """更新工作记忆状态"""
        if topic:
            session.current_topic = topic
        if task:
            session.current_task = task
        # 使用 "" 作为清除 pending_slot 的标记，None 表示不更新
        if pending_slot == "":
            session.pending_slot = None
        elif pending_slot is not None:
            session.pending_slot = pending_slot
        if order_id is not None:
            session.current_order_id = order_id
        if tool_status is not None:
            session.tool_status = tool_status

        await self.db.commit()
        await self.db.refresh(session)
        return session
    
    # ========== Session Summary ==========
    
    async def create_session_summary(
        self,
        session_id: str,
        anonymous_user_id: str,
        summary_text: str,
        topic: Optional[str] = None,
        task: Optional[str] = None,
        order_id: Optional[str] = None,
        resolved: bool = False,
        next_action: Optional[str] = None,
    ) -> SessionSummary:
        """创建会话摘要"""
        summary = SessionSummary(
            session_id=session_id,
            summary_text=summary_text,
            topic=topic,
            task=task,
            order_id=order_id,
            resolved=resolved,
            next_action=next_action,
        )
        
        self.db.add(summary)
        await self.db.commit()
        await self.db.refresh(summary)
        return summary
    
    async def get_session_summary(self, session_id: str) -> Optional[SessionSummary]:
        """获取会话摘要"""
        result = await self.db.execute(
            select(SessionSummary).where(SessionSummary.session_id == session_id)
        )
        return result.scalar_one_or_none()
    
    async def get_recent_summaries(
        self,
        anonymous_user_id: str,
        limit: int = 3
    ) -> List[SessionSummary]:
        """获取用户最近会话摘要"""
        result = await self.db.execute(
            select(SessionSummary)
            .where(SessionSummary.anonymous_user_id == anonymous_user_id)
            .order_by(SessionSummary.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    # ========== Topic Memory ==========
    
    async def get_topic_memory(
        self,
        anonymous_user_id: str,
        order_id: str
    ) -> Optional[TopicMemory]:
        """获取订单主题记忆"""
        result = await self.db.execute(
            select(TopicMemory)
            .where(
                and_(
                    TopicMemory.anonymous_user_id == anonymous_user_id,
                    TopicMemory.order_id == order_id
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def upsert_topic_memory(
        self,
        anonymous_user_id: str,
        order_id: str,
        topic: str,
        task: Optional[str] = None,
        last_status: Optional[str] = None,
        last_conclusion: Optional[str] = None,
        unresolved_action: Optional[str] = None,
        context_summary: Optional[str] = None,
    ) -> TopicMemory:
        """创建或更新主题记忆"""
        existing = await self.get_topic_memory(anonymous_user_id, order_id)
        
        if existing:
            existing.topic = topic
            if task:
                existing.task = task
            if last_status:
                existing.last_status = last_status
            if last_conclusion:
                existing.last_conclusion = last_conclusion
            if unresolved_action:
                existing.unresolved_action = unresolved_action
            if context_summary:
                existing.context_summary = context_summary
            existing.last_consulted_at = datetime.now()
            existing.updated_at = datetime.now()
            
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            topic_memory = TopicMemory(
                anonymous_user_id=anonymous_user_id,
                order_id=order_id,
                topic=topic,
                task=task,
                last_status=last_status,
                last_conclusion=last_conclusion,
                unresolved_action=unresolved_action,
                context_summary=context_summary,
            )
            self.db.add(topic_memory)
            await self.db.commit()
            await self.db.refresh(topic_memory)
            return topic_memory
    
    # ========== User Profile Memory ==========
    
    async def get_user_profile(
        self,
        anonymous_user_id: str
    ) -> Optional[UserProfileMemory]:
        """获取用户长期记忆"""
        result = await self.db.execute(
            select(UserProfileMemory)
            .where(UserProfileMemory.anonymous_user_id == anonymous_user_id)
        )
        return result.scalar_one_or_none()
    
    async def upsert_user_profile(
        self,
        anonymous_user_id: str,
        preferred_topics: Optional[List[str]] = None,
        frequent_issue_types: Optional[List[str]] = None,
        service_preferences: Optional[Dict[str, Any]] = None,
        unresolved_ticket_ids: Optional[List[str]] = None,
    ) -> UserProfileMemory:
        """创建或更新用户长期记忆"""
        existing = await self.get_user_profile(anonymous_user_id)
        
        if existing:
            if preferred_topics:
                existing.preferred_topics = json.dumps(preferred_topics)
            if frequent_issue_types:
                existing.frequent_issue_types = json.dumps(frequent_issue_types)
            if service_preferences:
                existing.service_preferences = json.dumps(service_preferences)
            if unresolved_ticket_ids:
                existing.unresolved_ticket_ids = json.dumps(unresolved_ticket_ids)
            existing.updated_at = datetime.now()
            
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            profile = UserProfileMemory(
                anonymous_user_id=anonymous_user_id,
                preferred_topics=json.dumps(preferred_topics) if preferred_topics else None,
                frequent_issue_types=json.dumps(frequent_issue_types) if frequent_issue_types else None,
                service_preferences=json.dumps(service_preferences) if service_preferences else None,
                unresolved_ticket_ids=json.dumps(unresolved_ticket_ids) if unresolved_ticket_ids else None,
            )
            self.db.add(profile)
            await self.db.commit()
            await self.db.refresh(profile)
            return profile
    
    # ========== Memory Retrieval ==========
    
    async def retrieve_history(
        self,
        anonymous_user_id: str,
        order_id: Optional[str] = None,
        topic: Optional[str] = None,
        limit_summaries: int = 3
    ) -> Dict[str, Any]:
        """
        检索历史记忆
        
        优先级：
        1. 订单主题记忆（如有 order_id）
        2. 最近会话摘要
        3. 用户长期记忆
        """
        result = {
            "topic_memory": None,
            "recent_summaries": [],
            "user_profile": None,
        }
        
        # 1. 订单主题记忆
        if order_id:
            topic_mem = await self.get_topic_memory(anonymous_user_id, order_id)
            if topic_mem:
                result["topic_memory"] = {
                    "order_id": topic_mem.order_id,
                    "topic": topic_mem.topic,
                    "last_status": topic_mem.last_status,
                    "last_conclusion": topic_mem.last_conclusion,
                    "context_summary": topic_mem.context_summary,
                }
        
        # 2. 最近会话摘要
        summaries = await self.get_recent_summaries(anonymous_user_id, limit_summaries)
        result["recent_summaries"] = [
            {
                "topic": s.topic,
                "task": s.task,
                "order_id": s.order_id,
                "summary": s.summary_text,
                "resolved": s.resolved,
                "next_action": s.next_action,
            }
            for s in summaries
        ]
        
        # 3. 用户长期记忆
        profile = await self.get_user_profile(anonymous_user_id)
        if profile:
            result["user_profile"] = {
                "preferred_topics": json.loads(profile.preferred_topics) if profile.preferred_topics else [],
                "frequent_issue_types": json.loads(profile.frequent_issue_types) if profile.frequent_issue_types else [],
                "unresolved_ticket_ids": json.loads(profile.unresolved_ticket_ids) if profile.unresolved_ticket_ids else [],
            }
        
        return result
    
    # ========== Drift Detection ==========
    
    def detect_topic_shift(
        self,
        current_topic: str,
        new_topic: str
    ) -> bool:
        """检测主题漂移"""
        if current_topic == "unknown":
            return False
        return current_topic != new_topic
    
    def detect_task_shift(
        self,
        current_task: str,
        new_task: str
    ) -> bool:
        """检测任务漂移"""
        if current_task == "chat":
            return False
        return current_task != new_task
    
    def classify_shift_type(
        self,
        current_topic: str,
        new_topic: str,
        current_task: str,
        new_task: str
    ) -> str:
        """
        分类漂移类型
        
        返回：
        - "none": 无漂移
        - "weak": 弱漂移（同主题内任务切换）
        - "strong": 强漂移（主题切换）
        """
        if current_topic == "unknown":
            return "none"
        
        if current_topic != new_topic:
            return "strong"
        
        if current_task != new_task:
            return "weak"
        
        return "none"
    
    # ========== Context Compression ==========
    
    async def compress_context_if_needed(
        self,
        session: Session,
        message_count_threshold: int = 12,
        token_estimate_threshold: int = 6000
    ) -> Optional[SessionSummary]:
        """
        检查并压缩上下文
        
        触发条件：
        1. 消息轮次超过阈值
        2. 预估 token 数超过阈值
        3. 发生主题切换
        
        Args:
            session: 当前会话
            message_count_threshold: 消息数量阈值
            token_estimate_threshold: token 数阈值
            
        Returns:
            生成的会话摘要，如果不需要压缩则返回 None
        """
        # 获取消息数量
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session.session_id)
            .order_by(Message.created_at.desc())
            .limit(message_count_threshold + 1)
        )
        messages = result.scalars().all()
        
        # 检查是否需要压缩
        need_compression = len(messages) > message_count_threshold
        
        # 预估 token 数（简化：中文字符数 * 1.5）
        if not need_compression and messages:
            total_chars = sum(len(m.content) for m in messages)
            estimated_tokens = total_chars * 1.5
            need_compression = estimated_tokens > token_estimate_threshold
        
        if not need_compression:
            return None
        
        # 生成摘要
        return await self._generate_session_summary(session, messages)
    
    async def _generate_session_summary(
        self,
        session: Session,
        messages: List[Message]
    ) -> SessionSummary:
        """
        生成会话摘要
        
        从最近消息中提取关键信息生成摘要
        """
        # 按时间正序排列
        messages = list(reversed(messages))
        
        # 提取关键信息
        user_messages = [m for m in messages if m.sender == "user"]
        bot_messages = [m for m in messages if m.sender == "bot"]
        
        # 构建摘要文本
        summary_parts = []
        
        # 主题和任务
        if session.current_topic != "unknown":
            summary_parts.append(f"主题: {session.current_topic}")
        if session.current_task != "chat":
            summary_parts.append(f"任务: {session.current_task}")
        
        # 订单信息
        if session.current_order_id:
            summary_parts.append(f"订单号: {session.current_order_id}")
        
        # 用户主要诉求（取最近3条用户消息）
        if user_messages:
            recent_user_msgs = [m.content[:50] for m in user_messages[-3:]]
            summary_parts.append(f"用户诉求: {'; '.join(recent_user_msgs)}")
        
        # 处理结果
        if session.tool_status:
            summary_parts.append(f"工具状态: {session.tool_status}")
        
        # 是否已解决
        resolved = session.tool_status == "success" or (
            len(bot_messages) > 0 and 
            any("已完成" in m.content or "已提交" in m.content for m in bot_messages[-3:])
        )
        
        # 生成摘要文本
        summary_text = "\n".join(summary_parts) if summary_parts else "会话进行中"
        
        # 确定下一步动作
        next_action = "continue"
        if not resolved and len(messages) > 10:
            next_action = "ticket_fallback"
        elif resolved:
            next_action = "completed"
        
        # 创建会话摘要
        summary = await self.create_session_summary(
            session_id=session.session_id,
            anonymous_user_id=session.anonymous_user_id,
            summary_text=summary_text,
            topic=session.current_topic,
            task=session.current_task,
            order_id=session.current_order_id,
            resolved=resolved,
            next_action=next_action
        )
        
        print(f"[MemoryService] 生成会话摘要: {summary_text[:100]}...")
        return summary
    
    async def get_compressed_working_memory(
        self,
        session_id: str,
        max_recent_messages: int = 4
    ) -> Dict[str, Any]:
        """
        获取压缩后的工作记忆
        
        包含：
        - 会话摘要
        - 最近 N 条消息
        - 当前状态
        """
        # 加载完整工作记忆
        working_memory = await self.load_working_memory(session_id, limit_messages=20)
        
        # 获取最近会话摘要
        summaries = await self.get_recent_summaries(
            working_memory.get("anonymous_user_id", ""),
            limit=1
        )
        
        # 压缩消息列表
        recent_messages = working_memory.get("recent_messages", [])
        if len(recent_messages) > max_recent_messages:
            # 保留最近 N 条，其余丢弃
            compressed_messages = recent_messages[-max_recent_messages:]
            working_memory["recent_messages"] = compressed_messages
            working_memory["has_more_history"] = True
        
        # 添加摘要信息
        if summaries:
            working_memory["session_summary"] = {
                "summary": summaries[0].summary_text,
                "topic": summaries[0].topic,
                "task": summaries[0].task,
                "resolved": summaries[0].resolved,
                "next_action": summaries[0].next_action
            }
        
        return working_memory
