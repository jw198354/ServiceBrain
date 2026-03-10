from sqlalchemy import Column, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base
import uuid


class Message(Base):
    """消息模型"""
    
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.session_id"), index=True, nullable=False)
    
    # 消息类型
    message_type = Column(String, nullable=False)  # user_text/bot_greeting/bot_text/bot_followup/bot_knowledge/bot_explain/tool_result_card/ticket_card/system_status/error_message
    
    # 内容
    content = Column(Text, nullable=False)
    sender = Column(String, nullable=False)  # user/bot/system
    
    # 状态
    status = Column(String, default="sent")  # sending/sent/failed
    trace_id = Column(String, index=True, nullable=True)
    
    # 元数据 (JSON 字符串)
    metadata_json = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    session = relationship("Session", back_populates="messages")
    
    def __repr__(self):
        return f"<Message {self.message_id} type={self.message_type} sender={self.sender}>"
