import time
import os
import yaml

class BalancedScheduler:
    """
    Manages regional budgets, rotating location offsets, and interleaved
    round-robin search queue execution.
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
        self.india_share = self.settings.get("india_share", 0.45)
        self.middle_east_share = self.settings.get("middle_east_share", 0.30)
        self.global_share = self.settings.get("global_share", 0.25)

        self.india_locations = self.locations_cfg.get("india_locations", [])
        self.middle_east_locations = self.locations_cfg.get("middle_east_locations", [])
        self.country_map = self.locations_cfg.get("country_map", {})

        source_cfg = self.sources_cfg.get("sources", {}).get("multiboard") or self.sources_cfg.get("sources", {}).get("jobspy", {})
        regional_sites = source_cfg.get("regional_sites", {})
        self.india_sites = regional_sites.get("India", ["linkedin", "indeed", "google", "bayt"])
        self.middle_east_sites = regional_sites.get("Middle East", ["linkedin", "indeed", "google", "bayt"])
        self.global_sites = regional_sites.get("Global", ["linkedin", "indeed", "google", "bayt"])

    def get_locations(self, region: str, mode: str = "Express") -> list:
        if region == "India":
            if mode == "Express":
                return ["India", "Bengaluru", "Delhi", "Gurgaon", "Mumbai", "Hyderabad"]
            return self.india_locations
        elif region == "Middle East":
            if mode == "Express":
                return ["Dubai, UAE", "Abu Dhabi, UAE", "Riyadh, Saudi Arabia"]
            return self.middle_east_locations
        return []

    def calculate_budgets(self, geography_choice: str = "All", mode: str = "Express"):
        """Calculates allocated search counts per region based on configured shares and speed mode."""
        budget_limit = 15 if mode == "Express" else min(60, self.max_searches)

        if geography_choice == "India":
            return budget_limit, 0, 0
        elif geography_choice == "Middle East":
            return 0, budget_limit, 0
        elif geography_choice == "Global":
            return 0, 0, budget_limit

        india = int(budget_limit * self.india_share)
        middle = int(budget_limit * self.middle_east_share)
        glob = budget_limit - india - middle
        return india, middle, glob

    def build_round_robin_plan(self, locations: list, sites: list, terms: list, region: str) -> list:
        """
        Builds a comprehensive plan with location-first rotation so that
        the start location rotates on every pass.
        """
        plan = []
        if not locations:
            return plan

        for term_index, term in enumerate(terms):
            for site in sites:
                for offset in range(len(locations)):
                    idx = (term_index + offset) % len(locations)
                    loc = locations[idx]
                    plan.append({
                        "region": region,
                        "location": loc,
                        "country": self.country_map.get(loc, ""),
                        "term": term,
                        "site": site,
                    })
        return plan

    def build_global_plan(self, terms: list) -> list:
        """Builds plan for Worldwide / Global search targets."""
        return [
            {
                "region": "Global",
                "location": "GLOBAL",
                "country": "Worldwide",
                "term": term,
                "site": site,
            }
            for term in terms
            for site in self.global_sites
        ]

    def take_evenly_spread(self, plan: list, budget: int) -> list:
        """Evenly samples items across the plan up to the region budget."""
        if not plan or budget <= 0:
            return []
        if len(plan) <= budget:
            return plan

        step = len(plan) / budget
        indexes = [min(int(i * step), len(plan) - 1) for i in range(budget)]

        seen = set()
        selected = []
        for idx in indexes:
            if idx not in seen:
                seen.add(idx)
                selected.append(plan[idx])

        return selected[:budget]

    def generate_execution_queues(self, search_terms: list, geography_choice: str = "All", mode: str = "Express") -> tuple:
        """Creates the interleaved queue iterator for India, Middle East, and Global."""
        india_b, middle_b, global_b = self.calculate_budgets(geography_choice, mode)

        if mode == "Express":
            # Focus on primary high-yield terms in Express mode to prevent repetitive micro-queries
            search_terms = search_terms[:2] if len(search_terms) > 2 else search_terms

        india_locations = self.get_locations("India", mode)
        middle_east_locations = self.get_locations("Middle East", mode)

        india_plan = self.build_round_robin_plan(india_locations, self.india_sites, search_terms, "India")
        middle_plan = self.build_round_robin_plan(middle_east_locations, self.middle_east_sites, search_terms, "Middle East")
        global_plan = self.build_global_plan(search_terms)

        india_selected = self.take_evenly_spread(india_plan, india_b)
        middle_selected = self.take_evenly_spread(middle_plan, middle_b)
        global_selected = self.take_evenly_spread(global_plan, global_b)

        queues = {
            "India": iter(india_selected),
            "Middle East": iter(middle_selected),
            "Global": iter(global_selected),
        }

        counts = {
            "India": len(india_selected),
            "Middle East": len(middle_selected),
            "Global": len(global_selected),
        }

        return queues, counts

