"""
P0 功能测试用例
测试工具结果卡片和工单兜底功能
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.services.orchestrator_service import OrchestratorService
from app.services.rule_service import RuleDecision, RuleResult
from app.models.session import Session, SessionStatus


class TestToolResultCard:
    """测试工具结果卡片功能"""
    
    @pytest.fixture
    def mock_session(self):
        """创建模拟会话"""
        session = Mock(spec=Session)
        session.session_id = "test_session_001"
        session.anonymous_user_id = "test_user_001"
        session.current_topic = "refund"
        session.current_task = "execute"
        session.current_order_id = "ORD12345678"
        session.pending_slot = None
        session.tool_status = None
        return session
    
    @pytest.fixture
    def mock_user(self):
        """创建模拟用户"""
        user = Mock()
        user.username = "测试用户"
        return user
    
    @pytest.mark.asyncio
    async def test_refund_execute_success_card(self, mock_session, mock_user):
        """测试退款执行成功返回 success 卡片"""
        # 准备
        db = AsyncMock()
        service = OrchestratorService(db)
        
        # Mock 规则服务 - 允许执行
        service.rule_service.check_refund_execution_allowed = Mock(
            return_value=RuleResult(decision=RuleDecision.ALLOW, reason="")
        )
        
        # Mock 工具服务 - 返回成功
        tool_result = Mock()
        tool_result.status = "success"
        tool_result.message = "退款申请已提交"
        service.tool_service.apply_refund = AsyncMock(return_value=tool_result)
        
        # Mock 记忆服务
        service.memory_service.update_working_memory = AsyncMock(return_value=mock_session)
        
        # 执行
        intent_result = {
            "topic": "refund",
            "task": "execute",
            "missing_slots": [],
            "confidence": 0.9
        }
        
        result = await service._handle_refund_execute(
            mock_session, mock_user, "帮我退款", intent_result, "trace_001"
        )
        
        # 验证
        assert result["type"] == "bot_message"
        assert result["payload"]["message_type"] == "tool_result_card"
        assert result["payload"]["card"]["status"] == "success"
        assert "退款申请已提交" in result["payload"]["card"]["title"]
        assert "ORD12345678" in result["payload"]["card"]["description"]
        assert len(result["payload"]["card"]["actions"]) == 2
        print("✅ 测试通过：退款执行成功返回 success 卡片")
    
    @pytest.mark.asyncio
    async def test_refund_execute_not_allowed_card(self, mock_session, mock_user):
        """测试退款执行被拒绝返回 not_allowed 卡片"""
        # 准备
        db = AsyncMock()
        service = OrchestratorService(db)
        
        # Mock 规则服务 - 拒绝执行
        service.rule_service.check_refund_execution_allowed = Mock(
            return_value=RuleResult(
                decision=RuleDecision.DENY,
                reason="订单已超过售后申请时效"
            )
        )
        
        # 执行
        intent_result = {
            "topic": "refund",
            "task": "execute",
            "missing_slots": [],
            "confidence": 0.9
        }
        
        result = await service._handle_refund_execute(
            mock_session, mock_user, "帮我退款", intent_result, "trace_001"
        )
        
        # 验证
        assert result["payload"]["message_type"] == "tool_result_card"
        assert result["payload"]["card"]["status"] == "not_allowed"
        assert "当前暂不支持退款" in result["payload"]["card"]["title"]
        assert "超过售后申请时效" in result["payload"]["card"]["description"]
        print("✅ 测试通过：退款执行被拒绝返回 not_allowed 卡片")
    
    @pytest.mark.asyncio
    async def test_refund_execute_fail_card_with_ticket(self, mock_session, mock_user):
        """测试退款执行失败返回 fail 卡片并触发工单"""
        # 准备
        db = AsyncMock()
        service = OrchestratorService(db)
        
        # Mock 规则服务 - 允许执行
        service.rule_service.check_refund_execution_allowed = Mock(
            return_value=RuleResult(decision=RuleDecision.ALLOW, reason="")
        )
        
        # Mock 工具服务 - 返回失败
        tool_result = Mock()
        tool_result.status = "fail"
        tool_result.message = "系统异常，请稍后重试"
        service.tool_service.apply_refund = AsyncMock(return_value=tool_result)
        
        # Mock 记忆服务
        service.memory_service.update_working_memory = AsyncMock(return_value=mock_session)
        
        # Mock 工单服务 - 返回工单
        ticket = Mock()
        ticket.ticket_id = "TKT001"
        service.ticket_service.create_ticket = AsyncMock(return_value=ticket)
        
        # 执行
        intent_result = {
            "topic": "refund",
            "task": "execute",
            "missing_slots": [],
            "confidence": 0.9
        }
        
        result = await service._handle_refund_execute(
            mock_session, mock_user, "帮我退款", intent_result, "trace_001"
        )
        
        # 验证
        assert result["payload"]["message_type"] == "ticket_card"
        assert "退款处理未完成" in result["payload"]["card"]["title"]
        assert result["payload"]["card"]["status"] == "ticket_suggested"
        print("✅ 测试通过：退款执行失败触发工单兜底")


class TestMessageTypes:
    """测试消息类型区分"""
    
    @pytest.fixture
    def mock_session(self):
        session = Mock(spec=Session)
        session.session_id = "test_session_001"
        session.anonymous_user_id = "test_user_001"
        session.current_topic = "unknown"
        session.current_task = "chat"
        session.current_order_id = None
        session.pending_slot = None
        return session
    
    @pytest.fixture
    def mock_user(self):
        user = Mock()
        user.username = "测试用户"
        return user
    
    @pytest.mark.asyncio
    async def test_followup_message_type(self, mock_session, mock_user):
        """测试追问消息类型为 bot_followup"""
        db = AsyncMock()
        service = OrchestratorService(db)
        service.memory_service.update_working_memory = AsyncMock()
        
        working_memory = {"current_topic": "refund", "current_task": "execute"}
        result = await service._handle_followup(
            mock_session, mock_user, working_memory, "order_id", "trace_001"
        )
        
        assert result["payload"]["message_type"] == "bot_followup"
        print("✅ 测试通过：追问消息类型为 bot_followup")
    
    @pytest.mark.asyncio
    async def test_explain_message_type(self, mock_session, mock_user):
        """测试解释消息类型为 bot_explain"""
        db = AsyncMock()
        service = OrchestratorService(db)
        service.memory_service.get_topic_memory = AsyncMock(return_value=None)
        service.memory_service.upsert_topic_memory = AsyncMock()
        
        intent_result = {"topic": "refund", "task": "explain"}
        working_memory = {"current_order_id": "ORD12345678"}
        
        result = await service._handle_refund_explain(
            mock_session, mock_user, "为什么不能退款", intent_result, working_memory, "trace_001"
        )
        
        assert result["payload"]["message_type"] == "bot_explain"
        print("✅ 测试通过：解释消息类型为 bot_explain")
    
    @pytest.mark.asyncio
    async def test_knowledge_message_type(self, mock_session, mock_user):
        """测试知识消息类型为 bot_knowledge"""
        db = AsyncMock()
        service = OrchestratorService(db)
        service.memory_service.get_topic_memory = AsyncMock(return_value=None)
        
        intent_result = {"topic": "refund", "task": "consult"}
        
        result = await service._handle_refund_consult(
            mock_session, mock_user, "退款规则是什么", intent_result, "trace_001"
        )
        
        assert result["payload"]["message_type"] == "bot_knowledge"
        print("✅ 测试通过：知识消息类型为 bot_knowledge")


class TestTicketFallback:
    """测试工单兜底功能"""
    
    @pytest.mark.asyncio
    async def test_user_rejection_detection(self):
        """测试用户不接受结果检测"""
        db = AsyncMock()
        service = OrchestratorService(db)
        
        # 测试各种不接受表达
        rejection_phrases = ["不接受", "不满意", "不行", "不对", "有误", "投诉", "人工", "找客服"]
        
        for phrase in rejection_phrases:
            result = service._check_user_rejection(f"我觉得这个结果{phrase}")
            assert result == True, f"应该检测到 '{phrase}' 为不接受表达"
        
        # 测试正常表达
        normal_phrases = ["好的", "明白了", "谢谢", "知道了"]
        for phrase in normal_phrases:
            result = service._check_user_rejection(phrase)
            assert result == False, f"不应该将 '{phrase}' 检测为不接受"
        
        print("✅ 测试通过：用户不接受结果检测正确")
    
    @pytest.mark.asyncio
    async def test_low_confidence_triggers_ticket(self):
        """测试低置信度触发工单"""
        db = AsyncMock()
        service = OrchestratorService(db)
        
        session = Mock()
        session.session_id = "test_session"
        
        working_memory = {"recent_messages": []}
        
        # 低置信度应触发工单
        should_ticket, reason = await service._should_trigger_ticket(
            session, working_memory, "blah blah", 0.2
        )
        
        assert should_ticket == True
        assert "无法识别" in reason
        print("✅ 测试通过：低置信度触发工单")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
