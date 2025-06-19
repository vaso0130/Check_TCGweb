# Check TCGweb

這個專案檢查政府網站是否過時並產生報表。

## 使用方式

1. 於 `config/websites.csv` 填入要檢查的網站 URL 與名稱。
2. 安裝依賴：`pip install -r requirements.txt`。
3. 請在根目錄下新增`.env`，並輸入`GEMINI_API_KEY=YOUR_GEMINI_KEY`儲存。
4. 執行：`python main.py`。
5. 報表將輸出至 `output/` 目錄。
