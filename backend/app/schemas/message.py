from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

# Python 3.6 compatibility: use typing_extensions for Literal
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal


# ============ WebSocket 入站消息 ============

class UserMessage(BaseModel):
    """用户消息"""
    type = "user_message"
    message_id: str
    session_id: str
    trace_id: Optional[str] = None
    content: str
    timestamp: int


class PingMessage(BaseModel):
    """心跳消息"""
    type = "ping"
    timestamp: int


# ============ WebSocket 出站消息 ============

class BotMessage(BaseModel):
    """机器人消息"""
    type = "bot_message"
    message_id: str
    session_id: str
    trace_id: Optional[str] = None
    payload: Dict[str, Any]


class AckMessage(BaseModel):
    """ACK 确认消息"""
    type = "ack"
    message_id: str
    status: str  # sent/failed
    timestamp: int


class PongMessage(BaseModel):
    """心跳响应"""
    type = "pong"
    timestamp: int


class SystemMessage(BaseModel):
    """系统消息"""
    type = "system"
    event: str  # connected/disconnected/reconnecting/error
    message: str
    data: Optional[Dict[str, Any]] = None


# ============ 卡片消息结构 ============

class CardAction(BaseModel):
    """卡片操作按钮"""
    label: str
    action: str
    payload: Optional[Dict[str, Any]] = None


class ToolResultCard(BaseModel):
    """工具结果卡片"""
    message_type: str = "tool_result_card"
    title: str
    description: str
    status: str  # success/not_allowed/fail/need_more_info
    actions: List[CardAction] = []


class TicketCard(BaseModel):
    """工单卡片"""
    message_type: str = "ticket_card"
    title: str
    description: str
    summary: Optional[str] = None
    actions: List[CardAction] = []
    status: str = "suggested"  # suggested/submitted/created
