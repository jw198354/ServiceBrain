from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.services.user_service import UserService
from app.services.session_service import SessionService
from app.schemas.user import UserCreate, UserInitResponse
from app.schemas.session import SessionInitRequest, SessionInitResponse
from app.models.session import SessionStatus

router = APIRouter()


@router.post("/user/init-anonymous", response_model=UserInitResponse)
async def init_anonymous_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    初始化匿名用户
    
    首次进入时调用，创建匿名用户并初始化会话
    """
    # 创建匿名用户
    user_service = UserService(db)
    user = await user_service.create_anonymous_user(user_data)
    
    # 创建会话
    session_service = SessionService(db)
    session = await session_service.create_session(user.anonymous_user_id)
    await session_service.activate_session(session)
    
    return UserInitResponse(
        anonymous_user_id=user.anonymous_user_id,
        anonymous_user_token=user.anonymous_user_token,
        username=user.username,
        session_id=session.session_id,
    )


@router.post("/session/init", response_model=SessionInitResponse)
async def init_session(
    request: SessionInitRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    初始化会话
    
    验证用户并创建/恢复会话
    """
    user_service = UserService(db)
    user = await user_service.get_user_by_token(request.anonymous_user_token)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    if user.anonymous_user_id != request.anonymous_user_id:
        raise HTTPException(status_code=401, detail="User ID mismatch")
    
    # 创建新会话
    session_service = SessionService(db)
    session = await session_service.create_session(user.anonymous_user_id)
    await session_service.activate_session(session)
    
    return SessionInitResponse(
        session_id=session.session_id,
        status=session.status.value,
    )


@router.post("/ticket/create")
async def create_ticket(
    session_id: str,
    summary: str,
    db: AsyncSession = Depends(get_db),
):
    """
    创建工单
    """
    from app.models.ticket import Ticket, TicketStatus
    
    ticket = Ticket(
        session_id=session_id,
        anonymous_user_id="unknown",  # TODO: 从 session 获取
        summary=summary,
        status=TicketStatus.CREATED,
    )
    
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    
    return {
        "ticket_id": ticket.ticket_id,
        "status": ticket.status.value,
        "message": "工单已创建",
    }


@router.get("/session/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    获取会话消息列表
    """
    from sqlalchemy import select
    from app.models.message import Message
    
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    
    messages = result.scalars().all()
    
    return {
        "messages": [
            {
                "message_id": msg.message_id,
                "type": msg.message_type,
                "content": msg.content,
                "sender": msg.sender,
                "timestamp": msg.created_at.isoformat(),
            }
            for msg in messages
        ]
    }
