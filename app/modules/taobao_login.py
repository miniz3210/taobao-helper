"""
Taobao Account Login Module
Handles login via username/password instead of cookies
"""
import httpx
from typing import Dict, Optional
from bs4 import BeautifulSoup
import json
import re


class TaobaoLogin:
    """Handles Taobao account authentication"""
    
    def __init__(self):
        self.session = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
            }
        )
        self.cookies_dict = {}
    
    async def login_with_account(
        self, 
        username: str, 
        password: str
    ) -> Dict[str, any]:
        """
        Login to Taobao with username and password
        Returns: {"success": bool, "cookies": str, "message": str}
        """
        try:
            # Step 1: Get login page and tokens
            login_url = "https://login.taobao.com/member/login.jhtml"
            response = await self.session.get(login_url)
            
            # Extract tokens from page
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for hidden form fields (common in login forms)
            form_data = {
                'TPL_username': username,
                'TPL_password': password,
                'TPL_redirect_url': 'https://www.taobao.com/',
                'ncoToken': self._extract_token(response.text, 'ncoToken'),
                'slideToken': self._extract_token(response.text, 'slideToken'),
                'fromSite': '0',
            }
            
            # Step 2: Submit login form
            post_url = "https://login.taobao.com/member/login.jhtml"
            login_response = await self.session.post(
                post_url,
                data=form_data,
                headers={
                    'Referer': login_url,
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            )
            
            # Step 3: Check if login successful
            if login_response.status_code == 200:
                # Extract cookies
                cookies_str = self._format_cookies(self.session.cookies)
                
                # Verify login by checking if we can access user page
                verify_url = "https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm"
                verify_response = await self.session.get(verify_url)
                
                if "我的淘宝" in verify_response.text or "My Taobao" in verify_response.text:
                    return {
                        "success": True,
                        "cookies": cookies_str,
                        "message": "登入成功！",
                        "username": username
                    }
                else:
                    return {
                        "success": False,
                        "cookies": "",
                        "message": "登入失敗：請檢查帳號密碼或需要驗證碼"
                    }
            else:
                return {
                    "success": False,
                    "cookies": "",
                    "message": f"登入失敗：HTTP {login_response.status_code}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "cookies": "",
                "message": f"登入錯誤：{str(e)}"
            }
    
    def _extract_token(self, html: str, token_name: str) -> str:
        """Extract hidden token from HTML"""
        pattern = f'{token_name}["\']?\s*[:=]\s*["\']([^"\']+)'
        match = re.search(pattern, html)
        return match.group(1) if match else ""
    
    def _format_cookies(self, cookies) -> str:
        """Format cookies object to string"""
        cookie_list = []
        for name, value in cookies.items():
            cookie_list.append(f"{name}={value}")
        return "; ".join(cookie_list)
    
    async def check_login_status(self, cookies: str) -> bool:
        """Check if cookies are still valid"""
        try:
            cookie_dict = self._parse_cookies(cookies)
            
            response = await self.session.get(
                "https://buyertrade.taobao.com/trade/itemlist/list_bought_items.htm",
                cookies=cookie_dict
            )
            
            return response.status_code == 200 and ("我的淘宝" in response.text or "My Taobao" in response.text)
            
        except Exception:
            return False
    
    def _parse_cookies(self, cookies_str: str) -> Dict[str, str]:
        """Parse cookie string to dict"""
        cookie_dict = {}
        if not cookies_str:
            return cookie_dict
        
        for item in cookies_str.split(';'):
            item = item.strip()
            if '=' in item:
                key, value = item.split('=', 1)
                cookie_dict[key.strip()] = value.strip()
        
        return cookie_dict
    
    async def close(self):
        """Close HTTP session"""
        await self.session.aclose()
