import os
import requests
import pandas as pd
from typing import Optional
from .base import BaseSourceAdapter
from core.cache import cache_adapter_response


class AdzunaAdapter(BaseSourceAdapter):
    """
    Adzuna Job Search API Adapter.
    Free tier: 50 requests per day (register at developer.adzuna.com).
    Covers UAE, Saudi Arabia, Qatar, Oman and other Middle East countries.
    """

    def __init__(self, app_id: Optional[str] = None, app_key: Optional[str] = None):
        super().__init__(name="adzuna")
        self.app_id = app_id or os.getenv("ADZUNA_APP_ID")
        self.app_key = app_key or os.getenv("ADZUNA_APP_KEY")
        self.base_url = "https://api.adzuna.com/v1/api/jobs"
        self.country_codes = {
            "United Arab Emirates": "ae",
            "UAE": "ae",
            "Dubai": "ae",
            "Abu Dhabi": "ae",
            "Saudi Arabia": "sa",
            "Riyadh": "sa",
            "Jeddah": "sa",
            "Qatar": "qa",
            "Doha": "qa",
            "Oman": "om",
            "Muscat": "om",
            "Kuwait": "kw",
            "Bahrain": "bh",
            "India": "in",
            "Global": "gb",
        }

    def _get_country_code(self, country: str, location: str) -> str:
        """Map country/location to Adzuna country code."""
        # Check location first (more specific)
        for key, code in self.country_codes.items():
            if key.lower() in location.lower():
                return code
        # Then check country
        for key, code in self.country_codes.items():
            if key.lower() in country.lower():
                return code
        return "gb"  # Default to UK/global

    @cache_adapter_response()
    def fetch_jobs(
        self,
        term: str,
        location: str = "",
        country: str = "",
        results_wanted: int = 25,
        hours_old: int = 72,
    ) -> pd.DataFrame:
        """
        Fetch jobs from Adzuna API.

        Args:
            term: Search term (e.g., "Product Designer")
            location: City/location (e.g., "Dubai")
            country: Country (e.g., "United Arab Emirates")
            results_wanted: Number of results to fetch
            hours_old: Max age of job postings in hours (Adzuna uses date filters differently)
        """
        if not self.app_id or not self.app_key:
            return pd.DataFrame()

        country_code = self._get_country_code(country, location)

        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": min(results_wanted, 50),  # Adzuna max is 50
            "what": term,
            "where": location,
            "content-type": "application/json",
            "sort_by": "date",
        }

        url = f"{self.base_url}/{country_code}/search/1"

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            jobs = data.get("results", [])
            if not jobs:
                return pd.DataFrame()

            rows = []
            for job in jobs[:results_wanted]:
                location_obj = job.get("location", {})
                area = location_obj.get("area", [])
                location_str = location_obj.get("display_name", "")
                country_str = area[0] if area else country

                company_obj = job.get("company", {})
                company = company_obj.get("display_name", "")

                category_obj = job.get("category", {})
                category = category_obj.get("label", "")

                salary_min = job.get("salary_min")
                salary_max = job.get("salary_max")
                currency = "USD"  # Adzuna returns in local currency but doesn't specify in response

                rows.append({
                    "id": str(job.get("id", "")),
                    "title": job.get("title", ""),
                    "company": company,
                    "location": location_str,
                    "country": country_str,
                    "region": "Middle East" if country_code in ["ae", "sa", "qa", "om", "kw", "bh"] else "Global",
                    "description": job.get("description", ""),
                    "date_posted": job.get("created", ""),
                    "job_url": job.get("redirect_url", ""),
                    "job_url_direct": job.get("redirect_url", ""),
                    "salary_min": salary_min,
                    "salary_max": salary_max,
                    "currency": currency,
                    "is_remote": "remote" in location_str.lower() if location_str else False,
                    "job_type": job.get("contract_type", "Full-time").capitalize(),
                    "category": category,
                    "Search Region": "Middle East" if country_code in ["ae", "sa", "qa", "om", "kw", "bh"] else "Global",
                    "Search Location": location,
                    "Search Term": term,
                    "Search Source": "adzuna",
                })

            return pd.DataFrame(rows)

        except Exception:
            return pd.DataFrame()

    def search(
        self,
        term: str,
        location: str,
        region: str,
        country: str,
        hours_old: int = 72,
        results_wanted: int = 25,
    ) -> pd.DataFrame:
        """Main search interface compatible with other adapters."""
        return self.fetch_jobs(
            term=term,
            location=location,
            country=country,
            results_wanted=results_wanted,
            hours_old=hours_old,
        )