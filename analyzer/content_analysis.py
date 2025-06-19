import os
import re
import json
from datetime import datetime
from dataclasses import dataclass
from typing import Dict

import google.generativeai as genai
from crawler.web_crawler import CrawlResult

@dataclass
class AnalysisResult:
    url: str
    status: str
    last_updated: str
    score: int
    notes: str
    broken_links: str


class ContentAnalysisAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-06-17')


    def analyze(self, crawl_result: CrawlResult) -> AnalysisResult:
        if not crawl_result.html:
            return AnalysisResult(
                url=crawl_result.url,
                status="❌ 錯誤",
                last_updated="",
                score=100,
                notes="無法抓取網頁內容",
                broken_links="",
            )

        today_str = datetime.now().strftime("%Y-%m-%d")

        broken_links_list = [
            f"{link} (狀態: {code})"
            for link, code in crawl_result.link_status.items()
            if code != 200
        ]
        broken_links_str = "\n".join(broken_links_list)

        prompt = f"""
        請根據以下HTML內容和抓取到的資訊，評估一個政府網站是否過時。
        你的角色是一位網站健檢專家。

        **參考資訊:**
        - **今天日期**: {today_str}
        - 網站 URL: {crawl_result.url}
        - 最後更新日期: {crawl_result.last_updated or '未找到'}
        - **失效連結**: {broken_links_str or '無'}

        **判斷標準:**
        1.  **更新時間**: 最後更新日期是否超過一年？
        2.  **時效性內容**: 內文是否提及明顯的過去年份（例如 4 年前）或過時事件（如 2020 年的疫情訊息）？
        3.  **設計風格**: 是否使用了過時的技術，如 Flash？（從HTML中判斷）
        4.  **連結狀態**: 是否有無法連線的內部連結？(參考上面的失效連結列表)

        **HTML 內容 (前 2000 字元):**
        ```html
        {crawl_result.html[:2000]}
        ```

        **輸出要求:**
        請嚴格按照以下 JSON 格式回傳，不要有任何額外的文字或說明：
        {{\n          "score": <一個 0-100 的整數，分數越高代表越過時>,\n          "notes": "<一段簡短的中文說明，總結你的發現，如果發現失效連結，請在說明中提及(完整連結url)>"\n        }}
        """

        try:
            response = self.model.generate_content(prompt)
            # 清理並解析 JSON
            cleaned_response = response.text.strip().replace('`', '')
            if cleaned_response.startswith("json"):
                cleaned_response = cleaned_response[4:]
            
            data = json.loads(cleaned_response)
            score = data.get("score", 100)
            notes = data.get("notes", "無法從 API 取得有效回覆")

        except (json.JSONDecodeError, ValueError, Exception) as e:
            print(f"Error processing API response for {crawl_result.url}: {e}")
            score = 100
            notes = f"API 回應解析失敗: {e}"


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
            notes=notes,
            broken_links=broken_links_str,
        )
