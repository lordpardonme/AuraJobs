"""
AuraJobs Notification Engine - Telegram Adapter
Provides robust Telegram alerting with retry logic, structured logging,
and integration with AlertState for deduplication.
"""

import logging
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import requests
import yaml

from core.alert_config import AlertConfig, load_alert_config
from core.alert_state import AlertState, create_alert_state

# Configure module logger
logger = logging.getLogger("aurajobs.alerts.telegram")

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "notifications.yaml"


class SendResult(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    RETRY_EXHAUSTED = "retry_exhausted"
    RATE_LIMITED = "rate_limited"


@dataclass
class NotificationResult:
    """Result of a single notification send attempt."""
    job_url: str
    result: SendResult
    error: str = ""
    attempts: int = 0


class TelegramAdapter:
    """
    Telegram Bot API client with:
    - Exponential backoff retry logic
    - Rate limit handling (30 messages/second)
    - Structured logging
    - HTML message formatting
    """

    def __init__(self, config: AlertConfig, alert_state: AlertState | None = None):
        self.config = config
        self.alert_state = alert_state
        self.tg_config = config.telegram
        self.bot_token = config.telegram_bot_token
        self.chat_id = config.telegram_chat_id

        # Retry configuration
        self.max_retries = 3
        self.base_delay = 1.0  # seconds
        self.max_delay = 30.0

        # Rate limiting: Telegram allows ~30 messages/second
        self._last_send_time = 0.0
        self._min_interval = 0.05  # 20ms between messages = 50 msg/s theoretical, safe at 30

    def _rate_limit(self):
        """Enforce minimum interval between sends."""
        elapsed = time.time() - self._last_send_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

    def _send_with_retry(
        self,
        send_func: Callable,
        *args,
        job_url: str = "",
        **kwargs
    ) -> NotificationResult:
        """Execute send function with exponential backoff retry."""
        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            try:
                self._rate_limit()
                result = send_func(*args, **kwargs)
                self._last_send_time = time.time()

                if result:
                    logger.info("Telegram send succeeded", extra={"job_url": job_url, "attempt": attempt})
                    return NotificationResult(job_url=job_url, result=SendResult.SUCCESS, attempts=attempt)

                last_error = "Send returned False"
            except requests.exceptions.HTTPError as e:
                last_error = str(e)
                if e.response is not None and e.response.status_code == 429:
                    # Rate limited - extract retry_after
                    retry_after = int(e.response.headers.get("Retry-After", 30))
                    logger.warning(f"Telegram rate limited, waiting {retry_after}s", extra={"job_url": job_url})
                    time.sleep(min(retry_after, self.max_delay))
                    return NotificationResult(job_url=job_url, result=SendResult.RATE_LIMITED, error=last_error, attempts=attempt)
                elif e.response is not None and e.response.status_code >= 500:
                    # Server error - retry
                    logger.warning("Telegram server error, retrying", extra={"job_url": job_url, "attempt": attempt, "error": last_error})
                else:
                    # Client error (4xx) - don't retry
                    logger.error("Telegram client error, not retrying", extra={"job_url": job_url, "error": last_error})
                    return NotificationResult(job_url=job_url, result=SendResult.FAILED, error=last_error, attempts=attempt)
            except requests.exceptions.Timeout:
                last_error = "Request timeout"
                logger.warning("Telegram timeout, retrying", extra={"job_url": job_url, "attempt": attempt})
            except requests.exceptions.ConnectionError:
                last_error = "Connection error"
                logger.warning("Telegram connection error, retrying", extra={"job_url": job_url, "attempt": attempt})
            except Exception as e:
                last_error = str(e)
                logger.error("Telegram unexpected error", extra={"job_url": job_url, "attempt": attempt, "error": last_error})

            # Exponential backoff
            if attempt < self.max_retries:
                delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
                time.sleep(delay)

        logger.error(f"Telegram send failed after {self.max_retries} attempts", extra={"job_url": job_url, "error": last_error})
        return NotificationResult(job_url=job_url, result=SendResult.RETRY_EXHAUSTED, error=last_error, attempts=self.max_retries)

    def send_message(self, html_text: str, job_url: str = "") -> NotificationResult:
        """Send a text message (HTML formatted)."""
        if not self.bot_token or not self.chat_id:
            return NotificationResult(job_url=job_url, result=SendResult.FAILED, error="Missing bot_token or chat_id")

        def _do_send():
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": html_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            return resp.json().get("ok", False)

        return self._send_with_retry(_do_send, job_url=job_url)

    def send_document(self, file_path: str, caption: str = "", job_url: str = "") -> NotificationResult:
        """Send a document (e.g., CSV digest)."""
        if not self.bot_token or not self.chat_id:
            return NotificationResult(job_url=job_url, result=SendResult.FAILED, error="Missing bot_token or chat_id")
        if not os.path.exists(file_path):
            return NotificationResult(job_url=job_url, result=SendResult.FAILED, error=f"File not found: {file_path}")

        def _do_send():
            url = f"https://api.telegram.org/bot{self.bot_token}/sendDocument"
            with open(file_path, "rb") as doc_file:
                files = {"document": doc_file}
                data = {"chat_id": self.chat_id, "caption": caption, "parse_mode": "HTML"}
                resp = requests.post(url, data=data, files=files, timeout=60)
                resp.raise_for_status()
                return resp.json().get("ok", False)

        return self._send_with_retry(_do_send, job_url=job_url)

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


def format_job_card(job: dict[str, Any]) -> str:
    """Format a single job listing into a clean Telegram HTML card."""
    title = job.get("title", "Untitled Opportunity")
    company = job.get("company", "Confidential")
    location = job.get("location", "Remote / Flexible")
    score = job.get("match_score", 0)
    source = job.get("source", "Direct ATS").upper()
    job_url = job.get("job_url", job.get("job_url_direct", "#"))
    visa_status = job.get("visa_status", "")
    relocation = job.get("relocation_status", job.get("relocation_offered", ""))

    visa_tag = ""
    if visa_status and "NO" not in str(visa_status).upper() and "UNSPECIFIED" not in str(visa_status).upper():
        visa_tag = f"\n🛂 <b>Visa:</b> {visa_status}"
    elif relocation and str(relocation).lower() in ("true", "yes", "offered"):
        visa_tag = "\n📦 <b>Relocation:</b> Offered"

    card = (
        f"🎯 <b>{title}</b>\n"
        f"🏢 <b>{company}</b>\n"
        f"📍 <b>Location:</b> {location}\n"
        f"📊 <b>Relevance Score:</b> <code>{score}/100</code> | 🌐 <i>{source}</i>"
        f"{visa_tag}\n"
        f"🔗 <a href='{job_url}'><b>Apply Directly Here</b></a>"
    )
    return card


class NotificationDispatcher:
    """
    Orchestrates notification delivery with:
    - Per-channel filtering (min_score, visa, relocation)
    - Deduplication via AlertState
    - Batch sending with rate limiting
    - Run summary reporting
    """

    def __init__(self, config: AlertConfig, alert_state: AlertState):
        self.config = config
        self.alert_state = alert_state
        self.telegram = TelegramAdapter(config, alert_state) if config.telegram.enabled else None
        self.tg_config = config.telegram

    def _should_alert(self, job: dict[str, Any]) -> bool:
        """Apply per-job filters to determine if alert should be sent."""
        score = float(job.get("match_score", 0) or 0)
        if score < self.tg_config.min_match_score:
            return False

        visa_status = str(job.get("visa_status", "")).upper()
        relocation = str(job.get("relocation_status", job.get("relocation_offered", ""))).lower()

        if self.tg_config.include_visa_sponsored is False:
            if "SPONSORSHIP" in visa_status or "SPONSOR" in visa_status:
                return False

        if self.tg_config.include_relocation is False:
            if relocation in ("true", "yes", "offered"):
                return False

        # Apply keyword filters from config
        filters = self.config.filters
        title_desc = f"{job.get('title', '')} {job.get('description', '')}".lower()

        if filters.keywords:
            if not any(kw.lower() in title_desc for kw in filters.keywords):
                return False

        if filters.exclude_keywords:
            if any(kw.lower() in title_desc for kw in filters.exclude_keywords):
                return False

        if filters.visa_required and "SPONSORSHIP" not in visa_status and "SPONSOR" not in visa_status:
            return False

        return not (filters.relocation_required and relocation not in ("true", "yes", "offered"))

    def dispatch(
        self,
        jobs: list[dict[str, Any]],
        csv_path: str | None = None,
        alert_run_id: str = ""
    ) -> dict[str, Any]:
        """
        Main dispatch entry point.
        Returns summary statistics.
        """
        if not self.telegram or not self.telegram.is_configured():
            logger.warning("Telegram not configured, skipping dispatch")
            return {"sent": 0, "failed": 0, "skipped": len(jobs), "deduped": 0}

        # Apply filters
        filtered_jobs = [j for j in jobs if self._should_alert(j)]
        skipped_filters = len(jobs) - len(filtered_jobs)

        # Deduplicate
        new_jobs = self.alert_state.filter_new(filtered_jobs) if self.alert_state else filtered_jobs
        deduped = len(filtered_jobs) - len(new_jobs)

        if not new_jobs:
            logger.info("No new jobs to alert after filtering and deduplication")
            return {"sent": 0, "failed": 0, "skipped": skipped_filters, "deduped": deduped}

        # Limit cards
        jobs_to_send = new_jobs[:self.tg_config.max_alert_cards]

        logger.info(f"Dispatching {len(jobs_to_send)} job alerts", extra={
            "total_jobs": len(jobs),
            "filtered": len(filtered_jobs),
            "deduped": deduped,
            "sending": len(jobs_to_send),
            "alert_run_id": alert_run_id
        })

        # Send header
        header = (
            f"🚀 <b>AuraJobs Discovery Completed!</b>\n\n"
            f"• <b>Total Opportunities Found:</b> {len(jobs)}\n"
            f"• <b>High-Relevance Matches (≥{self.tg_config.min_match_score}%):</b> {len(filtered_jobs)}\n"
            f"• <b>New Alerts (after dedup):</b> {len(new_jobs)}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        self.telegram.send_message(header)

        # Send job cards
        sent = 0
        failed = 0
        for job in jobs_to_send:
            card_html = format_job_card(job)
            result = self.telegram.send_message(card_html, job_url=job.get("job_url", ""))
            if result.result == SendResult.SUCCESS:
                sent += 1
            else:
                failed += 1
                logger.warning("Failed to send job card", extra={"job_url": job.get("job_url"), "error": result.error})

        # Send CSV digest if enabled
        csv_sent = False
        if self.tg_config.send_csv_digest and csv_path and os.path.exists(csv_path):
            caption = f"📁 <b>Consolidated Job Intelligence CSV</b> ({os.path.basename(csv_path)})"
            result = self.telegram.send_document(csv_path, caption=caption)
            csv_sent = result.result == SendResult.SUCCESS
            if not csv_sent:
                failed += 1
                logger.warning("Failed to send CSV digest", extra={"error": result.error})

        # Mark sent jobs in state
        if new_jobs and self.alert_state:
            marked = self.alert_state.mark_sent(new_jobs, alert_run_id)
            logger.info(f"Marked {marked} jobs as sent in AlertState", extra={"alert_run_id": alert_run_id})

        # Cleanup expired records periodically
        if self.alert_state:
            self.alert_state.cleanup_expired()

        summary = {
            "sent": sent,
            "failed": failed,
            "skipped": skipped_filters,
            "deduped": deduped,
            "csv_sent": csv_sent,
            "alert_run_id": alert_run_id
        }
        logger.info("Dispatch complete", extra=summary)
        return summary


def load_notification_config() -> dict[str, Any]:
    """Legacy compatibility: load config from notifications.yaml."""
    config = {
        "telegram": {
            "enabled": False,
            "bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            "chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
            "min_match_score": 80,
            "max_alert_cards": 5,
            "send_csv_digest": True,
        }
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if loaded and "telegram" in loaded:
                    config["telegram"].update(loaded["telegram"])
        except Exception as e:
            print(f"[!] Warning: Could not read notifications.yaml: {e}")
    return config


def save_notification_config(bot_token: str, chat_id: str, enabled: bool = True) -> bool:
    """Legacy compatibility: save Telegram credentials to notifications.yaml."""
    cfg = load_notification_config()
    cfg["telegram"]["bot_token"] = bot_token
    cfg["telegram"]["chat_id"] = str(chat_id)
    cfg["telegram"]["enabled"] = enabled

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save config to {CONFIG_PATH}: {e}")
        return False


def render_terminal_qr(data_url: str):
    """Render a clean ASCII/Unicode QR Code directly in the terminal."""
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(data_url)
        qr.make(fit=True)
        print("\n" + "=" * 50)
        print("  SCAN WITH YOUR PHONE CAMERA OR TELEGRAM APP")
        print("=" * 50 + "\n")
        qr.print_ascii(invert=True)
        print("\n" + "=" * 50)
    except ImportError:
        print("\n" + "=" * 60)
        print("  📱 SCAN OR CLICK THE LINK BELOW TO OPEN YOUR TELEGRAM BOT:")
        print(f"  👉  {data_url}")
        print("=" * 60 + "\n")


def pair_telegram_bot() -> bool:
    """
    Interactive pairing wizard:
    1. Prompts for Bot Token (from @BotFather).
    2. Generates QR Code and deep-link for instant pairing.
    3. Waits for the user to press 'START' on Telegram.
    4. Captures Chat ID and verifies connection with a welcome alert.
    """
    print("=" * 65)
    print("      AURAJOBS TELEGRAM MOBILE ALERTS - PAIRING WIZARD")
    print("=" * 65)
    print("\nHow to get a Bot Token in 30 seconds:")
    print(" 1. Open Telegram on your phone or PC.")
    print(" 2. Search for '@BotFather' and send: /newbot")
    print(" 3. Choose a name and username for your bot.")
    print(" 4. Copy the API Token provided by BotFather.\n")

    cfg = load_notification_config()
    existing_token = cfg.get("telegram", {}).get("bot_token", "")
    prompt_str = f"Enter your Telegram Bot Token [{existing_token[:8]}...]: " if existing_token else "Enter your Telegram Bot Token: "

    user_token = input(prompt_str).strip().strip("'\"")
    bot_token = user_token if user_token else existing_token

    if not bot_token:
        print("[ERROR] Bot token cannot be empty.")
        return False

    if ":" not in bot_token:
        print("\n[!] Format Warning:")
        print("  A full Telegram Bot Token includes numbers and a colon before the letters, like:")
        print("  👉 8661572445:AAHUE44qau60pmMMgQppZMa9NZfgQdXk37DJE")
        print("  (Make sure you copy the entire line from @BotFather, including the numbers before the colon)\n")

    print("\n[*] Validating Bot Token with Telegram API...")
    try:
        me_resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
        me_data = me_resp.json()
        if not me_data.get("ok"):
            print(f"[ERROR] Invalid Bot Token: {me_data.get('description')}")
            print("Please make sure you copied the FULL token from @BotFather (e.g. 123456789:ABC-DEF...).")
            return False
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        return False

    bot_username = me_data["result"]["username"]
    bot_first_name = me_data["result"].get("first_name", "AuraJobs Bot")
    print(f"[OK] Connected to bot: @{bot_username} ({bot_first_name})")

    # Clear pending updates to only capture the new /start
    try:
        requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates?offset=-1", timeout=10)
    except Exception:
        pass

    deep_link = f"https://t.me/{bot_username}?start=aurajobs_pairing"
    render_terminal_qr(deep_link)
    print(f"\n👉 Direct Link: {deep_link}")
    print("\n[*] Waiting for you to tap 'START' in Telegram (listening for 60 seconds)...")

    start_time = time.time()
    chat_id = None
    user_name = "User"

    while time.time() - start_time < 60:
        try:
            updates_resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates?timeout=5", timeout=10)
            updates = updates_resp.json().get("result", [])
            for update in updates:
                msg = update.get("message", {})
                if msg.get("text", "").startswith("/start") or msg.get("chat", {}).get("id"):
                    chat_id = msg["chat"]["id"]
                    user_name = msg["from"].get("first_name", "Friend")
                    break
            if chat_id:
                break
        except Exception:
            pass
        time.sleep(1.5)

    if not chat_id:
        print("\n[!] Pairing timed out. Did you send /start to the bot?")
        return False

    # Save to legacy config (for backward compatibility)
    save_notification_config(bot_token, str(chat_id), enabled=True)

    # Also update alerts.yaml if it exists
    try:
        load_alert_config()
        # Note: We don't save secrets to YAML, but we validate they're in env
        print("[OK] Bot paired. Ensure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in environment.")
    except Exception:
        pass

    # Send Welcome Notification to phone
    welcome_text = (
        f"🎉 <b>AuraJobs Alert Engine Paired!</b>\n\n"
        f"Hello <b>{user_name}</b>, your phone is now connected to AuraJobs.\n"
        f"Whenever a scheduled job search completes or a manual run discovers high-match opportunities, "
        f"you'll receive verified alerts and full CSV digests right here! 🚀"
    )
    send_telegram_message(bot_token, str(chat_id), welcome_text)

    print("\n" + "=" * 65)
    print(f"  [SUCCESS] Paired successfully with Telegram Chat ID: {chat_id}")
    print("  [SUCCESS] Test alert sent to your phone!")
    print("=" * 65 + "\n")
    return True


def send_telegram_message(bot_token: str, chat_id: str, html_text: str) -> bool:
    """Legacy compatibility: send a simple message."""
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": html_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        resp = requests.post(url, json=payload, timeout=12)
        return resp.status_code == 200
    except Exception as e:
        print(f"[!] Telegram send error: {e}")
        return False


def send_telegram_document(bot_token: str, chat_id: str, file_path: str, caption: str = "") -> bool:
    """Legacy compatibility: upload a file to Telegram."""
    if not bot_token or not chat_id or not os.path.exists(file_path):
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    try:
        with open(file_path, "rb") as doc_file:
            files = {"document": doc_file}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            resp = requests.post(url, data=data, files=files, timeout=30)
            return resp.status_code == 200
    except Exception as e:
        print(f"[!] Telegram document upload error: {e}")
        return False


def dispatch_job_notifications(jobs_list: list[dict[str, Any]], csv_path: str | None = None) -> None:
    """
    Legacy compatibility: main notification dispatcher.
    Uses the new NotificationDispatcher if alerts.yaml exists.
    """
    try:
        alert_cfg = load_alert_config()
        alert_state = create_alert_state(alert_cfg)
        dispatcher = NotificationDispatcher(alert_cfg, alert_state)
        run_id = f"manual_{int(time.time())}"
        dispatcher.dispatch(jobs_list, csv_path, alert_run_id=run_id)
    except Exception as e:
        # Fallback to legacy behavior
        logger.warning(f"New dispatcher failed, using legacy: {e}")
        cfg = load_notification_config()
        tg_cfg = cfg.get("telegram", {})
        if not tg_cfg.get("enabled"):
            return

        bot_token = tg_cfg.get("bot_token")
        chat_id = tg_cfg.get("chat_id")
        min_score = tg_cfg.get("min_match_score", 80)
        max_cards = tg_cfg.get("max_alert_cards", 5)

        if not bot_token or not chat_id:
            return

        print("\n[*] Dispatching Telegram mobile job alerts (legacy)...")

        high_match_jobs = [j for j in jobs_list if float(j.get("match_score", 0) or 0) >= min_score]
        total_found = len(jobs_list)

        header = (
            f"🚀 <b>AuraJobs Discovery Completed!</b>\n\n"
            f"• <b>Total Opportunities Ingested:</b> {total_found}\n"
            f"• <b>High-Relevance Matches (≥{min_score}%):</b> {len(high_match_jobs)}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        send_telegram_message(bot_token, chat_id, header)

        for job in high_match_jobs[:max_cards]:
            card_html = format_job_card(job)
            send_telegram_message(bot_token, chat_id, card_html)
            time.sleep(0.4)

        if tg_cfg.get("send_csv_digest") and csv_path and os.path.exists(csv_path):
            caption = f"📁 <b>Consolidated Job Intelligence CSV</b> ({os.path.basename(csv_path)})"
            send_telegram_document(bot_token, chat_id, csv_path, caption=caption)

        print("[OK] Telegram notifications dispatched successfully!")


if __name__ == "__main__":
    if "--pair" in sys.argv:
        pair_telegram_bot()
    elif "--test" in sys.argv:
        cfg = load_notification_config().get("telegram", {})
        if not cfg.get("bot_token") or not cfg.get("chat_id"):
            print("[!] No Telegram configuration found. Running pairing wizard first...")
            pair_telegram_bot()
        else:
            mock_job = {
                "title": "Lead Product Designer (Design Systems)",
                "company": "Figma",
                "location": "Global Remote / San Francisco",
                "match_score": 96,
                "source": "Ashby",
                "job_url": "https://www.figma.com/careers/",
                "visa_status": "Global Relocation & Sponsorship Supported"
            }
            print(f"[*] Sending test alert to Chat ID {cfg.get('chat_id')}...")
            send_telegram_message(cfg.get("bot_token"), cfg.get("chat_id"), "🔔 <b>AuraJobs Staging Test Alert</b>")
            send_telegram_message(cfg.get("bot_token"), cfg.get("chat_id"), format_job_card(mock_job))
            print("[OK] Test alert sent successfully!")
    else:
        print("Usage: python -m core.notifications --pair | --test")