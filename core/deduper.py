import re
import pandas as pd

def norm_val(val):
    if val is None or pd.isna(val):
        return ""
    return re.sub(r"\s+", " ", str(val).lower()).strip()

def deduplicate_jobs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Multi-stage deduplication:
      1. Exact job URL
      2. Normalized title + company + location composite key
    Preserves source provenance across duplicates.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # Track discovered sources
    if "source" in df.columns:
        source_col = df["source"].fillna("").astype(str)
    elif "Search Source" in df.columns:
        source_col = df["Search Source"].fillna("").astype(str)
    else:
        source_col = pd.Series([""] * len(df))

    df["discovered_sources"] = source_col

    # Stage 1: Deduplicate by exact job URL if available
    if "job_url" in df.columns:
        df["_url_clean"] = df["job_url"].fillna("").astype(str).str.lower().str.strip()
        has_url = df["_url_clean"].ne("")

        url_grouped = df[has_url].groupby("_url_clean", as_index=False).agg({
            "discovered_sources": lambda s: ", ".join(sorted(set(x for x in s if x)))
        })

        deduped_urls = df[has_url].drop_duplicates("_url_clean", keep="first").drop(columns=["discovered_sources"])
        deduped_urls = deduped_urls.merge(url_grouped, on="_url_clean", how="left")

        without_url = df[~has_url]
        df = pd.concat([deduped_urls, without_url], ignore_index=True)
        df = df.drop(columns=["_url_clean"], errors="ignore")

    # Stage 2: Deduplicate by normalized title + company + location
    key_fields = [f for f in ["title", "company", "location"] if f in df.columns]
    if key_fields:
        df["_composite_key"] = df.apply(
            lambda r: " | ".join(norm_val(r[f]) for f in key_fields),
            axis=1
        )

        composite_grouped = df.groupby("_composite_key", as_index=False).agg({
            "discovered_sources": lambda s: ", ".join(sorted(set(
                item.strip() for val in s for item in str(val).split(",") if item.strip()
            )))
        })

        df = df.drop_duplicates("_composite_key", keep="first").drop(columns=["discovered_sources"])
        df = df.merge(composite_grouped, on="_composite_key", how="left")
        df = df.drop(columns=["_composite_key"], errors="ignore")

    return df.reset_index(drop=True)
