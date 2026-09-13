import os
import re
import yaml
from datetime import datetime

class RoleExpander:
    """
    Expands user role input into a comprehensive search profile.
    Supports preset role taxonomies, smart seniority parsing, and dynamic query generation.
    """

    SENIORITY_PREFIXES = {
        "intern": ["intern", "internship", "trainee", "student"],
        "junior": ["junior", "entry level", "entry-level", "graduate", "associate"],
        "mid-level": ["mid", "mid-level", "mid level"],
        "senior": ["senior", "sr.", "sr"],
        "staff": ["staff"],
        "lead": ["lead", "team lead"],
        "principal": ["principal", "director", "head of", "head", "vp"],
    }

    SENIORITY_EXCLUSIONS = {
        "intern": ["senior", "sr.", "staff", "lead", "principal", "director", "head", "manager", "vp"],
        "junior": ["senior", "sr.", "staff", "lead", "principal", "director", "head", "manager", "vp"],
        "senior": ["intern", "internship", "trainee", "junior", "entry level", "student"],
        "staff": ["intern", "internship", "junior", "entry level", "trainee"],
        "lead": ["intern", "internship", "junior", "trainee"],
        "principal": ["intern", "internship", "junior", "entry level", "trainee"],
    }

    def __init__(self, config_path: str = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, "config", "roles.yaml")

        with open(config_path, "r", encoding="utf-8") as f:
            self.roles_cfg = yaml.safe_load(f)

        self.presets = self.roles_cfg.get("presets", {})
        self.seniority_levels = self.roles_cfg.get("seniority_levels", [])
        self.startup_prefixes = self.roles_cfg.get("startup_prefixes", [])
        self.global_exclusions = self.roles_cfg.get("global_exclusions", [])

    def detect_and_strip_seniority(self, role_input: str) -> tuple:
        """
        Extracts any explicit seniority prefix from the role string.
        e.g. 'Lead DevOps Engineer' -> ('DevOps Engineer', 'Lead')
        """
        role_clean = role_input.strip()
        role_lower = role_clean.lower()

        for canonical_level, triggers in self.SENIORITY_PREFIXES.items():
            for trigger in triggers:
                # Match start of string or end of string
                pattern_start = rf"^{re.escape(trigger)}\s+"
                pattern_end = rf"\s+{re.escape(trigger)}$"
                if re.search(pattern_start, role_lower):
                    base = re.sub(pattern_start, "", role_clean, flags=re.IGNORECASE).strip()
                    return base, canonical_level.capitalize()
                elif re.search(pattern_end, role_lower):
                    base = re.sub(pattern_end, "", role_clean, flags=re.IGNORECASE).strip()
                    return base, canonical_level.capitalize()

        return role_clean, None

    def find_preset(self, role_input: str):
        normalized = role_input.strip().lower()
        for key, preset in self.presets.items():
            if normalized == preset["name"].lower():
                return preset
            for alias in preset.get("aliases", []):
                if normalized == alias.lower() or alias.lower() in normalized:
                    return preset
        return None

    def build_search_profile(self, target_role: str, seniority: str = "Any",
                             skills: list = None, exclusions: list = None) -> dict:
        skills = skills or []
        exclusions = exclusions or []

        # 1. Parse base role and any implicit seniority in the title
        base_role, detected_sen = self.detect_and_strip_seniority(target_role)

        # If user explicitly chose seniority other than 'Any', that wins.
        # Otherwise, if the role title had an implicit seniority (e.g. 'Lead DevOps Engineer'), use it.
        effective_seniority = seniority
        if effective_seniority == "Any" and detected_sen:
            effective_seniority = detected_sen

        norm_sen = effective_seniority.lower()

        # Check presets using both full target_role and stripped base_role
        preset = self.find_preset(target_role) or self.find_preset(base_role)

        search_terms = []
        positive_title_terms = []
        combined_skills = list(skills)

        if preset:
            base_terms = list(preset.get("search_terms", []))
            positive_title_terms = list(preset.get("positive_title_terms", []))
            for s in preset.get("skills", []):
                if s not in combined_skills:
                    combined_skills.append(s)

            if norm_sen == "intern":
                search_terms = [
                    f"{base_role} Intern",
                    f"{base_role} Internship",
                    f"Junior {base_role}",
                ]
            elif norm_sen in ["junior", "entry", "entry-level"]:
                search_terms = [
                    f"Junior {base_role}",
                    f"Associate {base_role}",
                    f"Entry Level {base_role}",
                ]
            elif norm_sen in ["mid-level", "mid"]:
                search_terms = [
                    base_role,
                    f"Mid-Level {base_role}",
                ]
            elif norm_sen == "senior":
                # Only keep senior terms from preset
                senior_terms = [
                    t for t in base_terms
                    if "senior" in t.lower() or "sr" in t.lower().split()
                ]
                search_terms = senior_terms if senior_terms else [f"Senior {base_role}", f"Sr {base_role}"]
            elif norm_sen == "lead":
                lead_terms = [
                    t for t in base_terms
                    if "lead" in t.lower() or "manager" in t.lower()
                ]
                search_terms = lead_terms if lead_terms else [f"Lead {base_role}", f"{base_role} Lead"]
            elif norm_sen in ["staff", "principal"]:
                staff_terms = [
                    t for t in base_terms
                    if "staff" in t.lower() or "principal" in t.lower()
                ]
                search_terms = staff_terms if staff_terms else [f"{effective_seniority.capitalize()} {base_role}"]
            else:
                # Any seniority: use core balanced terms
                search_terms = [
                    base_role,
                    f"Senior {base_role}",
                    f"Lead {base_role}",
                ]

        else:
            # Dynamic expansion for custom role (e.g. HR Transformation Specialist, DevOps Engineer)
            words = base_role.split()
            generic_role_nouns = {
                "specialist", "consultant", "manager", "lead", "analyst", "associate",
                "director", "expert", "advisor", "officer", "coordinator", "partner",
                "practitioner", "engineer", "developer", "designer"
            }
            if len(words) >= 2 and words[-1].lower() in generic_role_nouns:
                core_domain = " ".join(words[:-1])
            else:
                core_domain = base_role

            positive_title_terms.append(base_role.lower())
            if core_domain.lower() not in positive_title_terms:
                positive_title_terms.append(core_domain.lower())
            if target_role.lower() not in positive_title_terms:
                positive_title_terms.append(target_role.lower())

            # Add common title variations for multi-word domain
            if len(words) >= 2:
                for noun in ["lead", "manager", "consultant", "specialist", "analyst", "advisor"]:
                    var = f"{core_domain.lower()} {noun}"
                    if var not in positive_title_terms:
                        positive_title_terms.append(var)

            if norm_sen == "intern":
                search_terms = [
                    f"{base_role} Intern",
                    f"{base_role} Internship",
                    f"{core_domain} Intern",
                ]
            elif norm_sen in ["junior", "entry", "entry-level"]:
                search_terms = [
                    f"Junior {base_role}",
                    f"Associate {base_role}",
                    f"Junior {core_domain}",
                ]
            elif norm_sen in ["mid-level", "mid"]:
                search_terms = [
                    base_role,
                    core_domain,
                    f"Mid {base_role}",
                ]
            elif norm_sen == "senior":
                search_terms = [
                    f"Senior {base_role}",
                    f"Senior {core_domain}",
                    f"Lead {core_domain}",
                    f"Sr {base_role}",
                ]
            elif norm_sen == "lead":
                search_terms = [
                    f"Lead {base_role}",
                    f"Lead {core_domain}",
                    f"{core_domain} Lead",
                    f"{core_domain} Manager",
                ]
            elif norm_sen == "staff":
                search_terms = [
                    f"Staff {base_role}",
                    f"Senior {core_domain}",
                    f"Staff {core_domain}",
                ]
            elif norm_sen in ["principal", "director"]:
                search_terms = [
                    f"Principal {base_role}",
                    f"Director of {core_domain}",
                    f"Head of {core_domain}",
                ]
            else:
                # Any: clean representative mix
                search_terms = [
                    base_role,
                    core_domain,
                    f"Senior {core_domain}",
                    f"Lead {core_domain}",
                ]

        # Compile exclusions: global exclusions (filtered for target conflict) + user exclusions + seniority exclusions
        target_lower = target_role.lower()
        base_lower = base_role.lower()
        filtered_global = [
            g for g in self.global_exclusions
            if g not in target_lower and g not in base_lower
        ]
        combined_exclusions = list(filtered_global)

        # Automatic exclusion of conflicting seniorities if user picked a specific level
        auto_sen_exclusions = self.SENIORITY_EXCLUSIONS.get(norm_sen, [])
        for sen_exc in auto_sen_exclusions:
            if sen_exc not in combined_exclusions:
                combined_exclusions.append(sen_exc)

        for exc in exclusions:
            exc_clean = exc.strip().lower()
            if exc_clean and exc_clean not in combined_exclusions:
                combined_exclusions.append(exc_clean)

        return {
            "target_role": target_role,
            "base_role": base_role,
            "seniority": effective_seniority,
            "skills": combined_skills,
            "user_exclusions": exclusions,
            "search_terms": list(dict.fromkeys(search_terms)),  # Deduplicate while preserving order
            "positive_title_terms": positive_title_terms,
            "negative_title_terms": combined_exclusions,
            "created_at": datetime.now().isoformat(),
        }
