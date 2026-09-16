"""
Unit Tests for AuraJobs Daily Alerts Feature
Tests alert_config, alert_state, notifications, alert_scheduler, and pipeline.
"""

import os
import sys
import tempfile
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.alert_config import (
    AlertConfig, ScheduleConfig, TelegramConfig, FiltersConfig,
    DeduplicationConfig, LoggingConfig, load_alert_config, save_alert_config
)
from core.alert_state import AlertState, create_alert_state
from core.notifications import (
    TelegramAdapter, NotificationDispatcher, NotificationResult, SendResult,
    format_job_card, pair_telegram_bot
)
from core.pipeline import run_search_pipeline, process_results
from core.alert_scheduler import AlertScheduler


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def sample_alert_config(temp_dir):
    """Create a sample AlertConfig for testing."""
    config = AlertConfig()
    config.schedule.cron = "0 8 * * *"
    config.schedule.timezone = "UTC"
    config.telegram.enabled = True
    config.telegram.min_match_score = 75
    config.telegram.max_alert_cards = 5
    config.telegram.send_csv_digest = True
    config.filters.regions = ["Global"]
    config.filters.visa_required = False
    config.deduplication.enabled = True
    config.deduplication.ttl_days = 30
    config.deduplication.store_type = "sqlite"
    config.deduplication.db_path = str(temp_dir / "test_alert_state.db")
    config.logging.level = "DEBUG"
    config.logging.file_path = str(temp_dir / "test_alerts.log")
    config.telegram_bot_token = "123456789:TEST_TOKEN"
    config.telegram_chat_id = "987654321"
    return config


@pytest.fixture
def sample_jobs():
    """Sample job data for testing."""
    return [
        {
            "id": "job_1",
            "job_url": "https://example.com/job/1",
            "title": "Senior Software Engineer",
            "company": "TechCorp",
            "location": "San Francisco, CA",
            "match_score": 90,
            "source": "ashby",
            "visa_status": "EXPLICIT_SPONSORSHIP",
            "relocation_status": True,
            "description": "We are looking for a senior engineer...",
        },
        {
            "id": "job_2",
            "job_url": "https://example.com/job/2",
            "title": "Product Designer",
            "company": "DesignCo",
            "location": "New York, NY",
            "match_score": 85,
            "source": "greenhouse",
            "visa_status": "UNSPECIFIED",
            "relocation_status": False,
            "description": "Join our design team...",
        },
        {
            "id": "job_3",
            "job_url": "https://example.com/job/3",
            "title": "Junior Developer",
            "company": "StartupInc",
            "location": "Remote",
            "match_score": 60,
            "source": "linkedin",
            "visa_status": "NO_SPONSORSHIP",
            "relocation_status": False,
            "description": "Entry level position...",
        },
    ]


# ============================================================
# AlertConfig Tests
# ============================================================

