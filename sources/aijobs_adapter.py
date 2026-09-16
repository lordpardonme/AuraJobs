import json
import urllib.parse
import urllib.request
import pandas as pd
from .base import BaseSourceAdapter

class AIJobsAdapter(BaseSourceAdapter):
    """
    Direct API adapter for Artificial Intelligence Jobs (https://artificialintelligencejobs.co).
    Zero-authentication, live crawler indexing positions across 260+ AI/ML companies
    with direct apply URLs to ATS platforms (Ashby, Greenhouse, Lever).
    """

    API_BASE = "https://artificialintelligencejobs.co/api/jobs"

    def __init__(self):
        super().__init__(name="aijobs")

    def fetch_jobs(self, search_term: str = "", limit: int = 50) -> pd.DataFrame:
        params = {"limit": min(limit, 50)}
        if search_term:
            params["q"] = search_term.strip()

        query_str = urllib.parse.urlencode(params)
        url = f"{self.API_BASE}?{query_str}"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AuraJobs/1.0",
                "Accept": "application/json",
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            jobs_list = data.get("jobs", [])
            if not jobs_list:
                return pd.DataFrame()

            rows = []
            for item in jobs_list:
                job_url = item.get("apply_url") or item.get("url") or ""
                loc = item.get("location") or "Remote"
                is_remote = item.get("remote", False) or "remote" in loc.lower()

                # Salary parsing if available
                salary_val = item.get("salary")
                sal_min, sal_max = None, None
                if isinstance(salary_val, (int, float)):
                    sal_min = salary_val

                rows.append({
                    "id": str(item.get("url", "").split("-")[-1] if item.get("url") else ""),
                    "title": item.get("title", ""),
                    "company": item.get("company", ""),
                    "location": loc,
                    "country": item.get("region", "Worldwide"),
                    "region": "Global" if is_remote else "Worldwide",
                    "description": f"Category: {item.get('category', '')}. Level: {item.get('level', '')}",
                    "date_posted": item.get("posted", ""),
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "salary_min": sal_min,
                    "salary_max": sal_max,
                    "currency": "USD",
                    "is_remote": is_remote,
                    "job_type": item.get("level") or "Full-time",
                    "Search Region": "Global",
                    "Search Location": loc,
                    "Search Term": search_term,
                    "Search Source": "aijobs",
                })

            df = pd.DataFrame(rows)
            return df

        except Exception:
            return pd.DataFrame()

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        return self.fetch_jobs(search_term=term, limit=results_wanted)
