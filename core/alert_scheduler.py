"""
AuraJobs Alert Scheduler
Runs the search pipeline on a cron schedule and dispatches Telegram alerts.
"""

import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.executors.pool import ThreadPoolExecutor as APSThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.alert_config import AlertConfig, load_alert_config
from core.alert_state import create_alert_state
from core.notifications import NotificationDispatcher
from core.pipeline import run_search_pipeline


# Configure logging
def setup_logging(config: AlertConfig):
    """Configure logging based on alert config."""
    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    handlers = [logging.StreamHandler(sys.stdout)]
    file_handler = None

    if config.logging.file_path:
        log_path = Path(config.logging.file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        handlers.append(file_handler)

    if config.logging.json_format:
        # Simple JSON formatter
        import json
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_obj = {
                    "timestamp": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                # Add extra fields
                for key, value in record.__dict__.items():
                    if key not in {"name", "msg", "args", "created", "filename", "funcName",
                                   "levelname", "levelno", "lineno", "module", "msecs",
                                   "message", "pathname", "process",
                                   "processName", "relativeCreated", "thread", "threadName",
                                   "exc_info", "exc_text", "stack_info", "getMessage"}:
                        log_obj[key] = value
                return json.dumps(log_obj)
        for h in handlers:
            h.setFormatter(JSONFormatter())
    else:
        for h in handlers:
            h.setFormatter(logging.Formatter(log_format))

    logging.basicConfig(level=log_level, handlers=handlers, force=True)
    return file_handler


def teardown_logging(file_handler=None):
    """Clean up logging handlers to release file locks."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()
    if file_handler:
        file_handler.close()


logger = logging.getLogger("aurajobs.alerts.scheduler")


class AlertScheduler:
    """
    Background scheduler for automated AuraJobs runs with Telegram alerts.
    """

    def __init__(self, config: AlertConfig | None = None, config_path: str | None = None):
        self.config = config or load_alert_config(config_path)
        self.alert_state = create_alert_state(self.config)
        self.dispatcher = NotificationDispatcher(self.config, self.alert_state)
        self.scheduler = None
        self._shutdown = False
        self._last_run_metadata = None
        self._run_count = 0
        self._log_file_handler = None

        # Validate secrets
        missing = self.config.validate_secrets()
        if missing:
            raise ValueError(f"Missing required environment variables: {missing}")

        # Setup logging
        self._log_file_handler = setup_logging(self.config)

    def _build_profile(self, profile_override: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build search profile from saved profile or override."""
        if profile_override:
            # Merge override with defaults
            base_profile = {
                "target_role": profile_override.get("role", "Software Engineer"),
                "seniority": profile_override.get("seniority", "Any"),
                "skills": profile_override.get("skills", []),
                "geography_choice": profile_override.get("geography", "All"),
                "freshness_hours": profile_override.get("freshness", 72),
                "search_mode": profile_override.get("mode", "Express"),
            }
            # Use expander to build full profile
            from core.expander import RoleExpander
            expander = RoleExpander()
            profile = expander.build_search_profile(
                target_role=base_profile["target_role"],
                seniority=base_profile["seniority"],
                skills=base_profile["skills"],
                exclusions=profile_override.get("exclusions", [])
            )
            profile.update({
                "geography_choice": base_profile["geography_choice"],
                "freshness_hours": base_profile["freshness_hours"],
                "search_mode": base_profile["search_mode"],
            })
            return profile

        # Try to load latest saved profile
        base_dir = Path(__file__).resolve().parent.parent
        logs_dir = base_dir / "logs"
        profile_files = sorted(logs_dir.glob("SEARCH_PROFILE_*.json"), reverse=True)
        if profile_files:
            import json
            with open(profile_files[0], "r", encoding="utf-8") as f:
                saved_profile = json.load(f)
            # Override with config filters if needed
            if self.config.filters.regions:
                saved_profile["geography_choice"] = self.config.filters.regions[0] if len(self.config.filters.regions) == 1 else "All"
            return saved_profile

        # Fallback: minimal default profile
        from core.expander import RoleExpander
        expander = RoleExpander()
        return expander.build_search_profile(
            target_role="Software Engineer",
            seniority="Any",
            skills=[],
            exclusions=[]
        )

    def run_once(self, profile_override: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Execute a single search + alert cycle.
        Returns run metadata.
        """
        run_id = f"scheduled_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._run_count += 1

        logger.info("Starting scheduled run", extra={"run_id": run_id, "run_number": self._run_count})

        try:
            profile = self._build_profile(profile_override)

            # Apply config filters to profile
            if self.config.filters.regions and "geography_choice" not in (profile_override or {}):
                profile["geography_choice"] = self.config.filters.regions[0] if len(self.config.filters.regions) == 1 else "All"

            max_searches = self.config.schedule.__dict__.get("max_searches", 60) if hasattr(self.config.schedule, '__dict__') else 60
            max_runtime = self.config.schedule.__dict__.get("max_runtime", 30) if hasattr(self.config.schedule, '__dict__') else 30

            # Use settings from config or defaults
            from core.scheduler import BalancedScheduler
            scheduler = BalancedScheduler()
            max_searches = min(max_searches, scheduler.max_searches)
            max_runtime = min(max_runtime, scheduler.max_runtime_minutes)

            final_df, metadata = run_search_pipeline(
                profile=profile,
                max_searches=max_searches,
                max_runtime=max_runtime,
                max_hours=profile.get("freshness_hours", 72),
                geography_choice=profile.get("geography_choice", "All"),
                search_mode=profile.get("search_mode", "Express"),
                non_interactive=True
            )

            # Dispatch alerts
            csv_path = metadata.get("output_file")
            dispatch_summary = self.dispatcher.dispatch(
                jobs=final_df.to_dict(orient="records") if not final_df.empty else [],
                csv_path=csv_path,
                alert_run_id=run_id
            )

            metadata.update({
                "run_id": run_id,
                "dispatch_summary": dispatch_summary,
                "timestamp": datetime.now().isoformat()
            })
            self._last_run_metadata = metadata

            logger.info("Scheduled run completed", extra=metadata)
            return metadata

        except Exception as e:
            logger.error(f"Scheduled run failed: {e}", extra={"run_id": run_id}, exc_info=True)
            return {
                "run_id": run_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "success": False
            }

    def start_daemon(self):
        """Start the background scheduler daemon."""
        if self.scheduler is not None:
            logger.warning("Scheduler already running")
            return

        # Parse cron expression
        cron_parts = self.config.schedule.cron.strip().split()
        if len(cron_parts) == 5:
            minute, hour, day, month, day_of_week = cron_parts
            second = "0"
        elif len(cron_parts) == 6:
            second, minute, hour, day, month, day_of_week = cron_parts
        else:
            raise ValueError(f"Invalid cron expression: {self.config.schedule.cron}")

        trigger = CronTrigger(
            second=second,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=self.config.schedule.timezone or None
        )

        self.scheduler = BackgroundScheduler(
            executors={"default": APSThreadPoolExecutor(max_workers=1)},
            job_defaults={"coalesce": True, "max_instances": 1},
            timezone=self.config.schedule.timezone or None
        )

        self.scheduler.add_job(
            self.run_once,
            trigger=trigger,
            id="aurajobs_daily_alert",
            name="AuraJobs Daily Alert",
            replace_existing=True
        )

        # Signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self._shutdown = True
            self.stop_daemon()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("Starting AuraJobs Alert Scheduler daemon")
        logger.info(f"Schedule: {self.config.schedule.cron} (timezone: {self.config.schedule.timezone or 'system'})")
        logger.info(f"Next run: {self.scheduler.get_job('aurajobs_daily_alert').next_run_time}")

        self.scheduler.start()

        # Keep alive
        try:
            while not self._shutdown:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop_daemon()

    def stop_daemon(self):
        """Stop the background scheduler."""
        if self.scheduler:
            self.scheduler.shutdown(wait=True)
            self.scheduler = None
            logger.info("Scheduler stopped")
        # Clean up logging handler
        if self._log_file_handler:
            teardown_logging(self._log_file_handler)
            self._log_file_handler = None

    def get_status(self) -> dict[str, Any]:
        """Get scheduler status information."""
        next_run = None
        if self.scheduler:
            job = self.scheduler.get_job("aurajobs_daily_alert")
            if job:
                next_run = job.next_run_time.isoformat() if job.next_run_time else None

        alert_stats = self.alert_state.get_stats()
        recent_runs = self.alert_state.get_recent_runs(5)

        return {
            "running": self.scheduler is not None,
            "schedule": self.config.schedule.cron,
            "timezone": self.config.schedule.timezone or "system",
            "next_run": next_run,
            "total_runs": self._run_count,
            "last_run": self._last_run_metadata,
            "alert_state": alert_stats,
            "recent_alert_runs": recent_runs
        }


def create_scheduler_from_env(config_path: str | None = None) -> AlertScheduler:
    """Factory function to create AlertScheduler from environment."""
    config = load_alert_config(config_path)
    return AlertScheduler(config)


if __name__ == "__main__":
    # Quick test
    import argparse
    parser = argparse.ArgumentParser(description="AuraJobs Alert Scheduler")
    parser.add_argument("--run-once", action="store_true", help="Run once and exit")
    parser.add_argument("--daemon", action="store_true", help="Start daemon")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--config", type=str, help="Path to alerts.yaml")
    args = parser.parse_args()

    try:
        scheduler = create_scheduler_from_env(args.config)
    except Exception as e:
        print(f"[ERROR] Failed to initialize scheduler: {e}")
        sys.exit(1)

    if args.status:
        status = scheduler.get_status()
        import json
        print(json.dumps(status, indent=2, default=str))
    elif args.run_once:
        result = scheduler.run_once()
        print(f"Run complete: {result.get('final_count', 0)} jobs, {result.get('dispatch_summary', {}).get('sent', 0)} alerts sent")
    elif args.daemon:
        scheduler.start_daemon()
    else:
        parser.print_help()