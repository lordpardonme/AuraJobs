import unittest
import pandas as pd
from sources import (
    FreeHireAdapter,
    ArbeitnowAdapter,
    AIJobsAdapter,
    ScraplingStealthAdapter,
    MultiBoardAdapter,
)

class TestNewAdapters(unittest.TestCase):
    def test_freehire_adapter(self):
        adapter = FreeHireAdapter()
        df = adapter.fetch_jobs(search_term="engineer", limit=5)
        self.assertIsInstance(df, pd.DataFrame)
        if not df.empty:
            self.assertIn("title", df.columns)
            self.assertIn("company", df.columns)
            self.assertIn("job_url", df.columns)
            self.assertEqual(df["Search Source"].iloc[0], "freehire")
            print(f"  [OK] FreeHire: fetched {len(df)} jobs.")

    def test_arbeitnow_adapter(self):
        adapter = ArbeitnowAdapter()
        df = adapter.fetch_jobs(search_term="developer", limit=5)
        self.assertIsInstance(df, pd.DataFrame)
        if not df.empty:
            self.assertIn("title", df.columns)
            self.assertIn("company", df.columns)
            self.assertIn("job_url", df.columns)
            self.assertEqual(df["Search Source"].iloc[0], "arbeitnow")
            print(f"  [OK] Arbeitnow: fetched {len(df)} jobs.")

    def test_aijobs_adapter(self):
        adapter = AIJobsAdapter()
        df = adapter.fetch_jobs(search_term="engineer", limit=5)
        self.assertIsInstance(df, pd.DataFrame)
        if not df.empty:
            self.assertIn("title", df.columns)
            self.assertIn("company", df.columns)
            self.assertIn("job_url", df.columns)
            self.assertEqual(df["Search Source"].iloc[0], "aijobs")
            print(f"  [OK] AIJobs: fetched {len(df)} jobs.")

    def test_scrapling_adapter_init(self):
        adapter = ScraplingStealthAdapter()
        fetcher = adapter._get_fetcher()
        self.assertIsNotNone(fetcher, "StealthyFetcher should be available via scrapling")
        print("  [OK] ScraplingStealthAdapter initialized successfully.")

    def test_multiboard_scrapling_escalation_flag(self):
        adapter = MultiBoardAdapter(enable_scrapling_escalation=True)
        self.assertTrue(adapter.enable_scrapling_escalation)
        self.assertIsNotNone(adapter.scrapling)
        print("  [OK] MultiBoardAdapter has Scrapling escalation enabled.")

if __name__ == "__main__":
    unittest.main()
