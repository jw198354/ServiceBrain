from sqlalchemy import Column, String, DateTime, Enum, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base
import uuid
import enum


class SessionStatus(str, enum.Enum):
    CREATING = "creating"
    ACTIVE = "active"
    CLOSED = "closed"
    ERROR = "error"


class Session(Base):
    """会话模型"""
    
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    anonymous_user_id = Column(String, index=True, nullable=False)
    status = Column(Enum(SessionStatus), default=SessionStatus.CREATING)
    
    # 当前状态
    current_topic = Column(String, default="unknown")  # refund/logistics/aftersale/presale/unknown
    current_task = Column(String, default="chat")  # consult/explain/execute/followup/ticket
    pending_slot = Column(String, nullable=True)  # 待补槽位名称
    current_order_id = Column(String, nullable=True)
    
    # 工具状态
    tool_status = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Session {self.session_id} topic={self.current_topic} task={self.current_task}>"
