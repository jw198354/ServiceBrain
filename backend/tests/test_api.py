"""
API 路由单元测试
测试 HTTP 接口
"""
import pytest
import json
from app.models.session import SessionStatus


class TestUserAPI:
    """用户相关 API 测试"""
    
    @pytest.mark.asyncio
    async def test_init_anonymous_user(self, test_client):
        """测试初始化匿名用户"""
        response = test_client.post(
            "/api/user/init-anonymous",
            json={"username": "api_test_user"},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "anonymous_user_id" in data
        assert "anonymous_user_token" in data
        assert data["username"] == "api_test_user"
        assert "session_id" in data
        assert data["anonymous_user_token"].startswith("sb_")
    
    @pytest.mark.asyncio
    async def test_init_user_with_whitespace(self, test_client):
        """测试用户名包含空格时自动修剪"""
        response = test_client.post(
            "/api/user/init-anonymous",
            json={"username": "  spaced_user  "},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["username"] == "spaced_user"
    
    @pytest.mark.asyncio
    async def test_init_user_empty_username(self, test_client):
        """测试空用户名"""
        response = test_client.post(
            "/api/user/init-anonymous",
            json={"username": ""},
        )
        
        # 空用户名应该被拒绝或处理
        assert response.status_code in [200, 422]


class TestSessionAPI:
    """会话相关 API 测试"""
    
    @pytest.mark.asyncio
    async def test_init_session(self, test_client):
        """测试初始化会话"""
        # 先创建用户
        user_response = test_client.post(
            "/api/user/init-anonymous",
            json={"username": "session_api_user"},
        )
        user_data = user_response.json()
        
        # 初始化会话
        session_response = test_client.post(
            "/api/session/init",
            json={
                "anonymous_user_id": user_data["anonymous_user_id"],
                "anonymous_user_token": user_data["anonymous_user_token"],
            },
        )
        
        assert session_response.status_code == 200
        data = session_response.json()
        
        assert "session_id" in data
        assert data["status"] == SessionStatus.ACTIVE.value
    
    @pytest.mark.asyncio
    async def test_init_session_invalid_token(self, test_client):
        """测试无效 token"""
        response = test_client.post(
            "/api/session/init",
            json={
                "anonymous_user_id": "fake_user_id",
                "anonymous_user_token": "fake_token",
            },
        )
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_init_session_user_mismatch(self, test_client):
        """测试用户 ID 不匹配"""
        # 创建用户
        user_response = test_client.post(
            "/api/user/init-anonymous",
            json={"username": "mismatch_user"},
        )
        user_data = user_response.json()
        
        # 使用错误的 user_id
        response = test_client.post(
            "/api/session/init",
            json={
                "anonymous_user_id": "wrong_user_id",
                "anonymous_user_token": user_data["anonymous_user_token"],
            },
        )
        
        assert response.status_code == 401


class TestMessageAPI:
    """消息相关 API 测试"""
    
    @pytest.mark.asyncio
    async def test_get_messages_empty(self, test_client):
        """测试获取空消息列表"""
        # 创建用户和会话
        user_response = test_client.post(
            "/api/user/init-anonymous",
            json={"username": "msg_user"},
        )
        user_data = user_response.json()
        
        # 获取消息（应该是空的）
        response = test_client.get(
            f"/api/session/{user_data['session_id']}/messages",
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "messages" in data
        assert isinstance(data["messages"], list)
        assert len(data["messages"]) == 0
    
    @pytest.mark.asyncio
    async def test_get_messages_with_limit(self, test_client):
        """测试获取消息带 limit 参数"""
        user_response = test_client.post(
            "/api/user/init-anonymous",
            json={"username": "limit_user"},
        )
        user_data = user_response.json()
        
        response = test_client.get(
            f"/api/session/{user_data['session_id']}/messages?limit=10",
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "messages" in data


class TestTicketAPI:
    """工单相关 API 测试"""
    
    @pytest.mark.asyncio
    async def test_create_ticket(self, test_client):
        """测试创建工单"""
        # 创建用户和会话
        user_response = test_client.post(
            "/api/user/init-anonymous",
            json={"username": "ticket_user"},
        )
        user_data = user_response.json()
        
        # 创建工单
        response = test_client.post(
            "/api/ticket/create",
            params={
                "session_id": user_data["session_id"],
                "summary": "Test ticket for refund issue",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "ticket_id" in data
        assert "status" in data
        assert data["message"] == "工单已创建"


class TestHealthCheck:
    """健康检查测试"""
    
    @pytest.mark.asyncio
    async def test_root_endpoint(self, test_client):
        """测试根路径"""
        response = test_client.get("/")
        
        # 应该返回 200 或 404（取决于是否有根路由）
        assert response.status_code in [200, 404]
    
    @pytest.mark.asyncio
    async def test_docs_endpoint(self, test_client):
        """测试 API 文档"""
        response = test_client.get("/docs")
        
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
