"""
Mock 后端桩 - 用于测试时模拟后端服务响应
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field


@dataclass
class StubConfig:
    """桩配置"""
    tool_name: str
    params: Dict[str, Any]
    response: Dict[str, Any]


class MockBackendStubs:
    """Mock 后端桩管理器"""

    def __init__(self):
        self._stubs: Dict[str, Dict[str, Any]] = {}

    def load_from_config(self, config: Dict[str, Any]):
        """从测试配置加载桩"""
        self._stubs = config.get("backend_stubs", {})

    def get_tool_response(self, tool_name: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """获取工具调用的模拟响应"""
        tool_stubs = self._stubs.get(tool_name, {})

        # 尝试根据参数匹配
        for key, response in tool_stubs.items():
            # key 可以是订单号等标识
            if key in str(params):
                return response

        # 默认响应
        return self._get_default_response(tool_name)

    def _get_default_response(self, tool_name: str) -> Dict[str, Any]:
        """获取默认响应"""
        defaults = {
            "refund_apply": {
                "result": "success",
                "message": "退款申请已提交",
                "refund_id": "REF123456"
            },
            "refund_status_query": {
                "status": "processing",
                "message": "退款正在处理中"
            },
            "refund_check": {
                "eligible": True,
                "message": "该订单符合退款条件"
            },
            "knowledge_search": {
                "hit": False,
                "message": "未找到相关知识"
            },
            "ticket_create": {
                "result": "success",
                "ticket_id": "TK123456"
            }
        }
        return defaults.get(tool_name, {"result": "unknown"})


class MockToolService:
    """Mock 工具服务 - 用于测试时替换真实工具服务"""

    def __init__(self, stubs: MockBackendStubs):
        self.stubs = stubs
        self.triggered_tools: list = []
        self.db = None  # 兼容接口

    async def apply_refund(
        self,
        session_id: str,
        anonymous_user_id: str,
        order_id: str,
        reason: Optional[str] = None
    ):
        """Mock 申请退款"""
        from app.services.tool_service import RefundToolResult
        from app.models.tool_record import ToolStatus

        self.triggered_tools.append({
            "tool": "refund_apply",
            "params": {"order_id": order_id, "reason": reason}
        })

        # 从 stubs 获取响应
        stub_response = self.stubs.get_tool_response("refund_apply", {"order_id": order_id})

        if stub_response:
            result_status = stub_response.get("result", "success")
            status_map = {
                "success": "success",
                "system_error": "fail",
                "error": "fail",
                "not_allowed": "not_allowed",
                "need_more_info": "need_more_info"
            }
            return RefundToolResult(
                status=status_map.get(result_status, "success"),
                code=stub_response.get("code", "RESULT"),
                message=stub_response.get("message", "处理完成"),
                detail={"order_id": order_id, "stub_response": stub_response}
            )

        # 默认成功
        return RefundToolResult(
            status="success",
            code="REFUND_SUCCESS",
            message="退款申请已提交",
            detail={"order_id": order_id, "refund_amount": 99.0, "estimated_days": "1-3 个工作日到账"}
        )

    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具（Mock 版本）"""
        self.triggered_tools.append({
            "tool": tool_name,
            "params": params
        })

        response = self.stubs.get_tool_response(tool_name, params)
        return response or {"result": "error", "message": "No stub configured"}

    def get_triggered_tools(self) -> List[Dict[str, Any]]:
        """获取已触发的工具列表"""
        return self.triggered_tools

    def clear_triggered_tools(self):
        """清空已触发工具记录"""
        self.triggered_tools = []
