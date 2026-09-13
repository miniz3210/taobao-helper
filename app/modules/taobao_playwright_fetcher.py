"""
Taobao Orders Fetcher using Playwright
Uses the browser session from QR login to fetch orders
"""
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Browser, Page
import json
import re
from datetime import datetime


class TaobaoPlaywrightFetcher:
    """Fetch Taobao orders using Playwright with saved cookies"""
    
    def __init__(self, cookies_file: str = "/app/data/cookies.json"):
        self.cookies_file = cookies_file
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    async def fetch_orders_with_cookies(self, cookies_json: str) -> List[Dict]:
        """
        Fetch orders using saved cookies via Playwright
        Returns list of parsed orders
        """
        all_orders = []
        
        try:
            # Load cookies
            with open(self.cookies_file, 'r') as f:
                cookies_data = json.load(f)
            
            cookies = cookies_data.get('cookies', [])
            
            print(f"\n{'='*80}")
            print(f"Starting Playwright order fetch with {len(cookies)} cookies")
            print(f"{'='*80}\n")
            
            # Launch browser
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            
            # Create context with cookies
            context = await self.browser.new_context(cookies=cookies)
            self.page = await context.new_page()
            
            # Navigate to orders page
            print("Navigating to Taobao orders page...")
            await self.page.goto(
                'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm',
                wait_until='networkidle',
                timeout=30000
            )
            
            print(f"Page loaded: {self.page.url}")
            
            # Check if we're logged in
            content = await self.page.content()
            
            if 'login.taobao.com' in self.page.url or 'loginFormData' in content:
                print("❌ Not logged in - cookies expired or invalid")
                return all_orders
            
            print("✅ Successfully logged in!")
            
            # Wait for orders to load
            try:
                await self.page.wait_for_selector('.bought-wrapper-mod__order-container, table.item-list, .js-order-container', timeout=10000)
                print("✅ Orders container found")
            except Exception as e:
                print(f"⚠️  No orders container found: {e}")
                # Save HTML for debugging
                with open('/app/data/logged_in_page.html', 'w') as f:
                    f.write(content)
                print("Saved page HTML to /app/data/logged_in_page.html")
            
            # Fetch all tabs
            tabs = [
                ('all', 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm'),
                ('waitPay', 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm?action=itemlist/BoughtQueryAction&event_submit_do_query=1&tabCode=waitPay'),
                ('waitSend', 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm?action=itemlist/BoughtQueryAction&event_submit_do_query=1&tabCode=waitSend'),
                ('waitConfirm', 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm?action=itemlist/BoughtQueryAction&event_submit_do_query=1&tabCode=waitConfirm'),
                ('waitRate', 'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm?action=itemlist/BoughtQueryAction&event_submit_do_query=1&tabCode=waitRate'),
            ]
            
            for tab_name, tab_url in tabs:
                print(f"\n--- Fetching tab: {tab_name} ---")
                
                try:
                    await self.page.goto(tab_url, wait_until='networkidle', timeout=30000)
                    
                    # Wait a bit for dynamic content
                    await self.page.wait_for_timeout(2000)
                    
                    # Parse orders from current page
                    orders = await self._parse_orders_from_current_page(tab_name)
                    
                    if orders:
                        all_orders.extend(orders)
                        print(f"✅ Found {len(orders)} orders in {tab_name}")
                    else:
                        print(f"⚠️  No orders in {tab_name}")
                    
                except Exception as e:
                    print(f"❌ Error fetching {tab_name}: {e}")
                    continue
            
            print(f"\n{'='*80}")
            print(f"✅ Total orders fetched: {len(all_orders)}")
            print(f"{'='*80}\n")
            
        except Exception as e:
            print(f"❌ Error in Playwright fetch: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await self.cleanup()
        
        return all_orders
    
    async def _parse_orders_from_current_page(self, tab_name: str) -> List[Dict]:
        """Parse orders from the current page"""
        orders = []
        
        try:
            # Get page content
            content = await self.page.content()
            
            # Try to find order containers using JavaScript
            order_elements = await self.page.query_selector_all('''
                div[class*="order-container"],
                table.item-list tbody tr,
                .js-order-container
            ''')
            
            print(f"Found {len(order_elements)} potential order elements")
            
            for element in order_elements:
                try:
                    order_data = await self._extract_order_from_element(element, tab_name)
                    if order_data and order_data.get('order_id'):
                        orders.append(order_data)
                except Exception as e:
                    print(f"Error parsing order element: {e}")
                    continue
            
        except Exception as e:
            print(f"Error parsing orders from page: {e}")
        
        return orders
    
    async def _extract_order_from_element(self, element, tab_name: str) -> Optional[Dict]:
        """Extract order data from a single element"""
        try:
            # Get text content
            text = await element.text_content()
            
            if not text or len(text) < 10:
                return None
            
            order_data = {}
            
            # Extract order ID (15+ digit number)
            order_id_match = re.search(r'(\d{15,})', text)
            if order_id_match:
                order_data['order_id'] = order_id_match.group(1)
            else:
                return None
            
            # Extract dates
            date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text)
            if date_match:
                date_str = date_match.group(1).replace('/', '-')
                try:
                    order_data['order_date'] = datetime.strptime(date_str, '%Y-%m-%d')
                except:
                    pass
            
            # Extract price
            price_match = re.search(r'¥?(\d+\.?\d*)', text)
            if price_match:
                try:
                    order_data['price'] = float(price_match.group(1))
                except:
                    order_data['price'] = 0.0
            
            # Try to get item title from inner elements
            try:
                title_element = await element.query_selector('a[class*="title"], span[class*="title"], .item-title')
                if title_element:
                    title = await title_element.text_content()
                    order_data['item_title'] = title.strip() if title else 'Unknown Item'
                else:
                    # Use first meaningful text as title
                    lines = [line.strip() for line in text.split('\n') if line.strip() and len(line.strip()) > 5]
                    order_data['item_title'] = lines[0] if lines else 'Unknown Item'
            except:
                order_data['item_title'] = 'Unknown Item'
            
            # Set status based on tab
            status_mapping = {
                'all': 'pending_shipment',
                'waitPay': 'pending_payment',
                'waitSend': 'pending_shipment',
                'waitConfirm': 'in_transit',
                'waitRate': 'received'
            }
            order_data['current_status'] = status_mapping.get(tab_name, 'pending_shipment')
            
            # Set defaults
            order_data['quantity'] = 1
            order_data['seller_name'] = None
            order_data['seller_express_no'] = None
            order_data['snapshot_url'] = None
            
            # Try to get image
            try:
                img_element = await element.query_selector('img')
                if img_element:
                    src = await img_element.get_attribute('src') or await img_element.get_attribute('data-src')
                    if src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        order_data['snapshot_url'] = src
            except:
                pass
            
            return order_data
            
        except Exception as e:
            print(f"Error extracting order data: {e}")
            return None
    
    async def cleanup(self):
        """Clean up resources"""
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            print(f"Cleanup error: {e}")
