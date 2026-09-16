import re
import urllib.parse
import pandas as pd
from .base import BaseSourceAdapter

class ScraplingStealthAdapter(BaseSourceAdapter):
    """
    Next-generation anti-bot escalation adapter powered by Scrapling and Patchright.
    Features:
      - Native Cloudflare Turnstile & challenge solving (solve_cloudflare=True)
      - Anti-fingerprint protection (hide_canvas=True, block_webrtc=True)
      - Non-blocking JavaScript execution and DOM hydration (load_dom=True, wait=2000)
      - Fast 15s timeout bounds to guarantee CLI responsiveness
      - Specialized stealth parsers for Naukri (HTTP 406 bypass) and Bayt (HTTP 403 bypass).
    """

    def __init__(self, headless: bool = True, timeout_ms: int = 15000):
        super().__init__(name="scrapling_stealth")
        self.headless = headless
        self.timeout_ms = timeout_ms

    def _get_fetcher(self):
        try:
            from scrapling.fetchers import StealthyFetcher
            return StealthyFetcher
        except ImportError:
            return None

    def fetch_page(self, url: str, wait_selector: str = None, solve_cf: bool = False):
        """Fetches a page using Scrapling's StealthyFetcher engine with tight timeouts."""
        StealthyFetcher = self._get_fetcher()
        if not StealthyFetcher:
            return None

        try:
            kwargs = {
                "headless": self.headless,
                "solve_cloudflare": solve_cf,
                "hide_canvas": True,
                "block_webrtc": True,
                "network_idle": False,      # Essential: don't hang on continuous ad/tracking websockets
                "load_dom": True,
                "wait": 2000,               # 2s buffer for JS hydration
                "timeout": self.timeout_ms,
            }
            if wait_selector:
                kwargs["wait_selector"] = wait_selector

            page = StealthyFetcher.fetch(url, **kwargs)
            return page
        except Exception:
            # Fallback isolation
            return None

    def scrape_naukri(self, term: str, location: str = "India", results_wanted: int = 25) -> pd.DataFrame:
        """
        Stealth scraper for Naukri.com, bypassing HTTP 406 Not Acceptable and bot challenges.
        """
        term_clean = re.sub(r"[^a-zA-Z0-9\s]", "", term).strip().lower().replace(" ", "-")
        loc_clean = re.sub(r"[^a-zA-Z0-9\s]", "", location).strip().lower().replace(" ", "-") if location else "india"

        url = f"https://www.naukri.com/{term_clean}-jobs-in-{loc_clean}"
        page = self.fetch_page(url, wait_selector=".srp-jobtuple-wrapper", solve_cf=False)
        if not page:
            return pd.DataFrame()

        rows = []
        try:
            job_tuples = page.css(".srp-jobtuple-wrapper") or page.css(".cust-job-tuple")
            for card in job_tuples[:results_wanted]:
                title_elem = card.css_first("a.title")
                title = title_elem.text.strip() if title_elem else ""
                job_url = title_elem.attrib.get("href", "") if title_elem else ""

                comp_elem = card.css_first("a.comp-name") or card.css_first(".comp-name")
                company = comp_elem.text.strip() if comp_elem else ""

                loc_elem = card.css_first(".locWdth") or card.css_first(".loc")
                loc = loc_elem.text.strip() if loc_elem else location

                sal_elem = card.css_first(".sal-wrap") or card.css_first(".sal")
                salary_text = sal_elem.text.strip() if sal_elem else ""

                desc_elem = card.css_first(".job-desc") or card.css_first(".row6")
                desc = desc_elem.text.strip() if desc_elem else ""

                if title:
                    rows.append({
                        "id": job_url.split("-")[-1].split("?")[0] if job_url else "",
                        "title": title,
                        "company": company,
                        "location": loc,
                        "country": "India",
                        "region": "India",
                        "description": f"{desc} | Salary: {salary_text}" if salary_text else desc,
                        "date_posted": "",
                        "job_url": job_url,
                        "job_url_direct": job_url,
                        "salary_min": None,
                        "salary_max": None,
                        "currency": "INR",
                        "is_remote": "remote" in loc.lower() or "hybrid" in loc.lower(),
                        "job_type": "Full-time",
                        "Search Region": "India",
                        "Search Location": location,
                        "Search Term": term,
                        "Search Source": "naukri (scrapling)",
                    })
        except Exception:
            pass

        return pd.DataFrame(rows)

    def scrape_bayt(self, term: str, location: str = "Middle East", results_wanted: int = 25) -> pd.DataFrame:
        """
        Stealth scraper for Bayt.com, bypassing international HTTP 403 Forbidden blocks.
        """
        term_clean = urllib.parse.quote(term.strip())
        url = f"https://www.bayt.com/en/international/jobs/{term_clean}-jobs/"
        page = self.fetch_page(url, wait_selector="li[data-js-job]", solve_cf=True)
        if not page:
            return pd.DataFrame()

        rows = []
        try:
            cards = page.css("li[data-js-job]") or page.css(".has-pointer-d")
            for card in cards[:results_wanted]:
                title_elem = card.css_first("h2 a") or card.css_first("a[data-js-job-link]")
                title = title_elem.text.strip() if title_elem else ""
                href = title_elem.attrib.get("href", "") if title_elem else ""
                job_url = f"https://www.bayt.com{href}" if href.startswith("/") else href

                comp_elem = card.css_first(".t-nowrap a") or card.css_first(".t-nowrap")
                company = comp_elem.text.strip() if comp_elem else ""

                loc_elem = card.css_first(".t-mute.t-small")
                loc = loc_elem.text.strip() if loc_elem else location

                desc_elem = card.css_first(".t-small:not(.t-mute)")
                desc = desc_elem.text.strip() if desc_elem else ""

                if title:
                    rows.append({
                        "id": job_url.split("-")[-1].replace("/", "") if job_url else "",
                        "title": title,
                        "company": company,
                        "location": loc,
                        "country": "Middle East",
                        "region": "Middle East",
                        "description": desc,
                        "date_posted": "",
                        "job_url": job_url,
                        "job_url_direct": job_url,
                        "salary_min": None,
                        "salary_max": None,
                        "currency": "AED",
                        "is_remote": "remote" in loc.lower(),
                        "job_type": "Full-time",
                        "Search Region": "Middle East",
                        "Search Location": location,
                        "Search Term": term,
                        "Search Source": "bayt (scrapling)",
                    })
        except Exception:
            pass

        return pd.DataFrame(rows)

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        """Dynamic dispatch based on target region."""
        if region == "India" or country.lower() == "india":
            return self.scrape_naukri(term=term, location=location, results_wanted=results_wanted)
        elif region == "Middle East" or any(c in location.lower() for c in ["dubai", "riyadh", "uae", "saudi"]):
            return self.scrape_bayt(term=term, location=location, results_wanted=results_wanted)
        else:
            return pd.DataFrame()