class TestAlertConfig:
    def test_default_config(self):
        config = AlertConfig()
        assert config.schedule.cron == "0 8 * * *"
        assert config.telegram.enabled is True
        assert config.telegram.min_match_score == 75
        assert config.deduplication.store_type == "sqlite"

    def test_cron_validation_valid(self):
        config = ScheduleConfig(cron="0 8 * * *")
        assert config.cron == "0 8 * * *"

        config = ScheduleConfig(cron="0 0 1 1 *")  # 6 fields
        assert config.cron == "0 0 1 1 *"

    def test_cron_validation_invalid(self):
        with pytest.raises(ValueError):
            ScheduleConfig(cron="0 8 * *")  # 4 fields

        with pytest.raises(ValueError):
            ScheduleConfig(cron="invalid cron expression")

    def test_telegram_config_bounds(self):
        with pytest.raises(ValueError):
            TelegramConfig(min_match_score=101)
        with pytest.raises(ValueError):
            TelegramConfig(min_match_score=-1)
        with pytest.raises(ValueError):
            TelegramConfig(max_alert_cards=0)
        with pytest.raises(ValueError):
            TelegramConfig(max_alert_cards=21)

    def test_filters_region_validation(self):
        with pytest.raises(ValueError):
            FiltersConfig(regions=["InvalidRegion"])

        # Valid
        config = FiltersConfig(regions=["India", "Global"])
        assert config.regions == ["India", "Global"]

    def test_filters_seniority_validation(self):
        with pytest.raises(ValueError):
            FiltersConfig(seniority=["InvalidLevel"])

        config = FiltersConfig(seniority=["Senior", "Lead"])
        assert config.seniority == ["Senior", "Lead"]

    def test_dedup_store_type_validation(self):
        with pytest.raises(ValueError):
            DeduplicationConfig(store_type="invalid")

        config = DeduplicationConfig(store_type="json")
        assert config.store_type == "json"

    def test_logging_level_validation(self):
        with pytest.raises(ValueError):
            LoggingConfig(level="INVALID")

        config = LoggingConfig(level="debug")
        assert config.level == "DEBUG"

    def test_load_secrets_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env_token_123")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "env_chat_456")

        config = AlertConfig()
        config.load_secrets_from_env()

        assert config.telegram_bot_token == "env_token_123"
        assert config.telegram_chat_id == "env_chat_456"

    def test_validate_secrets_missing(self):
        config = AlertConfig()
        config.telegram.enabled = True
        config.telegram_bot_token = ""
        config.telegram_chat_id = ""

        missing = config.validate_secrets()
        assert "TELEGRAM_BOT_TOKEN" in missing
        assert "TELEGRAM_CHAT_ID" in missing

    def test_validate_secrets_present(self):
        config = AlertConfig()
        config.telegram.enabled = True
        config.telegram_bot_token = "token"
        config.telegram_chat_id = "chat"

        missing = config.validate_secrets()
        assert missing == []

    def test_validate_secrets_disabled(self):
        config = AlertConfig()
        config.telegram.enabled = False
        config.telegram_bot_token = ""
        config.telegram_chat_id = ""

        missing = config.validate_secrets()
        assert missing == []


class TestConfigPersistence:
    def test_save_and_load_config(self, temp_dir):
        config_path = temp_dir / "test_alerts.yaml"
        config = AlertConfig()
        config.schedule.cron = "0 9 * * 1-5"
        config.telegram.min_match_score = 80

        # Save
        assert save_alert_config(config, str(config_path))

        # Load
        loaded = load_alert_config(str(config_path))
        assert loaded.schedule.cron == "0 9 * * 1-5"
        assert loaded.telegram.min_match_score == 80

    def test_load_nonexistent_config(self, temp_dir):
        with pytest.raises(FileNotFoundError):
            load_alert_config(str(temp_dir / "nonexistent.yaml"))


# ============================================================
# AlertState Tests
# ============================================================

