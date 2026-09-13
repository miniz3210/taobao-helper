"""
Taobao MTOP API Orders Fetcher
Intercepts MTOP API responses to extract order JSON directly
"""
from typing import List, Dict, Optional, Tuple
from playwright.async_api import async_playwright, Browser, Page, Response
import json
import re
from datetime import datetime
from pathlib import Path
import asyncio


class TaobaoMTOPFetcher:
    """Fetch Taobao orders by intercepting MTOP API responses"""
    
    def __init__(self, cookies_file: str = "/app/data/cookies.json"):
        self.cookies_file = cookies_file
    
    async def fetch_orders_with_cookies(self, cookies_json: str) -> Tuple[List[Dict], Optional[str]]:
        """
        Fetch orders by intercepting MTOP API responses
        
        Returns:
            Tuple[List[Dict], Optional[str]]: (orders, error_code)
        """
        all_orders = []
        error_code = None
        
        playwright = None
        browser = None
        page = None
        
        # Storage for intercepted API responses
        intercepted_orders = []
        
        try:
            # Load cookies
            cookies_path = Path(self.cookies_file)
            if not cookies_path.exists():
                return all_orders, "SESSION_INVALID"
            
            with open(self.cookies_file, 'r') as f:
                cookies_data = json.load(f)
            
            cookies = cookies_data.get('cookies', [])
            if not cookies:
                return all_orders, "SESSION_INVALID"
            
            print(f"\n{'='*80}")
            print(f"Starting MTOP API interception with {len(cookies)} cookies")
            print(f"{'='*80}\n")
            
            # Launch browser
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-TW',
                timezone_id='Asia/Taipei'
            )
            
            await context.add_cookies(cookies)
            page = await context.new_page()
            
            # Hide automation
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = { runtime: {} };
            """)
            
            # Set up response interceptor for MTOP API
            async def handle_response(response: Response):
                try:
                    url = response.url
                    # Check if this is an MTOP API call for orders
                    if 'mtop.taobao' in url and ('bought' in url.lower() or 'trade' in url.lower() or 'order' in url.lower()):
                        print(f"📡 Intercepted MTOP API: {url[:100]}...")
                        
                        try:
                            body = await response.text()
                            
                            # MTOP responses are often JSONP wrapped - extract JSON
                            json_match = re.search(r'\{.*\}', body, re.DOTALL)
                            if json_match:
                                data = json.loads(json_match.group(0))
                                
                                # Store intercepted data
                                intercepted_orders.append({
                                    'url': url,
                                    'data': data
                                })
                                
                                print(f"✅ Captured API response data")
                                
                        except Exception as e:
                            print(f"⚠️  Failed to parse API response: {e}")
                            
                except Exception as e:
                    pass  # Ignore errors in response handler
            
            page.on("response", handle_response)
            
            # Navigate to orders page
            print("🌐 Loading buyertrade.taobao.com...")
            await page.goto(
                'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm',
                wait_until='domcontentloaded',
                timeout=30000
            )
            
            # Wait for network to be idle (JavaScript finishes loading data)
            print("⏳ Waiting for network idle...")
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
                print("✅ Network idle")
            except:
                print("⚠️  Network idle timeout - continuing anyway")
            
            # Give extra time for any delayed API calls
            await page.wait_for_timeout(3000)
            
            # Check for redirects to login
            current_url = page.url
            if 'login' in current_url.lower():
                print("❌ Redirected to login page")
                return all_orders, "LOGIN_REQUIRED"
            
            print(f"📍 Final URL: {current_url}")
            print(f"📊 Intercepted {len(intercepted_orders)} API responses")
            
            # Parse intercepted API responses
            if intercepted_orders:
                all_orders = self._parse_mtop_responses(intercepted_orders)
                print(f"✅ Extracted {len(all_orders)} orders from API responses")
            
            # Fallback 1: Try to extract from window.__INITIAL_DATA__
            if not all_orders:
                print("🔍 Trying window.__INITIAL_DATA__ extraction...")
                initial_data_orders = await self._extract_from_initial_data(page)
                if initial_data_orders:
                    all_orders.extend(initial_data_orders)
                    print(f"✅ Extracted {len(initial_data_orders)} orders from __INITIAL_DATA__")
            
            # Fallback 2: Parse inline script tags
            if not all_orders:
                print("🔍 Trying inline script tag extraction...")
                script_orders = await self._extract_from_scripts(page)
                if script_orders:
                    all_orders.extend(script_orders)
                    print(f"✅ Extracted {len(script_orders)} orders from script tags")
            
            # Fallback 3: Regex on page content (last resort)
            if not all_orders:
                print("🔍 Trying regex fallback on page content...")
                content = await page.content()
                
                # Save for debugging
                with open('/app/data/mtop_page.html', 'w', encoding='utf-8') as f:
                    f.write(content)
                print("💾 Saved page to /app/data/mtop_page.html")
                
                # Extract order IDs
                order_ids = set(re.findall(r'\b(\d{15,})\b', content))
                for order_id in list(order_ids)[:50]:
                    all_orders.append({
                        'order_id': order_id,
                        'item_title': f'Order {order_id[:8]}...',
                        'price': 0.0,
                        'quantity': 1,
                        'current_status': 'pending_shipment',
                        'seller_name': None,
                        'seller_express_no': None,
                        'snapshot_url': None,
                        'order_date': None
                    })
                
                if order_ids:
                    print(f"✅ Regex found {len(order_ids)} order IDs")
            
            print(f"\n{'='*80}")
            print(f"✅ Total orders extracted: {len(all_orders)}")
            print(f"{'='*80}\n")
            
        except Exception as e:
            print(f"❌ Error in MTOP fetch: {e}")
            import traceback
            traceback.print_exc()
            error_code = "UNKNOWN_ERROR"
        
        finally:
            # Cleanup
            try:
                if page:
                    await page.close()
                if browser:
                    await browser.close()
                if playwright:
                    await playwright.stop()
            except:
                pass
        
        return all_orders, error_code
    
    def _parse_mtop_responses(self, responses: List[Dict]) -> List[Dict]:
        """Parse MTOP API responses to extract order data"""
        orders = []
        
        for response_data in responses:
            try:
                data = response_data['data']
                
                # Navigate through common MTOP response structures
                # MTOP responses usually have: {data: {data: {...}}} or {data: [...]}
                
                if 'data' in data:
                    inner_data = data['data']
                    
                    # Check if it's a list of orders
                    if isinstance(inner_data, list):
                        orders.extend(self._extract_orders_from_list(inner_data))
                    elif isinstance(inner_data, dict):
                        # Check for common order list keys
                        for key in ['mainOrders', 'orders', 'orderList', 'orderInfos', 'items']:
                            if key in inner_data and isinstance(inner_data[key], list):
                                orders.extend(self._extract_orders_from_list(inner_data[key]))
                                break
                
            except Exception as e:
                print(f"⚠️  Error parsing response: {e}")
                continue
        
        return orders
    
    def _extract_orders_from_list(self, order_list: List) -> List[Dict]:
        """Extract order dictionaries from a list of order objects"""
        orders = []
        
        for item in order_list:
            if not isinstance(item, dict):
                continue
            
            try:
                # Try to extract order ID
                order_id = None
                for key in ['orderId', 'order_id', 'id', 'bizOrderId', 'mainOrderId']:
                    if key in item:
                        order_id = str(item[key])
                        break
                
                if not order_id or len(order_id) < 15:
                    continue
                
                # Extract other fields
                order_data = {
                    'order_id': order_id,
                    'item_title': self._extract_title(item),
                    'price': self._extract_price(item),
                    'quantity': self._extract_quantity(item),
                    'current_status': self._extract_status(item),
                    'seller_name': self._extract_seller(item),
                    'seller_express_no': self._extract_tracking(item),
                    'snapshot_url': self._extract_image(item),
                    'order_date': self._extract_date(item)
                }
                
                orders.append(order_data)
                
            except Exception as e:
                continue
        
        return orders
    
    def _extract_title(self, item: Dict) -> str:
        """Extract item title from order object"""
        for key in ['title', 'itemTitle', 'goodsTitle', 'productTitle', 'itemName']:
            if key in item:
                return str(item[key])[:200]
        
        # Check nested structures
        if 'itemInfo' in item and isinstance(item['itemInfo'], dict):
            return self._extract_title(item['itemInfo'])
        
        return 'Unknown Item'
    
    def _extract_price(self, item: Dict) -> float:
        """Extract price from order object"""
        for key in ['actualFee', 'payment', 'totalFee', 'price', 'realTotalFee']:
            if key in item:
                try:
                    # Prices might be in cents (integer) or yuan (float/string)
                    val = item[key]
                    if isinstance(val, str):
                        val = float(val.replace('¥', '').replace(',', ''))
                    return float(val) if float(val) < 10000 else float(val) / 100
                except:
                    continue
        return 0.0
    
    def _extract_quantity(self, item: Dict) -> int:
        """Extract quantity from order object"""
        for key in ['quantity', 'num', 'amount', 'buyAmount']:
            if key in item:
                try:
                    return int(item[key])
                except:
                    continue
        return 1
    
    def _extract_status(self, item: Dict) -> str:
        """Extract and map order status"""
        status_map = {
            'WAIT_BUYER_PAY': 'pending_payment',
            'WAIT_SELLER_SEND_GOODS': 'pending_shipment',
            'WAIT_BUYER_CONFIRM_GOODS': 'in_transit',
            'TRADE_FINISHED': 'received',
            'TRADE_CLOSED': 'cancelled',
        }
        
        for key in ['status', 'orderStatus', 'statusCode', 'tradeStatus']:
            if key in item:
                status_val = str(item[key])
                return status_map.get(status_val, 'pending_shipment')
        
        return 'pending_shipment'
    
    def _extract_seller(self, item: Dict) -> Optional[str]:
        """Extract seller name"""
        for key in ['sellerNick', 'shopName', 'seller_nick', 'shopTitle']:
            if key in item:
                return str(item[key])
        return None
    
    def _extract_tracking(self, item: Dict) -> Optional[str]:
        """Extract tracking number"""
        for key in ['logisticsOrderId', 'mailNo', 'expressNo', 'tracking_number']:
            if key in item:
                return str(item[key])
        return None
    
    def _extract_image(self, item: Dict) -> Optional[str]:
        """Extract product image URL"""
        for key in ['picPath', 'itemPic', 'pic', 'imageUrl', 'productImg']:
            if key in item:
                url = str(item[key])
                if url and not url.startswith('http'):
                    url = 'https:' + url if url.startswith('//') else 'https://' + url
                return url
        return None
    
    def _extract_date(self, item: Dict) -> Optional[datetime]:
        """Extract order date"""
        for key in ['createTime', 'orderCreateTime', 'gmtCreate', 'createDate']:
            if key in item:
                try:
                    # Handle timestamp (milliseconds or seconds)
                    val = item[key]
                    if isinstance(val, (int, float)):
                        timestamp = val if val < 10000000000 else val / 1000
                        return datetime.fromtimestamp(timestamp)
                    # Handle date string
                    elif isinstance(val, str):
                        return datetime.fromisoformat(val.replace('Z', '+00:00'))
                except:
                    continue
        return None
    
    async def _extract_from_initial_data(self, page: Page) -> List[Dict]:
        """Extract orders from window.__INITIAL_DATA__"""
        try:
            initial_data = await page.evaluate('() => window.__INITIAL_DATA__')
            if initial_data:
                print(f"✅ Found __INITIAL_DATA__")
                # Try to find order arrays in the initial data
                return self._parse_mtop_responses([{'data': initial_data}])
        except:
            pass
        return []
    
    async def _extract_from_scripts(self, page: Page) -> List[Dict]:
        """Extract orders from inline script tags containing JSON"""
        try:
            scripts = await page.query_selector_all('script')
            for script in scripts[:20]:  # Limit to first 20 scripts
                try:
                    content = await script.text_content()
                    if not content or len(content) < 100:
                        continue
                    
                    # Look for JSON objects in script content
                    json_matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content[:50000])
                    for json_str in json_matches[:10]:
                        try:
                            data = json.loads(json_str)
                            if isinstance(data, dict):
                                extracted = self._parse_mtop_responses([{'data': data}])
                                if extracted:
                                    return extracted
                        except:
                            continue
                except:
                    continue
        except:
            pass
        return []
