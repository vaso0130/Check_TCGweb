import csv

from crawler.web_crawler import WebCrawlerAgent
from analyzer.content_analysis import ContentAnalysisAgent
from reporter.report_generation import ReportGenerationAgent


def load_websites(path: str):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [(row["URL"], row.get("name", "")) for row in reader]


def main():
    websites = load_websites("config/websites.csv")

    crawler = WebCrawlerAgent()
    analyzer = ContentAnalysisAgent()
    reporter = ReportGenerationAgent()

    results = []
    for url, name in websites:
        crawl_result = crawler.crawl(url)
        analysis = analyzer.analyze(crawl_result)
        results.append(analysis)
        print(f"Processed {url} -> {analysis.status}")

    output_path = reporter.generate(results)
    print(f"Report saved to {output_path}")


if __name__ == "__main__":
    main()
