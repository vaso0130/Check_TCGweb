import os
import re
import json
from datetime import datetime

import google.generativeai as genai

# 1. 從新的位置匯入資料結構
from common.data_structures import CrawlResult, AnalysisResult

class ContentAnalysisAgent:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    async def analyze(self, crawl_result: CrawlResult) -> AnalysisResult:
        # 2. 優先處理爬取過程中發生的錯誤
        if crawl_result.error_message:
            return AnalysisResult(
                url=crawl_result.url,
                status="🔥 錯誤",
                last_updated="N/A",
                score=100, # 標示為最高分，表示嚴重問題
                notes=f"無法抓取或處理網頁: {crawl_result.error_message}",
                broken_links_summary=""
            )

        today_str = datetime.now().strftime("%Y-%m-%d")

        # 3. 格式化失效連結字串
        broken_links_list = [
            f"- {link['url']} (狀態: {link['status_code']}, 類型: {link['type']})"
            for link in crawl_result.broken_links
        ]
        broken_links_str = "\n".join(broken_links_list) if broken_links_list else "無"

        # 新增：格式化偵測到的函式庫字串
        detected_libs_list = [
            f"- {lib['name']}: {lib['version']}"
            for lib in crawl_result.detected_libraries
        ]
        detected_libs_str = "\n".join(detected_libs_list) if detected_libs_list else "未偵測到"

        # 建立傳送給 AI 的 Prompt
        prompt = self._build_prompt(today_str, crawl_result, broken_links_str, detected_libs_str)

        try:
            response = await self.model.generate_content_async(prompt)
            # 從回傳的 Markdown 中解析 JSON
            json_text = self._extract_json_from_response(response.text)
            ai_result = json.loads(json_text)

            # 4. 新的計分邏輯
            scores = ai_result.get("scores", {})
            component_score = float(scores.get("outdated_component", 0))
            content_score = float(scores.get("outdated_content", 0))
            update_score = float(scores.get("last_update", 0))
            broken_link_penalty = float(scores.get("broken_link_penalty", 0))

            # 加總分數，並確保在 0-100 之間
            total_score = round(component_score + content_score + update_score + broken_link_penalty)
            total_score = min(100, total_score) # 將總分上限設為 100

            notes = ai_result.get("notes", "AI 未提供分析說明。")

            # 根據分數決定狀態
            if total_score >= 80:
                status = "❌ 嚴重過時"
            elif total_score >= 50:
                status = "⚠️ 疑似過時"
            else:
                status = "✅ 正常"

            return AnalysisResult(
                url=crawl_result.url,
                status=status,
                last_updated=crawl_result.update_date or "未找到",
                score=total_score,
                notes=notes,
                broken_links_summary=broken_links_str
            )

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            # 增強錯誤處理，捕捉更多潛在的 JSON 解析問題
            error_details = f"AI 分析時發生錯誤: {type(e).__name__} - {e}. Raw response: {response.text[:500]}"
            return AnalysisResult(
                url=crawl_result.url,
                status="🔥 錯誤",
                last_updated=crawl_result.update_date or "N/A",
                score=100,
                notes=error_details,
                broken_links_summary=broken_links_str
            )
        except Exception as e:
            return AnalysisResult(
                url=crawl_result.url,
                status="🔥 錯誤",
                last_updated=crawl_result.update_date or "N/A",
                score=100,
                notes=f"AI 分析時發生未知錯誤: {str(e)}",
                broken_links_summary=broken_links_str
            )

    def _extract_json_from_response(self, text: str) -> str:
        """從 AI 回傳的文字中提取 JSON 字串。"""
        match = re.search(r"```json\n({.*?})\n```", text, re.DOTALL)
        if match:
            return match.group(1)
        # 如果找不到 Markdown 格式，就假設整個回傳都是 JSON
        return text

    def _build_prompt(self, today_str: str, crawl_result: CrawlResult, broken_links_str: str, detected_libs_str: str) -> str:
        """建立傳送給 AI 的提示指令。"""
        return f"""
        請扮演一位網站健檢專家，根據我提供的結構化資料，專業地評估一個政府網站的狀態。

        **重要前提**: 您的評估應專注於**內容時效性**與**技術健全度**，忽略網站版型、Meta描述等模板化設計。

        **1. 基礎資訊:**
        - **檢測日期**: {today_str}
        - **網站 URL**: {crawl_result.url}
        - **偵測到的最後更新日期**: {crawl_result.update_date or '未找到'}

        **2. 技術元件資訊:**
        - **偵測到的前端函式庫**:
        ```
        {detected_libs_str}
        ```
        - **失效連結列表**:
        ```
        {broken_links_str}
        ```

        **3. 網頁主要文字內容 (已過濾導覽列、頁尾等無關部分):**
        ```text
        {crawl_result.body_text[:3000] if crawl_result.body_text else '[無內文]'}
        ```

        **4. 評分指南 (請嚴格遵循，總分100分):**
        您必須針對以下三個主要項目，各自給予 0 到 33.33 之間的分數。分數越高，代表該項目越過時或問題越嚴重。
        此外，您需要根據失效連結的數量給予一個額外的加分項。

        **A. 過時元件 (Outdated Component) - (0-33.33分):**
        - **基準**: jQuery < 3.0, React < 16.8, Vue < 2.6 皆視為過時。
        - **0分**: 未偵測到函式庫，或使用的函式庫皆為現代版本。
        - **1-15分**: 使用了一個過時的函式庫。
        - **16-33.33分**: 使用了多個過時的函式庫，或版本極為古老 (例如 jQuery 1.x)。

        **B. 過時內容 (Outdated Content) - (0-33.33分):**
        - **0分**: 內容非常新穎，提及近期的活動或資訊。
        - **1-15分**: 內容看起來不常更新 (例如都是通用性說明)，但沒有明確的過期指標。
        - **16-33.33分**: 內容有非常明確的過期資訊 (例如: 提及數年前的活動、新聞、法規，且無更新跡象)。

        **C. 過久未更新 (Last Update) - (0-33.33分):**
        - **0分**: 「最後更新日期」在一年內。
        - **1-15分**: 「最後更新日期」距今 1-2 年。
        - **16-33.33分**: 「最後更新日期」距今超過 2 年，或完全找不到更新日期。

        **D. 額外加分 - 失效連結 (Broken Link Penalty) - (0-5分):**
        - **0分**: 沒有失效連結。
        - **1-2分**: 存在 1-4 個失效連結。
        - **3-5分**: 存在 5 個或更多失效連結。

        **5. 你的任務:**
        請根據以上所有資訊，綜合判斷並嚴格按照下面的 JSON 格式回傳你的分析結果。
        在 `notes` 中，請簡潔地總結你的主要發現，並點出判斷的關鍵依據 (例如：「偵測到使用過時的 jQuery 1.12.4，且最後更新日為三年前，並發現3個失效連結。」)。

        **JSON 輸出 (請確保 JSON 格式正確):**
        ```json
        {{
          "scores": {{
            "outdated_component": <A項目的分數 (0-33.33)>,
            "outdated_content": <B項目的分數 (0-33.33)>,
            "last_update": <C項目的分數 (0-33.33)>,
            "broken_link_penalty": <D項目的分數 (0-5)>
          }},
          "notes": "<總結你發現的中文說明>"
        }}
        ```
        """
