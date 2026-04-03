from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.session import Session, SessionStatus, SessionStatusLog
from app.models.user import AnonymousUser
from typing import Optional, Union
from datetime import datetime


class SessionService:
    """会话管理服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_session(self, anonymous_user_id: str) -> Session:
        """创建新会话"""
        session = Session(
            anonymous_user_id=anonymous_user_id,
            status=SessionStatus.CREATING,
        )
        
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        
        return session
    
    async def get_session(self, session_id: str):
        """获取会话"""
        result = await self.db.execute(
            select(Session).where(Session.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_latest_active_session(self, anonymous_user_id: str) -> Optional[Session]:
        """获取用户最近活跃会话（优先复用）"""
        result = await self.db.execute(
            select(Session)
            .where(
                Session.anonymous_user_id == anonymous_user_id,
                Session.status == SessionStatus.ACTIVE,
            )
            .order_by(Session.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def update_session_status(
        self,
        session: Session,
        status: Optional[SessionStatus] = None,
        topic: Optional[str] = None,
        task: Optional[str] = None,
        pending_slot: Optional[str] = None,
        order_id: Optional[str] = None,
        tool_status: Optional[str] = None,
    ) -> Session:
        """更新会话状态"""
        if status is not None:
            session.status = status
        if topic is not None:
            session.current_topic = topic
        if task is not None:
            session.current_task = task
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
    
    async def activate_session(self, session: Session) -> Session:
        """
        激活会话（支持多会话并发）

        与旧版本不同，新版本不再自动关闭其他 ACTIVE 会话，
        允许用户同时拥有多个活跃会话。
        """
        session.status = SessionStatus.ACTIVE
        # 记录状态变更日志
        await self._log_status_change(
            session=session,
            old_status=SessionStatus.CREATING,
            new_status=SessionStatus.ACTIVE,
            reason="user_init",
            triggered_by="system",
        )
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def set_session_status(
        self,
        session: Session,
        new_status: SessionStatus,
        reason: Optional[str] = None,
        triggered_by: Optional[str] = None,
        context: Optional[str] = None,
    ) -> Session:
        """
        设置会话状态（带状态变更日志）

        Args:
            session: 目标会话
            new_status: 新状态
            reason: 变更原因（例如："user_init", "timeout", "escalate", "resolve"）
            triggered_by: 触发源（例如："system", "user", "agent", "api"）
            context: 额外上下文信息
        """
        old_status = session.status
        session.status = new_status

        # 记录状态变更日志
        await self._log_status_change(
            session=session,
            old_status=old_status,
            new_status=new_status,
            reason=reason,
            triggered_by=triggered_by,
            context=context,
        )

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def _log_status_change(
        self,
        session: Session,
        old_status: Optional[SessionStatus],
        new_status: SessionStatus,
        reason: Optional[str] = None,
        triggered_by: Optional[str] = None,
        context: Optional[str] = None,
    ):
        """记录会话状态变更日志"""
        log_entry = SessionStatusLog(
            session_id=session.session_id,
            old_status=old_status,
            new_status=new_status,
            reason=reason,
            triggered_by=triggered_by,
            context=context,
        )
        self.db.add(log_entry)
        # 注意：不 commit，由调用方统一提交

    async def get_user_sessions(
        self,
        anonymous_user_id: str,
        statuses: Optional[list[SessionStatus]] = None,
        limit: int = 20,
    ) -> list[Session]:
        """
        获取用户的会话列表

        Args:
            anonymous_user_id: 匿名用户 ID
            statuses: 可选，过滤特定状态的会话
            limit: 返回数量限制
        """
        query = select(Session).where(Session.anonymous_user_id == anonymous_user_id)

        if statuses:
            query = query.where(Session.status.in_(statuses))

        query = query.order_by(Session.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_session_status_logs(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[SessionStatusLog]:
        """
        获取会话的状态变更日志

        Args:
            session_id: 会话 ID
            limit: 返回数量限制
        """
        query = (
            select(SessionStatusLog)
            .where(SessionStatusLog.session_id == session_id)
            .order_by(SessionStatusLog.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(query)
        return result.scalars().all()
