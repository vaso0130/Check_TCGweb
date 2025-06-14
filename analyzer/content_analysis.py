import re
from datetime import datetime
from dataclasses import dataclass
from typing import Dict

from crawler.web_crawler import CrawlResult

@dataclass
class AnalysisResult:
    url: str
    status: str
    last_updated: str
    score: int
    notes: str


class ContentAnalysisAgent:
    def __init__(self, reference_year: int = datetime.now().year):
        self.reference_year = reference_year

    def analyze(self, crawl_result: CrawlResult) -> AnalysisResult:
        score = 0
        notes = []

        if crawl_result.last_updated:
            try:
                dt = datetime.strptime(crawl_result.last_updated, "%Y/%m/%d")
            except ValueError:
                try:
                    dt = datetime.strptime(crawl_result.last_updated, "%Y-%m-%d")
                except ValueError:
                    dt = None
            if dt and (datetime.now() - dt).days > 365:
                score += 50
                notes.append("更新超過一年")
        else:
            score += 50
            notes.append("無更新日期")

        old_years = set(re.findall(r"20\d{2}", crawl_result.html))
        for y in old_years:
            if int(y) <= self.reference_year - 4:
                score += 20
                notes.append(f"提及過去年份 {y}")
                break

        if any(code != 200 for code in crawl_result.link_status.values()):
            score += 20
            notes.append("存在死連結")

        if score < 50:
            status = "✅ 正常"
        elif score < 80:
            status = "⚠️ 疑似"
        else:
            status = "❌ 過時"

        return AnalysisResult(
            url=crawl_result.url,
            status=status,
            last_updated=crawl_result.last_updated,
            score=score,
            notes="; ".join(notes),
        )
