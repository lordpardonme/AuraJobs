import json
import urllib.request
import pandas as pd
from .base import BaseSourceAdapter

class RemoteOKAdapter(BaseSourceAdapter):
    """
    Direct API adapter for RemoteOK (https://remoteok.com/api).
    Instant, zero-block public REST endpoint for tech & digital product roles.
    """

    API_URL = "https://remoteok.com/api"

    def __init__(self):
        super().__init__(name="remoteok")

    def fetch_jobs(self, target_role: str = "", positive_terms: list = None) -> pd.DataFrame:
        req = urllib.request.Request(
            self.API_URL,
            headers={
                "User-Agent": "JobHuntingEngine/1.0 (Mozilla/5.0 Compatible)",
                "Accept": "application/json",
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if not isinstance(data, list):
                return pd.DataFrame()

            # The first element of RemoteOK is metadata/legal text
            job_items = [item for item in data if isinstance(item, dict) and "position" in item]

            terms = [t.lower() for t in (positive_terms or [target_role]) if t]

            rows = []
            for item in job_items:
                pos = str(item.get("position", "")).lower()
                tags = " ".join(item.get("tags", [])).lower()
                searchable = f"{pos} {tags}"

                # Match against target terms
                if terms and not any(term in searchable for term in terms):
                    continue

                url = item.get("apply_url") or item.get("url") or ""
                rows.append({
                    "id": str(item.get("id", "")),
                    "title": item.get("position", ""),
                    "company": item.get("company", ""),
                    "location": item.get("location") or "Worldwide (Remote)",
                    "country": "Worldwide",
                    "region": "Global",
                    "description": item.get("description", ""),
                    "date_posted": item.get("date", ""),
                    "job_url": url,
                    "job_url_direct": url,
                    "salary_min": item.get("salary_min"),
                    "salary_max": item.get("salary_max"),
                    "currency": "USD",
                    "is_remote": True,
                    "job_type": "Full-time",
                    "Search Region": "Global",
                    "Search Location": "Remote",
                    "Search Term": target_role,
                    "Search Source": "remoteok",
                })

            return pd.DataFrame(rows)

        except Exception as e:
            return pd.DataFrame()

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        return self.fetch_jobs(target_role=term)
