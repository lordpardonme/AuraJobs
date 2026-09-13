import json
import urllib.parse
import urllib.request
import pandas as pd
from .base import BaseSourceAdapter

class RemotiveAdapter(BaseSourceAdapter):
    """
    Direct API adapter for Remotive (https://remotive.com/api/remote-jobs).
    Public, zero-block REST endpoint with categorized remote listings.
    """

    API_BASE = "https://remotive.com/api/remote-jobs"

    def __init__(self):
        super().__init__(name="remotive")

    def fetch_jobs(self, search_term: str = "") -> pd.DataFrame:
        query_encoded = urllib.parse.quote(search_term.strip())
        url = f"{self.API_BASE}?search={query_encoded}" if query_encoded else self.API_BASE

        req = urllib.request.Request(
            url,
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

            rows = []
            for item in jobs_list:
                job_url = item.get("url", "")
                rows.append({
                    "id": str(item.get("id", "")),
                    "title": item.get("title", ""),
                    "company": item.get("company_name", ""),
                    "location": item.get("candidate_required_location") or "Worldwide (Remote)",
                    "country": "Worldwide",
                    "region": "Global",
                    "description": item.get("description", ""),
                    "date_posted": item.get("publication_date", ""),
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "salary_min": None,
                    "salary_max": None,
                    "currency": "USD",
                    "is_remote": True,
                    "job_type": item.get("job_type", "Full-time"),
                    "Search Region": "Global",
                    "Search Location": "Remote",
                    "Search Term": search_term,
                    "Search Source": "remotive",
                })

            return pd.DataFrame(rows)

        except Exception as e:
            return pd.DataFrame()

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        return self.fetch_jobs(search_term=term)
