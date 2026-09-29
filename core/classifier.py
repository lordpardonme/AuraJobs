import re
import unicodedata
import pandas as pd

STOPWORDS = {"de", "do", "da", "dos", "das", "em", "e", "para", "com", "of", "and", "in", "for", "the"}

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")

def norm_text(val):
    if val is None or pd.isna(val):
        return ""
    text = str(val).lower()
    text = strip_accents(text)
    # Padronizar t.i. e infra-estrutura
    text = re.sub(r"\bt\.i\.?\b", "ti", text)
    text = re.sub(r"\binfra-estrutura\b", "infraestrutura", text)
    return re.sub(r"\s+", " ", text).strip()

class RoleClassifier:
    """
    Title-led role classifier enforcing positive inclusions and strict exclusions.
    Supports Portuguese and English title variations, accents, and token sets.
    """

    def __init__(self, positive_terms: list = None, negative_terms: list = None):
        self.positive_terms = [norm_text(t) for t in (positive_terms or []) if norm_text(t)]
        self.negative_terms = [norm_text(t) for t in (negative_terms or []) if norm_text(t)]

    ROLE_LEVEL_NOUNS = {
        "specialist", "consultant", "manager", "lead", "analyst", "associate",
        "director", "expert", "advisor", "officer", "coordinator", "partner",
        "generalist", "representative", "practitioner", "engineer", "developer", "designer",
        # Português:
        "analista", "especialista", "consultor", "consultora", "gerente", "coordenador",
        "coordenadora", "lider", "diretor", "diretora", "engenheiro", "engenheira",
        "desenvolvedor", "desenvolvedora", "tecnico", "administrador", "administradora",
        "assistente", "auxiliar", "operador", "operadora", "supervisor", "supervisora", "suporte"
    }

    def is_relevant(self, title: str) -> bool:
        norm_title = norm_text(title)
        if not norm_title:
            return False

        # Exclusions take absolute precedence on title
        for exc in self.negative_terms:
            if re.search(r"\b" + re.escape(exc) + r"\b", norm_title) or (len(exc) > 4 and exc in norm_title):
                return False

        # If no positive terms configured, accept by default
        if not self.positive_terms:
            return True

        clean_title = re.sub(r"[^\w\s]", " ", norm_title)
        title_tokens = set(clean_title.split())

        for pos in self.positive_terms:
            clean_pos = re.sub(r"[^\w\s]", " ", pos)
            pos_tokens = clean_pos.split()
            if not pos_tokens:
                continue

            # Short single terms (e.g. "ti", "qa", "bi", "dev", "sre", "dba") MUST match as exact tokens
            if len(pos_tokens) == 1:
                if pos_tokens[0] in title_tokens:
                    return True
                continue

            # Multi-word exact phrase match with word boundaries
            if re.search(r"\b" + re.escape(pos) + r"\b", norm_title):
                return True

            # Meaningful tokens match (invariant of word order)
            pos_meaningful = [tok for tok in pos_tokens if tok not in STOPWORDS]
            if pos_meaningful and all(tok in title_tokens for tok in pos_meaningful):
                return True

            # Core domain token match (if term has 3+ words, e.g. "analista de infraestrutura e redes")
            if len(pos_tokens) >= 3:
                core_tokens = [tok for tok in pos_tokens if tok not in self.ROLE_LEVEL_NOUNS and tok not in STOPWORDS]
                if core_tokens and all(tok in title_tokens for tok in core_tokens):
                    return True

        return False

    def filter_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return df
        mask = df["title"].apply(self.is_relevant)
        return df[mask].copy()
