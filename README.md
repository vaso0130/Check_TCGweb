# Check TCGweb

這個專案依照 `AGENTS.md` 所述的多代理架構，檢查政府網站是否過時並產生報表。

## 使用方式

1. 於 `config/websites.csv` 填入要檢查的網站 URL 與名稱。
2. 安裝依賴：`pip install -r requirements.txt`。
3. 執行：`python main.py`。
4. 報表將輸出至 `output/` 目錄。
