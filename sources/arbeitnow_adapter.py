import json
import urllib.parse
import urllib.request
import pandas as pd
from .base import BaseSourceAdapter
from core.cache import cache_adapter_response

class ArbeitnowAdapter(BaseSourceAdapter):
    """
    Direct API adapter for Arbeitnow (https://www.arbeitnow.com/api/job-board-api).
    Zero-authentication job board endpoint delivering curated European and
    Global Remote technology and design listings with rich metadata.
    """

    API_BASE = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self):
        super().__init__(name="arbeitnow")

    @cache_adapter_response()
    def fetch_jobs(self, search_term: str = "", limit: int = 50) -> pd.DataFrame:
        req = urllib.request.Request(
            self.API_BASE,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AuraJobs/1.0",
                "Accept": "application/json",
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            jobs_list = data.get("data", [])
            if not jobs_list:
                return pd.DataFrame()

            term_lower = search_term.lower().strip() if search_term else ""

            rows = []
            for item in jobs_list:
                title = item.get("title", "")
                tags = " ".join(item.get("tags", []))
                description = item.get("description", "")
                
                # In-memory filter for relevance if a search term is specified
                if term_lower:
                    searchable = f"{title} {tags}".lower()
                    term_tokens = term_lower.split()
                    if not any(token in searchable for token in term_tokens):
                        continue

                job_url = item.get("url", "")
                loc = item.get("location") or "Remote"
                is_remote = item.get("remote", False) or "remote" in loc.lower()

                rows.append({
                    "id": str(item.get("slug", "")),
                    "title": title,
                    "company": item.get("company_name", ""),
                    "location": loc,
                    "country": "Remote" if is_remote else "Worldwide",
                    "region": "Global",
                    "description": description,
                    "date_posted": item.get("created_at", ""),
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "salary_min": None,
                    "salary_max": None,
                    "currency": "USD",
                    "is_remote": is_remote,
                    "job_type": ", ".join(item.get("job_types", [])) or "Full-time",
                    "Search Region": "Global",
                    "Search Location": loc,
                    "Search Term": search_term,
                    "Search Source": "arbeitnow",
                })

                if len(rows) >= limit:
                    break

            df = pd.DataFrame(rows)
            return df

        except Exception:
            return pd.DataFrame()

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        return self.fetch_jobs(search_term=term, limit=results_wanted)
