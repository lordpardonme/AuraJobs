#!/usr/bin/env python3
"""
AuraJobs Daily Alerts CLI
Entry point for managing automated Telegram job alerts.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.alert_config import AlertConfig, load_alert_config, save_alert_config
from core.alert_scheduler import create_scheduler_from_env
from core.alert_state import create_alert_state
from core.expander import RoleExpander
from core.notifications import (
    NotificationDispatcher,
    pair_telegram_bot,
)


def setup_wizard(config_path: str | None = None) -> bool:
    """Interactive setup wizard for daily alerts."""
    print("=" * 70)
    print("  AURAJOBS DAILY ALERTS - SETUP WIZARD")
    print("=" * 70)
    print("\nThis wizard will configure automated daily job alerts via Telegram.\n")

    # Step 1: Telegram Bot Pairing
    print("-" * 70)
    print("STEP 1: Telegram Bot Setup")
    print("-" * 70)
    print("You need a Telegram Bot Token from @BotFather.")
    print("If you already have one, you can enter it now.\n")

    pair_now = input("Run Telegram pairing wizard now? [Y/n]: ").strip().lower()
    if pair_now in ["", "y"]:
        success = pair_telegram_bot()
        if not success:
            print("[ERROR] Pairing failed. Please try again.")
            return False
    else:
        # Manual token entry
        bot_token = input("Enter your Telegram Bot Token: ").strip().strip("'\"")
        if not bot_token:
            print("[ERROR] Bot token is required.")
            return False
        if ":" not in bot_token:
            print("[WARN] Token format looks incorrect (should contain ':'). Continuing anyway...")

        chat_id = input("Enter your Telegram Chat ID: ").strip()
        if not chat_id:
            print("[ERROR] Chat ID is required.")
            return False

        # Save to environment (user must persist these)
        print("\n[IMPORTANT] Set these environment variables:")
        print(f"  export TELEGRAM_BOT_TOKEN='{bot_token}'")
        print(f"  export TELEGRAM_CHAT_ID='{chat_id}'")
        print("On Windows (PowerShell):")
        print(f"  $env:TELEGRAM_BOT_TOKEN='{bot_token}'")
        print(f"  $env:TELEGRAM_CHAT_ID='{chat_id}'")
        print("Add to your shell profile (.bashrc, .zshrc, PowerShell profile) for persistence.")

    # Step 2: Schedule Configuration
    print("\n" + "-" * 70)
    print("STEP 2: Schedule Configuration")
    print("-" * 70)
    print("When should the daily search run? (Cron expression)")
    print("  Examples:")
    print("    0 8 * * *     = Daily at 8:00 AM")
    print("    0 9 * * 1-5   = Weekdays at 9:00 AM")
    print("    0 */6 * * *   = Every 6 hours")
    print("    0 22 * * 0    = Weekly on Sunday at 10:00 PM")

    cron = input("\nCron expression [0 8 * * *]: ").strip() or "0 8 * * *"

    # Validate cron
    parts = cron.split()
    if len(parts) not in (5, 6):
        print(f"[ERROR] Invalid cron: '{cron}' (need 5 or 6 fields)")
        return False

    timezone = input("Timezone (IANA, e.g. Asia/Kolkata, America/New_York) [system default]: ").strip()

    # Step 3: Alert Filters
    print("\n" + "-" * 70)
    print("STEP 3: Alert Filters (Optional)")
    print("-" * 70)

    min_score = input("Minimum match score for alerts (0-100) [75]: ").strip()
    min_score = int(min_score) if min_score.isdigit() else 75

    max_cards = input("Max job cards per alert (1-20) [5]: ").strip()
    max_cards = int(max_cards) if max_cards.isdigit() else 5

    send_csv = input("Send CSV digest with alerts? [Y/n]: ").strip().lower()
    send_csv = send_csv not in ["n", "no"]

    visa_only = input("Only alert on visa sponsorship mentions? [y/N]: ").strip().lower()
    visa_only = visa_only in ["y", "yes"]

    relocation_only = input("Only alert on relocation offers? [y/N]: ").strip().lower()
    relocation_only = relocation_only in ["y", "yes"]

    # Step 4: Search Profile
    print("\n" + "-" * 70)
    print("STEP 4: Default Search Profile")
    print("-" * 70)
    print("This profile will be used for scheduled runs (can be overridden per-run).\n")

    role = input("Target role [Software Engineer]: ").strip() or "Software Engineer"
    seniority = input("Seniority (Any/Intern/Junior/Mid-Level/Senior/Staff/Lead/Principal) [Any]: ").strip() or "Any"
    skills_input = input("Key skills (comma-separated) []: ").strip()
    skills = [s.strip() for s in skills_input.split(",") if s.strip()] if skills_input else []

    geography = input("Geography (All/India/Middle East/Global) [All]: ").strip() or "All"
    freshness = input("Freshness hours (24/48/72) [72]: ").strip()
    freshness = int(freshness) if freshness.isdigit() else 72

    mode = input("Search mode (Express/Deep) [Express]: ").strip() or "Express"

    # Build and save config
    config = AlertConfig()
    config.schedule.cron = cron
    config.schedule.timezone = timezone
    config.telegram.min_match_score = min_score
    config.telegram.max_alert_cards = max_cards
    config.telegram.send_csv_digest = send_csv
    config.telegram.include_visa_sponsored = not visa_only
    config.telegram.include_relocation = not relocation_only
    config.filters.visa_required = visa_only
    config.filters.relocation_required = relocation_only

    # Save profile for scheduled runs
    expander = RoleExpander()
    profile = expander.build_search_profile(
        target_role=role,
        seniority=seniority,
        skills=skills,
        exclusions=[]
    )
    profile.update({
        "geography_choice": geography,
        "freshness_hours": freshness,
        "search_mode": mode,
    })

    # Save profile to logs
    base_dir = Path(__file__).resolve().parent
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    profile_path = logs_dir / f"SEARCH_PROFILE_{timestamp}.json"
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    print(f"\n[OK] Saved default search profile to {profile_path}")

    # Save alerts.yaml
    if save_alert_config(config, config_path):
        print("[OK] Saved alerts configuration to alerts.yaml")
    else:
        print("[ERROR] Failed to save alerts.yaml")
        return False

    print("\n" + "=" * 70)
    print("  SETUP COMPLETE!")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Ensure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in your environment")
    print("  2. Test with:  python alerts.py --test")
    print("  3. Run once:   python alerts.py --run-once")
    print("  4. Start daemon: python alerts.py --daemon")
    print("  5. Check status: python alerts.py --status")
    return True


def test_alert(config_path: str | None = None) -> bool:
    """Send a test alert to verify configuration."""
    print("=" * 70)
    print("  AURAJOBS DAILY ALERTS - TEST MODE")
    print("=" * 70)

    try:
        config = load_alert_config(config_path)
        missing = config.validate_secrets()
        if missing:
            print(f"[ERROR] Missing environment variables: {missing}")
            print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        return False

    state = create_alert_state(config)
    dispatcher = NotificationDispatcher(config, state)

    # Mock job for test
    mock_job = {
        "title": "Senior Software Engineer (Test Alert)",
        "company": "AuraJobs Demo",
        "location": "Global Remote",
        "match_score": 95,
        "source": "Test",
        "job_url": "https://github.com/lordpardonme/AuraJobs",
        "visa_status": "Global Relocation & Sponsorship Supported",
        "relocation_status": True,
        "id": "test_001"
    }

    print("\n[*] Sending test alert...")
    result = dispatcher.dispatch([mock_job], csv_path=None, alert_run_id=f"test_{int(time.time())}")

    print(f"\nResult: {result}")
    if result.get("sent", 0) > 0:
        print("[SUCCESS] Test alert sent! Check your Telegram.")
        return True
    else:
        print("[FAILED] Test alert not sent. Check logs.")
        return False


def run_once(config_path: str | None = None, profile_override: dict | None = None) -> bool:
    """Execute a single search + alert cycle."""
    print("=" * 70)
    print("  AURAJOBS DAILY ALERTS - MANUAL RUN")
    print("=" * 70)

    try:
        scheduler = create_scheduler_from_env(config_path)
    except Exception as e:
        print(f"[ERROR] Failed to initialize scheduler: {e}")
        return False

    print("\n[*] Running search pipeline and dispatching alerts...")
    result = scheduler.run_once(profile_override)

    if result.get("error"):
        print(f"\n[ERROR] Run failed: {result['error']}")
        return False

    print("\n[OK] Run completed successfully!")
    print(f"  Jobs found: {result.get('final_count', 0)}")
    print(f"  Alerts sent: {result.get('dispatch_summary', {}).get('sent', 0)}")
    print(f"  CSV: {result.get('output_file', 'N/A')}")
    return True


def show_status(config_path: str | None = None) -> bool:
    """Show scheduler and alert state status."""
    print("=" * 70)
    print("  AURAJOBS DAILY ALERTS - STATUS")
    print("=" * 70)

    try:
        scheduler = create_scheduler_from_env(config_path)
    except Exception as e:
        print(f"[ERROR] Failed to initialize scheduler: {e}")
        return False

    status = scheduler.get_status()

    print(f"\nScheduler Running: {'Yes' if status['running'] else 'No'}")
    print(f"Schedule: {status['schedule']} ({status['timezone']})")
    print(f"Next Run: {status['next_run'] or 'N/A'}")
    print(f"Total Runs: {status['total_runs']}")

    print("\nAlert State:")
    alert_state = status['alert_state']
    print(f"  Total Jobs Sent: {alert_state.get('total_sent', 0)}")
    print(f"  Last 7 Days: {alert_state.get('last_7_days', 0)}")
    print(f"  Store: {alert_state.get('store_type', 'unknown')} ({alert_state.get('db_path', 'N/A')})")

    recent = status.get('recent_alert_runs', [])
    if recent:
        print("\nRecent Alert Runs:")
        for run in recent:
            print(f"  {run['alert_run_id']}: {run['job_count']} jobs at {run['last_sent']}")

    last_run = status.get('last_run')
    if last_run:
        print("\nLast Run:")
        print(f"  Run ID: {last_run.get('run_id')}")
        print(f"  Jobs: {last_run.get('final_count', 0)}")
        print(f"  Alerts Sent: {last_run.get('dispatch_summary', {}).get('sent', 0)}")
        print(f"  Time: {last_run.get('timestamp')}")

    return True


def start_daemon(config_path: str | None = None) -> None:
    """Start the background scheduler daemon."""
    print("=" * 70)
    print("  AURAJOBS DAILY ALERTS - DAEMON MODE")
    print("=" * 70)

    try:
        scheduler = create_scheduler_from_env(config_path)
    except Exception as e:
        print(f"[ERROR] Failed to initialize scheduler: {e}")
        sys.exit(1)

    print("\n[*] Starting daemon... Press Ctrl+C to stop.")
    print(f"Schedule: {scheduler.config.schedule.cron} ({scheduler.config.schedule.timezone or 'system'})")
    job = scheduler.scheduler.get_job("aurajobs_daily_alert") if scheduler.scheduler else None
    if job and job.next_run_time:
        print(f"Next run: {job.next_run_time}")

    try:
        scheduler.start_daemon()
    except KeyboardInterrupt:
        print("\n[STOP] Daemon stopped by user.")
    except Exception as e:
        print(f"\n[ERROR] Daemon error: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="AuraJobs Daily Alerts - Automated Telegram Job Notifications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python alerts.py --setup           # Interactive setup wizard
  python alerts.py --test            # Send test alert
  python alerts.py --run-once        # Run search + alert once
  python alerts.py --daemon          # Start background scheduler
  python alerts.py --status          # Show status

Environment Variables:
  TELEGRAM_BOT_TOKEN    Bot token from @BotFather (required)
  TELEGRAM_CHAT_ID      Your chat ID (required)
        """
    )
    parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard")
    parser.add_argument("--test", action="store_true", help="Send test alert to Telegram")
    parser.add_argument("--run-once", action="store_true", help="Execute one search + alert cycle")
    parser.add_argument("--daemon", action="store_true", help="Start background scheduler daemon")
    parser.add_argument("--status", action="store_true", help="Show scheduler and alert state status")
    parser.add_argument("--config", type=str, help="Path to alerts.yaml config file")
    parser.add_argument("--role", type=str, help="Override target role for --run-once")
    parser.add_argument("--seniority", type=str, help="Override seniority for --run-once")
    parser.add_argument("--geo", type=str, help="Override geography for --run-once")
    parser.add_argument("--freshness", type=int, help="Override freshness hours for --run-once")
    parser.add_argument("--mode", type=str, choices=["Express", "Deep"], help="Override search mode for --run-once")

    args = parser.parse_args()

    if not any([args.setup, args.test, args.run_once, args.daemon, args.status]):
        parser.print_help()
        return

    profile_override = {}
    if args.role:
        profile_override["role"] = args.role
    if args.seniority:
        profile_override["seniority"] = args.seniority
    if args.geo:
        profile_override["geography"] = args.geo
    if args.freshness:
        profile_override["freshness"] = args.freshness
    if args.mode:
        profile_override["mode"] = args.mode

    if args.setup:
        success = setup_wizard(args.config)
        sys.exit(0 if success else 1)
    elif args.test:
        success = test_alert(args.config)
        sys.exit(0 if success else 1)
    elif args.run_once:
        success = run_once(args.config, profile_override if profile_override else None)
        sys.exit(0 if success else 1)
    elif args.daemon:
        start_daemon(args.config)
    elif args.status:
        success = show_status(args.config)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()