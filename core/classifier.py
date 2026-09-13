import re
import pandas as pd

def norm_text(val):
    if val is None or pd.isna(val):
        return ""
    return re.sub(r"\s+", " ", str(val).lower()).strip()

class RoleClassifier:
    """
    Title-led role classifier enforcing positive inclusions and strict exclusions.
    """

    def __init__(self, positive_terms: list = None, negative_terms: list = None):
        self.positive_terms = [norm_text(t) for t in (positive_terms or []) if norm_text(t)]
        self.negative_terms = [norm_text(t) for t in (negative_terms or []) if norm_text(t)]

    ROLE_LEVEL_NOUNS = {
        "specialist", "consultant", "manager", "lead", "analyst", "associate",
        "director", "expert", "advisor", "officer", "coordinator", "partner",
        "generalist", "representative", "practitioner", "engineer", "developer", "designer"
    }

    def is_relevant(self, title: str) -> bool:
        norm_title = norm_text(title)
        if not norm_title:
            return False

        # Exclusions take absolute precedence on title
        for exc in self.negative_terms:
            if exc in norm_title:
                return False

        # If no positive terms configured, accept by default
        if not self.positive_terms:
            return True

        # 1. Direct substring match (fast path)
        if any(pos in norm_title for pos in self.positive_terms):
            return True

        # 2. Token-set and word-order invariant match
        clean_title = re.sub(r"[^\w\s]", " ", norm_title)
        title_tokens = set(clean_title.split())

        for pos in self.positive_terms:
            clean_pos = re.sub(r"[^\w\s]", " ", pos)
            pos_tokens = clean_pos.split()
            if not pos_tokens:
                continue

            # Exact token subset match (e.g. "Specialist - HR Transformation")
            if all(tok in title_tokens for tok in pos_tokens):
                return True

            # Core domain token match (if term has 3+ words, e.g. "hr transformation specialist")
            if len(pos_tokens) >= 3:
                core_tokens = [tok for tok in pos_tokens if tok not in self.ROLE_LEVEL_NOUNS]
                if core_tokens and all(tok in title_tokens for tok in core_tokens):
                    return True

        return False

    def filter_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        mask = df["title"].apply(self.is_relevant)
        return df[mask].copy()
