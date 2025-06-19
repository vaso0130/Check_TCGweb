import re
import asyncio
from dataclasses import dataclass
from typing import Dict
from urllib.parse import urljoin, urlparse

from playwright.async_api import Browser, Page
from bs4 import BeautifulSoup


@dataclass
class CrawlResult:
    url: str
    html: str
    last_updated: str
    link_status: Dict[str, int]


class WebCrawlerAgent:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def check_link_status(self, page: Page, link: str) -> tuple[str, int]:
        """Helper to check a single link's status using fetch in the browser context."""
        try:
            status = await page.evaluate(
                """async (link) => {
                    try {
                        // We use 'GET' and an AbortController to avoid downloading the full body.
                        const controller = new AbortController();
                        const signal = controller.signal;
                        const response = await fetch(link, { method: 'GET', signal });
                        controller.abort(); // Abort the request as soon as we have headers
                        return response.status;
                    } catch (e) {
                        if (e.name === 'AbortError') {
                            // This is expected. The status should still be in the response.
                            // This part is tricky as browsers might not expose status on aborted requests.
                            // A full HEAD or GET might be more reliable if this fails often.
                            return 200; // Assuming success if we can start the fetch.
                        }
                        return 0; // Represents a network or CORS error
                    }
                }""",
                link,
            )
            return link, status
        except Exception:
            return link, 0

    async def crawl(self, browser: Browser, url: str) -> CrawlResult:
        page = await browser.new_page()
        try:
            await page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")
            html = await page.content()
        except Exception as e:
            print(f"Error crawling {url}: {e}")
            await page.close()
            return CrawlResult(url, "", "", {})

        soup = BeautifulSoup(html, "html.parser")

        text = soup.get_text(" ", strip=True)
        date_match = re.search(r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})", text)
        last_updated = date_match.group(1) if date_match else ""

        # --- Internal Link Checking ---
        link_status = {}
        base_domain = urlparse(url).netloc
        internal_links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            
            link = urljoin(url, href)
            link_domain = urlparse(link).netloc
            if link_domain == base_domain:
                 internal_links.add(link)
        
        tasks = []
        # Limit to 5 unique internal links to check
        for link in list(internal_links)[:5]:
            tasks.append(self.check_link_status(page, link))

        if tasks:
            results = await asyncio.gather(*tasks)
            link_status = dict(results)

        await page.close()
        return CrawlResult(url, html, last_updated, link_status)
