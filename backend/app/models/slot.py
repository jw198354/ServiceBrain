from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from .database import Base
import uuid


class Slot(Base):
    """槽位模型"""
    
    __tablename__ = "slots"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.session_id"), index=True, nullable=False)
    slot_name = Column(String, nullable=False)  # order_id/refund_reason 等
    slot_value = Column(Text, nullable=True)
    status = Column(String, default="pending")  # pending/filled
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<Slot {self.slot_name}={self.slot_value}>"
