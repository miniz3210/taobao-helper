# Taobao Order Scraping Bug Fix

## Problem Diagnosis

The scraper was returning 0 orders because:

1. **Authentication Loss**: After QR login, cookies were saved but not maintaining the session when reused
2. **Silent Redirect Handling**: HTTP client was following redirects to login page without detection
3. **Missing Anti-Bot Headers**: Taobao's anti-bot system was rejecting requests with incomplete headers
4. **Suboptimal Browser Context**: Playwright wasn't properly simulating a real browser session

## Root Cause

The debug HTML showed that both scraping methods (Playwright and HTTP) were being redirected to the login page (`login.taobao.com`) instead of showing the orders page, indicating cookies were not sufficient to maintain the session.

## Fixes Applied

### 1. HTTP Scraper (`app/modules/taobao_scraper.py`)

**Lines 46-64**: Enhanced headers and disabled auto-redirect
- Added comprehensive browser headers (Sec-Fetch-*, Accept-Encoding, etc.)
- Changed `follow_redirects=False` to detect auth failures early
- Added explicit redirect detection and handling

**Lines 94-120**: Improved redirect detection
- Added manual redirect handling with login page detection
- Better error messages for authentication failures

### 2. Playwright Fetcher (`app/modules/taobao_playwright_fetcher.py`)

**Lines 21-66**: Enhanced browser fingerprinting
- Added anti-detection flags (`--disable-blink-features=AutomationControlled`)
- Improved viewport size (1920x1080 vs 1280x720)
- Added locale and timezone settings (zh-TW, Asia/Taipei)
- Added comprehensive HTTP headers
- Added JavaScript to hide automation markers

**Lines 68-95**: Improved session establishment
- Added preliminary visit to `taobao.com` to establish session context
- Changed `wait_until='networkidle'` to `wait_until='domcontentloaded'` for faster loading
- Increased wait times for JavaScript execution
- Added better error page debugging

**Lines 97-115**: Better order container detection
- Expanded selector list for order containers
- Added "no orders" message detection
- Better error handling and debug output

**Lines 117-141**: Improved tab fetching
- Added fallback for networkidle timeout
- Better error handling with traceback

### 3. QR Login Module (`app/modules/taobao_qr_login.py`)

**Lines 248-263**: Added missing cancel_login method
- Properly cleanup resources when login is cancelled

## Testing Instructions

1. **Restart the container** to apply changes:
   ```bash
   docker compose restart taobao-helper
   # OR if using k8s:
   kubectl rollout restart deployment/taobao-helper
   ```

2. **Perform QR login** via the web interface

3. **Click "Scrape Orders"** to test the fixed scraping logic

4. **Check logs** for detailed debugging output:
   ```bash
   docker compose logs -f taobao-helper
   # OR:
   kubectl logs -f deployment/taobao-helper
   ```

## Expected Behavior

After the fix:
- **If cookies are valid**: Orders should be fetched successfully
- **If cookies expire**: Clear error message indicating login is required
- **Better debugging**: Detailed logs showing redirect attempts and page states
- **Faster detection**: Auth failures detected before full page load

## Debug Files Generated

The following debug files are saved when issues occur:
- `/app/data/debug_page.html` - First page of HTTP scraper
- `/app/data/playwright_failed_page.html` - Failed Playwright login page
- `/app/data/logged_in_page.html` - Playwright orders page (when selector fails)
- `/app/data/orders_page.html` - QR session orders page

## If Still Showing 0 Orders

1. **Check if account actually has orders** - The "no orders" detection should identify this
2. **Cookie expiration** - Try logging in again with QR code
3. **Taobao changed HTML structure** - Check the generated debug HTML files
4. **Anti-bot detection** - Taobao may require additional verification (CAPTCHA)

## Additional Notes

The core issue was that Taobao requires:
- Complete browser fingerprinting headers
- Proper session establishment flow (visit homepage first)
- Anti-automation detection evasion
- Cookies alone are NOT sufficient without proper headers

These fixes address all identified issues and provide better debugging visibility.
