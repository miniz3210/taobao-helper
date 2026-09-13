"""
Taobao Orders Fetcher using Playwright
Implements strict session validation, anti-bot detection, and fail-fast logic
"""
from typing import List, Dict, Optional, Tuple
from playwright.async_api import async_playwright, Browser, Page
import json
import re
from datetime import datetime
from pathlib import Path


class SessionValidationError(Exception):
    """Raised when session validation fails"""
    pass


class AntisBotDetectedError(Exception):
    """Raised when anti-bot or captcha is detected"""
    pass


class TaobaoPlaywrightFetcher:
    """Fetch Taobao orders using Playwright with saved cookies"""
    
    def __init__(self, cookies_file: str = "/app/data/cookies.json"):
        self.cookies_file = cookies_file
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
    
    async def fetch_orders_with_cookies(self, cookies_json: str) -> Tuple[List[Dict], Optional[str]]:
        """
        Fetch orders using saved cookies via Playwright
        
        Returns:
            Tuple[List[Dict], Optional[str]]: (orders, error_code)
            error_code can be: None, "SESSION_INVALID", "CAPTCHA_DETECTED", "LOGIN_REQUIRED"
        """
        all_orders = []
        error_code = None
        
        try:
            # Load cookies
            cookies_path = Path(self.cookies_file)
            if not cookies_path.exists():
                print("❌ No cookies file found")
                return all_orders, "SESSION_INVALID"
            
            with open(self.cookies_file, 'r') as f:
                cookies_data = json.load(f)
            
            cookies = cookies_data.get('cookies', [])
            
            if not cookies:
                print("❌ No cookies in file")
                return all_orders, "SESSION_INVALID"
            
            print(f"\n{'='*80}")
            print(f"Starting Playwright order fetch with {len(cookies)} cookies")
            print(f"{'='*80}\n")
            
            # Launch browser
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu'
                ]
            )
            
            # Create context with proper settings to avoid detection
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-TW',
                timezone_id='Asia/Taipei',
                extra_http_headers={
                    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1'
                }
            )
            
            # Add cookies to context
            await context.add_cookies(cookies)
            
            self.page = await context.new_page()
            
            # Add script to hide automation
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-TW', 'zh', 'en']
                });
            """)
            
            # Navigate to orders page and validate session
            print("🔍 Navigating to orders page and validating session...")
            try:
                validation_result = await self._navigate_and_validate_session()
                if not validation_result["success"]:
                    error_code = validation_result["error_code"]
                    print(f"❌ Session validation failed: {error_code}")
                    
                    # Save debug information
                    await self._save_debug_state(f"session_invalid_{error_code.lower()}")
                    
                    # Purge invalid cookies
                    await self._purge_invalid_cookies()
                    
                    return all_orders, error_code
                
                print("✅ Session validated successfully!")
                
            except (SessionValidationError, AntisBotDetectedError) as e:
                error_code = str(e)
                print(f"❌ Validation exception: {error_code}")
                await self._save_debug_state("validation_exception")
                await self._purge_invalid_cookies()
                return all_orders, error_code
            
            # Fetch orders from all tabs
            print("\n📦 Starting order extraction...")
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
                    await self.page.goto(tab_url, wait_until='domcontentloaded', timeout=30000)
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
            print(f"❌ Unexpected error in Playwright fetch: {e}")
            import traceback
            traceback.print_exc()
            error_code = "UNKNOWN_ERROR"
        
        finally:
            await self.cleanup()
        
        return all_orders, error_code
    
    async def _navigate_and_validate_session(self) -> Dict:
        """
        Navigate to orders page and perform strict session validation
        
        Returns:
            Dict with keys: success (bool), error_code (str)
        """
        try:
            # Navigate to orders page
            print("🌐 Loading buyertrade.taobao.com...")
            
            response = await self.page.goto(
                'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm',
                wait_until='domcontentloaded',
                timeout=30000
            )
            
            # Wait for page to settle
            await self.page.wait_for_timeout(3000)
            
            current_url = self.page.url
            print(f"📍 Current URL: {current_url}")
            
            # Check 1: Redirect to login page
            if 'login.taobao.com' in current_url or 'login.tmall.com' in current_url:
                print("❌ Redirected to login page - session expired")
                return {"success": False, "error_code": "LOGIN_REQUIRED"}
            
            # Check 2: Look for anti-bot/captcha elements
            print("🔍 Checking for anti-bot measures...")
            captcha_detected = await self._detect_antibot_elements()
            if captcha_detected:
                print("❌ Captcha or anti-bot mechanism detected")
                return {"success": False, "error_code": "CAPTCHA_DETECTED"}
            
            # Check 3: Verify we're on the correct domain
            if 'buyertrade.taobao.com' not in current_url:
                print(f"❌ Unexpected redirect to: {current_url}")
                return {"success": False, "error_code": "SESSION_INVALID"}
            
            # Check 4: Look for authenticated user elements
            print("🔍 Validating authenticated session...")
            is_authenticated = await self._verify_authenticated_session()
            if not is_authenticated:
                print("❌ Not authenticated - no user elements found")
                return {"success": False, "error_code": "SESSION_INVALID"}
            
            # Check 5: Look for orders container or empty state message
            print("🔍 Checking for orders container...")
            has_orders_container = await self._verify_orders_container()
            if not has_orders_container:
                print("⚠️  No orders container found - may be empty or page structure changed")
                # This is a warning, not a failure - account might just have no orders
            
            print("✅ All validation checks passed")
            return {"success": True, "error_code": None}
            
        except Exception as e:
            print(f"❌ Navigation/validation error: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error_code": "NAVIGATION_ERROR"}
    
    async def _detect_antibot_elements(self) -> bool:
        """
        Detect common Taobao anti-bot and captcha elements
        
        Returns:
            bool: True if anti-bot mechanism detected
        """
        # Check for sliding captcha
        sliding_captcha_selectors = [
            '#nc_1_wrapper',
            '.nc_wrapper',
            '#nc-container',
            '[id*="nc_"][id*="wrapper"]',
            '.nc-container',
            'div[class*="slider"]'
        ]
        
        for selector in sliding_captcha_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        print(f"🚨 Sliding captcha detected: {selector}")
                        return True
            except:
                continue
        
        # Check for login iframe
        try:
            iframes = await self.page.query_selector_all('iframe')
            for iframe in iframes:
                src = await iframe.get_attribute('src')
                if src and 'login' in src.lower():
                    print(f"🚨 Login iframe detected: {src}")
                    return True
        except:
            pass
        
        # Check page content for verification keywords
        try:
            content = await self.page.content()
            antibot_keywords = [
                '请滑动验证',
                '验证码',
                '安全验证',
                '请完成验证',
                'verification',
                'captcha',
                '滑块验证'
            ]
            
            for keyword in antibot_keywords:
                if keyword in content:
                    print(f"🚨 Anti-bot keyword detected: {keyword}")
                    return True
        except:
            pass
        
        return False
    
    async def _verify_authenticated_session(self) -> bool:
        """
        Verify that the user is authenticated by looking for user-specific elements
        
        Returns:
            bool: True if authenticated user elements found
        """
        # Look for user info elements
        user_selectors = [
            '[class*="user-nick"]',
            '[class*="username"]',
            '[class*="user-info"]',
            '.user-name',
            '#userName',
            '[data-spm*="user"]',
            'span[class*="nick"]',
            'div[class*="nick"]'
        ]
        
        for selector in user_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    if text and len(text.strip()) > 0:
                        print(f"✅ Found user element: {selector} = '{text.strip()[:20]}'")
                        return True
            except:
                continue
        
        # Check for logout button (indicates logged in)
        logout_selectors = [
            'a:has-text("退出")',
            'a:has-text("登出")',
            'a[href*="logout"]'
        ]
        
        for selector in logout_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    print(f"✅ Found logout button: {selector}")
                    return True
            except:
                continue
        
        # Check URL patterns - if we have order params, likely authenticated
        current_url = self.page.url
        if 'buyertrade.taobao.com' in current_url and 'login' not in current_url.lower():
            # Do a content check for login forms
            try:
                content = await self.page.content()
                login_indicators = [
                    'loginFormData',
                    'TPL_username',
                    'TPL_password',
                    'fm-login-id',
                    'J_Static2Quick'
                ]
                
                has_login_form = any(indicator in content for indicator in login_indicators)
                if not has_login_form:
                    print("✅ No login form detected in content")
                    return True
            except:
                pass
        
        return False
    
    async def _verify_orders_container(self) -> bool:
        """
        Verify that orders container or empty state is present
        
        Returns:
            bool: True if orders container or empty state found
        """
        # Look for orders container
        container_selectors = [
            'div[class*="order-container"]',
            'div[class*="bought-wrapper"]',
            'table.item-list',
            '.js-order-container',
            'tbody[class*="order"]',
            '[class*="orderList"]',
            '#tp-bought-root'
        ]
        
        for selector in container_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    print(f"✅ Found orders container: {selector}")
                    return True
            except:
                continue
        
        # Check for empty state messages
        try:
            content = await self.page.text_content('body')
            empty_state_keywords = [
                '暂无订单',
                '沒有訂單',
                '没有订单',
                '还没有订单',
                '無訂單'
            ]
            
            for keyword in empty_state_keywords:
                if keyword in content:
                    print(f"✅ Found empty state message: {keyword}")
                    return True
        except:
            pass
        
        return False
    
    async def _save_debug_state(self, reason: str):
        """
        Save full-page screenshot and HTML for debugging
        
        Args:
            reason: String describing why debug state is being saved
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save screenshot
            screenshot_path = f"/app/data/interception_state_{reason}_{timestamp}.png"
            await self.page.screenshot(path=screenshot_path, full_page=True)
            print(f"📸 Screenshot saved: {screenshot_path}")
            
            # Save HTML
            html_path = f"/app/data/interception_state_{reason}_{timestamp}.html"
            content = await self.page.content()
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"💾 HTML saved: {html_path}")
            
            # Save current URL for reference
            url_info_path = f"/app/data/interception_state_{reason}_{timestamp}_url.txt"
            with open(url_info_path, 'w', encoding='utf-8') as f:
                f.write(f"URL: {self.page.url}\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Reason: {reason}\n")
            print(f"📋 URL info saved: {url_info_path}")
            
        except Exception as e:
            print(f"⚠️  Failed to save debug state: {e}")
    
    async def _purge_invalid_cookies(self):
        """
        Delete invalid cookies from local storage to force re-authentication
        """
        try:
            cookies_path = Path(self.cookies_file)
            if cookies_path.exists():
                # Backup before deleting
                backup_path = f"{self.cookies_file}.invalid_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                cookies_path.rename(backup_path)
                print(f"🗑️  Invalid cookies backed up to: {backup_path}")
                print(f"🗑️  Cookies purged from: {self.cookies_file}")
            else:
                print("ℹ️  No cookies file to purge")
        except Exception as e:
            print(f"⚠️  Failed to purge cookies: {e}")
    
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
                .js-order-container,
                div[class*="bought-wrapper-mod__container"]
            ''')
            
            print(f"Found {len(order_elements)} potential order elements")
            
            for element in order_elements:
                try:
                    order_data = await self._extract_order_from_element(element, tab_name)
                    if order_data and order_data.get('order_id'):
                        orders.append(order_data)
                except Exception as e:
                    # Silently skip malformed elements
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
            else:
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
                    order_data['item_title'] = lines[0][:200] if lines else 'Unknown Item'
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
                        elif not src.startswith('http'):
                            src = 'https:' + src
                        order_data['snapshot_url'] = src
            except:
                pass
            
            return order_data
            
        except Exception as e:
            return None
    
    async def cleanup(self):
        """Clean up resources"""
        try:
            if self.page:
                await self.page.close()
                self.page = None
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
        except Exception as e:
            print(f"Cleanup error: {e}")
