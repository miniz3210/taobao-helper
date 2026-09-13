"""
Taobao Account Login Module
Handles username/password login using Playwright
More stable than QR code login for automated scraping
"""
import asyncio
import json
from pathlib import Path
from typing import Dict, Optional, List
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeout


class TaobaoAccountLogin:
    """Handles Taobao username/password authentication using Playwright"""
    
    def __init__(self, cookies_file: str = "/app/data/cookies.json"):
        self.cookies_file = Path(cookies_file)
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.login_status = "idle"
        self.cookies_dict = {}
        
    async def login_with_password(self, username: str, password: str) -> Dict[str, any]:
        """
        Login with username and password
        Returns: {"success": bool, "cookies": str, "message": str}
        """
        try:
            print(f"\n{'='*80}")
            print(f"Starting account login for user: {username}")
            print(f"{'='*80}\n")
            
            # Launch Playwright
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )
            
            # Create browser context with anti-detection
            context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
                extra_http_headers={
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                }
            )
            
            self.page = await context.new_page()
            
            # Hide automation
            await self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.chrome = { runtime: {} };
            """)
            
            # Navigate to login page
            print("Navigating to Taobao login page...")
            await self.page.goto('https://login.taobao.com/', wait_until='domcontentloaded')
            await asyncio.sleep(3)
            
            # Check if we need to switch to password login tab
            try:
                # Look for password login tab/link
                password_tab_selectors = [
                    'a:has-text("密码登录")',
                    'a:has-text("账户密码登录")',
                    '.login-password-tab',
                    '[data-spm*="password"]',
                ]
                
                for selector in password_tab_selectors:
                    try:
                        element = await self.page.wait_for_selector(selector, timeout=2000)
                        if element:
                            print(f"Found password tab: {selector}")
                            await element.click()
                            await asyncio.sleep(2)
                            break
                    except:
                        continue
            except Exception as e:
                print(f"Password tab switch attempt: {e}")
            
            # Fill in username
            print("Filling in username...")
            username_selectors = [
                'input[name="fm-login-id"]',
                'input[id="fm-login-id"]',
                'input[placeholder*="手机号"]',
                'input[placeholder*="会员名"]',
                'input[type="text"]',
            ]
            
            username_filled = False
            for selector in username_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=2000)
                    if element:
                        await element.fill(username)
                        print(f"Username filled with selector: {selector}")
                        username_filled = True
                        break
                except:
                    continue
            
            if not username_filled:
                raise Exception("Could not find username input field")
            
            await asyncio.sleep(1)
            
            # Fill in password
            print("Filling in password...")
            password_selectors = [
                'input[name="fm-password"]',
                'input[id="fm-password"]',
                'input[type="password"]',
                'input[placeholder*="密码"]',
            ]
            
            password_filled = False
            for selector in password_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=2000)
                    if element:
                        await element.fill(password)
                        print(f"Password filled with selector: {selector}")
                        password_filled = True
                        break
                except:
                    continue
            
            if not password_filled:
                raise Exception("Could not find password input field")
            
            await asyncio.sleep(1)
            
            # Check and click agreement checkbox BEFORE login
            print("Checking for terms agreement checkbox...")
            agreement_checked = False
            agreement_selectors = [
                'input[type="checkbox"]',
                '.protocol-content input',
                '#J_Agreement',
                'input[id*="agreement"]',
                'input[id*="protocol"]',
                'input[class*="agreement"]',
                '.agreement-checkbox',
                '[type="checkbox"][name*="agree"]',
            ]
            
            for selector in agreement_selectors:
                try:
                    # Try to find the checkbox
                    checkbox = await self.page.query_selector(selector)
                    if checkbox:
                        # Check if it's visible and not already checked
                        is_visible = await checkbox.is_visible()
                        is_checked = await checkbox.is_checked()
                        
                        if is_visible and not is_checked:
                            print(f"Found agreement checkbox with selector: {selector}")
                            await checkbox.check()
                            print("✅ Agreement checkbox checked")
                            agreement_checked = True
                            await asyncio.sleep(500)  # Wait 500ms after checking
                            break
                        elif is_checked:
                            print(f"Agreement checkbox already checked: {selector}")
                            agreement_checked = True
                            break
                except Exception as e:
                    continue
            
            # Try text-based selectors if checkbox not found
            if not agreement_checked:
                text_selectors = [
                    'text=已阅读并同意',
                    'text=已閱讀並同意',
                    'span:has-text("已阅读")',
                    'span:has-text("已閱讀")',
                    'label:has-text("同意")',
                ]
                
                for selector in text_selectors:
                    try:
                        element = await self.page.query_selector(selector)
                        if element:
                            is_visible = await element.is_visible()
                            if is_visible:
                                print(f"Found agreement text element: {selector}")
                                await element.click()
                                print("✅ Agreement element clicked")
                                agreement_checked = True
                                await asyncio.sleep(500)  # Wait 500ms after clicking
                                break
                    except Exception as e:
                        continue
            
            if agreement_checked:
                print("✅ Terms agreement handled successfully")
            else:
                print("ℹ️  No agreement checkbox found (may not be required)")
            
            # Handle slider CAPTCHA if present
            try:
                slider = await self.page.wait_for_selector('.nc_iconfont.btn_slide', timeout=3000)
                if slider:
                    print("⚠️  Slider CAPTCHA detected - attempting to solve...")
                    # Get slider bounds
                    box = await slider.bounding_box()
                    if box:
                        # Drag slider to the right
                        await self.page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                        await self.page.mouse.down()
                        await self.page.mouse.move(box['x'] + 300, box['y'] + box['height'] / 2, steps=30)
                        await self.page.mouse.up()
                        await asyncio.sleep(2)
                        print("✅ Slider CAPTCHA attempted")
            except:
                print("ℹ️  No slider CAPTCHA found")
            
            # Click login button
            print("Clicking login button...")
            login_button_selectors = [
                'button[type="submit"]',
                'button:has-text("登录")',
                '.fm-button',
                '#login-form button',
            ]
            
            button_clicked = False
            for selector in login_button_selectors:
                try:
                    element = await self.page.wait_for_selector(selector, timeout=2000)
                    if element:
                        await element.click()
                        print(f"Login button clicked with selector: {selector}")
                        button_clicked = True
                        break
                except:
                    continue
            
            if not button_clicked:
                # Try pressing Enter as fallback
                print("Trying Enter key as fallback...")
                await self.page.keyboard.press('Enter')
            
            # Wait for navigation or error
            print("Waiting for login result...")
            await asyncio.sleep(5)
            
            # Check for errors
            error_selectors = [
                '.error-msg',
                '.fm-error',
                '[class*="error"]',
            ]
            
            for selector in error_selectors:
                try:
                    error_element = await self.page.query_selector(selector)
                    if error_element:
                        error_text = await error_element.text_content()
                        if error_text and len(error_text.strip()) > 0:
                            print(f"❌ Login error: {error_text}")
                            # Save debug page
                            await self._save_debug_page('login_error')
                            return {
                                "success": False,
                                "cookies": None,
                                "message": f"登入失敗：{error_text}"
                            }
                except:
                    continue
            
            # Check if login was successful
            current_url = self.page.url
            print(f"Current URL after login: {current_url}")
            
            if 'login' not in current_url.lower():
                # Login successful!
                print("✅ Login appears successful - no longer on login page")
                
                # CRITICAL: Navigate to orders page to activate the session
                print("🔑 Navigating to orders page to activate session...")
                try:
                    await self.page.goto(
                        'https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm',
                        wait_until='domcontentloaded',
                        timeout=30000
                    )
                    await asyncio.sleep(3)
                    
                    orders_url = self.page.url
                    print(f"Orders page URL: {orders_url}")
                    
                    # Check if we're still authenticated
                    if 'login' in orders_url.lower():
                        print("❌ Session lost when accessing orders page")
                        await self._save_debug_page('session_lost_on_orders')
                        return {
                            "success": False,
                            "cookies": None,
                            "message": "登入成功但訪問訂單頁面時會話丟失，請稍後再試"
                        }
                    
                    print("✅ Successfully accessed orders page - session is active!")
                    
                except Exception as e:
                    print(f"⚠️  Failed to access orders page: {e}")
                    # Continue anyway, cookies might still work
                
                # Get cookies AFTER accessing orders page
                cookies = await self.page.context.cookies()
                print(f"Collected {len(cookies)} cookies after orders page access")
                
                # Check for session cookies
                cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
                session_indicators = ['cookie2', 'unb', 't', '_tb_token_']
                found_indicators = [key for key in session_indicators if key in cookie_dict]
                
                print(f"Session indicators found: {found_indicators}")
                
                if len(found_indicators) >= 2:
                    self.login_status = "success"
                    self.cookies_dict = cookie_dict
                    
                    # Save cookies
                    self._save_cookies(cookies)
                    
                    # Format cookies as string
                    cookies_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
                    
                    # Don't cleanup yet - keep browser open for immediate scraping
                    print("✅ Cookies saved with active session")
                    
                    return {
                        "success": True,
                        "cookies": cookies_str,
                        "message": "登入成功！",
                        "cookie_count": len(cookies),
                        "session_activated": True
                    }
                else:
                    print("⚠️  Session cookies not found, login may have failed")
                    await self._save_debug_page('no_session_cookies')
                    return {
                        "success": False,
                        "cookies": None,
                        "message": "登入可能失敗：未找到會話 Cookie"
                    }
            else:
                # Still on login page
                print("❌ Still on login page - login failed")
                await self._save_debug_page('still_on_login')
                
                # Try to get error message from page
                page_text = await self.page.text_content('body')
                if '验证码' in page_text or 'captcha' in page_text.lower():
                    message = "需要驗證碼，請使用 QR 登入或稍後再試"
                elif '密码错误' in page_text or '用户名错误' in page_text:
                    message = "用戶名或密碼錯誤"
                else:
                    message = "登入失敗，請檢查帳號密碼"
                
                return {
                    "success": False,
                    "cookies": None,
                    "message": message
                }
            
        except Exception as e:
            print(f"❌ Login exception: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                await self._save_debug_page('exception')
            except:
                pass
            
            return {
                "success": False,
                "cookies": None,
                "message": f"登入錯誤：{str(e)}"
            }
        
        finally:
            # Cleanup browser
            await self.cleanup()
    
    async def _save_debug_page(self, reason: str):
        """Save page HTML for debugging"""
        try:
            if self.page:
                content = await self.page.content()
                filename = f'/app/data/account_login_{reason}.html'
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Debug page saved to {filename}")
        except Exception as e:
            print(f"Could not save debug page: {e}")
    
    def _save_cookies(self, cookies: list):
        """Save cookies to JSON file"""
        try:
            self.cookies_file.parent.mkdir(parents=True, exist_ok=True)
            
            cookies_data = {
                'cookies': cookies,
                'timestamp': asyncio.get_event_loop().time(),
                'login_method': 'password'
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
