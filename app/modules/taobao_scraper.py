"""
Taobao Scraper & State Diff Module
Handles fetching orders from Taobao and detecting state changes
"""
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.system_log import SystemLog
from app.modules.image_archiver import ImageArchiver


class TaobaoScraper:
    """Scrapes Taobao order data and tracks state changes"""
    
    def __init__(self, image_archiver: ImageArchiver):
        self.image_archiver = image_archiver
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
    
    async def fetch_orders_from_taobao(self, cookies: str) -> List[Dict]:
        """
        Fetch orders from Taobao using session cookies
        This is a placeholder - actual implementation depends on Taobao's API/HTML structure
        
        Returns a list of order dictionaries with parsed data
        """
        # Note: This is a mock implementation. Real Taobao scraping would require:
        # 1. Valid session cookies
        # 2. Parsing actual Taobao HTML/API responses
        # 3. Handling pagination
        # 4. Anti-scraping measures (rate limiting, headers, etc.)
        
        orders = []
        
        try:
            # Parse cookies string into dict
            cookie_dict = self._parse_cookies(cookies)
            
            # Example: Fetch from Taobao bought items page
            # url = "https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm"
            # response = await self.client.get(url, cookies=cookie_dict)
            # soup = BeautifulSoup(response.text, 'html.parser')
            # orders = self._parse_order_html(soup)
            
            # For demo purposes, return empty list
            # Users will need to implement actual scraping logic based on Taobao's current structure
            
        except Exception as e:
            print(f"Error fetching orders from Taobao: {e}")
        
        return orders
    
    async def sync_orders(
        self, 
        session: AsyncSession, 
        scraped_orders: List[Dict]
    ) -> Tuple[int, int, List[str]]:
        """
        Sync scraped orders with database, detect changes
        Returns: (new_count, updated_count, change_logs)
        """
        new_count = 0
        updated_count = 0
        change_logs = []
        
        for order_data in scraped_orders:
            order_id = order_data.get('order_id')
            
            if not order_id:
                continue
            
            # Check if order exists
            result = await session.execute(
                select(Order).where(Order.order_id == order_id)
            )
            existing_order = result.scalar_one_or_none()
            
            if existing_order:
                # Update existing order and detect changes
                changes = await self._update_order(existing_order, order_data, session)
                if changes:
                    updated_count += 1
                    change_logs.extend(changes)
            else:
                # Create new order
                await self._create_order(order_data, session)
                new_count += 1
                change_logs.append(f"New order: {order_id} - {order_data.get('item_title', 'Unknown')}")
            
            # Download snapshot image if URL provided
            image_url = order_data.get('snapshot_url')
            if image_url:
                local_path = await self.image_archiver.download_and_save(image_url, order_id)
                if local_path and existing_order:
                    existing_order.snapshot_local_path = local_path
        
        await session.commit()
        
        return new_count, updated_count, change_logs
    
    async def _create_order(self, order_data: Dict, session: AsyncSession):
        """Create a new order in the database"""
        order = Order(
            order_id=order_data['order_id'],
            item_title=order_data.get('item_title', 'Unknown'),
            ai_clean_title=order_data.get('ai_clean_title'),
            price=order_data.get('price', 0.0),
            quantity=order_data.get('quantity', 1),
            seller_name=order_data.get('seller_name'),
            seller_express_no=order_data.get('seller_express_no'),
            carrier=order_data.get('carrier'),
            order_date=order_data.get('order_date'),
            pay_date=order_data.get('pay_date'),
            ship_date=order_data.get('ship_date'),
            receive_date=order_data.get('receive_date'),
            current_status=order_data.get('current_status', 'pending_shipment'),
            snapshot_local_path=order_data.get('snapshot_local_path'),
        )
        
        session.add(order)
        
        # Log creation
        log = SystemLog(
            log_type='scrape',
            order_id=order.order_id,
            message=f"New order created: {order.item_title}",
            metadata=json.dumps({'action': 'create'})
        )
        session.add(log)
    
    async def _update_order(
        self, 
        existing_order: Order, 
        order_data: Dict,
        session: AsyncSession
    ) -> List[str]:
        """
        Update existing order and detect changes
        Returns list of change descriptions
        """
        changes = []
        
        # Check status change
        new_status = order_data.get('current_status')
        if new_status and new_status != existing_order.current_status:
            changes.append(
                f"{existing_order.order_id}: Status changed from "
                f"'{existing_order.current_status}' to '{new_status}'"
            )
            existing_order.current_status = new_status
            
            # Log state change
            log = SystemLog(
                log_type='state_change',
                order_id=existing_order.order_id,
                message=f"Status changed: {existing_order.current_status} → {new_status}",
                metadata=json.dumps({
                    'old_status': existing_order.current_status,
                    'new_status': new_status
                })
            )
            session.add(log)
        
        # Update timeline dates if changed
        date_fields = ['order_date', 'pay_date', 'ship_date', 'receive_date']
        for field in date_fields:
            new_date = order_data.get(field)
            if new_date and getattr(existing_order, field) != new_date:
                changes.append(
                    f"{existing_order.order_id}: {field} updated to {new_date}"
                )
                setattr(existing_order, field, new_date)
        
        # Update other fields
        fields_to_update = [
            'item_title', 'price', 'quantity', 'seller_name', 
            'seller_express_no', 'carrier'
        ]
        
        for field in fields_to_update:
            new_value = order_data.get(field)
            if new_value and getattr(existing_order, field) != new_value:
                setattr(existing_order, field, new_value)
        
        return changes
    
    def _parse_cookies(self, cookies: str) -> Dict[str, str]:
        """Parse cookie string into dictionary"""
        cookie_dict = {}
        
        if not cookies:
            return cookie_dict
        
        # Handle different cookie formats
        if isinstance(cookies, dict):
            return cookies
        
        # Parse string format: "key1=value1; key2=value2"
        for item in cookies.split(';'):
            item = item.strip()
            if '=' in item:
                key, value = item.split('=', 1)
                cookie_dict[key.strip()] = value.strip()
        
        return cookie_dict
    
    async def manual_add_order(
        self,
        session: AsyncSession,
        order_data: Dict
    ) -> Order:
        """
        Manually add an order (for testing or manual entry)
        """
        order = Order(**order_data)
        session.add(order)
        await session.commit()
        await session.refresh(order)
        
        return order
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
