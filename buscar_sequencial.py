#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AuraJobs - Busca Sequencial Automatizada e Consolidação Única
Executa em sequência a varredura para os três cargos alvos:
  1. Analista de Infraestrutura (Londrina/PR Presencial/Híbrido/Remoto + Brasil Remoto)
  2. Analista de TI (Londrina/PR Presencial/Híbrido/Remoto + Brasil Remoto)
  3. Analista de Tecnologia (Londrina/PR Presencial/Híbrido/Remoto + Brasil Remoto)

Consolida todas as vagas encontradas em UMA ÚNICA PLANILHA EXCEL (.xlsx)
contendo dia da semana, data e hora, e APAGA todas as planilhas individuais/anteriores.
"""

import os
import sys
import time
import argparse
import subprocess
from datetime import datetime
import pandas as pd

# Garante que o diretório raiz do projeto esteja no PYTHONPATH
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.deduper import deduplicate_jobs
from core.exporters import OutputExporter

ROLES_DEFAULT = [
    "Analista de Infraestrutura",
    "Analista de TI",
    "Analista de Tecnologia",
]

DIAS_SEMANA = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}

def parse_args():
    parser = argparse.ArgumentParser(
        description="AuraJobs - Busca Sequencial e Consolidação Única com Data e Dia da Semana"
    )
    parser.add_argument(
        "--geo",
        type=str,
        default="Ambos",
        choices=["Ambos", "Remoto", "Londrina"],
        help="Cenário de busca: Ambos (Londrina/PR Presencial/Híbrido/Remoto + Brasil Remoto), Remoto ou Londrina [padrão: Ambos]"
    )
    parser.add_argument(
        "--freshness",
        type=int,
        default=48,
        help="Idade máxima da postagem em horas [padrão: 48]"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="Express",
        choices=["Express", "Deep"],
        help="Modo de busca: Express (~1-2 min por cargo) ou Deep (~5-10 min por cargo) [padrão: Express]"
    )
    parser.add_argument(
        "--max-searches",
        type=int,
        default=None,
        help="Limite máximo de consultas por cargo (opcional)"
    )
    parser.add_argument(
        "--seniority",
        type=str,
        default="Any",
        help="Nível de senioridade para os cargos [padrão: Any]"
    )
    parser.add_argument(
        "--broad-tech",
        dest="broad_tech",
        action="store_true",
        default=True,
        help="Aplica filtro amplo de Tecnologia para aceitar qualquer vaga da área de TI [padrão: True]"
    )
    parser.add_argument(
        "--strict-role",
        dest="broad_tech",
        action="store_false",
        help="Força filtro estrito de cargo em vez do filtro amplo de tecnologia"
    )
    return parser.parse_args()

def list_excel_files_in_output(output_dir: str) -> set:
    if not os.path.exists(output_dir):
        return set()
    return {
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.startswith("AURAJOBS_") and f.endswith(".xlsx")
    }

def main():
    args = parse_args()
    output_dir = os.path.join(BASE_DIR, "output")
    os.makedirs(output_dir, exist_ok=True)

    start_batch_time = datetime.now()
    batch_start_ts = time.time()
    dia_semana_nome = DIAS_SEMANA.get(start_batch_time.weekday(), "")
    data_formatada = start_batch_time.strftime("%d/%m/%Y")
    hora_formatada = start_batch_time.strftime("%H:%M:%S")

    print("\n" + "=" * 80)
    print("  AURAJOBS - BUSCA SEQUENCIAL E CONSOLIDAÇÃO EM PLANILHA ÚNICA")
    print("=" * 80)
    print(f"  Data da Execução : {data_formatada} ({dia_semana_nome}) às {hora_formatada}")
    print(f"  Cenário Alvo     : {args.geo} (Londrina/PR: Presencial, Híbrido ou Remoto | Brasil: Somente Remoto)")
    print(f"  Janela de Tempo  : Últimas {args.freshness} Horas")
    print(f"  Modo de Execução : {args.mode.upper()}")
    print(f"  Filtro Aplicado  : {'TECNOLOGIA AMPLA (Qualquer vaga de TI)' if args.broad_tech else 'ESTRITO POR CARGO'}")
    print(f"  Cargos Agendados : {len(ROLES_DEFAULT)}")
    for i, role in enumerate(ROLES_DEFAULT, 1):
        print(f"    [{i}] {role}")
    print("=" * 80 + "\n")

    generated_temp_files = []

    for index, role in enumerate(ROLES_DEFAULT, 1):
        print("\n" + "#" * 80)
        print(f"  ETAPA [{index}/{len(ROLES_DEFAULT)}]: BUSCANDO VAGAS PARA '{role.upper()}'")
        print("#" * 80 + "\n")

        files_before = list_excel_files_in_output(output_dir)

        cmd = [
            sys.executable,
            os.path.join(BASE_DIR, "main.py"),
            "--role", role,
            "--seniority", args.seniority,
            "--geo", args.geo,
            "--freshness", str(args.freshness),
            "--mode", args.mode,
            "--non-interactive",
        ]

        if args.broad_tech:
            cmd.append("--broad-tech")

        if args.max_searches:
            cmd.extend(["--max-searches", str(args.max_searches)])

        role_start = time.time()
        max_attempts = 2
        success = False
        for attempt in range(1, max_attempts + 1):
            try:
                subprocess.run(cmd, check=True)
                role_duration = time.time() - role_start
                success = True

                files_after = list_excel_files_in_output(output_dir)
                new_files = list(files_after - files_before)

                if new_files:
                    generated_path = sorted(new_files)[-1]
                    generated_temp_files.append((role, generated_path))
                    print(f"\n[OK] Concluído '{role}' em {role_duration:.1f}s -> {os.path.basename(generated_path)}")
                else:
                    print(f"\n[AVISO] Concluído '{role}' em {role_duration:.1f}s, nenhum arquivo novo detectado.")
                break

            except subprocess.CalledProcessError as e:
                if attempt < max_attempts:
                    print(f"\n[RETRY] Falha na tentativa {attempt} para '{role}' (código: {e.returncode}). Tentando novamente em 5s...")
                    time.sleep(5)
                else:
                    print(f"\n[ERRO] Falha ao processar o cargo '{role}' após {max_attempts} tentativas (código: {e.returncode}).")
            except KeyboardInterrupt:
                print("\n\n[PARADA] Execução sequencial interrompida pelo usuário.")
                break

        if not success and isinstance(sys.exc_info()[1], KeyboardInterrupt):
            break

    # =========================================================================
    # CONSOLIDAÇÃO DOS DADOS EM UMA ÚNICA PLANILHA MESTRE
    # =========================================================================
    print("\n" + "=" * 80)
    print("  CONSOLIDANDO TODAS AS VAGAS EM UMA PLANILHA ÚNICA")
    print("=" * 80)

    all_dfs = []
    for role, file_path in generated_temp_files:
        try:
            df = pd.read_excel(file_path, sheet_name="Vagas")
            if not df.empty:
                df["cargo_busca"] = role
                all_dfs.append(df)
        except Exception as e:
            print(f"[!] Erro ao ler planilha temporária {file_path}: {e}")

    if all_dfs:
        combined_df = pd.concat(all_dfs, ignore_index=True)
        deduped_df = deduplicate_jobs(combined_df)
    else:
        deduped_df = pd.DataFrame()

    # Adiciona explicitamente o dia da semana e a data da busca em todas as linhas
    if not deduped_df.empty:
        deduped_df["data_busca"] = data_formatada
        deduped_df["dia_semana"] = dia_semana_nome
        deduped_df["horario_busca"] = hora_formatada

    exporter = OutputExporter(output_dir)
    consolidated_filepath = exporter.export_single_file(
        final_df=deduped_df,
        target_role="Consolidado_Infra_TI_Tecnologia",
        geography=args.geo,
        started=start_batch_time
    )

    print(f"  +--> Total de vagas consolidadas: {len(deduped_df)}")
    print(f"  +--> Planilha Única Criada     : {consolidated_filepath}")

    # =========================================================================
    # APAGAR TODAS AS OUTRAS PLANILHAS (MANTENDO APENAS A CONSOLIDADA)
    # =========================================================================
    print("\n" + "=" * 80)
    print("  LIMPANDO ARQUIVOS: APAGANDO TODAS AS OUTRAS PLANILHAS")
    print("=" * 80)

    deleted_count = 0
    consolidated_abs = os.path.abspath(consolidated_filepath)

    for fname in os.listdir(output_dir):
        if fname.endswith(".xlsx"):
            fpath = os.path.abspath(os.path.join(output_dir, fname))
            if fpath == consolidated_abs:
                continue
            try:
                os.remove(fpath)
                print(f"  [-] Apagado: {fname}")
                deleted_count += 1
            except Exception as e:
                print(f"  [!] Não foi possível apagar {fname}: {e}")

    print(f"  [OK] {deleted_count} planilha(s) individual(is)/anterior(es) apagada(s) com sucesso!")

    # =========================================================================
    # RESUMO FINAL DO LOTE
    # =========================================================================
    total_batch_duration = (time.time() - batch_start_ts) / 60
    print("\n" + "=" * 80)
    print("  RESUMO FINAL DA EXECUÇÃO")
    print("=" * 80)
    print(f"  Data da Coleta            : {data_formatada} ({dia_semana_nome})")
    print(f"  Horário da Coleta         : {hora_formatada}")
    print(f"  Tempo Total do Lote       : {total_batch_duration:.2f} minutos")
    print(f"  Cargos Processados        : {len(generated_temp_files)} de {len(ROLES_DEFAULT)}")
    print(f"  Total de Vagas Qualificadas: {len(deduped_df)}")
    if not deduped_df.empty and "cenario" in deduped_df.columns:
        cenarios_dict = deduped_df["cenario"].value_counts().to_dict()
        cenarios_desc = ", ".join(f"{count} {c}" for c, count in cenarios_dict.items())
        print(f"  Cenários Identificados    : {cenarios_desc}")

    print("\n  ÚNICA PLANILHA GERADA E MANTIDA:")
    print(f"  ==> {consolidated_filepath}")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
