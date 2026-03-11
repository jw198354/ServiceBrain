from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum
from sqlalchemy.sql import func
from .database import Base
import uuid
import enum


class ToolStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    NOT_ALLOWED = "not_allowed"
    FAIL = "fail"
    NEED_MORE_INFO = "need_more_info"


class ToolRecord(Base):
    """Tool 调用记录模型"""
    
    __tablename__ = "tool_records"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    record_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.session_id"), index=True, nullable=False)
    anonymous_user_id = Column(String, index=True, nullable=False)
    
    # Tool 信息
    tool_name = Column(String, nullable=False)  # refund
    request_id = Column(String, unique=True, index=True, nullable=False)
    request_payload = Column(Text, nullable=True)  # JSON 字符串
    
    # 结果
    result_status = Column(String, nullable=True)  # success/not_allowed/fail/need_more_info
    result_payload = Column(Text, nullable=True)  # JSON 字符串
    
    # 时间
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<ToolRecord {self.tool_name} status={self.result_status}>"
