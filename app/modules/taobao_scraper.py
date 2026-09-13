"""
Taobao Scraper & State Diff Module
Handles fetching orders from Taobao and detecting state changes
"""
import json
import re
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
    
    # Tab URLs for different order statuses
    TAB_CONFIGS = {
        'all': {
            'url': 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm',
            'params': {}
        },
        'pending_payment': {
            'url': 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm',
            'params': {'action': 'itemlist/BoughtQueryAction', 'event_submit_do_query': '1', 'tabCode': 'waitPay'}
        },
        'pending_shipment': {
            'url': 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm',
            'params': {'action': 'itemlist/BoughtQueryAction', 'event_submit_do_query': '1', 'tabCode': 'waitSend'}
        },
        'in_transit': {
            'url': 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm',
            'params': {'action': 'itemlist/BoughtQueryAction', 'event_submit_do_query': '1', 'tabCode': 'waitConfirm'}
        },
        'pending_review': {
            'url': 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm',
            'params': {'action': 'itemlist/BoughtQueryAction', 'event_submit_do_query': '1', 'tabCode': 'waitRate'}
        }
    }
    
    def __init__(self, image_archiver: ImageArchiver):
        self.image_archiver = image_archiver
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
                'Referer': 'https://www.taobao.com/'
            }
        )
    
    async def fetch_orders_from_taobao(self, cookies: str) -> List[Dict]:
        """
        Fetch orders from Taobao using session cookies
        Iterates through all tabs and all pages
        
        Returns a list of order dictionaries with parsed data
        """
        all_orders = []
        cookie_dict = self._parse_cookies(cookies)
        
        print(f"\n{'='*80}")
        print(f"Starting Taobao scrape with cookies (length: {len(cookies)})")
        print(f"Cookie keys: {list(cookie_dict.keys())[:10]}")  # Show first 10 cookie names
        print(f"{'='*80}\n")
        
        # Iterate through all tabs
        for tab_name, tab_config in self.TAB_CONFIGS.items():
            print(f"\n{'='*60}")
            print(f"Scraping tab: {tab_name}")
            print(f"URL: {tab_config['url']}")
            print(f"Params: {tab_config['params']}")
            print(f"{'='*60}")
            
            try:
                page = 1
                has_more_pages = True
                
                while has_more_pages:
                    print(f"\n--- Fetching page {page} of {tab_name} ---")
                    
                    # Build URL with pagination
                    params = tab_config['params'].copy()
                    if page > 1:
                        params['pageNum'] = str(page)
                    
                    # Fetch page
                    try:
                        response = await self.client.get(
                            tab_config['url'],
                            params=params,
                            cookies=cookie_dict,
                            timeout=30.0
                        )
                        
                        print(f"Response status: {response.status_code}")
                        print(f"Response URL: {response.url}")
                        print(f"Response length: {len(response.text)} bytes")
                        
                    except Exception as e:
                        print(f"Request failed: {e}")
                        break
                    
                    if response.status_code != 200:
                        print(f"Failed to fetch {tab_name} page {page}: HTTP {response.status_code}")
                        break
                    
                    # Parse HTML
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Debug: Save first page HTML for inspection
                    if page == 1 and tab_name == 'all':
                        try:
                            with open('/app/data/debug_page.html', 'w', encoding='utf-8') as f:
                                f.write(response.text)
                            print("DEBUG: Saved page HTML to /app/data/debug_page.html")
                        except Exception as e:
                            print(f"Could not save debug HTML: {e}")
                    
                    # Check if we're still logged in
                    if self._check_login_required(soup):
                        print("❌ Login required - cookies may be invalid or expired")
                        print("Page title:", soup.title.string if soup.title else "No title")
                        # Print first 500 chars of page
                        print("Page preview:", response.text[:500])
                        return all_orders
                    
                    # Extract orders from this page
                    page_orders = self._parse_orders_from_page(soup, tab_name)
                    
                    if page_orders:
                        all_orders.extend(page_orders)
                        print(f"✅ Found {len(page_orders)} orders on page {page}")
                        # Print first order as example
                        if page_orders:
                            print(f"Example order: {page_orders[0].get('order_id')} - {page_orders[0].get('item_title', '')[:50]}")
                    else:
                        print(f"⚠️  No orders found on page {page}")
                    
                    # Check for next page
                    has_more_pages = self._has_next_page(soup)
                    print(f"Has next page: {has_more_pages}")
                    
                    if has_more_pages:
                        page += 1
                    else:
                        print(f"No more pages for {tab_name}")
                        break
                    
                    # Safety limit to prevent infinite loops
                    if page > 50:
                        print(f"⚠️  Reached page limit (50) for {tab_name}")
                        break
                        
            except Exception as e:
                print(f"❌ Error scraping {tab_name}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\n{'='*80}")
        print(f"✅ Total orders scraped: {len(all_orders)}")
        print(f"{'='*80}\n")
        return all_orders
    
    def _check_login_required(self, soup: BeautifulSoup) -> bool:
        """Check if page requires login"""
        # Check for login page indicators
        login_indicators = [
            soup.find('div', {'id': 'J_Static2Quick'}),  # Login form
            soup.find('input', {'name': 'TPL_username'}),  # Username field
            'login.taobao.com' in str(soup)[:1000]
        ]
        
        return any(login_indicators)
    
    def _parse_orders_from_page(self, soup: BeautifulSoup, tab_name: str) -> List[Dict]:
        """Parse orders from a single page"""
        orders = []
        
        # Try multiple selectors for order containers
        order_containers = []
        
        # Modern Taobao layout
        order_containers.extend(soup.find_all('div', class_=lambda x: x and 'index-mod__order-container' in x))
        
        # Legacy layout
        if not order_containers:
            order_containers.extend(soup.find_all('table', class_='item-list'))
        
        if not order_containers:
            order_containers.extend(soup.find_all('div', class_='js-order-container'))
        
        if not order_containers:
            order_containers.extend(soup.find_all('tbody', class_=lambda x: x and 'order' in str(x).lower()))
        
        print(f"Found {len(order_containers)} order containers")
        
        for container in order_containers:
            try:
                order_data = self._parse_single_order(container, tab_name)
                if order_data and order_data.get('order_id'):
                    orders.append(order_data)
            except Exception as e:
                print(f"Error parsing order container: {e}")
                continue
        
        return orders
    
    def _parse_single_order(self, container, tab_name: str) -> Optional[Dict]:
        """Parse a single order container"""
        order_data = {}
        
        # Extract Order ID
        order_id = self._extract_order_id(container)
        if not order_id:
            return None
        
        order_data['order_id'] = order_id
        
        # Extract Order Date
        order_data['order_date'] = self._extract_order_date(container)
        
        # Extract Store/Seller Name
        order_data['seller_name'] = self._extract_seller_name(container)
        
        # Extract Item Information
        item_info = self._extract_item_info(container)
        order_data.update(item_info)
        
        # Extract Status
        order_data['current_status'] = self._extract_status(container, tab_name)
        
        # Extract Tracking Number
        order_data['seller_express_no'] = self._extract_tracking_number(container)
        
        # Extract Snapshot URL
        order_data['snapshot_url'] = self._extract_snapshot_url(container)
        
        return order_data
    
    def _extract_order_id(self, container) -> Optional[str]:
        """Extract order ID"""
        # Try different selectors
        # Method 1: Find by class
        class_selectors = [
            container.find('span', {'class': lambda x: x and 'order-num' in str(x).lower()}),
            container.find('div', {'class': lambda x: x and 'head-info-line' in str(x)}),
        ]
        
        for element in class_selectors:
            if element:
                text = element.get_text(strip=True)
                # Extract number from text like "訂單號：123456789"
                match = re.search(r'(\d{15,})', text)
                if match:
                    return match.group(1)
        
        # Method 2: Find by text content
        text_elements = container.find_all('span')
        for element in text_elements:
            text = element.get_text(strip=True)
            if '訂單號' in text or '订单号' in text:
                match = re.search(r'(\d{15,})', text)
                if match:
                    return match.group(1)
        
        return None
    
    def _extract_order_date(self, container) -> Optional[datetime]:
        """Extract order date"""
        # Look for date patterns
        date_patterns = [
            r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})',  # YYYY-MM-DD or YYYY年MM月DD日
            r'(\d{4}\.\d{1,2}\.\d{1,2})',  # YYYY.MM.DD
        ]
        
        text = container.get_text()
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            if matches:
                date_str = matches[0]
                # Normalize date string
                date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '')
                date_str = date_str.replace('.', '-').replace('/', '-')
                
                try:
                    return datetime.strptime(date_str, '%Y-%m-%d')
                except:
                    pass
        
        return None
    
    def _extract_seller_name(self, container) -> Optional[str]:
        """Extract seller/store name"""
        selectors = [
            container.find('a', {'class': lambda x: x and 'seller' in str(x).lower()}),
            container.find('div', {'class': lambda x: x and 'seller' in str(x).lower()}),
            container.find('span', {'class': lambda x: x and 'shop' in str(x).lower()}),
        ]
        
        for element in selectors:
            if element:
                text = element.get_text(strip=True)
                if text and len(text) > 0:
                    return text
        
        return None
    
    def _extract_item_info(self, container) -> Dict:
        """Extract item title, price, and quantity"""
        info = {
            'item_title': 'Unknown Item',
            'price': 0.0,
            'quantity': 1
        }
        
        # Extract item title
        title_selectors = [
            container.find('a', {'class': lambda x: x and 'item-title' in str(x).lower()}),
            container.find('div', {'class': lambda x: x and 'item-title' in str(x).lower()}),
            container.find('p', {'class': lambda x: x and 'title' in str(x).lower()}),
            container.find('span', {'class': lambda x: x and 'item-mod__title' in str(x)}),
        ]
        
        for element in title_selectors:
            if element:
                title = element.get_text(strip=True)
                if title and len(title) > 3:
                    info['item_title'] = title
                    break
        
        # Extract price
        price_selectors = [
            container.find('strong', {'class': lambda x: x and 'price' in str(x).lower()}),
            container.find('span', {'class': lambda x: x and 'price' in str(x).lower()}),
            container.find('em', {'class': lambda x: x and 'price' in str(x).lower()}),
        ]
        
        for element in price_selectors:
            if element:
                price_text = element.get_text(strip=True)
                # Extract number from text like "¥123.45" or "123.45"
                match = re.search(r'(\d+\.?\d*)', price_text.replace(',', ''))
                if match:
                    try:
                        info['price'] = float(match.group(1))
                        break
                    except:
                        pass
        
        # Extract quantity
        qty_selectors = [
            container.find('span', text=lambda t: t and '數量' in str(t)),
            container.find('span', text=lambda t: t and '数量' in str(t)),
            container.find('div', {'class': lambda x: x and 'amount' in str(x).lower()}),
        ]
        
        for element in qty_selectors:
            if element:
                qty_text = element.get_text(strip=True)
                match = re.search(r'(\d+)', qty_text)
                if match:
                    try:
                        info['quantity'] = int(match.group(1))
                        break
                    except:
                        pass
        
        return info
    
    def _extract_status(self, container, tab_name: str) -> str:
        """Extract order status"""
        # Try to find status text
        status_selectors = [
            container.find('span', {'class': lambda x: x and 'status' in str(x).lower()}),
            container.find('div', {'class': lambda x: x and 'status' in str(x).lower()}),
            container.find('p', {'class': lambda x: x and 'status' in str(x).lower()}),
        ]
        
        status_text = ""
        for element in status_selectors:
            if element:
                status_text = element.get_text(strip=True)
                if status_text:
                    break
        
        # Map Chinese status to our status codes
        status_mapping = {
            '待付款': 'pending_payment',
            '等待買家付款': 'pending_payment',
            '待發貨': 'pending_shipment',
            '等待賣家發貨': 'pending_shipment',
            '賣家已發貨': 'in_transit',
            '待收貨': 'in_transit',
            '已發貨': 'in_transit',
            '待評價': 'received',
            '交易成功': 'received',
            '已收貨': 'received',
            '交易完成': 'received',
        }
        
        # Try to match status text
        for chinese, code in status_mapping.items():
            if chinese in status_text:
                return code
        
        # Fallback to tab name
        tab_status_mapping = {
            'pending_payment': 'pending_payment',
            'pending_shipment': 'pending_shipment',
            'in_transit': 'in_transit',
            'pending_review': 'received',
            'all': 'pending_shipment'
        }
        
        return tab_status_mapping.get(tab_name, 'pending_shipment')
    
    def _extract_tracking_number(self, container) -> Optional[str]:
        """Extract tracking/logistics number"""
        # Look for tracking number
        tracking_patterns = [
            r'(YT\d{13,})',  # YTO Express
            r'(SF\d{12,})',  # SF Express
            r'(\d{12,})',     # Generic tracking number
        ]
        
        text = container.get_text()
        
        for pattern in tracking_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_snapshot_url(self, container) -> Optional[str]:
        """Extract product image URL"""
        # Find image tags
        img_tags = container.find_all('img')
        
        for img in img_tags:
            src = img.get('src') or img.get('data-src')
            if src and ('jpg' in src.lower() or 'png' in src.lower()):
                # Ensure https
                if src.startswith('//'):
                    src = 'https:' + src
                elif not src.startswith('http'):
                    src = 'https:' + src
                
                return src
        
        return None
    
    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        """Check if there's a next page"""
        # Look for next page button
        next_buttons = [
            soup.find('a', {'class': lambda x: x and 'pagination-next' in str(x).lower()}),
            soup.find('a', text=lambda t: t and ('下一頁' in str(t) or '下一页' in str(t) or '下頁' in str(t))),
            soup.find('li', {'class': lambda x: x and 'next' in str(x).lower() and 'disabled' not in str(x).lower()}),
        ]
        
        for button in next_buttons:
            if button:
                # Check if button is disabled
                classes = button.get('class', [])
                if 'disabled' not in ' '.join(classes).lower():
                    return True
        
        return False
    
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
        
        print(f"\n=== Syncing {len(scraped_orders)} orders to database ===")
        
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
                change_logs.append(f"新訂單：{order_id} - {order_data.get('item_title', 'Unknown')}")
            
            # Download snapshot image if URL provided
            image_url = order_data.get('snapshot_url')
            if image_url:
                local_path = await self.image_archiver.download_and_save(image_url, order_id)
                if local_path:
                    if existing_order:
                        existing_order.snapshot_local_path = local_path
                    else:
                        # Update the newly created order
                        result = await session.execute(
                            select(Order).where(Order.order_id == order_id)
                        )
                        new_order = result.scalar_one_or_none()
                        if new_order:
                            new_order.snapshot_local_path = local_path
        
        await session.commit()
        
        print(f"Sync complete: {new_count} new, {updated_count} updated")
        
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
            message=f"新訂單建立：{order.item_title}",
            meta_data=json.dumps({'action': 'create'})
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
                f"{existing_order.order_id}: 狀態變更 "
                f"'{existing_order.current_status}' → '{new_status}'"
            )
            existing_order.current_status = new_status
            
            # Log state change
            log = SystemLog(
                log_type='state_change',
                order_id=existing_order.order_id,
                message=f"狀態變更：{existing_order.current_status} → {new_status}",
                meta_data=json.dumps({
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
                    f"{existing_order.order_id}: {field} 更新為 {new_date}"
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

