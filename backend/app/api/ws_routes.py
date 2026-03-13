from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func
from app.core.config import settings
from app.models.message import Message
from app.models.session import Session as ChatSession, SessionStatus
from app.models.user import AnonymousUser
from app.models.database import async_session_maker
from app.services.llm_service import LLMService
import uuid
import json
from datetime import datetime
import asyncio

router = APIRouter()

# LLM 服务实例
llm_service = LLMService()


async def verify_user(token: str):
    """异步验证用户"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(AnonymousUser).where(AnonymousUser.anonymous_user_token == token)
        )
        return result.scalar_one_or_none()


async def verify_and_activate_session(session_id: str):
    """异步验证并激活会话"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(ChatSession).where(ChatSession.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.status = SessionStatus.ACTIVE
            await db.commit()
        return session


async def get_session_messages_count(session_id: str) -> int:
    """异步获取会话消息数量"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(func.count(Message.message_id)).where(Message.session_id == session_id)
        )
        return result.scalar() or 0


async def save_message(
    session_id: str,
    message_type: str,
    content: str,
    sender: str,
    trace_id: str = None,
    status: str = "sent"
):
    """异步保存消息"""
    async with async_session_maker() as db:
        msg = Message(
            session_id=session_id,
            message_type=message_type,
            content=content,
            sender=sender,
            trace_id=trace_id or str(uuid.uuid4()),
            status=status,
        )
        db.add(msg)
        await db.commit()
        return msg


async def get_username(user_id: str) -> str:
    """异步获取用户名"""
    async with async_session_maker() as db:
        result = await db.execute(
            select(AnonymousUser).where(AnonymousUser.anonymous_user_id == user_id)
        )
        user = result.scalar_one_or_none()
        return user.username if user else "用户"


@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str,
    session_id: str,
):
    """
    WebSocket 聊天连接

    查询参数:
    - token: 匿名用户 token
    - session_id: 会话 ID
    """
    await websocket.accept()

    try:
        # 验证用户
        user = await verify_user(token)

        if not user:
            await websocket.send_json({
                "type": "system",
                "event": "error",
                "message": "Invalid token",
            })
            await websocket.close(code=4001)
            return

        # 验证并激活会话
        session = await verify_and_activate_session(session_id)

        if not session:
            await websocket.send_json({
                "type": "system",
                "event": "error",
                "message": "Session not found",
            })
            await websocket.close(code=4002)
            return

        # 发送连接成功消息
        await websocket.send_json({
            "type": "system",
            "event": "connected",
            "message": "已连接到智能客服助手",
        })

        # 发送首问消息（如果是新会话）
        message_count = await get_session_messages_count(session_id)
        if message_count == 0:
            # 使用 LLM 生成个性化问候语
            greeting_content = await llm_service.generate_greeting(user.username)

            greeting_message = {
                "type": "bot_message",
                "message_id": f"msg_{uuid.uuid4()}",
                "session_id": session_id,
                "payload": {
                    "message_type": "bot_greeting",
                    "content": greeting_content,
                },
            }
            await websocket.send_json(greeting_message)

            # 保存首问消息
            await save_message(
                session_id,
                "bot_greeting",
                greeting_content,
                "bot",
                None,
                "sent"
            )

        # 保持连接并处理消息
        while True:
            try:
                # 接收消息
                data = await websocket.receive_text()
                message_data = json.loads(data)

                # 处理 ping
                if message_data.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": int(datetime.now().timestamp()),
                    })
                    continue

                # 处理用户消息
                if message_data.get("type") == "user_message":
                    user_content = message_data.get("content", "")
                    message_id = message_data.get("message_id", f"msg_{uuid.uuid4()}")
                    trace_id = message_data.get("trace_id", str(uuid.uuid4()))

                    # 保存用户消息
                    await save_message(
                        session_id,
                        "user_text",
                        user_content,
                        "user",
                        trace_id,
                        "sent"
                    )

                    # 发送 ACK
                    await websocket.send_json({
                        "type": "ack",
                        "message_id": message_id,
                        "status": "sent",
                        "timestamp": int(datetime.now().timestamp()),
                    })

                    # 调用编排服务处理消息（使用异步 DB 会话）
                    from app.services.orchestrator_service import OrchestratorService
                    async with async_session_maker() as db:
                        orchestrator = OrchestratorService(db)
                        bot_response = await orchestrator.process_user_message(
                            session_id, user_content, trace_id
                        )
                    
                    # 发送机器人回复
                    await websocket.send_json(bot_response)

                    # 保存机器人回复
                    payload = bot_response.get("payload", {})
                    bot_content = payload.get("content", "")
                    message_type = payload.get("message_type", "bot_text")
                    
                    await save_message(
                        session_id,
                        message_type,
                        bot_content,
                        "bot",
                        trace_id,
                        "sent"
                    )

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "system",
                    "event": "error",
                    "message": "Invalid message format",
                })

    except Exception as e:
        import traceback
        print(f"WebSocket error: {traceback.format_exc()}")
        await websocket.send_json({
            "type": "system",
            "event": "error",
            "message": str(e),
        })
