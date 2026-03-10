from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """创建匿名用户请求"""
    username: str = Field(..., min_length=1, max_length=50, description="用户名")


class UserResponse(BaseModel):
    """匿名用户响应"""
    anonymous_user_id: str
    anonymous_user_token: str
    username: str
    
    class Config:
        from_attributes = True


class UserInitResponse(BaseModel):
    """初始化响应"""
    anonymous_user_id: str
    anonymous_user_token: str
    username: str
    session_id: str
