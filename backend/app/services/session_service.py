from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.session import Session, SessionStatus
from app.models.user import AnonymousUser
from typing import Optional, Union


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
        """激活会话"""
        # 同一用户仅允许一个 ACTIVE 会话，避免会话分叉
        await self.db.execute(
            update(Session)
            .where(
                Session.anonymous_user_id == session.anonymous_user_id,
                Session.session_id != session.session_id,
                Session.status == SessionStatus.ACTIVE,
            )
            .values(status=SessionStatus.CLOSED)
        )
        session.status = SessionStatus.ACTIVE
        await self.db.commit()
        await self.db.refresh(session)
        return session
