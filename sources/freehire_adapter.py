import json
import urllib.parse
import urllib.request
import pandas as pd
from .base import BaseSourceAdapter

class FreeHireAdapter(BaseSourceAdapter):
    """
    Direct API adapter for FreeHire (https://freehire.me/api/v1).
    Open, zero-authentication search engine aggregating jobs directly from
    company ATS boards (Greenhouse, Lever, Freshteam, Recruitee, Workable).
    Strong coverage for Indian tech hubs (Bengaluru, Mumbai, Delhi, Hyderabad)
    as well as Global Remote positions.
    """

    API_SEARCH_URL = "https://freehire.me/api/v1/jobs/search"
    API_JOBS_URL = "https://freehire.me/api/v1/jobs"

    def __init__(self):
        super().__init__(name="freehire")

    def fetch_jobs(self, search_term: str = "", location: str = "", limit: int = 50) -> pd.DataFrame:
        params = {"limit": min(limit, 100)}
        if search_term:
            params["q"] = search_term.strip()
        if location and location.lower() not in ["all", "global", "worldwide"]:
            params["location"] = location.strip()

        query_str = urllib.parse.urlencode(params)
        url = f"{self.API_SEARCH_URL}?{query_str}" if params.get("q") else f"{self.API_JOBS_URL}?{query_str}"

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

            jobs_list = data.get("data", [])
            if not jobs_list:
                return pd.DataFrame()

            rows = []
            for item in jobs_list:
                job_url = item.get("url") or item.get("apply_url") or ""
                loc = item.get("location") or "Remote"
                
                # Determine regional tagging
                loc_lower = loc.lower()
                if any(c in loc_lower for c in ["india", "bengaluru", "bangalore", "mumbai", "delhi", "hyderabad", "pune", "gurgaon", "noida", "chennai"]):
                    region = "India"
                    country = "India"
                elif any(c in loc_lower for c in ["uae", "dubai", "abu dhabi", "riyadh", "saudi", "qatar", "kuwait", "bahrain"]):
                    region = "Middle East"
                    country = "Middle East"
                else:
                    region = "Global"
                    country = "Worldwide"

                rows.append({
                    "id": str(item.get("public_slug") or item.get("external_id") or ""),
                    "title": item.get("title", ""),
                    "company": item.get("company", ""),
                    "location": loc,
                    "country": country,
                    "region": region,
                    "description": item.get("description", ""),
                    "date_posted": item.get("created_at") or item.get("updated_at") or "",
                    "job_url": job_url,
                    "job_url_direct": item.get("apply_url") or job_url,
                    "salary_min": item.get("salary_min"),
                    "salary_max": item.get("salary_max"),
                    "currency": item.get("currency", "USD"),
                    "is_remote": item.get("remote", False) or "remote" in loc_lower,
                    "job_type": item.get("job_type", "Full-time"),
                    "Search Region": region,
                    "Search Location": loc,
                    "Search Term": search_term,
                    "Search Source": "freehire",
                })

            df = pd.DataFrame(rows)
            return df

        except Exception:
            return pd.DataFrame()

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        return self.fetch_jobs(search_term=term, location=location, limit=results_wanted)
