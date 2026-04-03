from pydantic import BaseModel, Field, ConfigDict, field_validator


class UserCreate(BaseModel):
    """创建匿名用户请求"""
    username: str = Field(..., min_length=1, max_length=50, description="用户名")

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("用户名不能为空")
        return normalized


class UserResponse(BaseModel):
    """匿名用户响应"""
    anonymous_user_id: str
    anonymous_user_token: str
    username: str
    model_config = ConfigDict(from_attributes=True)


class UserInitResponse(BaseModel):
    """初始化响应"""
    anonymous_user_id: str
    anonymous_user_token: str
    username: str
    session_id: str
