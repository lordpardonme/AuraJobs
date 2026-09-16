import time
import logging
import pandas as pd
from jobspy import scrape_jobs
from .base import BaseSourceAdapter
from .scrapling_adapter import ScraplingStealthAdapter

# Silence internal scrapers from cluttering terminal output
logging.getLogger("JobSpy").setLevel(logging.CRITICAL)
logging.getLogger("jobspy").setLevel(logging.CRITICAL)

class MultiBoardAdapter(BaseSourceAdapter):
    """
    AuraJobs Multi-Board Adapter for scraping and querying across
    LinkedIn, Indeed, Google Jobs, Glassdoor, and regional boards.
    Includes resilient error isolation, rate limiting, and parameter mapping.
    Features a Cascading Escalation Tier: when fast HTTP requests encounter
    anti-bot blocks (Naukri HTTP 406 or Bayt HTTP 403), it automatically
    escalates to ScraplingStealthAdapter.
    """

    def __init__(self, request_delay: float = 2.5, indeed_country_map: dict = None, enable_scrapling_escalation: bool = True):
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
        self.enable_scrapling_escalation = enable_scrapling_escalation
        self.scrapling = ScraplingStealthAdapter() if enable_scrapling_escalation else None

    def search_single_site(self, site: str, term: str, location: str, region: str,
                           country: str, hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        """Executes a targeted search against a single underlying board with cascading anti-bot fallback."""
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

        jobs = pd.DataFrame()
        fast_http_failed = False

        try:
            jobs = scrape_jobs(**kwargs)
            if jobs is None:
                jobs = pd.DataFrame()
        except Exception:
            fast_http_failed = True
            jobs = pd.DataFrame()

        # Cascading Anti-Bot Escalation:
        # If fast HTTP returned empty on known bot-protected platforms (naukri/bayt), escalate to Scrapling
        if (jobs.empty or fast_http_failed) and self.enable_scrapling_escalation and self.scrapling:
            if site == "naukri":
                try:
                    escalated_df = self.scrapling.scrape_naukri(term=term, location=location, results_wanted=results_wanted)
                    if not escalated_df.empty:
                        jobs = escalated_df
                except Exception:
                    pass
            elif site == "bayt":
                try:
                    escalated_df = self.scrapling.scrape_bayt(term=term, location=location, results_wanted=results_wanted)
                    if not escalated_df.empty:
                        jobs = escalated_df
                except Exception:
                    pass

        if jobs is not None and not jobs.empty:
            jobs["Search Region"] = region
            jobs["Search Location"] = location
            jobs["Search Term"] = term
            if "Search Source" not in jobs.columns:
                jobs["Search Source"] = site

        if self.request_delay > 0:
            time.sleep(self.request_delay)

        return jobs if jobs is not None else pd.DataFrame()

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        return self.search_single_site("linkedin", term, location, region, country, hours_old, results_wanted)


# Backwards compatibility alias
JobSpyAdapter = MultiBoardAdapter
