from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from app.core.config import settings
from app.models.message import Message
from app.models.session import Session as ChatSession
from app.models.user import AnonymousUser
import uuid
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import asyncio

router = APIRouter()

# 创建同步数据库引擎用于 WebSocket
sync_engine = create_engine(
    settings.DATABASE_URL.replace("+aiosqlite", ""),
    echo=settings.DEBUG,
    pool_pre_ping=True,
)
sync_session_maker = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

# 线程池用于执行同步数据库操作
executor = ThreadPoolExecutor(max_workers=10)


def verify_user_sync(token: str):
    """同步验证用户"""
    db = sync_session_maker()
    try:
        # 直接查询而不是通过 service
        from sqlalchemy import select
        result = db.execute(
            select(AnonymousUser).where(AnonymousUser.anonymous_user_token == token)
        )
        return result.scalar_one_or_none()
    finally:
        db.close()


def verify_and_activate_session_sync(session_id: str):
    """同步验证并激活会话"""
    db = sync_session_maker()
    try:
        from sqlalchemy import select
        result = db.execute(
            select(ChatSession).where(ChatSession.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            from app.models.session import SessionStatus
            session.status = SessionStatus.ACTIVE
            db.commit()
        return session
    finally:
        db.close()


def get_session_messages_count_sync(session_id: str) -> int:
    """同步获取会话消息数量"""
    db = sync_session_maker()
    try:
        from sqlalchemy import select, func
        result = db.execute(
            select(func.count(Message.message_id)).where(Message.session_id == session_id)
        )
        return result.scalar() or 0
    finally:
        db.close()


def save_message_sync(
    session_id: str,
    message_type: str,
    content: str,
    sender: str,
    trace_id: str = None,
    status: str = "sent"
):
    """同步保存消息"""
    db = sync_session_maker()
    try:
        msg = Message(
            session_id=session_id,
            message_type=message_type,
            content=content,
            sender=sender,
            trace_id=trace_id or str(uuid.uuid4()),
            status=status,
        )
        db.add(msg)
        db.commit()
        return msg
    finally:
        db.close()


def get_username_sync(user_id: str) -> str:
    """同步获取用户名"""
    db = sync_session_maker()
    try:
        from sqlalchemy import select
        result = db.execute(
            select(AnonymousUser).where(AnonymousUser.anonymous_user_id == user_id)
        )
        user = result.scalar_one_or_none()
        return user.username if user else "用户"
    finally:
        db.close()


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
        # 使用线程池执行同步数据库操作
        loop = asyncio.get_event_loop()

        # 验证用户
        user = await loop.run_in_executor(executor, verify_user_sync, token)

        if not user:
            await websocket.send_json({
                "type": "system",
                "event": "error",
                "message": "Invalid token",
            })
            await websocket.close(code=4001)
            return

        # 验证并激活会话
        session = await loop.run_in_executor(executor, verify_and_activate_session_sync, session_id)

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
        message_count = await loop.run_in_executor(executor, get_session_messages_count_sync, session_id)
        if message_count == 0:
            greeting_message = {
                "type": "bot_message",
                "message_id": f"msg_{uuid.uuid4()}",
                "session_id": session_id,
                "payload": {
                    "message_type": "bot_greeting",
                    "content": f"你好，{user.username}，我是你的智能客服助手。你可以直接告诉我遇到的问题，比如订单、物流、退款或售后规则，我来帮你看看。",
                },
            }
            await websocket.send_json(greeting_message)

            # 保存首问消息
            await loop.run_in_executor(
                executor,
                save_message_sync,
                session_id,
                "bot_greeting",
                greeting_message["payload"]["content"],
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
                    trace_id = message_data.get("trace_id", str(uuid.uuid4()))

                    # 保存用户消息
                    await loop.run_in_executor(
                        executor,
                        save_message_sync,
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
                        "message_id": message_data.get("message_id"),
                        "status": "sent",
                        "timestamp": int(datetime.now().timestamp()),
                    })

                    # TODO: 调用编排服务处理消息
                    # 暂时返回一个简单的回复
                    bot_response = {
                        "type": "bot_message",
                        "message_id": f"msg_{uuid.uuid4()}",
                        "session_id": session_id,
                        "trace_id": trace_id,
                        "payload": {
                            "message_type": "bot_text",
                            "content": f"收到你的消息：{user_content}。我正在学习中，稍后会给你更智能的回复！",
                        },
                    }
                    await websocket.send_json(bot_response)

                    # 保存机器人回复
                    await loop.run_in_executor(
                        executor,
                        save_message_sync,
                        session_id,
                        "bot_text",
                        bot_response["payload"]["content"],
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
        await websocket.send_json({
            "type": "system",
            "event": "error",
            "message": str(e),
        })
