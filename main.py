import os
import sys
import time
import argparse
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

# Ensure terminal stdout/stderr handles UTF-8 cleanly without charmap crashes
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.prompt import prompt_user_profile
from core.scheduler import BalancedScheduler
from core.normalizer import normalize_dataframe
from core.classifier import RoleClassifier
from core.visa import detect_visa_sponsorship, detect_relocation
from core.scorer import MatchScorer, calculate_age_hours
from core.deduper import deduplicate_jobs
from core.checkpoint import CheckpointManager
from core.exporters import OutputExporter
from sources import (
    MultiBoardAdapter,
    RemoteOKAdapter,
    RemotiveAdapter,
    HimalayasAdapter,
    ATSAdapter,
    FreeHireAdapter,
    ArbeitnowAdapter,
    AIJobsAdapter,
    AdzunaAdapter,
)
from core.cache import get_cache, clear_cache

def parse_args():
    parser = argparse.ArgumentParser(description="AuraJobs - Autonomous Career Intelligence Engine")
    parser.add_argument("--role", type=str, default=None, help="Target role family (e.g. 'Product Designer', 'Data Scientist')")
    parser.add_argument("--seniority", type=str, default="Any", help="Seniority level (Any, Senior, Staff, Lead, Principal)")
    parser.add_argument("--geo", type=str, default="All", choices=["All", "India", "Middle East", "Global"], help="Target region")
    parser.add_argument("--freshness", type=int, default=72, help="Max posting age in hours (default 72)")
    parser.add_argument("--mode", type=str, default="Express", choices=["Express", "Deep"], help="Search mode: Express (~1 min) or Deep (~10 mins)")
    parser.add_argument("--max-searches", type=int, default=None, help="Hard maximum search count")
    parser.add_argument("--max-runtime", type=int, default=None, help="Hard maximum runtime in minutes")
    parser.add_argument("--non-interactive", action="store_true", help="Run with provided or default arguments without prompting")
    parser.add_argument("--no-cache", action="store_true", help="Disable API response caching")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache before running")
    parser.add_argument("--cache-ttl", type=int, default=24, help="Cache time-to-live in hours (default 24)")
    return parser.parse_args()

def format_progress_bar(current: int, total: int, bar_length: int = 20) -> str:
    fraction = min(1.0, current / total) if total > 0 else 0
    filled = int(bar_length * fraction)
    bar = "=" * filled + "-" * (bar_length - filled)
    return f"[{bar}] {int(fraction * 100)}%"

def process_results(raw_df: pd.DataFrame, profile: dict, scorer: MatchScorer, classifier: RoleClassifier, max_hours: int) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    df = normalize_dataframe(raw_df)

    df["date_posted"] = pd.to_datetime(df["date_posted"], errors="coerce", utc=True)
    df["age_hours"] = df["date_posted"].apply(calculate_age_hours)

    # Keep jobs where age_hours is within max_hours or where date_posted was not parsed
    # (JobSpy already passed hours_old directly to query parameters; APIs return active postings)
    df = df[
        df["age_hours"].isna()
        | ((df["age_hours"] >= 0) & (df["age_hours"] <= max_hours))
    ].copy()

    if df.empty:
        return df

    strict_df = classifier.filter_dataframe(df)

    if strict_df.empty and not df.empty:
        # Graceful Fallback Mode:
        # If strict title filtering produced 0 jobs, don't leave the user empty-handed!
        print("\n[!] Notice: No exact title matches met strict criteria.")
        print("    --> Activating Graceful Fallback Mode: Surfacing top broad domain opportunities...")

        # Keep jobs that do not hit hard negative exclusions
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

