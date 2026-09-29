import time
import os
import yaml

class BalancedScheduler:
    """
    Manages regional budgets, rotating location offsets, and interleaved
    round-robin search queue execution with focus on Brazil, Remote and Global jobs.
    """

    def __init__(self, settings_path: str = None, locations_path: str = None, sources_path: str = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        settings_path = settings_path or os.path.join(base_dir, "config", "settings.yaml")
        locations_path = locations_path or os.path.join(base_dir, "config", "locations.yaml")
        sources_path = sources_path or os.path.join(base_dir, "config", "sources.yaml")

        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = yaml.safe_load(f)

        with open(locations_path, "r", encoding="utf-8") as f:
            self.locations_cfg = yaml.safe_load(f)

        with open(sources_path, "r", encoding="utf-8") as f:
            self.sources_cfg = yaml.safe_load(f)

        self.max_searches = self.settings.get("max_searches", 500)
        self.max_runtime_minutes = self.settings.get("max_runtime_minutes", 90)
        self.remoto_share = self.settings.get("remoto_share", 0.50)
        self.londrina_share = self.settings.get("londrina_share", 0.50)

        self.londrina_locations = self.locations_cfg.get("londrina_locations", [
            "Londrina, PR", "Londrina, Paraná", "Londrina"
        ])
        self.remoto_locations = self.locations_cfg.get("remoto_locations", [
            "Remoto", "Home Office", "Teletrabalho"
        ])
        self.country_map = self.locations_cfg.get("country_map", {})

        source_cfg = self.sources_cfg.get("sources", {}).get("multiboard") or self.sources_cfg.get("sources", {}).get("jobspy", {})
        regional_sites = source_cfg.get("regional_sites", {})
        self.remoto_sites = regional_sites.get("Remoto", ["linkedin", "indeed", "google"])
        self.londrina_sites = regional_sites.get("Londrina", ["linkedin", "indeed", "google", "glassdoor"])

    def get_locations(self, region: str, mode: str = "Express") -> list:
        if region == "Londrina":
            if mode == "Express":
                return ["Londrina, PR"]
            return self.londrina_locations
        elif region == "Remoto":
            if mode == "Express":
                return ["Remoto", "Home Office"]
            return self.remoto_locations
        return []

    def calculate_budgets(self, geography_choice: str = "Ambos", mode: str = "Express"):
        """Calculates allocated search counts per region based on configured shares and speed mode."""
        budget_limit = 24 if mode == "Express" else min(60, self.max_searches)

        geo_lower = str(geography_choice).lower()
        if geo_lower in ["remoto", "remote", "remoto only", "apenas remoto"]:
            return budget_limit, 0
        elif geo_lower in ["londrina", "londrina only", "apenas londrina"]:
            return 0, budget_limit

        # Alocação balanceada padrão: Remoto + Londrina
        remoto_b = int(budget_limit * self.remoto_share)
        londrina_b = budget_limit - remoto_b
        return remoto_b, londrina_b

    def build_round_robin_plan(self, locations: list, sites: list, terms: list, region: str) -> list:
        """
        Builds an interleaved plan guaranteeing that every unique (term, site, location)
        combination is searched before any is repeated.  Within each round, locations
        are visited in order so the first pass covers every configured city.
        """
        plan = []
        if not locations or not sites or not terms:
            return plan

        # Generate ALL unique (location, term, site) combos for maximum diversity
        seen = set()
        # First: ensure every term gets at least one search on each site
        for term in terms:
            for site in sites:
                for loc in locations:
                    key = (loc, term, site)
                    if key not in seen:
                        seen.add(key)
                        plan.append({
                            "region": region,
                            "location": loc,
                            "country": self.country_map.get(loc, "Brazil"),
                            "term": term,
                            "site": site,
                        })
        return plan

    def take_evenly_spread(self, plan: list, budget: int) -> list:
        """Takes items sequentially from the interleaved plan to preserve complete city coverage."""
        if not plan or budget <= 0:
            return []
        return plan[:budget]

    def generate_execution_queues(self, search_terms: list, geography_choice: str = "Ambos", mode: str = "Express") -> tuple:
        """Creates the interleaved queue iterator for Remoto and Londrina."""
        remoto_b, londrina_b = self.calculate_budgets(geography_choice, mode)

        if mode == "Express":
            # Focus on primary high-yield terms in Express mode to prevent repetitive micro-queries
            search_terms = search_terms[:5] if len(search_terms) > 5 else search_terms

        remoto_locations = self.get_locations("Remoto", mode)
        londrina_locations = self.get_locations("Londrina", mode)

        remoto_plan = self.build_round_robin_plan(remoto_locations, self.remoto_sites, search_terms, "Remoto")
        londrina_plan = self.build_round_robin_plan(londrina_locations, self.londrina_sites, search_terms, "Londrina")

        remoto_selected = self.take_evenly_spread(remoto_plan, remoto_b)
        londrina_selected = self.take_evenly_spread(londrina_plan, londrina_b)

        queues = {
            "Remoto": iter(remoto_selected),
            "Londrina": iter(londrina_selected),
        }

        counts = {
            "Remoto": len(remoto_selected),
            "Londrina": len(londrina_selected),
        }

        return queues, counts

