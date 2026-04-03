from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.services.user_service import UserService
from app.services.session_service import SessionService
from app.schemas.user import UserCreate, UserInitResponse
from app.schemas.session import SessionInitRequest, SessionInitResponse, SessionListResponse, SessionSchema
from app.models.session import SessionStatus, Session
from typing import Optional

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
    
    # 优先复用用户已有活跃会话，避免无谓分叉
    session_service = SessionService(db)
    session = await session_service.get_latest_active_session(user.anonymous_user_id)
    if not session:
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
    anonymous_user_token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    创建工单
    """
    from app.models.ticket import Ticket, TicketStatus
    
    user_service = UserService(db)
    user = await user_service.get_user_by_token(anonymous_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    session_result = await db.execute(
        select(Session).where(Session.session_id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.anonymous_user_id != user.anonymous_user_id:
        raise HTTPException(status_code=403, detail="Forbidden session access")

    ticket = Ticket(
        session_id=session_id,
        anonymous_user_id=user.anonymous_user_id,
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
    anonymous_user_token: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    获取会话消息列表
    """
    from app.models.message import Message

    user_service = UserService(db)
    user = await user_service.get_user_by_token(anonymous_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    session_result = await db.execute(
        select(Session).where(Session.session_id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.anonymous_user_id != user.anonymous_user_id:
        raise HTTPException(status_code=403, detail="Forbidden session access")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    
    messages = result.scalars().all()
    
    from datetime import timezone

    return {
        "messages": [
            {
                "message_id": msg.message_id,
                "type": msg.message_type,
                "content": msg.content,
                "sender": msg.sender,
                # 确保时间戳包含时区信息（UTC），前端会转换为本地时间
                "timestamp": msg.created_at.replace(tzinfo=timezone.utc).isoformat() if msg.created_at else None,
            }
            for msg in messages
        ]
    }


@router.get("/user/sessions", response_model=SessionListResponse)
async def get_user_sessions(
    anonymous_user_token: str,
    status: Optional[str] = Query(default=None, description="会话状态过滤"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    获取用户的会话列表（支持多会话并发）

    前端可使用此接口展示会话列表，供用户选择/切换会话。
    """
    user_service = UserService(db)
    user = await user_service.get_user_by_token(anonymous_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    session_service = SessionService(db)

    # 解析状态过滤
    statuses = None
    if status:
        try:
            statuses = [SessionStatus(status)]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    sessions = await session_service.get_user_sessions(
        anonymous_user_id=user.anonymous_user_id,
        statuses=statuses,
        limit=limit,
    )

    return SessionListResponse(
        sessions=[
            SessionSchema(
                session_id=s.session_id,
                anonymous_user_id=s.anonymous_user_id,
                status=s.status.value,
                current_topic=s.current_topic,
                current_task=s.current_task,
                pending_slot=s.pending_slot,
                current_order_id=s.current_order_id,
                created_at=s.created_at,
            )
            for s in sessions
        ],
        total=len(sessions),
    )


@router.get("/session/{session_id}/status-logs", response_model=dict)
async def get_session_status_logs(
    session_id: str,
    anonymous_user_token: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    获取会话的状态变更日志（审计用途）
    """
    user_service = UserService(db)
    user = await user_service.get_user_by_token(anonymous_user_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    session_result = await db.execute(
        select(Session).where(Session.session_id == session_id)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.anonymous_user_id != user.anonymous_user_id:
        raise HTTPException(status_code=403, detail="Forbidden session access")

    session_service = SessionService(db)
    logs = await session_service.get_session_status_logs(session_id, limit=limit)

    from datetime import timezone

    return {
        "logs": [
            {
                "id": log.id,
                "session_id": log.session_id,
                "old_status": log.old_status.value if log.old_status else None,
                "new_status": log.new_status.value,
                "reason": log.reason,
                "triggered_by": log.triggered_by,
                "context": log.context,
                "timestamp": log.created_at.replace(tzinfo=timezone.utc).isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        "total": len(logs),
    }
