"""
工单服务 - 兜底工单处理

负责：
- 工单摘要生成
- 工单入库
- 工单提交
- 工单状态管理
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from app.models.ticket import Ticket, TicketStatus
from app.models.session import Session
from app.models.memory import SessionSummary


class TicketService:
    """工单管理服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_ticket(
        self,
        session_id: str,
        anonymous_user_id: str,
        summary: str,
        order_id: Optional[str] = None,
        topic: Optional[str] = None,
        fallback_reason: Optional[str] = None
    ) -> Ticket:
        """
        创建工单
        
        参数：
        - session_id: 会话 ID
        - anonymous_user_id: 匿名用户 ID
        - summary: 工单摘要
        - order_id: 相关订单号（可选）
        - topic: 问题主题
        - fallback_reason: 兜底原因
        """
        ticket = Ticket(
            session_id=session_id,
            anonymous_user_id=anonymous_user_id,
            summary=summary,
            order_id=order_id,
            topic=topic,
            fallback_reason=fallback_reason,
            status=TicketStatus.CREATED,
        )
        
        self.db.add(ticket)
        await self.db.commit()
        await self.db.refresh(ticket)
        
        return ticket
    
    async def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        """获取工单"""
        result = await self.db.execute(
            select(Ticket).where(Ticket.ticket_id == ticket_id)
        )
        return result.scalar_one_or_none()
    
    async def get_session_tickets(
        self,
        session_id: str,
        limit: int = 5
    ) -> List[Ticket]:
        """获取会话的工单列表"""
        result = await self.db.execute(
            select(Ticket)
            .where(Ticket.session_id == session_id)
            .order_by(Ticket.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def get_user_unresolved_tickets(
        self,
        anonymous_user_id: str,
        limit: int = 3
    ) -> List[Ticket]:
        """获取用户未解决工单"""
        result = await self.db.execute(
            select(Ticket)
            .where(
                Ticket.anonymous_user_id == anonymous_user_id,
                Ticket.status == TicketStatus.CREATED
            )
            .order_by(Ticket.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def update_ticket_status(
        self,
        ticket: Ticket,
        status: TicketStatus,
        processor_note: Optional[str] = None
    ) -> Ticket:
        """更新工单状态"""
        ticket.status = status
        if processor_note:
            ticket.processor_note = processor_note
        ticket.updated_at = datetime.now()
        
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket
    
    async def submit_ticket(
        self,
        ticket_id: str,
        additional_info: Optional[str] = None
    ) -> Optional[Ticket]:
        """
        提交工单（用户确认提交）
        
        Demo 阶段简化处理：直接标记为已提交
        """
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            return None
        
        # Demo 阶段：提交即完成
        ticket.status = TicketStatus.SUBMITTED
        if additional_info:
            ticket.summary = f"{ticket.summary}\n\n用户补充：{additional_info}"
        ticket.submitted_at = datetime.now()
        
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket
    
    def generate_ticket_summary(
        self,
        username: str,
        session_summary: Optional[str],
        recent_messages: List[Dict[str, Any]],
        order_id: Optional[str],
        current_topic: str,
        current_task: str,
        fallback_reason: str
    ) -> str:
        """
        生成工单摘要
        
        包含：
        - 用户名
        - 问题主题
        - 订单号（如有）
        - 最近对话摘要
        - 兜底原因
        """
        lines = [
            f"【用户】{username}",
            f"【主题】{current_topic}",
            f"【任务】{current_task}",
        ]
        
        if order_id:
            lines.append(f"【订单号】{order_id}")
        
        lines.append(f"【兜底原因】{fallback_reason}")
        
        # 添加对话摘要
        if session_summary:
            lines.append(f"\n【会话摘要】{session_summary}")
        
        # 添加最近消息（最多 3 条）
        if recent_messages:
            lines.append("\n【最近对话】")
            for msg in recent_messages[-3:]:
                role = "用户" if msg.get("role") == "user" else "机器人"
                content = msg.get("content", "")[:100]  # 限制长度
                lines.append(f"  - {role}: {content}")
        
        return "\n".join(lines)
    
    def create_ticket_card_payload(
        self,
        ticket: Ticket,
        show_actions: bool = True
    ) -> Dict[str, Any]:
        """
        生成工单卡片消息 payload
        
        用于前端渲染工单引导卡片
        """
        card = {
            "title": "建议提交跟进请求",
            "description": "当前问题机器人暂时无法直接完成处理，建议提交工单由专业人员跟进。",
            "summary": ticket.summary[:200],  # 限制长度
            "ticket_id": ticket.ticket_id,
            "status": ticket.status.value,
        }
        
        if show_actions:
            card["actions"] = [
                {
                    "label": "提交跟进请求",
                    "action": "submit_ticket",
                    "payload": {"ticket_id": ticket.ticket_id}
                },
                {
                    "label": "继续提问",
                    "action": "continue_chat",
                    "payload": {}
                }
            ]
        
        return {
            "message_type": "ticket_card",
            "card": card
        }
