from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class CrawlResult:
    """儲存單一網站爬取結果的資料結構。"""
    url: str
    status_code: int | str
    title: Optional[str] = None
    meta_description: Optional[str] = None
    h1: Optional[str] = None
    body_text: Optional[str] = None
    update_date: Optional[str] = None
    broken_links: List[Dict] = field(default_factory=list)
    detected_libraries: List[Dict] = field(default_factory=list) # 新增欄位
    error_message: Optional[str] = None # 用於記錄爬取過程中的錯誤

@dataclass
class AnalysisResult:
    """儲存單一網站分析結果的資料結構。"""
    url: str
    status: str  # 例如: "✅ 正常", "⚠️ 疑似過時", "❌ 嚴重過時", "🔥 錯誤"
    last_updated: str
    score: int  # 0-100 的過時分數
    notes: str
    broken_links_summary: str # 整理後的失效連結字串
    detected_libraries_summary: str # 新增：整理後的偵測到的函式庫字串
