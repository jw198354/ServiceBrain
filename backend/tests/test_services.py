"""
服务层单元测试
测试 UserService 和 SessionService
"""
import pytest
from app.models.user import AnonymousUser
from app.models.session import Session, SessionStatus
from app.services.user_service import UserService
from app.services.session_service import SessionService
from app.schemas.user import UserCreate


class TestUserService:
    """用户服务测试"""
    
    @pytest.mark.asyncio
    async def test_create_anonymous_user(self, test_db):
        """测试创建匿名用户"""
        user_service = UserService(test_db)
        user_data = UserCreate(username="test_user_001")
        
        user = await user_service.create_anonymous_user(user_data)
        
        assert user.username == "test_user_001"
        assert user.anonymous_user_id is not None
        assert user.anonymous_user_token is not None
        assert user.anonymous_user_token.startswith("sb_")
    
    @pytest.mark.asyncio
    async def test_create_user_trims_whitespace(self, test_db):
        """测试用户名自动去除空格"""
        user_service = UserService(test_db)
        user_data = UserCreate(username="  spaced_user  ")
        
        user = await user_service.create_anonymous_user(user_data)
        
        assert user.username == "spaced_user"
    
    @pytest.mark.asyncio
    async def test_get_user_by_token(self, test_db):
        """测试通过 token 获取用户"""
        user_service = UserService(test_db)
        user_data = UserCreate(username="token_lookup_user")
        
        created_user = await user_service.create_anonymous_user(user_data)
        
        # 通过 token 查找
        found_user = await user_service.get_user_by_token(created_user.anonymous_user_token)
        
        assert found_user is not None
        assert found_user.anonymous_user_id == created_user.anonymous_user_id
        assert found_user.username == "token_lookup_user"
    
    @pytest.mark.asyncio
    async def test_get_user_by_invalid_token(self, test_db):
        """测试无效 token 返回 None"""
        user_service = UserService(test_db)
        
        found_user = await user_service.get_user_by_token("invalid_token_xyz")
        
        assert found_user is None
    
    @pytest.mark.asyncio
    async def test_get_user_by_id(self, test_db):
        """测试通过 ID 获取用户"""
        user_service = UserService(test_db)
        user_data = UserCreate(username="id_lookup_user")
        
        created_user = await user_service.create_anonymous_user(user_data)
        
        # 通过 ID 查找
        found_user = await user_service.get_user_by_id(created_user.anonymous_user_id)
        
        assert found_user is not None
        assert found_user.anonymous_user_id == created_user.anonymous_user_id
    
    @pytest.mark.asyncio
    async def test_token_uniqueness(self, test_db):
        """测试每个用户 token 唯一"""
        user_service = UserService(test_db)
        
        tokens = set()
        for i in range(5):
            user_data = UserCreate(username=f"user_{i}")
            user = await user_service.create_anonymous_user(user_data)
            assert user.anonymous_user_token not in tokens
            tokens.add(user.anonymous_user_token)


class TestSessionService:
    """会话服务测试"""
    
    @pytest.mark.asyncio
    async def test_create_session(self, test_db):
        """测试创建会话"""
        # 先创建用户
        user_service = UserService(test_db)
        user = await user_service.create_anonymous_user(UserCreate(username="session_test_user"))
        
        session_service = SessionService(test_db)
        session = await session_service.create_session(user.anonymous_user_id)
        
        assert session.anonymous_user_id == user.anonymous_user_id
        assert session.status == SessionStatus.CREATING
        assert session.session_id is not None
    
    @pytest.mark.asyncio
    async def test_get_session(self, test_db):
        """测试获取会话"""
        user_service = UserService(test_db)
        user = await user_service.create_anonymous_user(UserCreate(username="get_session_user"))
        
        session_service = SessionService(test_db)
        created_session = await session_service.create_session(user.anonymous_user_id)
        
        # 获取会话
        retrieved_session = await session_service.get_session(created_session.session_id)
        
        assert retrieved_session is not None
        assert retrieved_session.session_id == created_session.session_id
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, test_db):
        """测试获取不存在的会话返回 None"""
        session_service = SessionService(test_db)
        
        session = await session_service.get_session("nonexistent_session_id")
        
        assert session is None
    
    @pytest.mark.asyncio
    async def test_activate_session(self, test_db):
        """测试激活会话"""
        user_service = UserService(test_db)
        user = await user_service.create_anonymous_user(UserCreate(username="activate_user"))
        
        session_service = SessionService(test_db)
        session = await session_service.create_session(user.anonymous_user_id)
        
        assert session.status == SessionStatus.CREATING
        
        # 激活会话
        activated = await session_service.activate_session(session)
        
        assert activated.status == SessionStatus.ACTIVE
    
    @pytest.mark.asyncio
    async def test_update_session_status(self, test_db):
        """测试更新会话状态"""
        user_service = UserService(test_db)
        user = await user_service.create_anonymous_user(UserCreate(username="update_status_user"))
        
        session_service = SessionService(test_db)
        session = await session_service.create_session(user.anonymous_user_id)
        
        # 更新多个字段
        updated = await session_service.update_session_status(
            session,
            status=SessionStatus.ACTIVE,
            topic="refund",
            task="execute",
        )
        
        assert updated.status == SessionStatus.ACTIVE
        assert updated.current_topic == "refund"
        assert updated.current_task == "execute"
    
    @pytest.mark.asyncio
    async def test_update_session_partial(self, test_db):
        """测试部分更新会话"""
        user_service = UserService(test_db)
        user = await user_service.create_anonymous_user(UserCreate(username="partial_update_user"))
        
        session_service = SessionService(test_db)
        session = await session_service.create_session(user.anonymous_user_id)
        
        # 只更新 topic
        updated = await session_service.update_session_status(
            session,
            topic="logistics",
        )
        
        assert updated.current_topic == "logistics"
        assert updated.status == SessionStatus.CREATING  # 状态不变
