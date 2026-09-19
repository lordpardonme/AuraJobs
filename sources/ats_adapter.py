import os
import json
import yaml
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from .base import BaseSourceAdapter
from core.cache import cache_adapter_response

class ATSAdapter(BaseSourceAdapter):
    """
    Direct ATS REST API adapter querying public endpoints for Ashby and Greenhouse.
    Fetches verified openings directly from top tech company career boards with zero scraping.
    """

    def __init__(self, config_path: str = None):
        super().__init__(name="ats")
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "companies.yaml")

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        self.ashby_companies = cfg.get("ashby_companies", [])
        self.greenhouse_companies = cfg.get("greenhouse_companies", [])

    def _fetch_ashby(self, company: str, terms: list) -> list:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
        req = urllib.request.Request(url, headers={"User-Agent": "JobHuntingEngine/1.0", "Accept": "application/json"})
        rows = []

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for job in data.get("jobs", []):
                title = job.get("title", "")
                title_lower = title.lower()

                if terms and not any(t in title_lower for t in terms):
                    continue

                url = job.get("jobUrl") or job.get("applyUrl") or ""
                loc = job.get("location") or "Remote / Multiple"
                rows.append({
                    "id": f"ashby-{job.get('id', '')}",
                    "title": title,
                    "company": company.capitalize(),
                    "location": loc,
                    "country": "Global",
                    "region": "Global",
                    "description": job.get("descriptionPlain", ""),
                    "date_posted": job.get("publishedAt", ""),
                    "job_url": url,
                    "job_url_direct": url,
                    "salary_min": None,
                    "salary_max": None,
                    "currency": "USD",
                    "is_remote": job.get("isRemote", True),
                    "job_type": job.get("employmentType", "Full-time"),
                    "Search Region": "Global",
                    "Search Location": loc,
                    "Search Term": terms[0] if terms else "",
                    "Search Source": f"ashby:{company}",
                })
        except Exception:
            pass

        return rows

    def _fetch_greenhouse(self, company: str, terms: list) -> list:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
        req = urllib.request.Request(url, headers={"User-Agent": "JobHuntingEngine/1.0", "Accept": "application/json"})
        rows = []

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for job in data.get("jobs", []):
                title = job.get("title", "")
                title_lower = title.lower()

                if terms and not any(t in title_lower for t in terms):
                    continue

                loc_data = job.get("location", {})
                loc_name = loc_data.get("name", "Multiple") if isinstance(loc_data, dict) else str(loc_data)

                url = job.get("absolute_url", "")
                rows.append({
                    "id": f"gh-{job.get('id', '')}",
                    "title": title,
                    "company": company.capitalize(),
                    "location": loc_name,
                    "country": "Global",
                    "region": "Global",
                    "description": "",
                    "date_posted": job.get("updated_at", ""),
                    "job_url": url,
                    "job_url_direct": url,
                    "salary_min": None,
                    "salary_max": None,
                    "currency": "USD",
                    "is_remote": "remote" in loc_name.lower(),
                    "job_type": "Full-time",
                    "Search Region": "Global",
                    "Search Location": loc_name,
                    "Search Term": terms[0] if terms else "",
                    "Search Source": f"greenhouse:{company}",
                })
        except Exception:
            pass

        return rows

    @cache_adapter_response()
    def fetch_all_ats(self, target_role: str = "", positive_terms: list = None) -> pd.DataFrame:
        """Queries curated Ashby and Greenhouse boards concurrently in under 3 seconds."""
        terms = [t.lower() for t in (positive_terms or [target_role]) if t]
        all_rows = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for c in self.ashby_companies:
                futures.append(executor.submit(self._fetch_ashby, c, terms))
            for c in self.greenhouse_companies:
                futures.append(executor.submit(self._fetch_greenhouse, c, terms))

            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        all_rows.extend(res)
                except Exception:
                    pass

        return pd.DataFrame(all_rows)

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        return self.fetch_all_ats(target_role=term)
