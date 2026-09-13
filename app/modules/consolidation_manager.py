"""
Consolidation Manager Module
Handles freight forwarding consolidation and customs export
"""
from typing import List, Dict
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.forwarder import ForwarderTracking
from app.models.system_log import SystemLog
from app.modules.backup_export_engine import BackupExportEngine


class ConsolidationManager:
    """Manages freight forwarding consolidation operations"""
    
    def __init__(self):
        self.backup_engine = BackupExportEngine()
    
    async def bind_orders_to_forwarder(
        self,
        session: AsyncSession,
        order_ids: List[str],
        tracking_no: str
    ) -> Dict:
        """
        Bind multiple orders to a forwarder tracking number
        """
        # Create or get forwarder tracking
        result = await session.execute(
            select(ForwarderTracking).where(ForwarderTracking.tracking_no == tracking_no)
        )
        forwarder = result.scalar_one_or_none()
        
        if not forwarder:
            forwarder = ForwarderTracking(
                tracking_no=tracking_no,
                status='pending_consolidation',
                consolidation_date=datetime.now()
            )
            session.add(forwarder)
        
        # Update orders
        bound_count = 0
        for order_id in order_ids:
            result = await session.execute(
                select(Order).where(Order.order_id == order_id)
            )
            order = result.scalar_one_or_none()
            
            if order:
                order.forwarder_tracking_no = tracking_no
                bound_count += 1
                
                # Log binding
                log = SystemLog(
                    log_type='consolidation',
                    order_id=order_id,
                    message=f"Bound to forwarder tracking: {tracking_no}"
                )
                session.add(log)
        
        await session.commit()
        
        return {
            'tracking_no': tracking_no,
            'bound_count': bound_count,
            'status': forwarder.status
        }
    
    async def update_forwarder_status(
        self,
        session: AsyncSession,
        tracking_no: str,
        new_status: str
    ) -> ForwarderTracking:
        """
        Update forwarder tracking status
        """
        result = await session.execute(
            select(ForwarderTracking).where(ForwarderTracking.tracking_no == tracking_no)
        )
        forwarder = result.scalar_one_or_none()
        
        if not forwarder:
            raise ValueError(f"Forwarder tracking not found: {tracking_no}")
        
        forwarder.status = new_status
        
        # Update timeline dates
        if new_status == 'consolidating' and not forwarder.consolidation_date:
            forwarder.consolidation_date = datetime.now()
        elif new_status == 'in_transit' and not forwarder.ship_date:
            forwarder.ship_date = datetime.now()
        elif new_status == 'delivered' and not forwarder.delivery_date:
            forwarder.delivery_date = datetime.now()
        
        await session.commit()
        await session.refresh(forwarder)
        
        return forwarder
    
    async def get_orders_by_forwarder(
        self,
        session: AsyncSession,
        tracking_no: str
    ) -> List[Order]:
        """
        Get all orders for a specific forwarder tracking number
        """
        result = await session.execute(
            select(Order).where(Order.forwarder_tracking_no == tracking_no)
        )
        return result.scalars().all()
    
    async def export_customs_declaration(
        self,
        session: AsyncSession,
        tracking_no: str
    ) -> str:
        """
        Export customs declaration sheet for a forwarder tracking
        """
        return await self.backup_engine.export_consolidation_sheet(
            session,
            tracking_no
        )
    
    async def get_all_forwarders(
        self,
        session: AsyncSession
    ) -> List[ForwarderTracking]:
        """
        Get all forwarder trackings
        """
        result = await session.execute(
            select(ForwarderTracking).order_by(ForwarderTracking.created_at.desc())
        )
        return result.scalars().all()
    
    async def unbind_order(
        self,
        session: AsyncSession,
        order_id: str
    ) -> bool:
        """
        Remove forwarder tracking binding from an order
        """
        result = await session.execute(
            select(Order).where(Order.order_id == order_id)
        )
        order = result.scalar_one_or_none()
        
        if order:
            order.forwarder_tracking_no = None
            await session.commit()
            return True
        
        return False
