import os
import json
import pandas as pd
from datetime import datetime

class CheckpointManager:
    """
    Saves and restores runtime state and collected jobs, allowing interrupted runs
    (Ctrl+C, rate limits, or crashes) to resume without repeating work.
    """

    def __init__(self, checkpoint_dir: str = None):
        if checkpoint_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            checkpoint_dir = os.path.join(base_dir, "checkpoints")

        self.checkpoint_dir = checkpoint_dir
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        self.state_file = os.path.join(self.checkpoint_dir, "latest_state.json")
        self.data_file = os.path.join(self.checkpoint_dir, "latest_raw_jobs.csv")

    def save(self, raw_df: pd.DataFrame, search_count: int, completed_keys: set, session_id: str):
        state = {
            "session_id": session_id,
            "search_count": search_count,
            "updated_at": datetime.now().isoformat(),
            "completed_keys": list(completed_keys),
            "raw_count": len(raw_df) if raw_df is not None else 0
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

        if raw_df is not None and not raw_df.empty:
            raw_df.to_csv(self.data_file, index=False, encoding="utf-8-sig")

    def load(self) -> tuple:
        """Loads state and DataFrame if checkpoint exists. Returns (state_dict, raw_df)."""
        if not os.path.exists(self.state_file):
            return None, pd.DataFrame()

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)

            raw_df = pd.DataFrame()
            if os.path.exists(self.data_file):
                raw_df = pd.read_csv(self.data_file)

            return state, raw_df
        except Exception as e:
            print(f"  [WARN] Failed to load checkpoint: {e}")
            return None, pd.DataFrame()

    def clear(self):
        """Cleans up checkpoint files after a run successfully completes."""
        if os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
            except Exception:
                pass
        if os.path.exists(self.data_file):
            try:
                os.remove(self.data_file)
            except Exception:
                pass
