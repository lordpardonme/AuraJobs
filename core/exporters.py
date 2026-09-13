import os
import re
from datetime import datetime
import pandas as pd

class OutputExporter:
    """
    Exports a single, clean, consolidated CSV file for the user's search
    without creating redundant sliced files or summary text documents.
    """

    def __init__(self, output_dir: str = None):
        if output_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(base_dir, "output")

        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export_single_file(self, final_df: pd.DataFrame, target_role: str,
                           geography: str, started: datetime) -> str:
        """
        Creates exactly ONE primary CSV output file containing all relevant jobs
        matching the user's preferences.
        """
        timestamp = started.strftime("%Y-%m-%d_%H-%M-%S")
        role_slug = re.sub(r"[^\w\-]", "_", target_role.strip()).strip("_")
        geo_slug = re.sub(r"[^\w\-]", "_", geography.strip()).strip("_")

        filename = f"AURAJOBS_{role_slug}_{geo_slug}_{timestamp}.csv"
        filepath = os.path.join(self.output_dir, filename)

        if final_df is not None and not final_df.empty:
            # Reorder key columns to the front for optimal viewing
            priority_cols = [
                "priority",
                "match_score",
                "title",
                "company",
                "location",
                "region",
                "source",
                "job_url",
                "visa_status",
                "relocation_status",
                "age_bucket",
                "date_posted",
                "salary_min",
                "salary_max",
                "currency",
                "remote_status",
                "discovered_sources",
                "description",
            ]
            existing_cols = [c for c in priority_cols if c in final_df.columns]
            other_cols = [c for c in final_df.columns if c not in existing_cols]
            ordered_df = final_df[existing_cols + other_cols]

            ordered_df.to_csv(filepath, index=False, encoding="utf-8-sig")
        else:
            # Create an empty file with headers so the user has a clear record
            pd.DataFrame(columns=[
                "priority", "match_score", "title", "company", "location",
                "region", "source", "job_url", "visa_status", "date_posted"
            ]).to_csv(filepath, index=False, encoding="utf-8-sig")

        return filepath
