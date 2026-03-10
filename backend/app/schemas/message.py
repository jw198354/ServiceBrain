from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any
from datetime import datetime


# ============ WebSocket 入站消息 ============

class UserMessage(BaseModel):
    """用户消息"""
    type: Literal["user_message"]
    message_id: str
    session_id: str
    trace_id: Optional[str] = None
    content: str
    timestamp: int


class PingMessage(BaseModel):
    """心跳消息"""
    type: Literal["ping"]
    timestamp: int


# ============ WebSocket 出站消息 ============

class BotMessage(BaseModel):
    """机器人消息"""
    type: Literal["bot_message"]
    message_id: str
    session_id: str
    trace_id: Optional[str] = None
    payload: Dict[str, Any]


class AckMessage(BaseModel):
    """ACK 确认消息"""
    type: Literal["ack"]
    message_id: str
    status: str  # sent/failed
    timestamp: int


class PongMessage(BaseModel):
    """心跳响应"""
    type: Literal["pong"]
    timestamp: int


class SystemMessage(BaseModel):
    """系统消息"""
    type: Literal["system"]
    event: str  # connected/disconnected/reconnecting/error
    message: str
    data: Optional[Dict[str, Any]] = None


# ============ 消息类型定义 ============

MessageType = Literal[
    "user_message",
    "bot_greeting",
    "bot_text",
    "bot_followup",
    "bot_knowledge",
    "bot_explain",
    "tool_result_card",
    "ticket_card",
    "system_status",
    "error_message",
]


# ============ 卡片消息结构 ============

class CardAction(BaseModel):
    """卡片操作按钮"""
    label: str
    action: str
    payload: Optional[Dict[str, Any]] = None


class ToolResultCard(BaseModel):
    """工具结果卡片"""
    message_type: Literal["tool_result_card"]
    title: str
    description: str
    status: Literal["success", "not_allowed", "fail", "need_more_info"]
    actions: list[CardAction] = []


class TicketCard(BaseModel):
    """工单卡片"""
    message_type: Literal["ticket_card"]
    title: str
    description: str
    summary: Optional[str] = None
    actions: list[CardAction] = []
    status: Literal["suggested", "submitted", "created"] = "suggested"
