from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SessionInitRequest(BaseModel):
    """会话初始化请求"""
    anonymous_user_id: str
    anonymous_user_token: str


class SessionInitResponse(BaseModel):
    """会话初始化响应"""
    session_id: str
    status: str
    message: str = "会话初始化成功"


class SessionResponse(BaseModel):
    """会话响应"""
    session_id: str
    anonymous_user_id: str
    status: str
    current_topic: Optional[str] = None
    current_task: Optional[str] = None
    pending_slot: Optional[str] = None
    current_order_id: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
