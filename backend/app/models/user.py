from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from .database import Base
import uuid


class AnonymousUser(Base):
    """匿名用户模型"""
    
    __tablename__ = "anonymous_users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    anonymous_user_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    anonymous_user_token = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<AnonymousUser {self.username}>"
