"""
Taobao QR Code Login Module
Handles QR code login using Playwright
"""
import asyncio
import json
import base64
from pathlib import Path
from typing import Dict, Optional
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout


class TaobaoQRLogin:
    """Handles Taobao QR code authentication using Playwright"""
    
    def __init__(self, cookies_file: str = "/app/data/cookies.json"):
        self.cookies_file = Path(cookies_file)
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.login_status = "idle"  # idle, pending, success, failed
        self.qr_image_base64 = None
        self.cookies_dict = {}
        
    async def start_qr_login(self) -> Dict[str, any]:
        """
        Start QR code login process
        Returns: {"success": bool, "qr_image": str (base64), "message": str}
        """
        try:
            # Launch Playwright
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            
            # Create new page
            context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            self.page = await context.new_page()
            
            # Navigate to Taobao login page
            await self.page.goto('https://login.taobao.com', wait_until='networkidle')
            
            # Wait a bit for page to stabilize
            await asyncio.sleep(2)
            
            # Try to find and click QR code tab if it exists
            try:
                # Look for QR code login tab/button
                qr_tab_selectors = [
                    'a:has-text("掃碼登錄")',
                    'a:has-text("扫码登录")',
                    '.login-scan-tab',
                    '[data-spm="qrcode"]',
                    '#J_QRCodeImg',
                ]
                
                for selector in qr_tab_selectors:
                    try:
                        element = await self.page.wait_for_selector(selector, timeout=2000)
                        if element:
                            await element.click()
                            await asyncio.sleep(1)
                            break
                    except:
                        continue
                        
            except Exception as e:
                print(f"QR tab click attempt: {e}")
            
            # Find QR code element
            qr_selectors = [
                '#J_QRCodeImg',
                '.qrcode-img',
                'img[alt*="二维码"]',
                'img[alt*="QR"]',
                'canvas.qrcode',
                '.login-qrcode img',
                '[class*="qrcode"] img',
            ]
            
            qr_element = None
            for selector in qr_selectors:
                try:
                    qr_element = await self.page.wait_for_selector(selector, timeout=3000)
                    if qr_element:
                        print(f"Found QR code with selector: {selector}")
                        break
                except:
                    continue
            
            if not qr_element:
                # Try to capture entire login area if QR not found specifically
                try:
                    login_area = await self.page.wait_for_selector('.login-content, .login-box, #login', timeout=2000)
                    if login_area:
                        qr_element = login_area
                except:
                    pass
            
            if not qr_element:
                # Last resort: screenshot the whole page
                screenshot_bytes = await self.page.screenshot(full_page=False)
            else:
                # Screenshot the QR code element
                screenshot_bytes = await qr_element.screenshot()
            
            # Convert to base64
            self.qr_image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            self.login_status = "pending"
            
            return {
                "success": True,
                "qr_image": f"data:image/png;base64,{self.qr_image_base64}",
                "message": "請使用淘寶 App 掃描 QR Code",
                "session_id": "active"
            }
            
        except Exception as e:
            self.login_status = "failed"
            await self.cleanup()
            return {
                "success": False,
                "qr_image": None,
                "message": f"啟動 QR 登入失敗：{str(e)}"
            }
    
    async def check_login_status(self) -> Dict[str, any]:
        """
        Check if user has scanned QR code and logged in
        Returns: {"status": str, "cookies": str, "message": str}
        """
        if not self.page:
            print("No page instance available")
            return {
                "status": "idle",
                "logged_in": False,
                "message": "未在登入流程中"
            }
        
        if self.login_status != "pending":
            print(f"Login status is not pending: {self.login_status}")
            return {
                "status": self.login_status,
                "logged_in": False,
                "message": "未在登入流程中"
            }
        
        try:
            # Get current cookies
            cookies = await self.page.context.cookies()
            print(f"Current cookies count: {len(cookies)}")
            
            # Check for Taobao session cookies
            cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
            
            # Key session cookies that indicate successful login
            session_indicators = ['cookie2', 'unb', 't', '_tb_token_']
            
            found_indicators = [key for key in session_indicators if key in cookie_dict]
            has_session = len(found_indicators) > 0
            
            print(f"Session indicators found: {found_indicators}")
            
            if has_session:
                # Successful login detected!
                print(f"Session cookies detected: {list(cookie_dict.keys())}")
                
                self.login_status = "success"
                self.cookies_dict = cookie_dict
                
                # Save cookies to file
                self._save_cookies(cookies)
                
                # Format cookies as string
                cookies_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
                
                print(f"Login successful, returning cookies (length: {len(cookies_str)})")
                
                # DON'T cleanup yet - keep browser open for order fetching
                # The /api/scrape endpoint will use this browser session
                
                return {
                    "status": "success",
                    "logged_in": True,
                    "cookies": cookies_str,
                    "message": "登入成功！",
                    "keep_browser": True  # Signal to keep browser open
                }
            
            # Still waiting for scan
            return {
                "status": "pending",
                "logged_in": False,
                "message": "等待掃描中..."
            }
            
        except Exception as e:
            print(f"Check login status error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "pending",
                "logged_in": False,
                "message": "檢查登入狀態..."
            }
    
    def _save_cookies(self, cookies: list):
        """Save cookies to JSON file"""
        try:
            self.cookies_file.parent.mkdir(parents=True, exist_ok=True)
            
            cookies_data = {
                'cookies': cookies,
                'timestamp': asyncio.get_event_loop().time()
            }
            
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies_data, f, ensure_ascii=False, indent=2)
                
            print(f"Cookies saved to {self.cookies_file}")
            
        except Exception as e:
            print(f"Error saving cookies: {e}")
    
    def load_saved_cookies(self) -> Optional[str]:
        """Load cookies from file"""
        try:
            if not self.cookies_file.exists():
                return None
            
            with open(self.cookies_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            cookies = data.get('cookies', [])
            cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
            
            return "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
            
        except Exception as e:
            print(f"Error loading cookies: {e}")
            return None
    
    async def cancel_login(self):
        """Cancel the QR login process"""
        await self.cleanup()
        self.login_status = "idle"
        return {
            "success": True,
            "message": "QR 登入已取消"
        }
    
    async def cleanup(self):
        """Clean up browser resources"""
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
    
    async def fetch_orders_from_current_session(self) -> List[Dict]:
        """
        Fetch orders using the current browser session (after QR login)
        This must be called while the browser is still open
        """
        if not self.page or self.login_status != "success":
            print("No active browser session for fetching orders")
            return []
        
        print("\n=== Fetching orders from active QR login session ===")
        all_orders = []
        
        try:
            # Navigate to orders page
            await self.page.goto(
                'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm',
                wait_until='networkidle',
                timeout=30000
            )
            
            print(f"Page loaded: {self.page.url}")
            
            # Check if we're still logged in
            if 'login.taobao.com' in self.page.url:
                print("❌ Session lost - redirected to login")
                return []
            
            print("✅ Successfully accessing orders page")
            
            # Wait for page to load
            await self.page.wait_for_timeout(2000)
            
            # Try to extract orders from current page
            content = await self.page.content()
            
            # Save for debugging
            with open('/app/data/orders_page.html', 'w', encoding='utf-8') as f:
                f.write(content)
            print("Saved orders page HTML to /app/data/orders_page.html")
            
            # Simple extraction - look for order numbers in the page
            import re
            order_ids = set(re.findall(r'\b(\d{15,})\b', content))
            
            print(f"Found {len(order_ids)} unique order IDs in page")
            
            for order_id in list(order_ids)[:100]:  # Limit to 100 orders
                all_orders.append({
                    'order_id': order_id,
                    'item_title': 'Item from QR Session',
                    'price': 0.0,
                    'quantity': 1,
                    'current_status': 'pending_shipment',
                    'seller_name': None,
                    'seller_express_no': None,
                    'snapshot_url': None
                })
            
        except Exception as e:
            print(f"Error fetching orders from session: {e}")
            import traceback
            traceback.print_exc()
        
        return all_orders
