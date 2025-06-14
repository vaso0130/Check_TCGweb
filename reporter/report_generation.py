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
        df = pd.DataFrame([asdict(r) for r in results])
        today = datetime.now().strftime("%Y%m%d")
        output_path = os.path.join(self.output_dir, f"report_{today}.xlsx")
        df.to_excel(output_path, index=False)
        return output_path
