import uuid
from datetime import datetime
import pandas as pd

CANONICAL_COLUMNS = [
    "job_id",
    "source_job_id",
    "source",
    "source_url",
    "job_url",
    "company",
    "title",
    "location",
    "country",
    "region",
    "description",
    "date_posted",
    "scraped_at",
    "age_hours",
    "age_bucket",
    "employment_type",
    "remote_status",
    "salary_min",
    "salary_max",
    "currency",
    "visa_status",
    "visa_evidence",
    "relocation_status",
    "relocation_evidence",
    "match_score",
    "priority",
    "query_used",
    "search_location",
]

def clean_str(val):
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()

def normalize_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Transforms raw scraper output into the canonical 27-field normalized job schema."""
    if raw_df is None or raw_df.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    df = raw_df.copy()
    rows = []
    now_str = datetime.now().isoformat()

    for _, r in df.iterrows():
        # Map source fields from JobSpy
        source = clean_str(r.get("site", r.get("Search Source", "")))
        source_job_id = clean_str(r.get("id", ""))
        job_url = clean_str(r.get("job_url", r.get("job_url_direct", "")))
        company = clean_str(r.get("company", ""))
        title = clean_str(r.get("title", ""))
        location = clean_str(r.get("location", ""))
        country = clean_str(r.get("country", ""))
        region = clean_str(r.get("Search Region", ""))
        description = clean_str(r.get("description", ""))
        date_posted = clean_str(r.get("date_posted", ""))
        scraped_at = clean_str(r.get("scraped_at", now_str))

        # Employment & compensation
        emp_type = clean_str(r.get("job_type", r.get("employment_type", "")))
        is_remote = r.get("is_remote", None)
        remote_status = "Remote" if is_remote is True else ("On-site / Hybrid" if is_remote is False else "Unknown")
        salary_min = r.get("min_amount", None)
        salary_max = r.get("max_amount", None)
        currency = clean_str(r.get("currency", ""))

        # Query attribution
        query_used = clean_str(r.get("Search Term", ""))
        search_loc = clean_str(r.get("Search Location", ""))

        # Generate unique stable ID if not present
        job_id = str(uuid.uuid4())[:8]

        row_dict = {
            "job_id": job_id,
            "source_job_id": source_job_id,
            "source": source,
            "source_url": clean_str(r.get("job_url_direct", job_url)),
            "job_url": job_url,
            "company": company,
            "title": title,
            "location": location,
            "country": country,
            "region": region,
            "description": description,
            "date_posted": date_posted,
            "scraped_at": scraped_at,
            "age_hours": r.get("Age Hours", None),
            "age_bucket": clean_str(r.get("Age Bucket", "")),
            "employment_type": emp_type,
            "remote_status": remote_status,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "currency": currency,
            "visa_status": clean_str(r.get("Sponsorship", r.get("visa_status", "UNKNOWN"))),
            "visa_evidence": clean_str(r.get("visa_evidence", "")),
            "relocation_status": clean_str(r.get("Relocation", r.get("relocation_status", "UNKNOWN"))),
            "relocation_evidence": clean_str(r.get("relocation_evidence", "")),
            "match_score": r.get("Match Score", 0),
            "priority": clean_str(r.get("Priority", "")),
            "query_used": query_used,
            "search_location": search_loc,
        }
        rows.append(row_dict)

    return pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
