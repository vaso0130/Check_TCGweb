
import sqlite3
import json
from datetime import date
from typing import List, Dict, Optional

DB_PATH = 'output/website_analysis.db'

def init_db():
    """初始化資料庫，如果資料表不存在則建立它。"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                analysis_date DATE NOT NULL,
                outdated_score INTEGER,
                raw_analysis_response TEXT,
                broken_links_count INTEGER,
                detected_libraries TEXT,
                UNIQUE(url, analysis_date)
            )
        """)
        conn.commit()

def save_analysis_result(
    url: str,
    analysis_date: date,
    outdated_score: Optional[int],
    raw_analysis_response: Optional[str],
    broken_links: List[Dict],
    detected_libraries: List[Dict]
):
    """將單一網站的分析結果儲存到資料庫。"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO analysis_history (url, analysis_date, outdated_score, raw_analysis_response, broken_links_count, detected_libraries)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                url,
                analysis_date,
                outdated_score,
                raw_analysis_response,
                len(broken_links),
                json.dumps(detected_libraries, ensure_ascii=False)
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            print(f"警告: 今天 ({analysis_date}) 的 {url} 的分析結果已存在於資料庫中，將會覆寫。")
            cursor.execute("""
                UPDATE analysis_history
                SET outdated_score = ?,
                    raw_analysis_response = ?,
                    broken_links_count = ?,
                    detected_libraries = ?
                WHERE url = ? AND analysis_date = ?
            """, (
                outdated_score,
                raw_analysis_response,
                len(broken_links),
                json.dumps(detected_libraries, ensure_ascii=False),
                url,
                analysis_date
            ))
            conn.commit()
        except Exception as e:
            print(f"儲存到資料庫時發生錯誤: {e}")
            conn.rollback()

def get_history_for_url(url: str) -> List[Dict]:
    """根據 URL 獲取其所有的歷史分析資料。"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM analysis_history WHERE url = ? ORDER BY analysis_date DESC", (url,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

