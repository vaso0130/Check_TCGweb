import asyncio
import re
import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright, TimeoutError as PlaywrightTimeoutError, Browser

# 匯入資料結構
from common.data_structures import CrawlResult

async def crawl(browser: Browser, url: str) -> CrawlResult:
    """使用共享的瀏覽器實例爬取網站，並統一回傳 CrawlResult。"""
    page = await browser.new_page()
    try:
        # 增加導航超時並等待到 'domcontentloaded' 即可開始分析，'networkidle' 有時會過久
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # 等待一個較短的時間讓動態內容有機會載入
        await page.wait_for_timeout(3000) 

        html_content = await page.content()
        soup = BeautifulSoup(html_content, 'html.parser')

        title, meta_desc, h1, body_text, update_date = await extract_structured_data(soup, page, url, html_content)

        # 偵測 JS 函式庫
        detected_libs = await detect_js_libraries(page)
        
        # 將 browser 物件傳遞給 check_links
        broken_links = await check_links(browser, page, url)

        return CrawlResult(
            url=url,
            status_code=200,
            title=title,
            meta_description=meta_desc,
            h1=h1,
            body_text=body_text,
            update_date=update_date,
            broken_links=broken_links,
            detected_libraries=detected_libs
        )
    except PlaywrightTimeoutError:
        return CrawlResult(
            url=url,
            status_code="Timeout",
            error_message="頁面載入超時 (60秒)"
        )
    except Exception as e:
        return CrawlResult(
            url=url,
            status_code="Error",
            error_message=f"爬取時發生未知錯誤: {str(e)}"
        )
    finally:
        await page.close()

async def check_links(browser: Browser, page: Page, base_url: str) -> List[Dict]:
    """
    使用 Playwright 全面檢查頁面上的所有連結（內部與外部），並過濾頁內錨點。
    將 browser 物件傳遞給 check_link_with_playwright。
    """
    try:
        # el.href 會回傳完整的、已解析的 URL
        links = await page.eval_on_selector_all('a', 'elements => elements.map(el => el.href)')
    except Exception as e:
        print(f"無法從 {base_url} 提取連結: {e}")
        links = []

    unique_links = set()
    # 標準化 base_url，移除 fragment 和尾部的斜線，用於比對
    base_url_defrag = urldefrag(base_url)[0].rstrip('/')

    for link in links:
        # 1. 過濾掉無效或非 http 的連結
        if not link or link.startswith(('javascript:', 'mailto:', 'tel:')):
            continue

        # Playwright 的 .href 屬性回傳的已是絕對路徑，但 urljoin 可確保安全
        full_link = urljoin(base_url, link.strip())
        
        # 2. 過濾掉指向相同頁面的錨點連結
        # 標準化連結，移除 fragment 和尾部的斜線
        full_link_defrag = urldefrag(full_link)[0].rstrip('/')
        
        # 如果移除 fragment 後的連結與當前頁面相同，則視為頁內錨點，跳過檢查
        if full_link_defrag == base_url_defrag:
            continue
            
        unique_links.add(full_link)

    # 對要去檢查的連結進行排序
    sorted_unique_links = sorted(list(unique_links))
    # 將 browser 物件傳遞給 check_link_with_playwright
    tasks = [check_link_with_playwright(browser, link) for link in sorted_unique_links]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)

    broken_links = []
    for result in results:
        if isinstance(result, dict):
            broken_links.append(result)
        elif isinstance(result, Exception):
            # 記錄 gather 中發生的異常
            print(f"檢查連結時發生未預期的 gather 錯誤: {result}")

    return broken_links

