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

    def is_relevant(self, title: str) -> bool:
        norm_title = norm_text(title)
        if not norm_title:
            return False

        # Exclusions take absolute precedence on title
        for exc in self.negative_terms:
            if exc in norm_title:
                return False

        # Positive match requirement
        if self.positive_terms:
            return any(pos in norm_title for pos in self.positive_terms)

        return True

    def filter_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        mask = df["title"].apply(self.is_relevant)
        return df[mask].copy()
