import json
import urllib.request
import pandas as pd
from .base import BaseSourceAdapter
from core.cache import cache_adapter_response

class HimalayasAdapter(BaseSourceAdapter):
    """
    Direct API adapter for Himalayas (https://himalayas.app/jobs/api).
    Public REST API with salary transparency and verified tech/design roles.
    """

    API_URL = "https://himalayas.app/jobs/api?limit=50"

    def __init__(self):
        super().__init__(name="himalayas")

    @cache_adapter_response()
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

            jobs_list = data.get("jobs", [])
            if not jobs_list:
                return pd.DataFrame()

            terms = [t.lower() for t in (positive_terms or [target_role]) if t]

            rows = []
            for item in jobs_list:
                title = item.get("title", "")
                title_lower = title.lower()

                if terms and not any(t in title_lower for t in terms):
                    continue

                app_link = item.get("applicationLink") or item.get("url") or ""
                rows.append({
                    "id": str(item.get("id", "")),
                    "title": title,
                    "company": item.get("companyName", ""),
                    "location": "Worldwide (Remote)",
                    "country": "Worldwide",
                    "region": "Global",
                    "description": item.get("excerpt", ""),
                    "date_posted": item.get("publishedAt", item.get("updatedAt", "")),
                    "job_url": app_link,
                    "job_url_direct": app_link,
                    "salary_min": item.get("minSalary"),
                    "salary_max": item.get("maxSalary"),
                    "currency": "USD",
                    "is_remote": True,
                    "job_type": item.get("employmentType", "Full-time"),
                    "Search Region": "Global",
                    "Search Location": "Remote",
                    "Search Term": target_role,
                    "Search Source": "himalayas",
                })

            return pd.DataFrame(rows)

        except Exception as e:
            return pd.DataFrame()

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        return self.fetch_jobs(target_role=term)
