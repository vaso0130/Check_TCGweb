import csv
import os
import asyncio
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from crawler.web_crawler import WebCrawlerAgent
from analyzer.content_analysis import ContentAnalysisAgent
from reporter.report_generation import ReportGenerationAgent


def load_websites(path: str):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return [(row["URL"], row.get("name", "")) for row in reader]


async def main():
    load_dotenv()
    websites = load_websites("config/websites.csv")

    crawler = WebCrawlerAgent()
    analyzer = ContentAnalysisAgent()
    reporter = ReportGenerationAgent()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        results = []
        for url, name in websites:
            crawl_result = await crawler.crawl(browser, url)
            analysis = analyzer.analyze(crawl_result)
            results.append(analysis)
            print(f"Processed {url} -> {analysis.status}")
        await browser.close()

    output_path = reporter.generate(results)
    print(f"Report saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
