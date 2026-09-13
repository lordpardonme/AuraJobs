import time
import logging
import pandas as pd
from jobspy import scrape_jobs
from .base import BaseSourceAdapter

# Silence internal scrapers from cluttering terminal output
logging.getLogger("JobSpy").setLevel(logging.CRITICAL)
logging.getLogger("jobspy").setLevel(logging.CRITICAL)

class MultiBoardAdapter(BaseSourceAdapter):
    """
    AuraJobs Multi-Board Adapter for scraping and querying across
    LinkedIn, Indeed, Google Jobs, Glassdoor, and regional boards.
    Includes resilient error isolation, rate limiting, and parameter mapping.
    """

    def __init__(self, request_delay: float = 2.5, indeed_country_map: dict = None):
        super().__init__(name="multiboard")
        self.request_delay = request_delay
        self.indeed_country_map = indeed_country_map or {
            "India": "india",
            "United Arab Emirates": "united arab emirates",
            "Saudi Arabia": "saudi arabia",
            "Qatar": "qatar",
            "Kuwait": "kuwait",
            "Bahrain": "bahrain",
            "Oman": "oman",
        }

    def search_single_site(self, site: str, term: str, location: str, region: str,
                           country: str, hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        """Executes a targeted search against a single underlying board."""
        kwargs = {
            "site_name": [site],
            "search_term": term,
            "results_wanted": results_wanted,
            "hours_old": hours_old,
            "verbose": 0,
        }

        if region == "Global":
            if site == "google":
                kwargs["google_search_term"] = f"{term} jobs worldwide"
                kwargs["location"] = "Worldwide"
            elif site == "bayt":
                kwargs["location"] = None
            else:
                kwargs["location"] = "Worldwide"
        elif site in ["indeed", "glassdoor"]:
            kwargs["location"] = location
            mapped_country = self.indeed_country_map.get(country, country.lower() if country else "india")
            kwargs["country_indeed"] = mapped_country
        elif site == "google":
            kwargs["location"] = location
            kwargs["google_search_term"] = f"{term} jobs {location}"
        elif site == "bayt":
            kwargs["location"] = None
        else:
            kwargs["location"] = location

        try:
            jobs = scrape_jobs(**kwargs)

            if jobs is None or jobs.empty:
                return pd.DataFrame()

            jobs["Search Region"] = region
            jobs["Search Location"] = location
            jobs["Search Term"] = term
            jobs["Search Source"] = site

            return jobs

        except Exception:
            # Silently isolate source failures so the scheduler continues smoothly
            return pd.DataFrame()

        finally:
            if self.request_delay > 0:
                time.sleep(self.request_delay)

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        return self.search_single_site("linkedin", term, location, region, country, hours_old, results_wanted)


# Backwards compatibility alias
JobSpyAdapter = MultiBoardAdapter
