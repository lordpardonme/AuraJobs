import os
import re
from datetime import datetime
import pandas as pd

class OutputExporter:
    """
    Exports a single, clean, consolidated Excel (.xlsx) file for the user's search
    with autofilters and adjusted column widths.
    """

    def __init__(self, output_dir: str = None):
        if output_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            output_dir = os.path.join(base_dir, "output")

        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export_single_file(self, final_df: pd.DataFrame, target_role: str,
                           geography: str, started: datetime, custom_filename: str = None) -> str:
        """
        Creates exactly ONE primary Excel (.xlsx) output file containing all relevant jobs
        matching the user's preferences, with day of week and formatted date.
        """
        dias_slug = {
            0: "segunda-feira",
            1: "terca-feira",
            2: "quarta-feira",
            3: "quinta-feira",
            4: "sexta-feira",
            5: "sabado",
            6: "domingo",
        }
        dias_nome = {
            0: "Segunda-feira",
            1: "Terça-feira",
            2: "Quarta-feira",
            3: "Quinta-feira",
            4: "Sexta-feira",
            5: "Sábado",
            6: "Domingo",
        }

        dia_slug = dias_slug.get(started.weekday(), "dia")
        date_str = started.strftime("%Y-%m-%d")
        time_str = started.strftime("%H-%M-%S")
        role_slug = re.sub(r"[^\w\-]", "_", target_role.strip()).strip("_")
        geo_slug = re.sub(r"[^\w\-]", "_", geography.strip()).strip("_")

        if custom_filename:
            filename = custom_filename if custom_filename.endswith(".xlsx") else f"{custom_filename}.xlsx"
        else:
            filename = f"AURAJOBS_{role_slug}_{geo_slug}_{date_str}_{dia_slug}_{time_str}.xlsx"

        filepath = os.path.join(self.output_dir, filename)

        if final_df is not None and not final_df.empty:
            final_df = final_df.copy()
            if "data_busca" not in final_df.columns:
                final_df["data_busca"] = started.strftime("%d/%m/%Y")
            if "dia_semana" not in final_df.columns:
                final_df["dia_semana"] = dias_nome.get(started.weekday(), "")
            if "horario_busca" not in final_df.columns:
                final_df["horario_busca"] = started.strftime("%H:%M:%S")

            # Reorder key columns to the front for optimal viewing
            priority_cols = [
                "cenario",
                "cargo_busca",
                "data_busca",
                "dia_semana",
                "horario_busca",
                "priority",
                "match_type",
                "match_score",
                "title",
                "company",
                "location",
                "region",
                "regime_contrato",
                "modalidade",
                "ai_evaluated",
                "ai_modality",
                "ai_tech_prob",
                "source",
                "job_url",
                "visa_status",
                "relocation_status",
                "age_bucket",
                "date_posted",
                "salary_min",
                "salary_max",
                "currency",
                "remote_status",
                "discovered_sources",
                "description",
            ]
            existing_cols = [c for c in priority_cols if c in final_df.columns]
            other_cols = [c for c in final_df.columns if c not in existing_cols]
            ordered_df = final_df[existing_cols + other_cols].copy()

            # Remove fuso horário para total compatibilidade com o formato Excel
            for col in ordered_df.select_dtypes(include=["datetimetz"]).columns:
                ordered_df[col] = ordered_df[col].dt.tz_localize(None)

            with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
                ordered_df.to_excel(writer, sheet_name="Vagas", index=False)
                worksheet = writer.sheets["Vagas"]

                # Ajustar largura das colunas e habilitar autofiltro
                for col_idx, col_name in enumerate(ordered_df.columns, 1):
                    max_len = max(len(str(col_name)), 10)
                    for val in ordered_df[col_name].head(50):
                        if pd.notna(val):
                            first_line = str(val).split("\n")[0]
                            max_len = max(max_len, min(len(first_line), 50))
                    col_letter = worksheet.cell(row=1, column=col_idx).column_letter
                    worksheet.column_dimensions[col_letter].width = min(max_len + 3, 50)

                worksheet.auto_filter.ref = worksheet.dimensions
        else:
            # Create an empty Excel file with headers
            empty_cols = [
                "cenario", "priority", "match_score", "title", "company", "location",
                "region", "regime_contrato", "modalidade", "source", "job_url", "visa_status", "date_posted"
            ]
            empty_df = pd.DataFrame(columns=empty_cols)
            with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
                empty_df.to_excel(writer, sheet_name="Vagas", index=False)

        return filepath
