from sqlalchemy import Column, String, DateTime, Enum, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base
import uuid
import enum


class SessionStatus(str, enum.Enum):
    # 初始状态
    CREATING = "creating"

    # 活跃状态
    ACTIVE = "active"

    # 等待状态
    PAUSED = "paused"              # 暂停中（等待用户回复）
    PENDING_USER = "pending_user"  # 等待用户补充信息
    PENDING_AGENT = "pending_agent" # 等待坐席接入

    # 升级状态
    ESCALATED = "escalated"        # 已升级人工处理

    # 终态
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
    status_logs = relationship("SessionStatusLog", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Session {self.session_id} topic={self.current_topic} task={self.current_task}>"


class SessionStatusLog(Base):
    """会话状态变更日志表"""

    __tablename__ = "session_status_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)

    # 状态变更前后
    old_status = Column(Enum(SessionStatus), nullable=True)  # 首次创建时为 None
    new_status = Column(Enum(SessionStatus), nullable=False)

    # 变更原因/触发源
    reason = Column(String, nullable=True)  # 例如："user_init", "timeout", "escalate", "resolve"
    triggered_by = Column(String, nullable=True)  # 例如："system", "user", "agent", "api"

    # 额外上下文
    context = Column(Text, nullable=True)  # JSON 字符串或描述文本

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # 关系
    session = relationship("Session", back_populates="status_logs")

    def __repr__(self):
        return f"<SessionStatusLog {self.id} session={self.session_id} {self.old_status}→{self.new_status}>"
