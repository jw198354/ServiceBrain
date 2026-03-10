from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Enum
from sqlalchemy.sql import func
from .database import Base
import uuid
import enum


class TicketStatus(str, enum.Enum):
    SUGGESTED = "suggested"
    SUBMITTING = "submitting"
    CREATED = "created"
    FAILED = "failed"


class Ticket(Base):
    """工单模型"""
    
    __tablename__ = "tickets"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.session_id"), index=True, nullable=False)
    anonymous_user_id = Column(String, index=True, nullable=False)
    
    # 工单内容
    summary = Column(Text, nullable=False)
    issue_type = Column(String, nullable=True)
    order_id = Column(String, nullable=True)
    
    # 状态
    status = Column(Enum(TicketStatus), default=TicketStatus.SUGGESTED)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<Ticket {self.ticket_id} status={self.status}>"
