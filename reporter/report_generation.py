import os
from dataclasses import asdict
from datetime import datetime
from typing import List

import pandas as pd

from analyzer.content_analysis import AnalysisResult


class ReportGenerationAgent:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(self, results: List[AnalysisResult]):
        data = [asdict(r) for r in results]
        df = pd.DataFrame(data)

        # 確保欄位順序一致，並將失效連結放在最後
        column_order = [
            "url",
            "status",
            "last_updated",
            "score",
            "notes",
            "broken_links",
        ]
        df = df.reindex(columns=[col for col in column_order if col in df.columns])

        today = datetime.now().strftime("%Y%m%d")
        output_path = os.path.join(self.output_dir, f"report_{today}.xlsx")
        df.to_excel(output_path, index=False)
        return output_path
