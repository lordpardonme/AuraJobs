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
        "intern": ["intern", "internship", "trainee", "student", "estagiario", "estagiaria", "estagiário", "estagiária", "estagio", "estágio"],
        "junior": ["junior", "júnior", "jr.", "jr", "entry level", "entry-level", "graduate", "associate", "iniciante"],
        "mid-level": ["mid", "mid-level", "mid level", "pleno", "pl.", "pl"],
        "senior": ["senior", "sênior", "sr.", "sr"],
        "staff": ["staff", "especialista", "specialist"],
        "lead": ["lead", "team lead", "lider", "líder", "coordenador", "coordenadora", "tech lead"],
        "principal": ["principal", "director", "diretor", "diretora", "head of", "head", "gerente", "vp"],
    }

    SENIORITY_EXCLUSIONS = {
        "intern": ["senior", "sênior", "sr.", "sr", "staff", "especialista", "lead", "lider", "líder", "principal", "director", "diretor", "head", "manager", "gerente", "vp", "pleno"],
        "junior": ["senior", "sênior", "sr.", "sr", "staff", "especialista", "lead", "lider", "líder", "principal", "director", "diretor", "head", "manager", "gerente", "vp", "pleno"],
        "mid-level": ["intern", "estagio", "estágio", "trainee", "junior", "júnior", "jr", "entry level", "diretor", "vp"],
        "senior": ["intern", "internship", "estagio", "estágio", "trainee", "junior", "júnior", "jr", "entry level", "student", "estagiario"],
        "staff": ["intern", "estagio", "estágio", "junior", "júnior", "jr", "entry level", "trainee"],
        "lead": ["intern", "estagio", "estágio", "junior", "júnior", "jr", "trainee"],
        "principal": ["intern", "estagio", "estágio", "junior", "júnior", "jr", "trainee"],
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

            if norm_sen in ["intern", "estagio", "estágio"]:
                intern_terms = [t for t in base_terms if any(w in t.lower() for w in ["intern", "estagio", "estágio", "trainee", "estagiario", "estagiário"])]
                search_terms = intern_terms if intern_terms else [f"{base_role} Estágio", f"{base_role} Intern"]
            elif norm_sen in ["junior", "júnior", "jr", "entry", "entry-level"]:
                jr_terms = [t for t in base_terms if any(w in t.lower() for w in ["junior", "júnior", "jr", "entry", "associate"])]
                search_terms = jr_terms if jr_terms else [f"{base_role} Júnior", f"{base_role} Jr", f"Junior {base_role}"]
            elif norm_sen in ["mid-level", "mid", "pleno"]:
                mid_terms = [t for t in base_terms if any(w in t.lower() for w in ["pleno", "pl", "mid"])]
                search_terms = mid_terms if mid_terms else [base_role, f"{base_role} Pleno"]
            elif norm_sen in ["senior", "sênior", "sr"]:
                senior_terms = [t for t in base_terms if any(w in t.lower() for w in ["senior", "sênior", "sr"])]
                search_terms = senior_terms if senior_terms else [f"{base_role} Sênior", f"{base_role} Senior", f"{base_role} Sr"]
            elif norm_sen in ["lead", "lider", "líder"]:
                lead_terms = [t for t in base_terms if any(w in t.lower() for w in ["lead", "lider", "líder", "coordenador", "manager"])]
                search_terms = lead_terms if lead_terms else [f"Líder {base_role}", f"Lead {base_role}"]
            elif norm_sen in ["staff", "especialista"]:
                staff_terms = [t for t in base_terms if any(w in t.lower() for w in ["staff", "principal", "especialista"])]
                search_terms = staff_terms if staff_terms else [f"{base_role} Especialista", f"Staff {base_role}"]
            else:
                # Any seniority: use the full preset search_terms for maximum coverage
                if base_terms:
                    search_terms = list(base_terms)
                elif any(w in base_role.lower() for w in ["analista", "engenheiro", "tecnico", "desenvolvedor"]):
                    search_terms = [
                        base_role,
                        f"{base_role} Pleno",
                        f"{base_role} Sênior",
                        f"{base_role} Jr",
                    ]
                else:
                    search_terms = [
                        base_role,
                        f"Senior {base_role}",
                        f"Lead {base_role}",
                    ]

        else:
            # Dynamic expansion for custom role (e.g. Analista de Infraestrutura, DevOps Engineer)
            words = base_role.split()
            generic_role_nouns = {
                "specialist", "consultant", "manager", "lead", "analyst", "associate",
                "director", "expert", "advisor", "officer", "coordinator", "partner",
                "practitioner", "engineer", "developer", "designer",
                "analista", "especialista", "consultor", "consultora", "gerente", "coordenador",
                "coordenadora", "lider", "líder", "engenheiro", "engenheira", "desenvolvedor",
                "desenvolvedora", "tecnico", "técnico", "administrador", "administradora",
                "assistente", "suporte"
            }

            if len(words) >= 2 and words[0].lower() in generic_role_nouns:
                if len(words) >= 3 and words[1].lower() in ["de", "do", "da", "em", "e", "para"]:
                    core_domain = " ".join(words[2:])
                else:
                    core_domain = " ".join(words[1:])
            elif len(words) >= 2 and words[-1].lower() in generic_role_nouns:
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
                for noun in ["lider", "líder", "coordenador", "gerente", "especialista", "analista", "lead", "manager", "consultant", "specialist"]:
                    var = f"{noun} {core_domain.lower()}"
                    if var not in positive_title_terms:
                        positive_title_terms.append(var)

            if norm_sen in ["intern", "estagio", "estágio"]:
                search_terms = [
                    f"{base_role} Estágio",
                    f"Estágio {base_role}",
                    f"Estagiário {base_role}",
                    f"{base_role} Trainee",
                    f"{base_role} Intern",
                ]
            elif norm_sen in ["junior", "júnior", "jr", "entry", "entry-level"]:
                search_terms = [
                    f"{base_role} Júnior",
                    f"{base_role} Junior",
                    f"{base_role} Jr",
                    f"Junior {base_role}",
                ]
            elif norm_sen in ["mid-level", "mid", "pleno"]:
                search_terms = [
                    base_role,
                    f"{base_role} Pleno",
                    core_domain,
                ]
            elif norm_sen in ["senior", "sênior", "sr"]:
                search_terms = [
                    f"{base_role} Sênior",
                    f"{base_role} Senior",
                    f"{base_role} Sr",
                    f"Senior {base_role}",
                    f"{core_domain} Sênior",
                ]
            elif norm_sen in ["lead", "lider", "líder"]:
                search_terms = [
                    f"Líder {base_role}",
                    f"Coordenador {base_role}",
                    f"Lead {base_role}",
                    f"{base_role} Lead",
                ]
            elif norm_sen in ["staff", "especialista"]:
                search_terms = [
                    f"{base_role} Especialista",
                    f"Especialista {base_role}",
                    f"Especialista em {core_domain}",
                    f"Staff {base_role}",
                ]
            elif norm_sen in ["principal", "director", "diretor", "gerente"]:
                search_terms = [
                    f"Gerente de {core_domain}",
                    f"Diretor de {core_domain}",
                    f"Principal {base_role}",
                ]
            else:
                # Any:
                search_terms = [
                    base_role,
                    f"{base_role} Pleno",
                    f"{base_role} Sênior",
                    f"{base_role} Jr",
                    core_domain,
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
