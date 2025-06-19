import nest_asyncio
nest_asyncio.apply()

import csv
import os
import asyncio
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser
from tqdm.asyncio import tqdm_asyncio

# 1. 匯入重構後的 Agent 和新的資料結構
from crawler.web_crawler import WebCrawlerAgent
from analyzer.content_analysis import ContentAnalysisAgent
from reporter.report_generation import ReportGenerationAgent
from common.data_structures import AnalysisResult

# --- Configuration ---
CONCURRENT_TASKS = 10 # 稍微增加並行任務數


def load_websites(path: str):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # 增加一個篩選器，忽略被註解掉的 URL
        return [(row["URL"], row.get("name", "")) for row in reader if row["URL"] and not row["URL"].startswith('#')]

async def process_website(
    url: str, 
    name: str, 
    crawler: WebCrawlerAgent, 
    analyzer: ContentAnalysisAgent, 
    semaphore: asyncio.Semaphore, 
    browser: Browser
) -> AnalysisResult:
    """處理單一網站的 Worker Task"""
    async with semaphore:
        try:
            # 流程不變：爬取 -> 分析
            crawl_result = await crawler.crawl(browser, url)
            analysis = await analyzer.analyze(crawl_result)
            return analysis
        except Exception as e:
            print(f"處理 {url} 時發生未預期的嚴重錯誤: {e}")
            # 2. 更新錯誤回傳，以匹配新的 AnalysisResult 結構
            return AnalysisResult(
                url=url,
                status="🔥 錯誤",
                last_updated="N/A",
                score=100,
                notes=f"主流程發生未預期錯誤: {e}",
                broken_links_summary=""
            )

async def main():
    load_dotenv()
    websites = load_websites("config/websites.csv")

    # 初始化 Agents
    crawler = WebCrawlerAgent()
    analyzer = ContentAnalysisAgent()
    reporter = ReportGenerationAgent()
    
    semaphore = asyncio.Semaphore(CONCURRENT_TASKS)

    async with async_playwright() as p:
        # 啟動共享的瀏覽器實例
        browser = await p.chromium.launch(headless=True)
        
        tasks = [
            process_website(url, name, crawler, analyzer, semaphore, browser)
            for url, name in websites
        ]

        print(f"開始分析 {len(tasks)} 個網站 (並行數量: {CONCURRENT_TASKS})...")
        
        # 使用 tqdm 顯示進度條並執行所有任務
        results = await tqdm_asyncio.gather(*tasks)

        await browser.close()
    
    # 3. 在所有流程結束後，優雅地關閉 crawler agent 內部的 httpx 客戶端
    await crawler.http_client.aclose()

    valid_results = [res for res in results if res is not None]

    print(f"\n分析完成，共取得 {len(valid_results)} 筆結果。正在產生報告...")
    output_path = reporter.generate(valid_results)
    print(f"報告已儲存至: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
