"""
AuraJobs Core Search Pipeline
Extracted from main.py to enable reuse by both CLI and Alert Scheduler.
"""

import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import pandas as pd

from core.checkpoint import CheckpointManager
from core.classifier import RoleClassifier
from core.deduper import deduplicate_jobs
from core.exporters import OutputExporter
from core.normalizer import normalize_dataframe
from core.scheduler import BalancedScheduler
from core.scorer import MatchScorer, calculate_age_hours
from core.visa import detect_relocation, detect_visa_sponsorship
from sources import (
    AIJobsAdapter,
    ArbeitnowAdapter,
    ATSAdapter,
    FreeHireAdapter,
    HimalayasAdapter,
    MultiBoardAdapter,
    RemoteOKAdapter,
    RemotiveAdapter,
)


def format_progress_bar(current: int, total: int, bar_length: int = 20) -> str:
    fraction = min(1.0, current / total) if total > 0 else 0
    filled = int(bar_length * fraction)
    bar = "=" * filled + "-" * (bar_length - filled)
    return f"[{bar}] {int(fraction * 100)}%"


def process_results(raw_df: pd.DataFrame, profile: dict, scorer: MatchScorer, classifier: RoleClassifier, max_hours: int) -> pd.DataFrame:
    """Process raw jobs through normalization, filtering, scoring, and deduplication."""
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    df = normalize_dataframe(raw_df)

    df["date_posted"] = pd.to_datetime(df["date_posted"], errors="coerce", utc=True)
    df["age_hours"] = df["date_posted"].apply(calculate_age_hours)

    df = df[
        df["age_hours"].isna()
        | ((df["age_hours"] >= 0) & (df["age_hours"] <= max_hours))
    ].copy()

    if df.empty:
        return df

    strict_df = classifier.filter_dataframe(df)

    if strict_df.empty and not df.empty:
        print("\n[!] Notice: No exact title matches met strict criteria.")
        print("    --> Activating Graceful Fallback Mode: Surfacing top broad domain opportunities...")

        fallback_mask = df["title"].apply(lambda t: not any(neg in str(t).lower() for neg in classifier.negative_terms))
        fallback_df = df[fallback_mask].copy()

        if not fallback_df.empty:
            df = fallback_df
            df["match_type"] = "BROAD DOMAIN MATCH"
        else:
            df = strict_df
    else:
        df = strict_df.copy()
        df["match_type"] = "EXACT MATCH"

    if df.empty:
        return df

    visa_results = df.apply(lambda r: detect_visa_sponsorship(r["title"], r["description"]), axis=1)
    df["visa_status"] = [v[0] for v in visa_results]
    df["visa_evidence"] = [v[1] for v in visa_results]

    relo_results = df.apply(lambda r: detect_relocation(r["title"], r["description"]), axis=1)
    df["relocation_status"] = [rel[0] for rel in relo_results]
    df["relocation_evidence"] = [rel[1] for rel in relo_results]

    df["match_score"] = df.apply(
        lambda r: scorer.calculate_score(
            title=r["title"],
            description=r["description"],
            age_hours=r["age_hours"],
            visa_status=r["visa_status"],
            relocation_status=r["relocation_status"]
        ),
        axis=1
    )

    df["priority"] = df.apply(
        lambda r: scorer.assign_priority(
            age_hours=r["age_hours"],
            visa_status=r["visa_status"]
        ),
        axis=1
    )

    df["age_bucket"] = df["age_hours"].apply(
        lambda h: f"< {max_hours}H (PLATFORM FILTERED)" if pd.isna(h) or h is None
        else ("0-24 HOURS" if h <= 24 else "24-72 HOURS")
    )

    df = deduplicate_jobs(df)

    priority_order = {
        "URGENT - VISA": 0,
        "URGENT - NEW": 1,
        "FRESH": 2,
        "LAST 72H": 3,
    }
    df["_p_rank"] = df["priority"].map(priority_order).fillna(9)
    df = df.sort_values(
        by=["_p_rank", "match_score", "age_hours"],
        ascending=[True, False, True]
    ).drop(columns=["_p_rank"], errors="ignore").reset_index(drop=True)

    return df


