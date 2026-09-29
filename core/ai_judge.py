import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("AuraJobs.AIJudge")

class TypeSafeJudge:
    """
    Intelligent semantic judgment engine powered by TypeSafe System One (Jev).
    Produces typed decisions and probabilities for job modality and tech domain fit.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("TYPESAFE_API_KEY")
        self.available = bool(self.api_key and self.api_key.startswith("apikey_"))
        self._client = None
        if self.available:
            try:
                from typesafe_sdk import TypeSafeClient
                self._client_class = TypeSafeClient
            except ImportError:
                self.available = False
                logger.warning("typesafe-sdk not installed; TypeSafeJudge disabled.")

    def is_available(self) -> bool:
        return self.available

    def judge_job(self, title: str, description: str, location: str) -> dict:
        """
        Submits structured Choice and Noul questions to TypeSafe Jev.
        Returns modality judgment and tech role probability.
        """
        if not self.available:
            return None

        from typesafe_sdk import Choice, Noul

        clean_title = str(title or "").strip()
        clean_desc = str(description or "").strip()
        clean_loc = str(location or "").strip()

        # Limit description size to avoid excessive tokens while preserving key context
        desc_snippet = clean_desc[:2500] if clean_desc else "Sem descrição detalhada."

        state = {
            "title": clean_title,
            "location": clean_loc,
            "description": desc_snippet,
        }

        questions = {
            "modality": Choice(
                instructions="Qual é a modalidade de trabalho desta vaga com base no título, localização e descrição?",
                criteria={
                    "remoto": "O trabalho é 100% remoto ou home office (sem exigência de comparecimento presencial regular no escritório).",
                    "hibrido": "O trabalho exige dias presenciais no escritório e dias em home office.",
                    "presencial": "O trabalho é totalmente presencial na sede física da empresa.",
                    "desconhecido": "A modalidade não foi informada ou é indeterminável.",
                },
            ),
            "is_tech": Noul(
                instructions="Esta vaga pertence à área de Tecnologia da Informação (TI), desenvolvimento de software, infraestrutura, suporte técnico, cloud, dados ou segurança?"
            ),
        }

        try:
            with self._client_class(api_key=self.api_key) as client:
                res = client.system_one(state=state, questions=questions)

            mod_ans = res.answers.get("modality")
            tech_ans = res.answers.get("is_tech")

            mod_choice = mod_ans.choice if mod_ans else "desconhecido"
            mod_conf = mod_ans.confidence if mod_ans else 0.0
            tech_prob = tech_ans.noul if tech_ans else 0.5

            modality_map = {
                "remoto": "Remoto",
                "hibrido": "Híbrido",
                "presencial": "Presencial",
                "desconhecido": "Não informado",
            }

            return {
                "modality": modality_map.get(mod_choice, "Não informado"),
                "modality_confidence": round(float(mod_conf), 2),
                "is_tech": tech_prob >= 0.70,
                "tech_probability": round(float(tech_prob), 2),
            }

        except Exception as e:
            err_str = str(e)
            if "402" in err_str or "credits" in err_str.lower() or "billing" in err_str.lower():
                if self.available:
                    print("\n[!] Aviso TypeSafe AI: Saldo de créditos da API esgotado (HTTP 402).")
                    print("    --> Recarga disponível em: https://console.typesafe.ai/settings/billing")
                    print("    --> AuraJobs operando normalmente via regras determinísticas de contingência.")
                    self.available = False
            elif "401" in err_str or "unauthorized" in err_str.lower():
                if self.available:
                    print("\n[!] Aviso TypeSafe AI: Chave de API não autorizada (HTTP 401).")
                    self.available = False
            else:
                logger.debug(f"TypeSafe API evaluation failed: {e}")
            return None

    def refine_dataframe(self, df: pd.DataFrame, max_workers: int = 4) -> pd.DataFrame:
        """
        Enriches candidate DataFrame with TypeSafe semantic judgments for ambiguous jobs.
        """
        if df is None or df.empty or not self.available:
            return df

        df = df.copy()
        if "ai_evaluated" not in df.columns:
            df["ai_evaluated"] = False
            df["ai_modality"] = df.get("modalidade", "Não informado")
            df["ai_tech_prob"] = 1.0

        # Identify jobs that need AI judgment:
        # - candidate for Remote (Brasil) to verify it is strictly 100% remote
        # - modality is 'Não informado'
        # - local jobs to verify tech relevance
        targets = []
        for idx, row in df.iterrows():
            if not self.available:
                break

            desc = str(row.get("description", "")).strip()
            loc = str(row.get("location", "")).lower()
            mod = str(row.get("modalidade", "")).capitalize()

            is_londrina = any(c in loc for c in ["londrina", "cambe", "cambé", "ibipora", "ibiporã", "rolandia", "rolândia"])

            # If job is already Presencial/Híbrido and NOT in Londrina, it will be discarded anyway
            if mod in ["Presencial", "Híbrido"] and not is_londrina:
                continue

            has_desc = bool(desc and desc not in ["None", "nan", ""])
            targets.append((idx, row.get("title", ""), desc if has_desc else "", row.get("location", "")))

        if not targets or not self.available:
            return df

        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.judge_job, t, d, l): idx
                for idx, t, d, l in targets
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    res = future.result()
                    if res:
                        results[idx] = res
                except Exception:
                    pass

        # Apply AI judgments to DataFrame
        adjusted_modality_count = 0
        non_tech_indices = []

        for idx, res in results.items():
            df.at[idx, "ai_evaluated"] = True
            df.at[idx, "ai_modality"] = res["modality"]
            df.at[idx, "ai_tech_prob"] = res["tech_probability"]

            # Filter out confirmed non-tech roles (e.g. cleaning, driver, non-tech sales)
            if res.get("tech_probability", 1.0) < 0.40:
                non_tech_indices.append(idx)
                continue

            # If AI has high confidence, refine modality
            if res["modality"] in ["Remoto", "Híbrido", "Presencial"] and res["modality_confidence"] >= 0.75:
                if df.at[idx, "modalidade"] != res["modality"]:
                    df.at[idx, "modalidade"] = res["modality"]
                    adjusted_modality_count += 1

        if non_tech_indices:
            df = df.drop(index=non_tech_indices)

        return df