class TestAlertStateSQLite:
    def test_init_creates_db(self, temp_dir):
        db_path = temp_dir / "test_state.db"
        state = AlertState(db_path=str(db_path), store_type="sqlite")
        assert db_path.exists()
        state.close()

    def test_contains_empty(self, temp_dir):
        db_path = temp_dir / "test.db"
        state = AlertState(db_path=str(db_path), store_type="sqlite")
        assert state.contains("https://example.com/job/1") is False
        state.close()

    def test_mark_sent_and_contains(self, temp_dir):
        db_path = temp_dir / "test.db"
        state = AlertState(db_path=str(db_path), store_type="sqlite")
        jobs = [{"job_url": "https://example.com/job/1", "title": "Engineer", "company": "Acme", "match_score": 90, "id": "1"}]
        added = state.mark_sent(jobs, "run_1")
        assert added == 1
        assert state.contains("https://example.com/job/1") is True
        state.close()

    def test_filter_new(self, temp_dir):
        db_path = temp_dir / "test.db"
        state = AlertState(db_path=str(db_path), store_type="sqlite")
        jobs = [
            {"job_url": "https://example.com/job/1", "title": "Engineer", "match_score": 90},
            {"job_url": "https://example.com/job/2", "title": "Designer", "match_score": 85},
        ]
        state.mark_sent(jobs[:1], "run_1")

        new_jobs = state.filter_new(jobs)
        assert len(new_jobs) == 1
        assert new_jobs[0]["job_url"] == "https://example.com/job/2"
        state.close()

    def test_filter_new_no_url(self, temp_dir):
        db_path = temp_dir / "test.db"
        state = AlertState(db_path=str(db_path), store_type="sqlite")
        jobs = [{"title": "Engineer", "match_score": 90}]  # No job_url
        new_jobs = state.filter_new(jobs)
        assert len(new_jobs) == 1  # Conservative: include if no URL
        state.close()

    def test_cleanup_expired(self, temp_dir):
        db_path = temp_dir / "test.db"
        state = AlertState(db_path=str(db_path), store_type="sqlite", ttl_days=0)
        jobs = [{"job_url": "https://example.com/job/1", "title": "Engineer", "match_score": 90, "id": "1"}]
        state.mark_sent(jobs, "run_1")

        # Manually set old timestamp using the same connection pattern as AlertState
        import sqlite3
        conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            old_date = (datetime.now() - timedelta(days=1)).isoformat()
            conn.execute("UPDATE sent_jobs SET sent_at = ? WHERE job_url = ?", (old_date, "https://example.com/job/1"))
            conn.commit()
        finally:
            conn.close()

        removed = state.cleanup_expired()
        assert removed == 1
        assert state.contains("https://example.com/job/1") is False
        state.close()
        # Force garbage collection to release file handles on Windows
        import gc
        gc.collect()

    def test_get_stats(self, temp_dir):
        db_path = temp_dir / "test.db"
        state = AlertState(db_path=str(db_path), store_type="sqlite")
        jobs = [{"job_url": "https://example.com/job/1", "title": "Engineer", "match_score": 90, "id": "1"}]
        state.mark_sent(jobs, "run_1")

        stats = state.get_stats()
        assert stats["total_sent"] == 1
        assert stats["store_type"] == "sqlite"
        state.close()

    def test_get_recent_runs(self, temp_dir):
        db_path = temp_dir / "test.db"
        state = AlertState(db_path=str(db_path), store_type="sqlite")
        # Use different job URLs for different runs
        jobs1 = [{"job_url": "https://example.com/job/1", "title": "Engineer", "match_score": 90, "id": "1"}]
        jobs2 = [{"job_url": "https://example.com/job/2", "title": "Designer", "match_score": 85, "id": "2"}]
        state.mark_sent(jobs1, "run_1")
        time.sleep(0.01)  # Ensure different timestamps
        state.mark_sent(jobs2, "run_2")

        runs = state.get_recent_runs(5)
        assert len(runs) == 2
        # Most recent run should be first (run_2)
        assert runs[0]["alert_run_id"] == "run_2"
        state.close()


class TestAlertStateJSON:
    def test_json_backend(self, temp_dir):
        db_path = temp_dir / "test.db"
        state = AlertState(db_path=str(db_path), store_type="json", ttl_days=30)
        jobs = [{"job_url": "https://example.com/job/1", "title": "Engineer", "match_score": 90, "id": "1"}]
        added = state.mark_sent(jobs, "run_1")
        assert added == 1
        assert state.contains("https://example.com/job/1") is True

        new_jobs = state.filter_new(jobs)
        assert len(new_jobs) == 0
        state.close()


class TestCreateAlertState:
    def test_factory_function(self, sample_alert_config):
        state = create_alert_state(sample_alert_config)
        assert isinstance(state, AlertState)
        assert state.ttl_days == 30
        assert state.store_type == "sqlite"
        state.close()


# ============================================================
# Notifications Tests
# ============================================================

