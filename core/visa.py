import re
import unicodedata
import pandas as pd

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")

def norm_text(val):
    if val is None or pd.isna(val):
        return ""
    text = str(val).lower()
    text = strip_accents(text)
    return re.sub(r"\s+", " ", text).strip()

SPONSORSHIP_POSITIVE = [
    # Inglês
    "visa sponsorship",
    "visa sponsor",
    "sponsorship available",
    "sponsorship provided",
    "work visa sponsorship",
    "employment visa sponsorship",
    "company sponsored visa",
    "company sponsorship",
    "visa support",
    "work permit sponsorship",
    "work permit support",
    "employment visa",
    "relocation and visa",
    "relocation assistance and visa",
    "visa assistance",
    "sponsor work visa",
    "sponsor your visa",
    # Português
    "patrocinio de visto",
    "patrocinio de visto de trabalho",
    "apoio para visto",
    "visto de trabalho",
    "suporte para visto",
    "oferece visto",
    "oferecemos visto",
    "patrocinamos visto",
    "visto para portugal",
    "visto de residencia",
    "auxilio visto",
]

SPONSORSHIP_NEGATIVE = [
    # Inglês
    "no visa sponsorship",
    "visa sponsorship not available",
    "visa sponsorship unavailable",
    "unable to sponsor",
    "cannot sponsor",
    "will not sponsor",
    "we do not sponsor",
    "does not sponsor",
    "not able to sponsor",
    "must already have the right to work",
    "must have the right to work",
    "right to work required",
    "valid work authorization required",
    "valid work permit required",
    "without sponsorship",
    # Português
    "nao oferecemos visto",
    "nao oferece visto",
    "sem patrocinio de visto",
    "sem apoio para visto",
    "necessario residir no brasil",
    "apenas residentes no brasil",
    "somente para residentes no brasil",
    "obrigatorio residir no brasil",
]

RELOCATION_TERMS = [
    # Inglês
    "relocation assistance",
    "relocation support",
    "relocation package",
    "relocation provided",
    "relocation available",
    "relocation offered",
    "relocation assistance available",
    "relocation support available",
    # Português
    "auxilio mudanca",
    "ajuda de custo mudanca",
    "ajuda de custo para mudanca",
    "pacote de realocacao",
    "apoio a realocacao",
    "suporte a realocacao",
    "realocacao oferecida",
    "auxilio para mudanca",
]

def detect_visa_sponsorship(title: str, description: str) -> tuple:
    """Returns (status, evidence_phrase)."""
    text = norm_text(title) + " " + norm_text(description)

    for neg in SPONSORSHIP_NEGATIVE:
        if neg in text:
            return "SEM VISTO", neg

    for pos in SPONSORSHIP_POSITIVE:
        if pos in text:
            return "VISTO MENCIONADO", pos

    return "DESCONHECIDO", ""

def detect_relocation(title: str, description: str) -> tuple:
    """Returns (status, evidence_phrase)."""
    text = norm_text(title) + " " + norm_text(description)

    for rel in RELOCATION_TERMS:
        if rel in text:
            return "REALOCACAO MENCIONADA", rel

    return "DESCONHECIDO", ""

def detect_contract_regime(title: str, description: str) -> str:
    """Detects Brazilian contract regime: CLT, PJ, Estágio, Cooperado."""
    text = norm_text(title) + " " + norm_text(description)
    if re.search(r"\bclt\b", text):
        return "CLT"
    if re.search(r"\bpj\b|pessoa juridica", text):
        return "PJ"
    if re.search(r"\bestagio\b|\bestagiario\b|\btrainee\b", text):
        return "Estágio"
    if re.search(r"\bcooperado\b", text):
        return "Cooperado"
    return "Não informado"

def detect_work_modality(title: str, description: str, location: str = "", is_remote: bool = None) -> str:
    """Detects modality: Remoto, Híbrido, Presencial."""
    norm_t = norm_text(title)
    norm_d = norm_text(description)
    norm_l = norm_text(location)
    full_text = f"{norm_t} {norm_d} {norm_l}"

    # 1. Regras estritas de Presencial (exclusões absolutas de remoto)
    strict_presencial = [
        "100% presencial", "apenas presencial", "somente presencial",
        "totalmente presencial", "regime presencial", "trabalho presencial",
        "atuacao presencial", "atuação presencial", "modelo presencial",
        "nao e remoto", "não é remoto", "sem possibilidade de home office",
        "sem home office", "disponibilidade para atuar presencialmente",
        "disponibilidade para trabalho presencial"
    ]
    if any(p in full_text for p in strict_presencial):
        return "Presencial"

    # 2. Híbrido (precedência sobre remoto, pois quase todo anúncio híbrido diz 'X dias remoto e Y dias presencial')
    hybrid_keywords = [
        "hibrido", "híbrido", "hybrid", "hibrida", "híbrida",
        "modelo hibrido", "modelo híbrido", "formato hibrido", "formato híbrido",
        "regime hibrido", "regime híbrido", "escala hibrida", "escala híbrida",
        "dias presenciais", "dias no escritorio", "dias no escritório",
        "dias home office e"
    ]
    if any(h in full_text for h in hybrid_keywords):
        return "Híbrido"

    # 3. Flag de fonte verificada como remota (ex: Indeed location=Remoto, BR)
    if is_remote is True:
        return "Remoto"

    # 4. Remoto explícito no título ou localização
    if any(r in norm_t or r in norm_l for r in ["remoto", "home office", "teletrabalho", "remote"]):
        return "Remoto"

    # 5. Remoto na descrição
    remote_keywords = [
        "100% remoto", "totalmente remoto", "trabalho remoto", "regime remoto",
        "atuacao remota", "atuação remota", "modelo remoto", "posicao remota",
        "posição remota", "vaga remota", "vaga 100% remota", "contratacao remota",
        "contratação remota", "home office", "teletrabalho", "anywhere office"
    ]
    if any(r in norm_d for r in remote_keywords):
        return "Remoto"

    # 6. Presencial explícito
    if any(p in full_text for p in ["presencial", "on-site", "onsite", "in-person"]):
        return "Presencial"

    # 7. Cidade física informada sem qualquer menção de remoto -> Presencial
    clean_loc = norm_l.replace("brasil", "").replace("brazil", "").strip(" ,-")
    if clean_loc and clean_loc not in ["remoto", "home office", "teletrabalho", "worldwide"]:
        return "Presencial"

    return "Não informado"
