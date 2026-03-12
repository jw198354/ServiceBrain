"""
工具服务 - Tool 调用代理

负责：
- 退款 Tool 代理调用
- 统一结果模型
- 超时与失败处理
- 幂等控制

Tool 不直接暴露给模型自由调用，由编排层根据规则决定是否调用。
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Dict, Any, List

# Python 3.6 compatibility
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal
from pydantic import BaseModel
from datetime import datetime
import uuid
import json

from app.models.tool_record import ToolRecord, ToolStatus


class RefundToolRequest(BaseModel):
    """退款工具请求"""
    session_id: str
    anonymous_user_id: str
    order_id: str
    reason: Optional[str] = None
    request_id: Optional[str] = None


class RefundToolResult(BaseModel):
    """退款工具结果"""
    status: Literal["success", "not_allowed", "need_more_info", "fail"]
    code: str
    message: str
    detail: Optional[Dict[str, Any]] = None


class ToolService:
    """工具调用服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        # Demo 阶段幂等键缓存（内存）
        self._idempotency_cache: Dict[str, RefundToolResult] = {}
    
    async def apply_refund(
        self,
        session_id: str,
        anonymous_user_id: str,
        order_id: str,
        reason: Optional[str] = None
    ) -> RefundToolResult:
        """
        申请退款
        
        Demo 阶段使用模拟逻辑：
        - 订单号以"1"开头 → 成功
        - 订单号以"2"开头 → 不可退款（超过时效）
        - 订单号以"3"开头 → 系统失败
        - 其他 → 需要更多信息
        """
        request_id = str(uuid.uuid4())
        
        # 1. 检查幂等（5 分钟内）
        idempotency_key = f"refund:{session_id}:{order_id}"
        if idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]
        
        # 2. 记录工具调用
        tool_record = ToolRecord(
            session_id=session_id,
            anonymous_user_id=anonymous_user_id,
            tool_name="refund",
            request_id=request_id,
            request_payload=json.dumps({
                "order_id": order_id,
                "reason": reason
            }),
            result_status=ToolStatus.PROCESSING.value,
        )
        self.db.add(tool_record)
        await self.db.commit()
        
        # 3. 模拟退款处理（Demo 逻辑）
        result = await self._mock_refund_process(order_id, reason)
        
        # 4. 更新工具记录
        tool_record.result_status = ToolStatus(result.status)
        tool_record.result_payload = json.dumps(result.model_dump())
        tool_record.processed_at = datetime.now()
        await self.db.commit()
        
        # 5. 缓存结果（幂等）
        self._idempotency_cache[idempotency_key] = result
        
        return result
    
    async def _mock_refund_process(
        self,
        order_id: str,
        reason: Optional[str] = None
    ) -> RefundToolResult:
        """
        模拟退款处理
        
        Demo 阶段根据订单号返回不同结果
        """
        # 订单号以"1"开头 → 成功
        if order_id.startswith("1"):
            return RefundToolResult(
                status="success",
                code="REFUND_SUCCESS",
                message="退款申请已提交",
                detail={
                    "order_id": order_id,
                    "refund_amount": 99.00,
                    "estimated_days": "1-3 个工作日到账"
                }
            )
        
        # 订单号以"2"开头 → 不可退款（超过时效）
        if order_id.startswith("2"):
            return RefundToolResult(
                status="not_allowed",
                code="REFUND_NOT_ALLOWED",
                message="该订单已超过售后申请时效",
                detail={
                    "order_id": order_id,
                    "reason": "超过 7 天售后时效",
                    "days_since_delivery": 15
                }
            )
        
        # 订单号以"3"开头 → 系统失败
        if order_id.startswith("3"):
            return RefundToolResult(
                status="fail",
                code="SYSTEM_ERROR",
                message="系统暂时处理失败，请稍后重试",
                detail={
                    "order_id": order_id,
                    "retry_after": "5 分钟"
                }
            )
        
        # 其他 → 需要更多信息
        return RefundToolResult(
            status="need_more_info",
            code="NEED_MORE_INFO",
            message="需要补充更多信息",
            detail={
                "order_id": order_id,
                "missing_fields": ["refund_reason", "product_issue"]
            }
        )
    
    async def get_tool_record(
        self,
        request_id: str
    ) -> Optional[ToolRecord]:
        """获取工具调用记录"""
        result = await self.db.execute(
            select(ToolRecord).where(ToolRecord.request_id == request_id)
        )
        return result.scalar_one_or_none()
    
    async def get_session_tool_records(
        self,
        session_id: str,
        limit: int = 10
    ) -> List[ToolRecord]:
        """获取会话的工具调用记录"""
        result = await self.db.execute(
            select(ToolRecord)
            .where(ToolRecord.session_id == session_id)
            .order_by(ToolRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    def result_to_card_payload(
        self,
        result: RefundToolResult,
        session_id: str
    ) -> Dict[str, Any]:
        """
        将工具结果转换为前端卡片消息 payload
        """
        if result.status == "success":
            return {
                "message_type": "tool_result_card",
                "card": {
                    "title": "退款申请已提交",
                    "description": result.message,
                    "status": "success",
                    "detail": result.detail,
                    "actions": [
                        {
                            "label": "查看退款进度",
                            "action": "check_refund_status",
                            "payload": {"session_id": session_id}
                        },
                        {
                            "label": "继续提问",
                            "action": "continue_chat",
                            "payload": {}
                        }
                    ]
                }
            }
        
        elif result.status == "not_allowed":
            return {
                "message_type": "tool_result_card",
                "card": {
                    "title": "当前暂不支持退款",
                    "description": result.message,
                    "status": "not_allowed",
                    "detail": result.detail,
                    "actions": [
                        {
                            "label": "了解原因",
                            "action": "ask_why",
                            "payload": {}
                        },
                        {
                            "label": "提交跟进请求",
                            "action": "create_ticket",
                            "payload": {"session_id": session_id}
                        }
                    ]
                }
            }
        
        elif result.status == "fail":
            return {
                "message_type": "tool_result_card",
                "card": {
                    "title": "本次处理未完成",
                    "description": result.message,
                    "status": "fail",
                    "detail": result.detail,
                    "actions": [
                        {
                            "label": "稍后重试",
                            "action": "retry",
                            "payload": {"session_id": session_id}
                        },
                        {
                            "label": "提交跟进请求",
                            "action": "create_ticket",
                            "payload": {"session_id": session_id}
                        }
                    ]
                }
            }
        
        else:  # need_more_info
            return {
                "message_type": "tool_result_card",
                "card": {
                    "title": "还需要补充信息",
                    "description": result.message,
                    "status": "need_more_info",
                    "detail": result.detail,
                    "actions": []
                }
            }
