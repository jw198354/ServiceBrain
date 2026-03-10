from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.session import Session, SessionStatus
from app.models.user import AnonymousUser
from typing import Optional


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
    
    async def get_session(self, session_id: str) -> Session | None:
        """获取会话"""
        result = await self.db.execute(
            select(Session).where(Session.session_id == session_id)
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
        if status:
            session.status = status
        if topic:
            session.current_topic = topic
        if task:
            session.current_task = task
        if pending_slot:
            session.pending_slot = pending_slot
        if order_id:
            session.current_order_id = order_id
        if tool_status:
            session.tool_status = tool_status
        
        await self.db.commit()
        await self.db.refresh(session)
        
        return session
    
    async def activate_session(self, session: Session) -> Session:
        """激活会话"""
        session.status = SessionStatus.ACTIVE
        await self.db.commit()
        await self.db.refresh(session)
        return session
