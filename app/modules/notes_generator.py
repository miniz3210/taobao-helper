"""
Notes Generator Module
Generates structured text notes with order summaries and change logs
"""
from datetime import datetime
from typing import List, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.system_log import SystemLog


class NotesGenerator:
    """Generates structured notes and summaries"""
    
    async def generate_notes(
        self, 
        session: AsyncSession,
        recent_changes: List[str] = None
    ) -> str:
        """
        Generate comprehensive notes file content
        """
        lines = []
        
        # Header
        lines.append("=" * 80)
        lines.append("TAOBAO & FREIGHT FORWARDING HELPER - NOTES")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        lines.append("")
        
        # Recent Changes Section
        if recent_changes:
            lines.append("📋 RECENT CHANGES")
            lines.append("-" * 80)
            for change in recent_changes[-20:]:  # Last 20 changes
                lines.append(f"  • {change}")
            lines.append("")
        
        # Orders by Status
        statuses = [
            ('pending_shipment', '📦 PENDING SHIPMENT'),
            ('in_transit', '🚚 IN TRANSIT'),
            ('received', '✅ RECEIVED AT HUB'),
        ]
        
        for status_key, status_title in statuses:
            result = await session.execute(
                select(Order)
                .where(Order.current_status == status_key)
                .order_by(Order.order_date.desc())
            )
            orders = result.scalars().all()
            
            lines.append(status_title)
            lines.append("-" * 80)
            
            if orders:
                for order in orders:
                    lines.append(f"  Order ID: {order.order_id}")
                    lines.append(f"  Item: {order.item_title[:60]}...")
                    lines.append(f"  Price: ¥{order.price} × {order.quantity}")
                    if order.seller_express_no:
                        lines.append(f"  Tracking: {order.seller_express_no}")
                    if order.forwarder_tracking_no:
                        lines.append(f"  Forwarder: {order.forwarder_tracking_no}")
                    lines.append("")
            else:
                lines.append("  (No items)")
                lines.append("")
        
        # Quick Copy Summary
        lines.append("=" * 80)
        lines.append("📋 ONE-CLICK COPY SUMMARY")
        lines.append("=" * 80)
        
        # Count by status
        for status_key, status_title in statuses:
            result = await session.execute(
                select(Order).where(Order.current_status == status_key)
            )
            count = len(result.scalars().all())
            lines.append(f"{status_title}: {count} items")
        
        lines.append("")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    async def get_status_summary(self, session: AsyncSession) -> Dict[str, int]:
        """Get count of orders by status"""
        summary = {}
        
        statuses = ['pending_shipment', 'in_transit', 'received', 'cancelled']
        
        for status in statuses:
            result = await session.execute(
                select(Order).where(Order.current_status == status)
            )
            summary[status] = len(result.scalars().all())
        
        return summary
