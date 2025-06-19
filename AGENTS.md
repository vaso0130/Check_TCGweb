# AGENTS.md

## 1. 專案概述

本專案透過多代理架構，自動化檢查 400+ 個政府網站是否「過時」，並產出可操作的評估報告。

## 2. 代理人 (Agents)

### 2.1 WebCrawlerAgent

- **職責**：抓取每個網站的首頁 HTML 與公告／最新消息內容，並擷取：
  - 最後更新時間戳
  - 圖片與連結狀態
- **輸入**：網站 URL 清單
- **輸出**：原始 HTML、公告文字、資源檢視結果
- **技術棧**：`requests`、`BeautifulSoup`、`playwright`

### 2.2 ContentAnalysisAgent

- **職責**：將爬取結果提交至 LLM，根據判斷標準評估「過時」風險，回傳：
  - 過時分數 (0–100)
  - 過時標記與原因說明
- **輸入**：WebCrawlerAgent 輸出之內容
- **輸出**：結構化分析結果
- **技術棧**：OpenAI GPT-4 或 Gemini 1.5 Pro API

### 2.3 ReportGenerationAgent

- **職責**：整合所有分析結果，產出最終報表
- **輸入**：ContentAnalysisAgent 回傳之結果列表
- **輸出**：Excel (`.xlsx`) 或 Google Sheets
- **技術棧**：`pandas`、`openpyxl`、`gspread`

## 3. 判斷標準 (Judgement Criteria)

| 檢查面向       | 標準說明                  |
| ---------- | --------------------- |
| 更新時間       | 最後更新超過 1 年            |
| 時效性內容      | 文中提及過去年度 (如 2020、疫情等) |
| 設計風格       | 使用 Flash、舊式前端框架       |
| SSL / HTTP | 憑證過期或連線失敗             |
| 連結與圖檔      | 存在死連結或圖片無法載入          |

## 4. 技術流程 (Workflow)

1. **Initialization**：讀取 `config/websites.csv`，啟動 WebCrawlerAgent 逐一抓取。
2. **Content Analysis**：每筆結果傳給 ContentAnalysisAgent，取得過時評估。
3. **Report Assembly**：ReportGenerationAgent 整合，輸出 `output/report_{YYYYMMDD}.xlsx`。

## 5. 配置與部署 (Config & Deployment)

- **網站清單**：`config/websites.csv`，格式：`URL, name`
- **API 金鑰**：環境變數  `GEMINI_API_KEY`
- **報表目錄**：`output/`

## 6. 預期輸出範例 (Expected Output)

| 網站 URL       | 狀態    | 最近更新       | 過時分數 | 說明       |
| ------------ | ----- | ---------- | ---- | -------- |
| a.gov.taiepi | ✅ 正常  | 2025/01/01 | 10   | 近期公告更新   |
| b.org.taiepi | ⚠️ 疑似 | 2020/05/12 | 95   | 多處陳舊疫情訊息 |
