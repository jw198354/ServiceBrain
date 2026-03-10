from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from .database import Base
import uuid


class ToolRecord(Base):
    """Tool 调用记录模型"""
    
    __tablename__ = "tool_records"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    record_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.session_id"), index=True, nullable=False)
    
    # Tool 信息
    tool_name = Column(String, nullable=False)  # refund_tool
    tool_input = Column(Text, nullable=True)  # JSON 字符串
    
    # 结果
    tool_output = Column(Text, nullable=True)  # JSON 字符串
    status = Column(String, nullable=True)  # success/not_allowed/fail
    
    # 幂等键
    idempotency_key = Column(String, index=True, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<ToolRecord {self.tool_name} status={self.status}>"
