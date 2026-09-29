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
            "Brasil": "brazil",
            "Brazil": "brazil",
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

        if region == "Remoto" or location in ["Remoto", "Home Office", "Teletrabalho"]:
            kwargs["is_remote"] = True
            if site == "linkedin":
                kwargs["location"] = "Brazil"
                # Only append 'remoto' for Portuguese terms; English terms work
                # better with is_remote=True alone to avoid double-filtering
                term_lower = term.lower()
                if any(w in term_lower for w in ["analista", "engenheiro", "técnico", "tecnico", "suporte", "administrador", "coordenador"]):
                    if "remoto" not in term_lower and "home office" not in term_lower:
                        kwargs["search_term"] = f"{term} remoto"
            elif site in ["indeed", "glassdoor"]:
                kwargs["location"] = "Remoto"
                kwargs["country_indeed"] = "brazil"
            elif site == "google":
                kwargs["location"] = "Brasil"
                kwargs["google_search_term"] = f"vagas {term} remoto home office brasil"
            else:
                kwargs["location"] = "Brazil"
        elif region == "Londrina" or "londrina" in location.lower():
            kwargs["is_remote"] = False
            if site == "linkedin":
                kwargs["location"] = "Londrina, Paraná, Brasil"
            elif site in ["indeed", "glassdoor"]:
                kwargs["location"] = "Londrina, PR"
                kwargs["country_indeed"] = "brazil"
            elif site == "google":
                kwargs["location"] = "Londrina, PR"
                kwargs["google_search_term"] = f"vagas {term} Londrina PR"
            else:
                kwargs["location"] = "Londrina, PR"
        elif region == "Global":
            if site == "google":
                kwargs["google_search_term"] = f"{term} jobs worldwide"
                kwargs["location"] = "Worldwide"
            elif site == "bayt":
                kwargs["location"] = None
            else:
                kwargs["location"] = "Worldwide"
        elif region == "Brasil" or country in ["Brazil", "Brasil"]:
            if site == "linkedin":
                kwargs["location"] = "Brazil" if location in ["Brasil", "Brazil"] else location
            elif site in ["indeed", "glassdoor"]:
                kwargs["location"] = location
                kwargs["country_indeed"] = "brazil"
            elif site == "google":
                kwargs["location"] = location
                kwargs["google_search_term"] = f"vagas {term} {location}"
            else:
                kwargs["location"] = location
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
