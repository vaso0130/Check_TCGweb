import nest_asyncio
nest_asyncio.apply()

import csv
import os
import asyncio
import traceback # 匯入 traceback 模組
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser
from tqdm.asyncio import tqdm_asyncio
from database.db_handler import init_db, save_analysis_result
from datetime import date

# 1. 匯入重構後的函式和 Agent
from crawler.web_crawler import crawl # 直接匯入 crawl 函式
from analyzer.content_analysis import ContentAnalysisAgent
from reporter.report_generation import ReportGenerationAgent
from common.data_structures import AnalysisResult

# --- Configuration ---
CONCURRENT_TASKS = 5


def load_websites(path: str):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # 增加一個篩選器，忽略被註解掉的 URL
        return [(row["URL"], row.get("name", "")) for row in reader if row["URL"] and not row["URL"].startswith('#')]

async def process_website(
    url: str, 
    name: str, 
    analyzer: ContentAnalysisAgent, 
    semaphore: asyncio.Semaphore, 
    browser: Browser
) -> AnalysisResult:
    """處理單一網站的 Worker Task"""
    async with semaphore:
        try:
            # 直接呼叫 crawl 函式
            crawl_result = await crawl(browser, url)
            analysis = await analyzer.analyze(crawl_result)
            
            # 在這裡儲存到資料庫
            save_analysis_result(
                url=crawl_result.url,
                analysis_date=date.today(),
                outdated_score=analysis.score if analysis else None,
                raw_analysis_response=analysis.notes if analysis else "",
                broken_links=crawl_result.broken_links,
                detected_libraries=crawl_result.detected_libraries
            )

            return analysis
        except Exception as e:
            print(f"處理 {url} 時發生未預期的嚴重錯誤: {e}")
            traceback.print_exc() # 印出詳細的錯誤追蹤
            # 確保所有欄位都有預設值
            return AnalysisResult(
                url=url,
                status="🔥 錯誤",
                last_updated="N/A",
                score=100,
                notes=f"主流程發生未預期錯誤: {e}",
                broken_links_summary="無法分析",
                detected_libraries_summary="無法分析"
            )

async def main():
    load_dotenv()
    
    # 初始化資料庫
    init_db()

    websites = load_websites("config/websites.csv")

    # 初始化 Agents (不再需要 crawler agent)
    analyzer = ContentAnalysisAgent()
    reporter = ReportGenerationAgent()
    
    semaphore = asyncio.Semaphore(CONCURRENT_TASKS)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        tasks = [
            process_website(url, name, analyzer, semaphore, browser)
            for url, name in websites
        ]

        print(f"開始分析 {len(tasks)} 個網站 (並行數量: {CONCURRENT_TASKS})...")
        
        # 使用 tqdm 顯示進度條並執行所有任務
        results = await tqdm_asyncio.gather(*tasks)

        # 優雅地關閉瀏覽器，忽略在關閉時可能發生的連線錯誤
        try:
            await browser.close()
        except Exception as e:
            print(f"\n關閉瀏覽器時發生非嚴重錯誤 (可忽略): {e}")
    
    valid_results = [res for res in results if res is not None]

    print(f"\n分析完成，共取得 {len(valid_results)} 筆結果。正在產生報告...")
    output_path = reporter.generate(valid_results)
    print(f"報告已儲存至: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
