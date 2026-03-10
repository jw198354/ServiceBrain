"""
模型层单元测试
测试数据库模型的基本功能
"""
import pytest
import uuid
from datetime import datetime

from app.models.user import AnonymousUser
from app.models.session import Session, SessionStatus
from app.models.message import Message


class TestAnonymousUser:
    """匿名用户模型测试"""
    
    @pytest.mark.asyncio
    async def test_create_user(self, test_db):
        """测试创建匿名用户"""
        user = AnonymousUser(
            username="test_user",
            anonymous_user_token="test_token_123",
        )
        
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)
        
        assert user.username == "test_user"
        assert user.anonymous_user_token == "test_token_123"
        assert user.anonymous_user_id is not None
        assert isinstance(user.created_at, datetime)
    
    @pytest.mark.asyncio
    async def test_user_id_is_uuid(self, test_db):
        """测试 user_id 是 UUID 格式"""
        user = AnonymousUser(
            username="uuid_test",
            anonymous_user_token="token_uuid",
        )
        
        test_db.add(user)
        await test_db.commit()
        
        # 验证 UUID 格式
        try:
            uuid.UUID(user.anonymous_user_id)
        except ValueError:
            pytest.fail("anonymous_user_id 不是有效的 UUID")


class TestSession:
    """会话模型测试"""
    
    @pytest.mark.asyncio
    async def test_create_session(self, test_db):
        """测试创建会话"""
        # 先创建用户
        user = AnonymousUser(
            username="session_user",
            anonymous_user_token="token_session",
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)
        
        session = Session(
            anonymous_user_id=user.anonymous_user_id,
            status=SessionStatus.CREATING,
        )
        
        test_db.add(session)
        await test_db.commit()
        await test_db.refresh(session)
        
        assert session.anonymous_user_id == user.anonymous_user_id
        assert session.status == SessionStatus.CREATING
        assert session.current_topic == "unknown"
        assert session.current_task == "chat"
    
    @pytest.mark.asyncio
    async def test_session_status_enum(self, test_db):
        """测试会话状态枚举"""
        user = AnonymousUser(
            username="status_user",
            anonymous_user_token="token_status",
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)
        
        for status in SessionStatus:
            session = Session(
                anonymous_user_id=user.anonymous_user_id,
                status=status,
            )
            test_db.add(session)
            await test_db.commit()
            await test_db.refresh(session)
            
            assert session.status == status
            test_db.delete(session)
            await test_db.commit()
    
    @pytest.mark.asyncio
    async def test_session_update_status(self, test_db):
        """测试更新会话状态"""
        user = AnonymousUser(
            username="update_user",
            anonymous_user_token="token_update",
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)
        
        session = Session(
            anonymous_user_id=user.anonymous_user_id,
            status=SessionStatus.CREATING,
        )
        test_db.add(session)
        await test_db.commit()
        await test_db.refresh(session)
        
        # 更新状态
        session.status = SessionStatus.ACTIVE
        session.current_topic = "refund"
        await test_db.commit()
        await test_db.refresh(session)
        
        assert session.status == SessionStatus.ACTIVE
        assert session.current_topic == "refund"


class TestMessage:
    """消息模型测试"""
    
    @pytest.mark.asyncio
    async def test_create_message(self, test_db):
        """测试创建消息"""
        # 创建用户和会话
        user = AnonymousUser(
            username="msg_user",
            anonymous_user_token="token_msg",
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)
        
        session = Session(
            anonymous_user_id=user.anonymous_user_id,
        )
        test_db.add(session)
        await test_db.commit()
        await test_db.refresh(session)
        
        message = Message(
            session_id=session.session_id,
            message_type="user_text",
            content="Hello, this is a test message!",
            sender="user",
        )
        
        test_db.add(message)
        await test_db.commit()
        await test_db.refresh(message)
        
        assert message.content == "Hello, this is a test message!"
        assert message.message_type == "user_text"
        assert message.sender == "user"
        assert message.session_id == session.session_id
    
    @pytest.mark.asyncio
    async def test_message_types(self, test_db):
        """测试不同消息类型"""
        user = AnonymousUser(
            username="type_user",
            anonymous_user_token="token_type",
        )
        test_db.add(user)
        await test_db.commit()
        await test_db.refresh(user)
        
        session = Session(
            anonymous_user_id=user.anonymous_user_id,
        )
        test_db.add(session)
        await test_db.commit()
        await test_db.refresh(session)
        
        message_types = [
            "user_text", "bot_greeting", "bot_text", "bot_followup",
            "tool_result_card", "ticket_card", "error_message"
        ]
        
        for msg_type in message_types:
            message = Message(
                session_id=session.session_id,
                message_type=msg_type,
                content="Test " + msg_type,
                sender="user",
            )
            test_db.add(message)
            await test_db.commit()
            await test_db.refresh(message)
            
            assert message.message_type == msg_type
            test_db.delete(message)
            await test_db.commit()
