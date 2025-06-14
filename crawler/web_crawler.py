import re
from dataclasses import dataclass
from typing import Dict
from urllib.parse import urljoin

import requests
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

    def crawl(self, url: str) -> CrawlResult:
        try:
            resp = requests.get(url, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException:
            return CrawlResult(url, "", "", {})

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        text = soup.get_text(" ", strip=True)
        date_match = re.search(r"(\d{4}[/-]\d{1,2}[/-]\d{1,2})", text)
        last_updated = date_match.group(1) if date_match else ""

        link_status = {}
        for a in soup.find_all("a", href=True)[:5]:
            link = urljoin(url, a["href"])
            try:
                r = requests.head(link, timeout=5)
                link_status[link] = r.status_code
            except requests.RequestException:
                link_status[link] = 0

        return CrawlResult(url, html, last_updated, link_status)