def run_stage1_apis(profile: dict, geography_choice: str) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Execute Stage 1: Parallel zero-auth public APIs & direct ATS feeds.
    Returns combined DataFrame and per-source counts.
    """
    print("=" * 78)
    print("  STAGE 1: INSTANT ZERO-AUTH PUBLIC APIS & DIRECT ATS FEEDS")
    print("=" * 78)
    print("Querying RemoteOK, Remotive, Himalayas, FreeHire, Arbeitnow, AIJobs, Ashby & Greenhouse...")

    api_start = time.time()
    rok = RemoteOKAdapter()
    rem = RemotiveAdapter()
    him = HimalayasAdapter()
    ats = ATSAdapter()
    fh = FreeHireAdapter()
    an = ArbeitnowAdapter()
    ai = AIJobsAdapter()

    with ThreadPoolExecutor(max_workers=7) as executor:
        f_rok = executor.submit(rok.fetch_jobs, profile["target_role"], profile.get("positive_title_terms", []))
        f_rem = executor.submit(rem.fetch_jobs, profile["target_role"])
        f_him = executor.submit(him.fetch_jobs, profile["target_role"], profile.get("positive_title_terms", []))
        f_ats = executor.submit(ats.fetch_all_ats, profile["target_role"], profile.get("positive_title_terms", []))
        f_fh = executor.submit(fh.fetch_jobs, profile["target_role"], geography_choice)
        f_an = executor.submit(an.fetch_jobs, profile["target_role"])
        f_ai = executor.submit(ai.fetch_jobs, profile["target_role"])

        df_rok = f_rok.result()
        df_rem = f_rem.result()
        df_him = f_him.result()
        df_ats = f_ats.result()
        df_fh = f_fh.result()
        df_an = f_an.result()
        df_ai = f_ai.result()

    source_counts = {
        "RemoteOK": len(df_rok),
        "Remotive": len(df_rem),
        "Himalayas": len(df_him),
        "Direct ATS": len(df_ats),
        "FreeHire": len(df_fh),
        "Arbeitnow": len(df_an),
        "AI Jobs": len(df_ai),
    }

    api_dfs = [d for d in [df_rok, df_rem, df_him, df_ats, df_fh, df_an, df_ai] if not d.empty]
    combined = pd.concat(api_dfs, ignore_index=True) if api_dfs else pd.DataFrame()

    api_time = time.time() - api_start
    total = len(combined)
    print(f"  +--> RemoteOK   : {len(df_rok)} listings")
    print(f"  +--> Remotive   : {len(df_rem)} listings")
    print(f"  +--> Himalayas  : {len(df_him)} listings")
    print(f"  +--> Direct ATS : {len(df_ats)} listings (Linear, Notion, Cursor, GitLab, Stripe, etc.)")
    print(f"  +--> FreeHire   : {len(df_fh)} listings (Greenhouse, Lever, Freshteam, Recruitee ATS)")
    print(f"  +--> Arbeitnow  : {len(df_an)} listings (Europe / Global Remote)")
    print(f"  +--> AI Jobs    : {len(df_ai)} listings (Live AI/ML company crawl)")
    print(f"  [OK] Ingested {total} verified jobs across all APIs in {api_time:.1f}s!\n")

    return combined, source_counts


def run_stage2_scraper(
    profile: dict,
    geography_choice: str,
    search_mode: str,
    max_searches: int,
    max_runtime: int,
    max_hours: int,
    scheduler: BalancedScheduler,
    checkpoint_mgr: CheckpointManager,
    session_id: str,
    completed_keys: set,
    search_count: int,
    total_jobs_found: int,
    collected_dfs: list[pd.DataFrame]
) -> tuple[int, int, int, str]:
    """
    Execute Stage 2: Regional hub scraper with checkpointing.
    Returns updated (search_count, total_jobs_found, stop_reason, elapsed_time)
    """
    print("=" * 78)
    print(f"  STAGE 2: REGIONAL HUB SCRAPER ({search_mode.upper()} MODE)")
    print("=" * 78)

    queues, counts = scheduler.generate_execution_queues(
        search_terms=profile["search_terms"],
        geography_choice=geography_choice,
        mode=search_mode
    )

    delay = 1.5 if search_mode == "Express" else scheduler.settings.get("request_delay_seconds", 2.5)
    adapter = MultiBoardAdapter(request_delay=delay)

    finished_regions = {r: (counts[r] == 0) for r in ["India", "Middle East", "Global"]}
    start_time = time.time()
    stop_reason = "NORMAL_COMPLETION"

    try:
        while not all(finished_regions.values()):
            elapsed = (time.time() - start_time) / 60
            if elapsed >= max_runtime:
                stop_reason = "MAX_RUNTIME_REACHED"
                print(f"\n[!] Reached maximum runtime limit of {max_runtime} minutes.")
                break
            if search_count >= max_searches:
                stop_reason = "MAX_SEARCHES_REACHED"
                print(f"\n[!] Completed all {max_searches} planned regional searches.")
                break

            progressed = False
            for region in ["India", "Middle East", "Global"]:
                if finished_regions[region]:
                    continue

                try:
                    item = next(queues[region])
                except StopIteration:
                    finished_regions[region] = True
                    continue

                item_key = f"{item['region']}_{item['location']}_{item['term']}_{item['site']}"
                if item_key in completed_keys:
                    continue

                progressed = True
                search_count += 1
                elapsed = (time.time() - start_time) / 60
                pct = int((search_count / max_searches) * 100) if max_searches else 0

                print(f"[{search_count:03d}/{max_searches:03d} | {pct:2d}%] Time: {elapsed:4.1f}m | Found: {total_jobs_found:3d} | {item['site'].upper():<8} | {item['location']:<20} | \"{item['term']}\"")

                result = adapter.search_single_site(
                    site=item["site"],
                    term=item["term"],
                    location=item["location"],
                    region=item["region"],
                    country=item.get("country", ""),
                    hours_old=max_hours,
                    results_wanted=scheduler.settings.get("results_per_site", 25)
                )

                if result is not None and not result.empty:
                    found_count = len(result)
                    total_jobs_found += found_count
                    collected_dfs.append(result)
                    print(f"       +--> [OK] Found {found_count} listings! (Total: {total_jobs_found})")

                completed_keys.add(item_key)

                if search_count % 15 == 0 and search_count < max_searches:
                    bar = format_progress_bar(search_count, max_searches)
                    avg_rate = search_count / max(0.1, elapsed)
                    est_rem = (max_searches - search_count) / max(0.1, avg_rate)
                    print("  " + "-" * 74)
                    print(f"   STATUS: {bar} | Est. Remaining: ~{est_rem:.1f} mins | Total Raw Jobs: {total_jobs_found}")
                    print("  " + "-" * 74)

                if search_count % 10 == 0 and collected_dfs:
                    current_raw = pd.concat(collected_dfs, ignore_index=True)
                    checkpoint_mgr.save(current_raw, search_count, completed_keys, session_id)

            if not progressed:
                break

    except KeyboardInterrupt:
        stop_reason = "STOPPED_BY_USER_CTRL_C"
        print("\n\n[STOP] Search halted by user (Ctrl+C). Finalizing acquired data...")

    except Exception as e:
        stop_reason = f"ERROR_{type(e).__name__}"
        print(f"\n[ERROR] {e}")
        traceback.print_exc()

    elapsed_total = (time.time() - start_time) / 60
    return search_count, total_jobs_found, elapsed_total, stop_reason


def run_search_pipeline(
    profile: dict,
    max_searches: int = 60,
    max_runtime: int = 30,
    max_hours: int = 72,
    geography_choice: str = "All",
    search_mode: str = "Express",
    non_interactive: bool = True,
    checkpoint_dir: str | None = None,
    output_dir: str | None = None
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Execute the complete AuraJobs search pipeline.

    Args:
        profile: Search profile from prompt_user_profile or built manually
        max_searches: Hard cap on regional scraper queries
        max_runtime: Hard cap on execution time in minutes
        max_hours: Freshness window in hours
        geography_choice: "All", "India", "Middle East", "Global"
        search_mode: "Express" or "Deep"
        non_interactive: Skip interactive prompts
        checkpoint_dir: Directory for checkpoint files
        output_dir: Directory for output CSV

    Returns:
        Tuple of (final_df, metadata_dict)
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = output_dir or os.path.join(base_dir, "output")
    checkpoint_dir = checkpoint_dir or os.path.join(base_dir, "checkpoints")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(checkpoint_dir, exist_ok=True)

    # Initialize components
    scheduler = BalancedScheduler()
    classifier = RoleClassifier(
        positive_terms=profile.get("positive_title_terms", []),
        negative_terms=profile.get("negative_title_terms", [])
    )
    scorer = MatchScorer(
        target_role=profile["target_role"],
        skills=profile.get("skills", []),
        seniority=profile.get("seniority", "Any")
    )
    exporter = OutputExporter(output_dir)
    checkpoint_mgr = CheckpointManager(checkpoint_dir)

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    start_time = time.time()

    # Checkpoint resume
    collected_dfs = []
    completed_keys = set()
    search_count = 0
    total_jobs_found = 0

    prev_state, checkpoint_df = checkpoint_mgr.load()
    if prev_state and not checkpoint_df.empty and not non_interactive:
        # In non-interactive/alert mode, we don't prompt for resume
        pass

    # Stage 1: Direct APIs
    stage1_df, source_counts = run_stage1_apis(profile, geography_choice)
    if not stage1_df.empty:
        collected_dfs.append(stage1_df)
        total_jobs_found += len(stage1_df)

    # Stage 2: Regional Scraper
    search_count, total_jobs_found, _stage2_elapsed, stop_reason = run_stage2_scraper(
        profile=profile,
        geography_choice=geography_choice,
        search_mode=search_mode,
        max_searches=max_searches,
        max_runtime=max_runtime,
        max_hours=max_hours,
        scheduler=scheduler,
        checkpoint_mgr=checkpoint_mgr,
        session_id=session_id,
        completed_keys=completed_keys,
        search_count=search_count,
        total_jobs_found=total_jobs_found,
        collected_dfs=collected_dfs
    )

    # Combine and process
    raw_combined = pd.concat(collected_dfs, ignore_index=True) if collected_dfs else pd.DataFrame()

    print("\n" + "=" * 78)
    print("  NORMALIZING & FILTERING RESULTS")
    print("=" * 78)

    final_df = process_results(raw_combined, profile, scorer, classifier, max_hours)

    # Export
    output_filepath = exporter.export_single_file(
        final_df=final_df,
        target_role=profile["target_role"],
        geography=geography_choice,
        started=datetime.fromtimestamp(start_time)
    )

    # Clear checkpoint on success
    if stop_reason in ["NORMAL_COMPLETION", "MAX_SEARCHES_REACHED"]:
        checkpoint_mgr.clear()

    runtime_minutes = (time.time() - start_time) / 60

    metadata = {
        "target_role": profile["target_role"],
        "seniority": profile.get("seniority", "Any"),
        "geography": geography_choice,
        "search_mode": search_mode,
        "stop_reason": stop_reason,
        "searches_completed": search_count,
        "runtime_minutes": runtime_minutes,
        "raw_ingested": len(raw_combined),
        "final_count": len(final_df),
        "source_counts": source_counts,
        "output_file": output_filepath,
        "session_id": session_id
    }

    return final_df, metadata


if __name__ == "__main__":
    # Quick test with minimal profile
    test_profile = {
        "target_role": "Software Engineer",
        "seniority": "Senior",
        "positive_title_terms": ["software", "engineer", "developer"],
        "negative_title_terms": ["intern", "junior", "trainee"],
        "skills": ["Python", "AWS", "Kubernetes"],
        "search_terms": ["Software Engineer", "Backend Engineer"],
    }
    df, meta = run_search_pipeline(
        profile=test_profile,
        max_searches=5,
        max_runtime=5,
        max_hours=24,
        geography_choice="Global",
        search_mode="Express",
        non_interactive=True
    )
    print(f"\nPipeline test complete: {len(df)} jobs, output: {meta.get('output_file')}")