async def check_link_with_playwright(browser: Browser, url: str) -> Optional[Dict]:
    """
    使用雙重檢查機制和獨立的瀏覽器上下文 (Browser Context) 來驗證連結狀態。
    這可以避免因主頁面關閉而導致的 context 失效問題。
    1.  **快速檢查 (HEAD request)**: 先用輕量的 HEAD 請求，快速過濾正常連結。
    2.  **深度檢查 (page.goto)**: 如果 HEAD 請求失敗，則在新的分頁中模擬使用者點擊。
    """
    # 白名單，對於這些域名我們假設它們是正常的，以節省時間
    whitelisted_domains = [
        'facebook.com', 'www.facebook.com', 'instagram.com', 
        'twitter.com', 'x.com', 'youtube.com', 'youtu.be', 't.co',
        'line.me', 'plus.google.com',
        'accessibility.moda.gov.tw' # 無障礙標章
    ]
    
    parsed_url = urlparse(url)
    if parsed_url.netloc in whitelisted_domains:
        return None # 如果在白名單中，直接跳過檢查

    context = None
    try:
        # 建立一個獨立的、忽略 HTTPS 錯誤的 context
        context = await browser.new_context(ignore_https_errors=True)

        # --- 步驟 1: 快速 HEAD 請求 ---
        try:
            response = await context.request.head(url, timeout=15000)
            if response.ok:
                return None  # 連結正常，直接返回
        except Exception:
            # HEAD 請求失敗 (例如超時、或伺服器不支援 HEAD)，進入步驟 2
            pass

        # --- 步驟 2: 深度 page.goto 檢查 ---
        page = await context.new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # 新增：判斷是否為下載檔案導致的 net::ERR_ABORTED
            if response is None:
                # 這種情況通常是下載檔案，Playwright 不會回傳 response
                # 嘗試用 HEAD 再抓一次 Content-Type
                try:
                    head_resp = await context.request.head(url, timeout=10000)
                    content_type = head_resp.headers.get("content-type", "").lower()
                    if any(x in content_type for x in ["pdf", "msword", "excel", "zip", "octet-stream"]):
                        return {"url": url, "status_code": "Download", "error_message": f"檔案下載 ({content_type})"}
                except Exception:
                    pass
                # 若無法判斷，仍標記為下載
                return {"url": url, "status_code": "Download", "error_message": "檔案下載/非網頁內容"}
            if response and response.ok:
                return None
            elif response:
                return {"url": url, "status_code": response.status, "error_message": response.status_text}
            else:
                return {"url": url, "status_code": "Error", "error_message": "goto 檢查失敗"}
        finally:
            await page.close() # 確保深度檢查的分頁被關閉

    except PlaywrightTimeoutError:
        return {"url": url, "status_code": "Timeout", "error_message": "請求超時 (30秒)"}
    except Exception as e:
        # 捕捉其他所有 Playwright 請求錯誤，並簡化錯誤訊息
        full_error_message = str(e)
        
        if "net::ERR_NAME_NOT_RESOLVED" in full_error_message or "ENOTFOUND" in full_error_message:
            status_code = "DNS Error"
            simple_error_message = "DNS 查無此域名"
        elif "net::ERR_CONNECTION_RESET" in full_error_message:
            status_code = "Connection Reset"
            simple_error_message = "連線被重設"
        elif "net::ERR_CONNECTION_TIMED_OUT" in full_error_message or "Timeout" in full_error_message:
             status_code = "Connection Timeout"
             simple_error_message = "連線逾時"
        elif "404" in full_error_message:
            status_code = 404
            simple_error_message = "Not Found"
        else:
            status_code = "Error"
            # 截取第一行作為簡化錯誤訊息
            simple_error_message = full_error_message.split('\n')[0]

        return {"url": url, "status_code": status_code, "error_message": simple_error_message}
    finally:
        if context:
            await context.close() # 確保獨立的 context 被關閉


