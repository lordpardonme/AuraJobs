"""
GitHub Company Enrichment Module for AuraJobs.

Fetches GitHub organization data for companies to add:
- company_tech_stack: Primary languages used
- github_activity_score: 0-100 activity level
- top_repos: Top 5 repositories by stars
- org_public_repos: Number of public repositories
- org_followers: GitHub followers count
"""

import os
import json
import time
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import requests

try:
    from core.cache import get_cache
except ImportError:
    # Fallback if cache module not available
    class MockCache:
        def get(self, *args, **kwargs): return None
        def set(self, *args, **kwargs): pass
    def get_cache(*args, **kwargs): return MockCache()


class GitHubEnricher:
    """
    Enriches job listings with GitHub company intelligence.

    Uses GitHub REST API (no auth required for public data, 60 req/hour).
    With auth token: 5000 req/hour.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        cache_ttl_hours: int = 168,  # 1 week default
        max_workers: int = 5,
        rate_limit_delay: float = 0.1,
    ):
        """
        Initialize enricher.

        Args:
            token: GitHub personal access token (optional, increases rate limit)
            cache_ttl_hours: Cache TTL in hours
            max_workers: Max concurrent enrichment workers
            rate_limit_delay: Delay between requests (seconds)
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.max_workers = max_workers
        self.rate_limit_delay = rate_limit_delay
        self.base_url = "https://api.github.com"

        # Session with auth if available
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "User-Agent": "AuraJobs/1.0",
        })
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"

        # Cache for company enrichment
        self.cache = get_cache(
            cache_dir="cache/github",
            ttl_hours=cache_ttl_hours,
            enabled=True
        )

    def _make_cache_key(self, company_name: str) -> str:
        """Generate cache key for company."""
        normalized = company_name.lower().strip().replace(" ", "-")
        return hashlib.sha256(normalized.encode()).hexdigest()[:24]

    def _guess_github_org(self, company_name: str) -> Optional[str]:
        """
        Guess GitHub organization name from company name.

        Strategies:
        1. Direct name match (lowercase, hyphens)
        2. Common patterns (company-github, company-org)
        3. Search API fallback
        """
        # Clean company name
        clean = company_name.lower().strip()

        # Remove common suffixes
        suffixes = [" inc", " inc.", " ltd", " ltd.", " llc", " corp", " corporation",
                   " technologies", " technology", " systems", " labs", " lab",
                   " ai", " io", " co", " company", " group", " holdings"]
        for suffix in suffixes:
            if clean.endswith(suffix):
                clean = clean[:-len(suffix)]

        # Replace spaces/special chars with hyphens
        clean = clean.replace(" ", "-").replace(".", "").replace(",", "")
        clean = "".join(c for c in clean if c.isalnum() or c == "-")
        clean = clean.strip("-")

        if not clean:
            return None

        # Try direct match first
        return clean

    def _fetch_org(self, org_name: str) -> Optional[Dict[str, Any]]:
        """Fetch GitHub organization data."""
        cache_key = self._make_cache_key(org_name)

        # Check cache
        cached = self.cache.get("github_enricher", "_fetch_org", org=org_name)
        if cached is not None:
            return cached

        try:
            # Get org details
            url = f"{self.base_url}/orgs/{org_name}"
            response = self.session.get(url, timeout=10)

            if response.status_code == 404:
                return None
            elif response.status_code == 403:
                # Rate limited
                reset_time = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(0, reset_time - time.time() + 1)
                print(f"  [GitHub] Rate limited, waiting {wait:.0f}s")
                time.sleep(wait)
                return self._fetch_org(org_name)
            elif response.status_code != 200:
                return None

            org_data = response.json()

            # Get repos (top 100 by stars)
            repos_url = f"{self.base_url}/orgs/{org_name}/repos?per_page=100&sort=stars&direction=desc"
            repos_resp = self.session.get(repos_url, timeout=10)
            repos = repos_resp.json() if repos_resp.status_code == 200 else []

            # Get languages across top repos
            languages = {}
            for repo in repos[:20]:  # Sample top 20 repos
                if repo.get("fork"):
                    continue
                lang = repo.get("language")
                if lang:
                    languages[lang] = languages.get(lang, 0) + repo.get("stargazers_count", 1)

            # Build enrichment data
            result = {
                "github_org": org_name,
                "org_name": org_data.get("name", org_name),
                "org_login": org_data.get("login", org_name),
                "org_description": org_data.get("description", ""),
                "org_public_repos": org_data.get("public_repos", 0),
                "org_followers": org_data.get("followers", 0),
                "org_created_at": org_data.get("created_at", ""),
                "org_location": org_data.get("location", ""),
                "org_blog": org_data.get("blog", ""),
                "top_repos": [
                    {
                        "name": r.get("name", ""),
                        "description": r.get("description", ""),
                        "stars": r.get("stargazers_count", 0),
                        "language": r.get("language", ""),
                        "url": r.get("html_url", ""),
                    }
                    for r in repos[:5] if not r.get("fork")
                ],
                "tech_stack": list(languages.keys()),
                "tech_stack_weighted": languages,
            }

            # Calculate activity score (0-100)
            result["github_activity_score"] = self._calculate_activity_score(result)

            # Cache result
            self.cache.set("github_enricher", "_fetch_org", pd.DataFrame([result]), org=org_name)

            return result

        except Exception as e:
            print(f"  [GitHub] Error fetching {org_name}: {e}")
            return None

    def _calculate_activity_score(self, org_data: Dict[str, Any]) -> int:
        """Calculate 0-100 GitHub activity score."""
        score = 0

        # Public repos (max 30 points)
        repos = org_data.get("org_public_repos", 0)
        if repos >= 100: score += 30
        elif repos >= 50: score += 25
        elif repos >= 20: score += 20
        elif repos >= 10: score += 15
        elif repos >= 5: score += 10
        elif repos >= 1: score += 5

        # Followers (max 20 points)
        followers = org_data.get("org_followers", 0)
        if followers >= 10000: score += 20
        elif followers >= 5000: score += 15
        elif followers >= 1000: score += 10
        elif followers >= 100: score += 5

        # Top repo stars (max 25 points)
        top_repos = org_data.get("top_repos", [])
        max_stars = max([r.get("stars", 0) for r in top_repos], default=0)
        if max_stars >= 10000: score += 25
        elif max_stars >= 5000: score += 20
        elif max_stars >= 1000: score += 15
        elif max_stars >= 100: score += 10
        elif max_stars >= 10: score += 5

        # Tech stack diversity (max 15 points)
        tech_stack = org_data.get("tech_stack", [])
        if len(tech_stack) >= 10: score += 15
        elif len(tech_stack) >= 5: score += 10
        elif len(tech_stack) >= 2: score += 5

        # Recent activity (max 10 points)
        # Check if top repo updated recently
        # (would need additional API call, simplified here)

        return min(100, score)

    def enrich_company(self, company_name: str) -> Dict[str, Any]:
        """
        Enrich a single company with GitHub data.

        Returns dict with enrichment fields (empty strings/0 if not found).
        """
        if not company_name:
            return self._empty_enrichment()

        # Try direct org name guess
        org_name = self._guess_github_org(company_name)
        if not org_name:
            return self._empty_enrichment()

        result = self._fetch_org(org_name)

        if result:
            return {
                "github_org": result.get("github_org", ""),
                "github_org_name": result.get("org_name", ""),
                "github_public_repos": result.get("org_public_repos", 0),
                "github_followers": result.get("org_followers", 0),
                "github_activity_score": result.get("github_activity_score", 0),
                "github_tech_stack": ", ".join(result.get("tech_stack", [])),
                "github_top_repos": "; ".join([f"{r['name']} ({r['stars']}⭐)" for r in result.get("top_repos", [])]),
                "github_org_url": f"https://github.com/{result.get('org_login', org_name)}",
            }

        return self._empty_enrichment()

    def _empty_enrichment(self) -> Dict[str, Any]:
        """Return empty enrichment structure."""
        return {
            "github_org": "",
            "github_org_name": "",
            "github_public_repos": 0,
            "github_followers": 0,
            "github_activity_score": 0,
            "github_tech_stack": "",
            "github_top_repos": "",
            "github_org_url": "",
        }

    def enrich_dataframe(
        self,
        df: pd.DataFrame,
        company_col: str = "company",
        progress: bool = True,
    ) -> pd.DataFrame:
        """
        Enrich entire DataFrame with GitHub company data.

        Args:
            df: DataFrame with job listings
            company_col: Column name containing company names
            progress: Whether to print progress

        Returns:
            DataFrame with added GitHub enrichment columns
        """
        if df.empty or company_col not in df.columns:
            return df

        # Get unique companies
        companies = df[company_col].dropna().unique()
        companies = [c for c in companies if c and str(c).strip()]

        if not companies:
            return df

        if progress:
            print(f"\n[GitHub] Enriching {len(companies)} unique companies...")

        # Enrich in parallel
        enrichment_map = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.enrich_company, c): c for c in companies}

            for i, future in enumerate(as_completed(futures), 1):
                company = futures[future]
                try:
                    enrichment_map[company] = future.result()
                except Exception:
                    enrichment_map[company] = self._empty_enrichment()

                if progress and i % 10 == 0:
                    print(f"  [GitHub] Enriched {i}/{len(companies)} companies")

                time.sleep(self.rate_limit_delay)

        if progress:
            print(f"  [GitHub] Completed enrichment for {len(companies)} companies\n")

        # Apply enrichment to DataFrame
        enriched_rows = []
        for _, row in df.iterrows():
            company = row.get(company_col, "")
            enrichment = enrichment_map.get(company, self._empty_enrichment())

            new_row = row.copy()
            for key, value in enrichment.items():
                new_row[key] = value
            enriched_rows.append(new_row)

        return pd.DataFrame(enriched_rows)


def enrich_jobs_with_github(
    df: pd.DataFrame,
    token: Optional[str] = None,
    company_col: str = "company",
    progress: bool = True,
) -> pd.DataFrame:
    """
    Convenience function to enrich jobs DataFrame with GitHub data.

    Usage:
        from core.github_enrichment import enrich_jobs_with_github
        enriched_df = enrich_jobs_with_github(df)
    """
    enricher = GitHubEnricher(token=token)
    return enricher.enrich_dataframe(df, company_col=company_col, progress=progress)


# CLI helper
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    # Test with sample companies
    test_companies = [
        "Airbnb", "Stripe", "Figma", "Linear", "Notion",
        "Vercel", "Supabase", "Prisma", "Turborepo", "Railway"
    ]

    enricher = GitHubEnricher()

    print("Testing GitHub enrichment...")
    for company in test_companies:
        result = enricher.enrich_company(company)
        if result["github_org"]:
            print(f"  ✅ {company}: {result['github_activity_score']}/100 | {result['github_tech_stack'][:60]} | {result['github_top_repos'][:80]}")
        else:
            print(f"  ❌ {company}: No GitHub org found")