class TestFormatJobCard:
    def test_format_job_card_complete(self):
        job = {
            "title": "Senior Software Engineer",
            "company": "TechCorp",
            "location": "San Francisco, CA",
            "match_score": 90,
            "source": "ashby",
            "job_url": "https://example.com/job/1",
            "visa_status": "EXPLICIT_SPONSORSHIP",
            "relocation_status": True,
        }
        card = format_job_card(job)
        assert "Senior Software Engineer" in card
        assert "TechCorp" in card
        assert "San Francisco" in card
        assert "90/100" in card
        assert "ASHBY" in card
        assert "EXPLICIT_SPONSORSHIP" in card
        assert "Apply Directly Here" in card

    def test_format_job_card_no_visa(self):
        job = {
            "title": "Engineer",
            "company": "Co",
            "location": "Remote",
            "match_score": 80,
            "source": "linkedin",
            "job_url": "https://example.com/job/1",
            "visa_status": "NO_SPONSORSHIP",
            "relocation_status": False,
        }
        card = format_job_card(job)
        assert "Visa" not in card
        assert "Relocation" not in card


class TestTelegramAdapter:
    @pytest.fixture
    def adapter(self, sample_alert_config):
        state = create_alert_state(sample_alert_config)
        adapter = TelegramAdapter(sample_alert_config, state)
        yield adapter
        state.close()

    def test_is_configured(self, adapter):
        assert adapter.is_configured() is True

    def test_is_configured_missing_token(self, sample_alert_config):
        sample_alert_config.telegram_bot_token = ""
        state = create_alert_state(sample_alert_config)
        adapter = TelegramAdapter(sample_alert_config, state)
        assert adapter.is_configured() is False

    @patch("core.notifications.requests.post")
    def test_send_message_success(self, mock_post, adapter):
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = adapter.send_message("<b>Test</b>", job_url="https://example.com/job/1")

        assert result.result == SendResult.SUCCESS
        assert result.attempts == 1
        mock_post.assert_called_once()

    @patch("core.notifications.requests.post")
    def test_send_message_retry_on_timeout(self, mock_post, adapter):
        mock_post.side_effect = [
            requests.exceptions.Timeout(),
            Mock(json=lambda: {"ok": True}, raise_for_status=Mock())
        ]

        result = adapter.send_message("<b>Test</b>", job_url="https://example.com/job/1")

        assert result.result == SendResult.SUCCESS
        assert result.attempts == 2
        assert mock_post.call_count == 2

    @patch("core.notifications.requests.post")
    def test_send_message_rate_limited(self, mock_post, adapter):
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "5"}
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        result = adapter.send_message("<b>Test</b>", job_url="https://example.com/job/1")

        assert result.result == SendResult.RATE_LIMITED

    @patch("core.notifications.requests.post")
    def test_send_document_success(self, mock_post, adapter, temp_dir):
        # Create a dummy CSV file
        csv_path = temp_dir / "test.csv"
        csv_path.write_text("id,title\n1,Test\n")

        mock_response = Mock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        result = adapter.send_document(str(csv_path), caption="Test", job_url="https://example.com/job/1")

        assert result.result == SendResult.SUCCESS
        mock_post.assert_called_once()