def main():
    args = parse_args()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "output")
    checkpoint_dir = os.path.join(base_dir, "checkpoints")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(checkpoint_dir, exist_ok=True)

    # Initialize cache
    if args.clear_cache:
        clear_cache()
        print("[OK] Cache cleared.")

    cache = get_cache(
        cache_dir=os.path.join(base_dir, "cache"),
        ttl_hours=args.cache_ttl,
        enabled=not args.no_cache
    )

    if args.no_cache:
        print("[INFO] API response caching disabled (--no-cache)")
    else:
        stats = cache.stats()
        print(f"[INFO] API cache: {stats['entries']} entries, {stats['size_mb']} MB, TTL {stats['ttl_hours']}h")

    # 1. Obtain Search Profile
    if args.non_interactive:
        profile = prompt_user_profile(
            output_dir=output_dir,
            non_interactive=True,
            default_role=args.role or "Product Designer",
            default_seniority=args.seniority or "Any"
        )
        if args.geo != "All":
            profile["geography_choice"] = args.geo
        if args.freshness:
            profile["freshness_hours"] = args.freshness
        profile["search_mode"] = args.mode or "Express"
    else:
        profile = prompt_user_profile(output_dir=output_dir, default_role=args.role or "Product Designer")
        if not profile:
            return

    # 2. Initialize Scheduler & Budgets
    scheduler = BalancedScheduler()
    max_searches = args.max_searches or scheduler.max_searches
    max_runtime = args.max_runtime or scheduler.max_runtime_minutes
    max_hours = profile.get("freshness_hours", 72)
    geography_choice = profile.get("geography_choice", "All")
    search_mode = profile.get("search_mode", "Express")

    queues, counts = scheduler.generate_execution_queues(
        search_terms=profile["search_terms"],
        geography_choice=geography_choice,
        mode=search_mode
    )

    total_scheduled = sum(counts.values())
    target_searches = min(max_searches, total_scheduled)

    # Clean dashboard header
    print("\n" + "=" * 78)
    print("  AURAJOBS - LIVE MULTI-SOURCE SEARCH")
    print("=" * 78)
    print(f"  Target Role     : {profile['target_role']} ({profile['seniority']})")
    print(f"  Freshness Window: Last {max_hours} Hours")
    print(f"  Target Region   : {geography_choice}")
    print(f"  Search Mode     : {search_mode.upper()} ({target_searches} regional scraper queries)")
    print(f"  Direct Sources  : RemoteOK, Remotive, Himalayas, FreeHire, Arbeitnow, AIJobs, Ashby, Greenhouse")
    print(f"  Scraper Sources : LinkedIn, Indeed, Google, Naukri, Bayt (with Scrapling Anti-Bot Escalation)")
    print(f"  Safety Limits   : Max {max_searches} searches | Max {max_runtime} mins")
    print("=" * 78 + "\n")

    # 3. Checkpoint Resume
    checkpoint_mgr = CheckpointManager(checkpoint_dir)
    prev_state, checkpoint_df = checkpoint_mgr.load()

    collected_dfs = []
    completed_keys = set()
    search_count = 0
    total_jobs_found = 0

    if prev_state and not checkpoint_df.empty and not args.non_interactive:
        resume_prompt = input(f"> Found checkpoint with {len(checkpoint_df)} existing jobs ({prev_state.get('updated_at')}). Resume? [Y/n]: ").strip().lower()
        if resume_prompt in ["", "y"]:
            collected_dfs.append(checkpoint_df)
            completed_keys = set(prev_state.get("completed_keys", []))
            search_count = prev_state.get("search_count", 0)
            total_jobs_found = len(checkpoint_df)
            print(f"[OK] Resumed: {total_jobs_found} previous jobs loaded.\n")

    # 4. Initialize Core Components
    delay = 1.5 if search_mode == "Express" else scheduler.settings.get("request_delay_seconds", 2.5)
    adapter = MultiBoardAdapter(request_delay=delay)
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

    start_time = time.time()
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    stop_reason = "NORMAL_COMPLETION"

    # =========================================================================
    # STAGE 1: INSTANT ZERO-AUTH PUBLIC APIS & DIRECT ATS FEEDS
    # =========================================================================
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
    adz = AdzunaAdapter()

    with ThreadPoolExecutor(max_workers=8) as executor:
        f_rok = executor.submit(rok.fetch_jobs, profile["target_role"], profile.get("positive_title_terms", []))
        f_rem = executor.submit(rem.fetch_jobs, profile["target_role"])
        f_him = executor.submit(him.fetch_jobs, profile["target_role"], profile.get("positive_title_terms", []))
        f_ats = executor.submit(ats.fetch_all_ats, profile["target_role"], profile.get("positive_title_terms", []))
        f_fh = executor.submit(fh.fetch_jobs, profile["target_role"], geography_choice)
        f_an = executor.submit(an.fetch_jobs, profile["target_role"])
        f_ai = executor.submit(ai.fetch_jobs, profile["target_role"])
        f_adz = executor.submit(adz.fetch_jobs, profile["target_role"], "", geography_choice, 25, max_hours)

        df_rok = f_rok.result()
        df_rem = f_rem.result()
        df_him = f_him.result()
        df_ats = f_ats.result()
        df_fh = f_fh.result()
        df_an = f_an.result()
        df_ai = f_ai.result()
        df_adz = f_adz.result()

    api_dfs = [d for d in [df_rok, df_rem, df_him, df_ats, df_fh, df_an, df_ai, df_adz] if not d.empty]
    if api_dfs:
        combined_api = pd.concat(api_dfs, ignore_index=True)
        collected_dfs.append(combined_api)
        total_jobs_found += len(combined_api)

    api_time = time.time() - api_start
    print(f"  +--> RemoteOK   : {len(df_rok)} listings")
    print(f"  +--> Remotive   : {len(df_rem)} listings")
    print(f"  +--> Himalayas  : {len(df_him)} listings")
    print(f"  +--> Direct ATS : {len(df_ats)} listings (Linear, Notion, Cursor, GitLab, Stripe, etc.)")
    print(f"  +--> FreeHire   : {len(df_fh)} listings (Greenhouse, Lever, Freshteam, Recruitee ATS)")
    print(f"  +--> Arbeitnow  : {len(df_an)} listings (Europe / Global Remote)")
    print(f"  +--> AI Jobs    : {len(df_ai)} listings (Live AI/ML company crawl)")
    print(f"  +--> Adzuna     : {len(df_adz)} listings (Middle East coverage)")
    print(f"  [OK] Ingested {total_jobs_found} verified jobs across all APIs in {api_time:.1f}s!\n")

    # =========================================================================
    # STAGE 2: TARGETED REGIONAL SCRAPER (LINKEDIN & INDEED)
    # =========================================================================
    print("=" * 78)
    print(f"  STAGE 2: REGIONAL HUB SCRAPER ({search_mode.upper()} MODE)")
    print("=" * 78)

    finished_regions = {r: (counts[r] == 0) for r in ["India", "Middle East", "Global"]}

    try:
        while not all(finished_regions.values()):
            elapsed = (time.time() - start_time) / 60
            if elapsed >= max_runtime:
                stop_reason = "MAX_RUNTIME_REACHED"
                print(f"\n[!] Reached maximum runtime limit of {max_runtime} minutes.")
                break
            if search_count >= target_searches:
                stop_reason = "MAX_SEARCHES_REACHED"
                print(f"\n[!] Completed all {target_searches} planned regional searches.")
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
                pct = int((search_count / target_searches) * 100) if target_searches else 0

                # Formatted status block
                print(f"[{search_count:03d}/{target_searches:03d} | {pct:2d}%] Time: {elapsed:4.1f}m | Found: {total_jobs_found:3d} | {item['site'].upper():<8} | {item['location']:<20} | \"{item['term']}\"")

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

                # Status check update every 15 searches
                if search_count % 15 == 0 and search_count < target_searches:
                    bar = format_progress_bar(search_count, target_searches)
                    avg_rate = search_count / max(0.1, elapsed)
                    est_rem = (target_searches - search_count) / max(0.1, avg_rate)
                    print("  " + "-" * 74)
                    print(f"   STATUS: {bar} | Est. Remaining: ~{est_rem:.1f} mins | Total Raw Jobs: {total_jobs_found}")
                    print("  " + "-" * 74)

                # Periodic checkpointing
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

    # =========================================================================
    # PROCESS & EXPORT INTO EXACTLY ONE CSV FILE
    # =========================================================================
    runtime_minutes = (time.time() - start_time) / 60
    raw_combined = pd.concat(collected_dfs, ignore_index=True) if collected_dfs else pd.DataFrame()

    print("\n" + "=" * 78)
    print("  NORMALIZING & FILTERING RESULTS")
    print("=" * 78)

    final_df = process_results(raw_combined, profile, scorer, classifier, max_hours)

    # =========================================================================
    # GITHUB COMPANY ENRICHMENT
    # =========================================================================
    if not final_df.empty:
        print("\n" + "=" * 78)
        print("  GITHUB COMPANY ENRICHMENT")
        print("=" * 78)
        try:
            from core.github_enrichment import enrich_jobs_with_github
            final_df = enrich_jobs_with_github(final_df, company_col="company", progress=True)
            print("[OK] GitHub enrichment completed")
        except Exception as e:
            print(f"[WARN] GitHub enrichment failed: {e}")

    output_filepath = exporter.export_single_file(
        final_df=final_df,
        target_role=profile["target_role"],
        geography=profile["geography_choice"],
        started=datetime.fromtimestamp(start_time)
    )

    if stop_reason in ["NORMAL_COMPLETION", "MAX_SEARCHES_REACHED"]:
        checkpoint_mgr.clear()

    # Summary Report (printed to terminal only)
    print("\n" + "=" * 78)
    print("  RUN SUMMARY")
    print("=" * 78)
    print(f"  Target Role                 : {profile['target_role']} ({profile['seniority']})")
    print(f"  Target Region               : {profile['geography_choice']}")
    print(f"  Search Mode                 : {search_mode.upper()}")
    print(f"  Stop Reason                 : {stop_reason}")
    print(f"  Regional Searches Completed : {search_count}")
    print(f"  Runtime                     : {runtime_minutes:.2f} minutes")
    print(f"  Raw Results Ingested        : {len(raw_combined)}")
    print(f"  Relevant Qualified Jobs     : {len(final_df)}")
    if not final_df.empty and "match_type" in final_df.columns:
        match_types = final_df["match_type"].value_counts().to_dict()
        match_desc = ", ".join(f"{count} {mtype}" for mtype, count in match_types.items())
        print(f"  Match Classification        : {match_desc}")
    if not final_df.empty and "visa_status" in final_df.columns:
        visa_count = len(final_df[final_df["visa_status"] == "SPONSORSHIP MENTIONED"])
        print(f"  Visa Sponsorship Mentioned  : {visa_count}")

    if not final_df.empty:
        print("\nTOP OPPORTUNITIES DISCOVERED:")
        print("-" * 78)
        cols = ["priority", "match_type", "match_score", "visa_status", "title", "company", "location", "job_url"]
        cols = [c for c in cols if c in final_df.columns]
        print(final_df[cols].head(15).to_string(index=False))

    print("\nOUTPUT FILE CREATED:")
    print(f"  ==> {output_filepath}")
    print("=" * 78 + "\n")

    # Optional Mobile Notification Dispatcher (Telegram Staging Engine)
    try:
        from core.notifications import dispatch_job_notifications
        records = final_df.to_dict(orient="records") if not final_df.empty else []
        dispatch_job_notifications(records, csv_path=output_filepath)
    except Exception as e:
        pass

if __name__ == "__main__":
    main()
