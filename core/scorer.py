import re
import pandas as pd

def norm_text(val):
    if val is None or pd.isna(val):
        return ""
    return re.sub(r"\s+", " ", str(val).lower()).strip()

def calculate_age_hours(date_val) -> float:
    """Calculates job age in hours from UTC now."""
    try:
        posted = pd.to_datetime(date_val, errors="coerce", utc=True)
        if pd.isna(posted):
            return None
        now = pd.Timestamp.now(tz="UTC")
        return round(max((now - posted).total_seconds() / 3600, 0), 2)
    except Exception:
        return None

class MatchScorer:
    """Calculates match score (0-100) and urgency priority based on role profile."""

    def __init__(self, target_role: str = "", skills: list = None, seniority: str = "Any"):
        self.target_role = norm_text(target_role)
        self.skills = [norm_text(s) for s in (skills or [])]
        self.seniority = norm_text(seniority)

    def calculate_score(self, title: str, description: str, age_hours: float,
                        visa_status: str, relocation_status: str) -> int:
        norm_title = norm_text(title)
        text = norm_title + " " + norm_text(description)
        score = 0

        # Title role alignment
        if self.target_role and self.target_role in norm_title:
            score += 45
        elif any(part in norm_title for part in self.target_role.split()):
            score += 25

        # Seniority match based on user's requested level
        sen_target = self.seniority.lower()
        if sen_target == "senior":
            if any(w in norm_title for w in ["senior", "sr.", "sr "]):
                score += 15
        elif sen_target == "intern":
            if any(w in norm_title for w in ["intern", "trainee", "student"]):
                score += 15
        elif sen_target in ["junior", "entry"]:
            if any(w in norm_title for w in ["junior", "entry", "associate"]):
                score += 15
        elif sen_target == "lead":
            if any(w in norm_title for w in ["lead", "manager"]):
                score += 15
        elif sen_target in ["staff", "principal"]:
            if any(w in norm_title for w in ["staff", "principal"]):
                score += 15
        elif sen_target == "any":
            if any(sen in norm_title for sen in ["senior", "lead", "staff", "principal", "founding"]):
                score += 10
            else:
                score += 5

        # Skill overlap (up to +20)
        skill_hits = sum(1 for skill in self.skills if skill in text)
        score += min(skill_hits * 3, 20)

        # Freshness bonus
        if age_hours is not None:
            if age_hours <= 24:
                score += 15
            elif age_hours <= 48:
                score += 10
            elif age_hours <= 72:
                score += 5
        else:
            # Jobs retrieved under the platform's query filter
            score += 10

        # Visa / relocation
        if visa_status == "SPONSORSHIP MENTIONED":
            score += 15
        elif visa_status == "NO SPONSORSHIP":
            score -= 20

        if relocation_status == "RELOCATION MENTIONED":
            score += 8

        return max(0, min(score, 100))

    def assign_priority(self, age_hours: float, visa_status: str) -> str:
        if visa_status == "SPONSORSHIP MENTIONED":
            return "URGENT - VISA"
        if age_hours is not None:
            if age_hours <= 24:
                return "URGENT - NEW"
            if age_hours <= 48:
                return "FRESH"
            return "LAST 72H"
        return "FRESH"