class TestNotificationDispatcher:
    @pytest.fixture
    def dispatcher(self, sample_alert_config, sample_jobs):
        state = create_alert_state(sample_alert_config)
        dispatcher = NotificationDispatcher(sample_alert_config, state)
        yield dispatcher, sample_jobs
        state.close()

    def test_should_alert_min_score(self, dispatcher):
        dispatcher_obj, jobs = dispatcher
        # Job with score 90 should pass (min 75)
        assert dispatcher_obj._should_alert(jobs[0]) is True
        # Job with score 60 should fail (min 75)
        assert dispatcher_obj._should_alert(jobs[2]) is False

    def test_should_alert_visa_required(self, sample_alert_config):
        config = sample_alert_config
        config.filters.visa_required = True
        state = create_alert_state(config)
        dispatcher = NotificationDispatcher(config, state)

        job_with_visa = {"visa_status": "EXPLICIT_SPONSORSHIP", "match_score": 90, "title": "Eng", "company": "Co", "location": "Remote", "source": "ashby", "job_url": "https://x.com"}
        job_without_visa = {"visa_status": "UNSPECIFIED", "match_score": 90, "title": "Eng", "company": "Co", "location": "Remote", "source": "ashby", "job_url": "https://x.com"}

        assert dispatcher._should_alert(job_with_visa) is True
        assert dispatcher._should_alert(job_without_visa) is False

    def test_should_alert_keywords(self, sample_alert_config):
        config = sample_alert_config
        config.filters.keywords = ["python", "aws"]
        state = create_alert_state(config)
        dispatcher = NotificationDispatcher(config, state)

        job_match = {"title": "Python Engineer", "description": "AWS experience", "match_score": 90, "visa_status": "", "relocation_status": "", "company": "Co", "location": "Remote", "source": "ashby", "job_url": "https://x.com"}
        job_no_match = {"title": "Java Engineer", "description": "Spring boot", "match_score": 90, "visa_status": "", "relocation_status": "", "company": "Co", "location": "Remote", "source": "ashby", "job_url": "https://x.com"}

        assert dispatcher._should_alert(job_match) is True
        assert dispatcher._should_alert(job_no_match) is False

    def test_should_alert_exclude_keywords(self, sample_alert_config):
        config = sample_alert_config
        config.filters.exclude_keywords = ["intern", "junior"]
        state = create_alert_state(config)
        dispatcher = NotificationDispatcher(config, state)

        job_excluded = {"title": "Junior Engineer", "description": "Entry level", "match_score": 90, "visa_status": "", "relocation_status": "", "company": "Co", "location": "Remote", "source": "ashby", "job_url": "https://x.com"}
        job_ok = {"title": "Senior Engineer", "description": "Lead role", "match_score": 90, "visa_status": "", "relocation_status": "", "company": "Co", "location": "Remote", "source": "ashby", "job_url": "https://x.com"}

        assert dispatcher._should_alert(job_excluded) is False
        assert dispatcher._should_alert(job_ok) is True

    @patch("core.notifications.TelegramAdapter.send_message")
    @patch("core.notifications.TelegramAdapter.send_document")
    def test_dispatch_integration(self, mock_send_doc, mock_send_msg, dispatcher, sample_alert_config):
        dispatcher_obj, jobs = dispatcher
        # Mock successful sends
        mock_send_msg.return_value = NotificationResult(job_url="", result=SendResult.SUCCESS)
        mock_send_doc.return_value = NotificationResult(job_url="", result=SendResult.SUCCESS)

        result = dispatcher_obj.dispatch(jobs, csv_path=None, alert_run_id="test_run")

        assert result["sent"] == 2  # Two jobs above min_score (75)
        assert result["deduped"] == 0
        assert result["skipped"] == 1  # One job below min_score (60)
        assert mock_send_msg.call_count >= 2  # Header + job cards


# ============================================================
# Pipeline Tests
# ============================================================

class TestPipeline:
    def test_process_results_empty(self):
        import pandas as pd
        from core.classifier import RoleClassifier
        from core.scorer import MatchScorer

        df = pd.DataFrame()
        profile = {"target_role": "Engineer", "seniority": "Senior", "skills": ["Python"]}
        classifier = RoleClassifier(positive_terms=["engineer"], negative_terms=["intern"])
        scorer = MatchScorer(target_role="Engineer", skills=["Python"], seniority="Senior")

        result = process_results(df, profile, scorer, classifier, 72)
        assert result.empty

    def test_process_results_with_data(self):
        import pandas as pd
        from core.classifier import RoleClassifier
        from core.scorer import MatchScorer

        df = pd.DataFrame([{
            "title": "Senior Software Engineer",
            "company": "TechCorp",
            "location": "San Francisco, CA",
            "job_url": "https://example.com/job/1",
            "source": "ashby",
            "description": "Python, AWS, Kubernetes",
            "date_posted": datetime.now().isoformat(),
        }])

        profile = {"target_role": "Software Engineer", "seniority": "Senior", "skills": ["Python", "AWS"]}
        classifier = RoleClassifier(positive_terms=["software", "engineer"], negative_terms=["intern"])
        scorer = MatchScorer(target_role="Software Engineer", skills=["Python", "AWS"], seniority="Senior")

        result = process_results(df, profile, scorer, classifier, 72)

        assert not result.empty
        assert "match_score" in result.columns
        assert "priority" in result.columns
        assert "visa_status" in result.columns
        assert "match_type" in result.columns


