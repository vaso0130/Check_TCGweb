import asyncio
import re
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright, TimeoutError as PlaywrightTimeoutError, Browser

# 1. 從新的位置匯入資料結構
from common.data_structures import CrawlResult

# 2. 建立 Agent 類別來管理資源和封裝邏輯
class WebCrawlerAgent:
    def __init__(self):
        # 將 httpx 客戶端作為 Agent 的一部分來管理
        # 3. 調整 httpx 設定以提高穩定性
        # 增加連線池大小並延長超時時間，以避免在高併發下出現 PoolTimeout
        limits = httpx.Limits(max_connections=200, max_keepalive_connections=40)
        timeout = httpx.Timeout(30.0, pool=10.0) # 30秒整體超時, 10秒等待連線池

        self.http_client = httpx.AsyncClient(
            follow_redirects=True,
            verify=False,
            limits=limits,
            timeout=timeout
        )

    async def crawl(self, browser: Browser, url: str) -> CrawlResult:
        """使用共享的瀏覽器實例爬取網站，並統一回傳 CrawlResult。"""
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'html.parser')

            title, meta_desc, h1, body_text, update_date = await extract_structured_data(soup, page, url, html_content)

            # 新增：偵測 JS 函式庫
            detected_libs = await detect_js_libraries(page)
            broken_links = await self.check_links(page, url)

            return CrawlResult(
                url=url,
                status_code=200,
                title=title,
                meta_description=meta_desc,
                h1=h1,
                body_text=body_text,
                update_date=update_date,
                broken_links=broken_links,
                detected_libraries=detected_libs # 儲存偵測結果
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

    async def check_links(self, page: Page, base_url: str) -> List[Dict]:
        """混合模式連結檢查總管"""
        try:
            links = await page.eval_on_selector_all('a', 'elements => elements.map(el => el.href)')
        except Exception:
            links = []

        unique_links = sorted(list(set(
            urljoin(base_url, link.strip()) for link in links if link and not link.startswith(('javascript:', '#', 'mailto:', 'tel:'))
        )))

        base_hostname = urlparse(base_url).hostname
        tasks = []
        for link in unique_links:
            try:
                link_hostname = urlparse(link).hostname
                if link_hostname == base_hostname:
                    tasks.append(self.check_internal_link(link))
                else:
                    tasks.append(check_external_link(page, link))
            except Exception:
                continue

        results = await asyncio.gather(*tasks, return_exceptions=True)

        broken_links = []
        for result in results:
            if isinstance(result, dict):
                broken_links.append(result)

        return broken_links

    async def check_internal_link(self, url: str) -> Optional[Dict]:
        """內部連結檢查員 (從嚴)：使用 agent 的 httpx 客戶端。"""
        try:
            response = await self.http_client.get(url)
            if response.status_code >= 400:
                return {"url": url, "status_code": response.status_code, "type": "internal"}
            return None
        except httpx.RequestError as e:
            return {"url": url, "status_code": f"RequestError: {type(e).__name__}", "type": "internal"}
        except Exception as e:
            return {"url": url, "status_code": f"UnknownError: {type(e).__name__}", "type": "internal"}

# --- Helper Functions (獨立於 Agent 之外) ---

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

async def check_external_link(page: Page, url: str) -> Optional[Dict]:
    """外部連結檢查員 (從寬)：使用 Playwright 和白名單。"""
    known_social_domains = [
        'facebook.com', 'www.facebook.com', 'instagram.com', 
        'twitter.com', 'x.com', 'youtube.com', 'youtu.be', 't.co'
    ]
    whitelisted_domains = known_social_domains + ['accessibility.moda.gov.tw']

    try:
        parsed_url = urlparse(url)
        if parsed_url.netloc in whitelisted_domains:
            return None
    except Exception:
        pass

    try:
        response = await page.request.get(url, timeout=30000)
        status = response.status
        if status >= 400:
            return {"url": url, "status_code": status, "type": "external"}
        return None
    except Exception as e:
        error_message = str(e)
        status_code = "Error"
        if "Timeout" in error_message:
            status_code = "Timeout"
        elif "net::" in error_message:
            match = re.search(r'net::(ERR_\w+)', error_message)
            if match:
                status_code = match.group(1)
        return {"url": url, "status_code": status_code, "type": "external"}

async def extract_structured_data(soup: BeautifulSoup, page: Page, url: str, html_content: str) -> Tuple[str, str, str, str, str]:
    """從 soup 和 page 中提取結構化資料。"""
    title = soup.title.string.strip() if soup.title else ""
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_desc = meta_desc_tag["content"].strip() if meta_desc_tag else ""
    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else ""

    # 移除不需要的標籤
    for tag in soup(["nav", "footer", "script", "style", "header"]):
        tag.decompose()
    body_text = soup.get_text(separator="\n", strip=True)

    # 尋找更新日期
    date_pattern = r'(更新|發布|建立|修改)日期?[：:\s]*(\d{3,4}[-.\/年]\d{1,2}[-.\/月]\d{1,2})[日]?'
    match = re.search(date_pattern, html_content)
    update_date = match.group(2) if match else ""

    return title, meta_desc, h1, body_text, update_date