async def extract_structured_data(soup: BeautifulSoup, page: Page, base_url: str, html_content: str) -> Tuple[str, str, str, str, Optional[datetime.datetime]]:
    """從 soup 和 page 中提取結構化資料，並強化日期提取邏輯。"""
    title = soup.title.string.strip() if soup.title else ""
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = meta_desc_tag["content"].strip() if meta_desc_tag else ""
    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else ""

    # --- 日期提取強化 --- 
    update_date = ""

    # 1. 優先從 Meta 標籤尋找
    meta_selectors = [
        {'name': 'publish_date'}, {'property': 'og:updated_time'},
        {'name': 'last-modified'}, {'name': 'date'},
        {'name': 'dc.date.modified'}, {'name': 'last-update'}
    ]
    for selector in meta_selectors:
        tag = soup.find("meta", attrs=selector)
        if tag and tag.get('content'):
            parsed_date = _parse_and_normalize_date(tag['content'])
            if parsed_date:
                update_date = parsed_date
                break
    
    # 2. 如果 Meta 中沒有，則搜尋內文
    if not update_date:
        # 移除腳本和樣式，避免干擾
        for tag in soup(["script", "style"]):
            tag.decompose()
        
        # 使用更寬鬆的內文進行搜尋
        text_content = soup.get_text()

        # 包含「更新日期」等關鍵字和日期的模式
        # (?: ... ) 是非捕獲組
        date_pattern = r'(?:更新|發布|修改|建立|上版|異動)日期?[:：\s]*(\d{3,4}[-.\/年]\d{1,2}[-.\/月]\d{1,2}日?)'
        matches = re.finditer(date_pattern, text_content)
        
        latest_date = None
        for match in matches:
            parsed_date = _parse_and_normalize_date(match.group(1))
            if parsed_date:
                current_date = datetime.datetime.strptime(parsed_date, '%Y-%m-%d').date()
                if latest_date is None or current_date > latest_date:
                    latest_date = current_date
        
        if latest_date:
            update_date = latest_date.isoformat()

    # --- 資料清理與回傳 ---
    # 移除不需要的標籤以取得乾淨的 body text
    for tag in soup(["nav", "footer", "script", "style", "header"]):
        # soup.find(...) might find a tag that was already decomposed
        if tag in soup.find_all(tag.name):
             tag.decompose()
    body_text = soup.get_text(separator="\n", strip=True)

    return title, meta_desc, h1, body_text, update_date

# --- 新增：日期處理輔助函式 ---
def _parse_and_normalize_date(date_str: str) -> Optional[str]:
    """
    嘗試解析多種格式的日期字串，並將其標準化為 YYYY-MM-DD。
    支援民國年轉換。
    """
    if not date_str:
        return None

    # 移除時間部分，只關注日期
    date_str = date_str.split(' ')[0]

    # 處理民國年 (e.g., 113.05.20 or 113-05-20)
    match = re.match(r'(1\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})日?'
, date_str)
    if match:
        roc_year, month, day = map(int, match.groups())
        if roc_year > 150: # 避免誤判西元年
            return None
        ad_year = roc_year + 1911
        try:
            return datetime.date(ad_year, month, day).isoformat()
        except ValueError:
            return None

    # 處理西元年 (e.g., 2024-05-20, 2024/05/20, etc.)
    try:
        # 使用 dateutil.parser 會更強大，但為減少依賴，先用 datetime
        # 移除所有非數字字元，用標準格式嘗試
        parts = re.split(r'[.\-/年日月]', date_str)
        parts = [p for p in parts if p.isdigit()]
        if len(parts) == 3:
            year, month, day = map(int, parts)
            if year < 1900: # 假設不會有這麼舊的網站
                return None
            return datetime.date(year, month, day).isoformat()
    except (ValueError, TypeError):
        pass

    return None


# --- Helper Functions (部分修改) ---

async def detect_js_libraries(page: Page) -> List[Dict]:
    """在頁面中執行 JS 來偵測前端函式庫版本。"""
    libraries = []
    try:
        # 偵測 jQuery
        jquery_version = await page.evaluate("""() => {
            try { return window.jQuery.fn.jquery; } catch (e) { return null; }
        }""")
        if jquery_version:
            libraries.append({"name": "jQuery", "version": jquery_version})

        # 偵測 React
        react_version = await page.evaluate("""() => {
            try {
                if (window.React) return window.React.version;
                const reactRoot = document.querySelector('[data-reactroot]');
                if (reactRoot) {
                    const instance = reactRoot._reactRootContainer || reactRoot._internalRoot;
                    if (instance) return instance.current.memoizedState.current.memoizedState.version;
                }
                return null;
            } catch (e) { return null; }
        }""")
        if react_version:
            libraries.append({"name": "React", "version": react_version})

        # 偵測 Vue
        vue_version = await page.evaluate("""() => {
            try { return window.Vue.version; } catch (e) { return null; }
        }""")
        if vue_version:
            libraries.append({"name": "Vue", "version": vue_version})

    except Exception as e:
        # 如果偵測失敗，不中斷爬取流程，僅印出錯誤
        print(f"無法為 {page.url} 偵測 JS 函式庫: {e}")

    return libraries