# ============================================================
# AlertScheduler Tests
# ============================================================

class TestAlertScheduler:
    @patch("core.alert_scheduler.run_search_pipeline")
    @patch("core.alert_scheduler.NotificationDispatcher.dispatch")
    def test_run_once(self, mock_dispatch, mock_pipeline, sample_alert_config, sample_jobs):
        import pandas as pd

        # Mock pipeline return
        mock_pipeline.return_value = (
            pd.DataFrame(sample_jobs),
            {
                "final_count": 3,
                "output_file": "/tmp/test.csv",
                "source_counts": {},
                "session_id": "test",
            }
        )

        # Mock dispatch return
        mock_dispatch.return_value = {
            "sent": 2,
            "failed": 0,
            "skipped": 1,
            "deduped": 0,
            "csv_sent": False,
            "alert_run_id": "test_run"
        }

        scheduler = AlertScheduler(sample_alert_config)
        result = scheduler.run_once()

        assert result["run_id"].startswith("scheduled_")
        assert result["final_count"] == 3
        assert result["dispatch_summary"]["sent"] == 2
        mock_pipeline.assert_called_once()
        mock_dispatch.assert_called_once()
        # Cleanup
        if scheduler._log_file_handler:
            from core.alert_scheduler import teardown_logging
            teardown_logging(scheduler._log_file_handler)

    def test_get_status(self, sample_alert_config):
        scheduler = AlertScheduler(sample_alert_config)
        status = scheduler.get_status()

        assert "running" in status
        assert "schedule" in status
        assert "alert_state" in status
        assert status["schedule"] == "0 8 * * *"
        # Cleanup
        if scheduler._log_file_handler:
            from core.alert_scheduler import teardown_logging
            teardown_logging(scheduler._log_file_handler)


# ============================================================
# Integration Test (Full Flow Mocked)
# ============================================================

class TestIntegration:
    @patch("core.alert_scheduler.run_search_pipeline")
    @patch("core.notifications.TelegramAdapter.send_message")
    @patch("core.notifications.TelegramAdapter.send_document")
    def test_full_scheduled_run(
        self, mock_send_doc, mock_send_msg, mock_pipeline,
        sample_alert_config, sample_jobs, temp_dir
    ):
        import pandas as pd

        # Create a dummy CSV file
        csv_path = temp_dir / "test.csv"
        csv_path.write_text("id,title\n1,Test\n")

        # Setup mocks
        mock_pipeline.return_value = (
            pd.DataFrame(sample_jobs),
            {
                "final_count": 3,
                "output_file": str(csv_path),
                "source_counts": {"ashby": 1, "greenhouse": 1, "linkedin": 1},
                "session_id": "test_session",
            }
        )
        mock_send_msg.return_value = NotificationResult(job_url="", result=SendResult.SUCCESS)
        mock_send_doc.return_value = NotificationResult(job_url="", result=SendResult.SUCCESS)

        # Create scheduler and run
        scheduler = AlertScheduler(sample_alert_config)
        result = scheduler.run_once()

        # Verify
        assert result["final_count"] == 3
        assert result["dispatch_summary"]["sent"] == 2  # 2 jobs >= 75 score
        assert result["dispatch_summary"]["skipped"] == 1  # 1 job < 75 score
        assert mock_send_msg.call_count >= 3  # Header + 2 job cards
        mock_send_doc.assert_called_once()  # CSV sent

        # Cleanup
        if scheduler._log_file_handler:
            from core.alert_scheduler import teardown_logging
            teardown_logging(scheduler._log_file_handler)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])