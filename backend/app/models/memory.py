from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.sql import func
from .database import Base
import uuid


class SessionSummary(Base):
    """会话摘要模型"""
    
    __tablename__ = "session_summaries"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, unique=True, index=True, nullable=False)
    
    # 摘要内容
    summary_text = Column(Text, nullable=False)
    topic = Column(String, nullable=True)
    task = Column(String, nullable=True)
    
    # 状态
    resolved = Column(Boolean, default=False)
    order_id = Column(String, nullable=True)
    next_action = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<SessionSummary {self.session_id} topic={self.topic}>"


class TopicMemory(Base):
    """主题记忆模型（按订单聚合）"""
    
    __tablename__ = "topic_memories"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    anonymous_user_id = Column(String, index=True, nullable=False)
    order_id = Column(String, index=True, nullable=False)
    
    # 主题信息
    topic = Column(String, nullable=False)  # refund/logistics/aftersale
    task = Column(String, nullable=True)
    
    # 状态
    last_status = Column(String, nullable=True)
    last_conclusion = Column(Text, nullable=True)
    unresolved_action = Column(String, nullable=True)
    
    # 上下文摘要
    context_summary = Column(Text, nullable=True)
    
    last_consulted_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<TopicMemory order={self.order_id} topic={self.topic}>"


class UserProfileMemory(Base):
    """用户长期记忆模型"""
    
    __tablename__ = "user_profile_memories"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    anonymous_user_id = Column(String, unique=True, index=True, nullable=False)
    
    # 偏好
    preferred_topics = Column(Text, nullable=True)  # JSON 字符串
    frequent_issue_types = Column(Text, nullable=True)  # JSON 字符串
    service_preferences = Column(Text, nullable=True)  # JSON 字符串
    
    # 未完成事项
    unresolved_ticket_ids = Column(Text, nullable=True)  # JSON 字符串
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<UserProfileMemory {self.anonymous_user_id}>"
