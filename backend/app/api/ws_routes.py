from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.services.session_service import SessionService
from app.services.user_service import UserService
from app.models.message import Message
from app.models.session import SessionStatus
import uuid
import json
from datetime import datetime

router = APIRouter()


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
    
    db: AsyncSession = None
    
    try:
        # 验证用户
        async for db_session in get_db():
            db = db_session
            break
        
        user_service = UserService(db)
        user = await user_service.get_user_by_token(token)
        
        if not user:
            await websocket.send_json({
                "type": "system",
                "event": "error",
                "message": "Invalid token",
            })
            await websocket.close(code=4001)
            return
        
        # 验证会话
        session_service = SessionService(db)
        session = await session_service.get_session(session_id)
        
        if not session:
            await websocket.send_json({
                "type": "system",
                "event": "error",
                "message": "Session not found",
            })
            await websocket.close(code=4002)
            return
        
        # 激活会话
        await session_service.activate_session(session)
        
        # 发送连接成功消息
        await websocket.send_json({
            "type": "system",
            "event": "connected",
            "message": "已连接到智能客服助手",
        })
        
        # 发送首问消息（如果是新会话）
        message_count = len(session.messages)
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
            bot_msg = Message(
                session_id=session_id,
                message_type="bot_greeting",
                content=greeting_message["payload"]["content"],
                sender="bot",
                status="sent",
            )
            db.add(bot_msg)
            await db.commit()
        
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
                    user_msg = Message(
                        session_id=session_id,
                        message_type="user_text",
                        content=user_content,
                        sender="user",
                        trace_id=trace_id,
                        status="sent",
                    )
                    db.add(user_msg)
                    await db.commit()
                    
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
                    bot_msg = Message(
                        session_id=session_id,
                        message_type="bot_text",
                        content=bot_response["payload"]["content"],
                        sender="bot",
                        trace_id=trace_id,
                        status="sent",
                    )
                    db.add(bot_msg)
                    await db.commit()
            
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
    finally:
        if db:
            await db.close()
