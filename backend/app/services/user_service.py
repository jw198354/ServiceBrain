from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import AnonymousUser
from app.schemas.user import UserCreate, UserResponse
import uuid
import secrets


class UserService:
    """匿名用户服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_anonymous_user(self, user_data: UserCreate) -> UserResponse:
        """创建匿名用户"""
        # 生成 token
        token = f"sb_{secrets.token_urlsafe(32)}"
        
        user = AnonymousUser(
            username=user_data.username.strip(),
            anonymous_user_token=token,
        )
        
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        
        return UserResponse(
            anonymous_user_id=user.anonymous_user_id,
            anonymous_user_token=user.anonymous_user_token,
            username=user.username,
        )
    
    async def get_user_by_token(self, token: str):
        """通过 token 获取用户"""
        result = await self.db.execute(
            select(AnonymousUser).where(AnonymousUser.anonymous_user_token == token)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_id(self, user_id: str):
        """通过 user_id 获取用户"""
        result = await self.db.execute(
            select(AnonymousUser).where(AnonymousUser.anonymous_user_id == user_id)
        )
        return result.scalar_one_or_none()
