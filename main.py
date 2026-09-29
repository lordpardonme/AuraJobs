import os
import sys
import time
import argparse
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

# Ensure terminal stdout/stderr handles UTF-8 cleanly without charmap crashes
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from core.prompt import prompt_user_profile
from core.scheduler import BalancedScheduler
from core.normalizer import normalize_dataframe
from core.classifier import RoleClassifier
from core.visa import detect_visa_sponsorship, detect_relocation, detect_contract_regime, detect_work_modality
from core.scorer import MatchScorer, calculate_age_hours
from core.deduper import deduplicate_jobs
from core.checkpoint import CheckpointManager
from core.exporters import OutputExporter
from core.ai_judge import TypeSafeJudge
from sources import MultiBoardAdapter, RemoteOKAdapter, RemotiveAdapter, HimalayasAdapter, ATSAdapter

def parse_args():
    parser = argparse.ArgumentParser(description="AuraJobs - Motor Autônomo de Inteligência de Carreiras e Agregação de Vagas")
    parser.add_argument("--role", type=str, default=None, help="Cargo ou família de funções (ex: 'Analista de Infraestrutura', 'Analista de TI')")
    parser.add_argument("--seniority", type=str, default="Any", help="Nível de senioridade (Any, Estágio, Júnior, Pleno, Sênior, Especialista, Líder, Gerente)")
    parser.add_argument("--geo", type=str, default="Ambos", choices=["Ambos", "Remoto", "Londrina", "All"], help="Cenário de busca: Ambos (Londrina/PR Presencial/Híbrido/Remoto + Brasil Remoto), Remoto ou Londrina")
    parser.add_argument("--freshness", type=int, default=24, help="Idade máxima da postagem em horas (padrão 24)")
    parser.add_argument("--mode", type=str, default="Express", choices=["Express", "Deep"], help="Modo de busca: Express (~1-2 min) ou Deep (~5-10 min)")
    parser.add_argument("--max-searches", type=int, default=None, help="Limite máximo de consultas")
    parser.add_argument("--max-runtime", type=int, default=None, help="Limite máximo de tempo de execução em minutos")
    parser.add_argument("--non-interactive", action="store_true", help="Executa diretamente com os argumentos fornecidos sem abrir prompt")
    parser.add_argument("--broad-tech", action="store_true", help="Aplica filtro amplo de Tecnologia para capturar qualquer oportunidade da área de TI")
    return parser.parse_args()

def format_progress_bar(current: int, total: int, bar_length: int = 20) -> str:
    fraction = min(1.0, current / total) if total > 0 else 0
    filled = int(bar_length * fraction)
    bar = "=" * filled + "-" * (bar_length - filled)
    return f"[{bar}] {int(fraction * 100)}%"

def classify_and_filter_scenario(df: pd.DataFrame, geography_choice: str = "Ambos") -> pd.DataFrame:
    """
    Classifica cada vaga estritamente nos critérios solicitados:
    1. 'Londrina/PR (Presencial / Híbrido / Remoto)': Vagas na cidade de Londrina e região metropolitana em qualquer modalidade.
    2. 'Remoto (Brasil)': Vagas em qualquer localidade do Brasil, mas estritamente 100% Remotas.

    Descarta qualquer vaga presencial ou híbrida fora de Londrina, e vagas remotas restritas a outros países.
    """
    if df.empty:
        return df

    londrina_keywords = ["londrina", "cambe", "cambé", "ibipora", "ibiporã", "rolandia", "rolândia"]
    foreign_only_keywords = ["us only", "usa only", "united states", "canada", "europe only", "emea only", "uk only", "germany"]

    cenarios = []
    keep_indices = []

    geo_filter = str(geography_choice).strip().lower()

    for idx, row in df.iterrows():
        loc = str(row.get("location", "")).lower()
        title = str(row.get("title", "")).lower()
        desc = str(row.get("description", "")).lower()
        modalidade = str(row.get("modalidade", "")).capitalize()
        full_text = f"{loc} {title} {desc}"

        # Identifica se é baseada em Londrina e região metropolitana
        londrina_direct = any(k in loc for k in londrina_keywords)
        londrina_in_text = any(phrase in full_text for phrase in [
            "em londrina", "de londrina", "londrina/pr", "londrina - pr", "londrina pr",
            "cambé", "cambe", "ibiporã", "ibipora", "rolândia", "rolandia"
        ])
        is_londrina = londrina_direct or (londrina_in_text and any(k in loc for k in ["paraná", "parana", "pr", "brasil", "brazil", ""]))

        scenario = None

        if is_londrina:
            # Londrina e região metropolitana: aceita Presencial, Híbrido ou Remoto
            mod_label = modalidade if modalidade in ["Presencial", "Híbrido", "Remoto"] else "Presencial"
            scenario = f"Londrina/PR ({mod_label})"
        elif modalidade == "Remoto":
            # Brasil fora de Londrina: SOMENTE REMOTO
            # Rejeita vagas remotas restritas a outros países
            is_foreign_restricted = any(fk in full_text for fk in foreign_only_keywords) and not (
                "brasil" in full_text or "brazil" in full_text or "latam" in full_text or "latin america" in full_text
            )
            if not is_foreign_restricted:
                scenario = "Remoto (Brasil)"
        else:
            # Vaga presencial ou híbrida fora de Londrina (ex: São Paulo, Belo Horizonte, Curitiba) -> descarta!
            continue

        if scenario is None:
            continue

        # Aplica filtro de seleção do usuário
        if geo_filter in ["remoto", "remote"]:
            if modalidade != "Remoto":
                continue
        elif geo_filter in ["londrina"]:
            if not is_londrina:
                continue

        keep_indices.append(idx)
        cenarios.append(scenario)

    filtered_df = df.loc[keep_indices].copy()
    filtered_df["cenario"] = cenarios
    return filtered_df

def process_results(raw_df: pd.DataFrame, profile: dict, scorer: MatchScorer, classifier: RoleClassifier, max_hours: int) -> pd.DataFrame:
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    df = normalize_dataframe(raw_df)

    df["date_posted"] = pd.to_datetime(df["date_posted"], errors="coerce", utc=True)
    df["age_hours"] = df["date_posted"].apply(calculate_age_hours)

    # Keep jobs where age_hours is within max_hours or where date_posted was not parsed
    df = df[
        df["age_hours"].isna()
        | ((df["age_hours"] >= 0) & (df["age_hours"] <= max_hours))
    ].copy()

    if df.empty:
        return df

    strict_df = classifier.filter_dataframe(df)

    if strict_df.empty and not df.empty:
        # Modo de Fallback Gracioso:
        # Se a filtragem estrita resultar em 0 vagas, destaca as melhores da área ampla sem exclusões rígidas
        print("\n[!] Aviso: Nenhuma vaga atendeu aos critérios estritos de título.")
        print("    --> Ativando Modo de Fallback Gracioso: Exibindo melhores oportunidades da área...")

        fallback_mask = df["title"].apply(lambda t: not any(neg in str(t).lower() for neg in classifier.negative_terms))
        fallback_df = df[fallback_mask].copy()

        if not fallback_df.empty:
            df = fallback_df
            df["match_type"] = "CORRESPONDÊNCIA AMPLA"
        else:
            df = strict_df
    else:
        df = strict_df.copy()
        df["match_type"] = "CORRESPONDÊNCIA EXATA"

    if df.empty:
        return df

    visa_results = df.apply(lambda r: detect_visa_sponsorship(r["title"], r["description"]), axis=1)
    df["visa_status"] = [v[0] for v in visa_results]
    df["visa_evidence"] = [v[1] for v in visa_results]

    relo_results = df.apply(lambda r: detect_relocation(r["title"], r["description"]), axis=1)
    df["relocation_status"] = [rel[0] for rel in relo_results]
    df["relocation_evidence"] = [rel[1] for rel in relo_results]

    # Detecção de regime de contratação (CLT, PJ, Estágio) e modalidade (Remoto, Híbrido, Presencial)
    df["regime_contrato"] = df.apply(lambda r: detect_contract_regime(r["title"], r["description"]), axis=1)
    df["modalidade"] = df.apply(lambda r: detect_work_modality(r["title"], r["description"], r["location"], r.get("is_remote")), axis=1)

    # Refinamento Semântico com TypeSafe AI (System One Jev) se configurado
    try:
        judge = TypeSafeJudge()
        if judge.is_available():
            print("  --> [TypeSafe AI] Refinando modalidade e adequação técnica via modelo Jev...")
            df = judge.refine_dataframe(df)
    except Exception as e:
        print(f"  [!] Aviso: Falha ao executar refinamento TypeSafe AI: {e}")

    # Filtragem e classificação estrita dos dois cenários solicitados
    geography_choice = profile.get("geography_choice", "Ambos")
    df = classify_and_filter_scenario(df, geography_choice)
    if df.empty:
        return df

    df["match_score"] = df.apply(
        lambda r: scorer.calculate_score(
            title=r["title"],
            description=r["description"],
            age_hours=r["age_hours"],
            visa_status=r["visa_status"],
            relocation_status=r["relocation_status"]
        ),
        axis=1
    )

    df["priority"] = df.apply(
        lambda r: scorer.assign_priority(
            age_hours=r["age_hours"],
            visa_status=r["visa_status"]
        ),
        axis=1
    )

    df["age_bucket"] = df["age_hours"].apply(
        lambda h: f"< {max_hours}H (FILTRO DA PLATAFORMA)" if pd.isna(h) or h is None
        else ("0-24 HORAS" if h <= 24 else "24-72 HORAS")
    )

    df = deduplicate_jobs(df)

    priority_order = {
        "URGENTE - VISTO": 0,
        "URGENTE - VISA": 0,
        "URGENTE - NOVA": 1,
        "URGENTE - NEW": 1,
        "RECENTE": 2,
        "FRESH": 2,
        "ÚLTIMAS 72H": 3,
        "LAST 72H": 3,
    }
    df["_p_rank"] = df["priority"].map(priority_order).fillna(9)
    df = df.sort_values(
        by=["_p_rank", "match_score", "age_hours"],
        ascending=[True, False, True]
    ).drop(columns=["_p_rank"], errors="ignore").reset_index(drop=True)

    return df

def main():
    args = parse_args()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "output")
    checkpoint_dir = os.path.join(base_dir, "checkpoints")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(checkpoint_dir, exist_ok=True)

    # 1. Obter Perfil de Busca
    if args.non_interactive:
        profile = prompt_user_profile(
            output_dir=output_dir,
            non_interactive=True,
            default_role=args.role or "Analista de Infraestrutura",
            default_seniority=args.seniority or "Any"
        )
        if args.geo != "All":
            profile["geography_choice"] = args.geo
        if args.freshness:
            profile["freshness_hours"] = args.freshness
        profile["search_mode"] = args.mode or "Express"
    else:
        profile = prompt_user_profile(output_dir=output_dir, default_role=args.role or "Analista de Infraestrutura")
        if not profile:
            return

    # 2. Inicializar Agendador e Orçamentos
    scheduler = BalancedScheduler()
    max_searches = args.max_searches or scheduler.max_searches
    max_runtime = args.max_runtime or scheduler.max_runtime_minutes
    max_hours = profile.get("freshness_hours", scheduler.settings.get("max_hours", 24))
    geography_choice = profile.get("geography_choice", "All")
    search_mode = profile.get("search_mode", "Express")

    queues, counts = scheduler.generate_execution_queues(
        search_terms=profile["search_terms"],
        geography_choice=geography_choice,
        mode=search_mode
    )

    total_scheduled = sum(counts.values())
    target_searches = min(max_searches, total_scheduled)

    # Painel inicial do terminal
    print("\n" + "=" * 78)
    print("  AURAJOBS - BUSCA DE VAGAS EM TEMPO REAL")
    print("=" * 78)
    print(f"  Cargo Alvo      : {profile['target_role']} ({profile['seniority']})")
    print(f"  Janela de Tempo : Últimas {max_hours} Horas")
    print(f"  Região Alvo     : {geography_choice}")
    print(f"  Modo de Busca   : {search_mode.upper()} ({target_searches} consultas regionais planejadas)")
    print(f"  Fontes Diretas  : RemoteOK, Remotive, Himalayas, Ashby ATS, Greenhouse ATS")
    print(f"  Scrapers        : LinkedIn, Indeed, Google Jobs, Glassdoor")
    print(f"  Limites         : Máx {max_searches} buscas | Máx {max_runtime} mins")
    print("=" * 78 + "\n")

    # 3. Ponto de Restauração (Checkpoint)
    checkpoint_mgr = CheckpointManager(checkpoint_dir)
    prev_state, checkpoint_df = checkpoint_mgr.load()

    collected_dfs = []
    completed_keys = set()
    search_count = 0
    total_jobs_found = 0

    if prev_state and not checkpoint_df.empty and not args.non_interactive:
        resume_prompt = input(f"> Encontrado ponto de restauração com {len(checkpoint_df)} vagas ({prev_state.get('updated_at')}). Continuar busca anterior? [S/n]: ").strip().lower()
        if resume_prompt in ["", "s", "sim", "y"]:
            collected_dfs.append(checkpoint_df)
            completed_keys = set(prev_state.get("completed_keys", []))
            search_count = prev_state.get("search_count", 0)
            total_jobs_found = len(checkpoint_df)
            print(f"[OK] Busca retomada: {total_jobs_found} vagas anteriores carregadas.\n")

    # 4. Inicializar Componentes Centrais
    delay = 1.5 if search_mode == "Express" else scheduler.settings.get("request_delay_seconds", 2.5)
    adapter = MultiBoardAdapter(request_delay=delay)
    positive_terms = list(profile.get("positive_title_terms", []))
    if getattr(args, "broad_tech", False) or str(profile.get("target_role", "")).lower() in [
        "tecnologia", "ti", "qualquer vaga de tecnologia", "tech", "tecnologia geral", "ti geral"
    ]:
        from core.expander import RoleExpander
        expander = RoleExpander()
        tech_preset = expander.find_preset("tecnologia")
        if tech_preset:
            for pt in tech_preset.get("positive_title_terms", []):
                if pt not in positive_terms:
                    positive_terms.append(pt)

    classifier = RoleClassifier(
        positive_terms=positive_terms,
        negative_terms=profile.get("negative_title_terms", [])
    )
    scorer = MatchScorer(
        target_role=profile["target_role"],
        skills=profile.get("skills", []),
        seniority=profile.get("seniority", "Any")
    )
    exporter = OutputExporter(output_dir)

    start_time = time.time()
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    stop_reason = "CONCLUIDO_COM_SUCESSO"

    # =========================================================================
    # ETAPA 1: APIS PÚBLICAS INSTANTÂNEAS & ATS DIRETO
    # =========================================================================
    if geography_choice.lower() != "londrina":
        print("=" * 78)
        print("  ETAPA 1: APIS INSTANTÂNEAS & ATS DIRETO (ASHBY + GREENHOUSE)")
        print("=" * 78)
        print("Consultando RemoteOK, Remotive, Himalayas, Ashby e Greenhouse em paralelo...")

        api_start = time.time()
        rok = RemoteOKAdapter()
        rem = RemotiveAdapter()
        him = HimalayasAdapter()
        ats = ATSAdapter()

        with ThreadPoolExecutor(max_workers=4) as executor:
            f_rok = executor.submit(rok.fetch_jobs, profile["target_role"], profile.get("positive_title_terms", []))
            f_rem = executor.submit(rem.fetch_jobs, profile["target_role"])
            f_him = executor.submit(him.fetch_jobs, profile["target_role"], profile.get("positive_title_terms", []))
            f_ats = executor.submit(ats.fetch_all_ats, profile["target_role"], profile.get("positive_title_terms", []))

            df_rok = f_rok.result()
            df_rem = f_rem.result()
            df_him = f_him.result()
            df_ats = f_ats.result()

        api_dfs = [d for d in [df_rok, df_rem, df_him, df_ats] if not d.empty]
        if api_dfs:
            combined_api = pd.concat(api_dfs, ignore_index=True)
            collected_dfs.append(combined_api)
            total_jobs_found += len(combined_api)

        api_time = time.time() - api_start
        print(f"  +--> RemoteOK   : {len(df_rok)} vagas")
        print(f"  +--> Remotive   : {len(df_rem)} vagas")
        print(f"  +--> Himalayas  : {len(df_him)} vagas")
        print(f"  +--> ATS Direto : {len(df_ats)} vagas (Nubank, QuintoAndar, Loggi, Stripe, etc.)")
        print(f"  [OK] Ingeridas {total_jobs_found} vagas verificadas em {api_time:.1f}s!\n")
    else:
        print("=" * 78)
        print("  ETAPA 1: PULANDO APIS REMOTAS (Cenário focado exclusivamente em Londrina/PR)")
        print("=" * 78 + "\n")

    # =========================================================================
    # ETAPA 2: VARREDURA REGIONAL (LINKEDIN, INDEED, GOOGLE, GLASSDOOR)
    # =========================================================================
    print("=" * 78)
    print(f"  ETAPA 2: VARREDURA REGIONAL ({search_mode.upper()})")
    print("=" * 78)

    active_regions = list(queues.keys())
    finished_regions = {r: (counts.get(r, 0) == 0) for r in active_regions}

    try:
        while not all(finished_regions.values()):
            elapsed = (time.time() - start_time) / 60
            if elapsed >= max_runtime:
                stop_reason = "LIMITE_TEMPO_ATINGIDO"
                print(f"\n[!] Atingido tempo limite de execução ({max_runtime} minutos).")
                break
            if search_count >= target_searches:
                stop_reason = "LIMITE_BUSCAS_ATINGIDO"
                print(f"\n[!] Concluídas todas as {target_searches} buscas regionais planejadas.")
                break

            progressed = False
            for region in active_regions:
                if finished_regions[region]:
                    continue

                try:
                    item = next(queues[region])
                except StopIteration:
                    finished_regions[region] = True
                    continue

                item_key = f"{item['region']}_{item['location']}_{item['term']}_{item['site']}"
                if item_key in completed_keys:
                    continue

                progressed = True
                search_count += 1
                elapsed = (time.time() - start_time) / 60
                pct = int((search_count / target_searches) * 100) if target_searches else 0

                # Linha de status formatada
                print(f"[{search_count:03d}/{target_searches:03d} | {pct:2d}%] Tempo: {elapsed:4.1f}m | Vagas: {total_jobs_found:3d} | {item['site'].upper():<8} | {item['location']:<20} | \"{item['term']}\"")

                result = adapter.search_single_site(
                    site=item["site"],
                    term=item["term"],
                    location=item["location"],
                    region=item["region"],
                    country=item.get("country", ""),
                    hours_old=max_hours,
                    results_wanted=scheduler.settings.get("results_per_site", 25)
                )

                if result is not None and not result.empty:
                    found_count = len(result)
                    total_jobs_found += found_count
                    collected_dfs.append(result)
                    print(f"       +--> [OK] Encontradas {found_count} vagas! (Total acumulado: {total_jobs_found})")

                completed_keys.add(item_key)

                # Atualização de estimativa a cada 15 buscas
                if search_count % 15 == 0 and search_count < target_searches:
                    bar = format_progress_bar(search_count, target_searches)
                    avg_rate = search_count / max(0.1, elapsed)
                    est_rem = (target_searches - search_count) / max(0.1, avg_rate)
                    print("  " + "-" * 74)
                    print(f"   STATUS: {bar} | Restante Est.: ~{est_rem:.1f} mins | Total Vagas: {total_jobs_found}")
                    print("  " + "-" * 74)

                # Checkpoint periódico
                if search_count % 10 == 0 and collected_dfs:
                    current_raw = pd.concat(collected_dfs, ignore_index=True)
                    checkpoint_mgr.save(current_raw, search_count, completed_keys, session_id)

            if not progressed:
                break

    except KeyboardInterrupt:
        stop_reason = "INTERROMPIDO_PELO_USUARIO"
        print("\n\n[PARADA] Busca interrompida pelo usuário (Ctrl+C). Finalizando processamento dos dados coletados...")

    except Exception as e:
        stop_reason = f"ERRO_{type(e).__name__}"
        print(f"\n[ERRO] {e}")
        traceback.print_exc()

    # =========================================================================
    # PROCESSAMENTO E EXPORTAÇÃO EM UM ÚNICO ARQUIVO EXCEL (.XLSX)
    # =========================================================================
    runtime_minutes = (time.time() - start_time) / 60
    raw_combined = pd.concat(collected_dfs, ignore_index=True) if collected_dfs else pd.DataFrame()

    print("\n" + "=" * 78)
    print("  NORMALIZANDO, PONTUANDO E FILTRANDO RESULTADOS")
    print("=" * 78)

    final_df = process_results(raw_combined, profile, scorer, classifier, max_hours)

    output_filepath = exporter.export_single_file(
        final_df=final_df,
        target_role=profile["target_role"],
        geography=profile["geography_choice"],
        started=datetime.fromtimestamp(start_time)
    )

    if stop_reason in ["CONCLUIDO_COM_SUCESSO", "LIMITE_BUSCAS_ATINGIDO"]:
        checkpoint_mgr.clear()

    # Resumo Final (exibido apenas no terminal)
    print("\n" + "=" * 78)
    print("  RESUMO DA EXECUÇÃO")
    print("=" * 78)
    print(f"  Cargo Alvo                 : {profile['target_role']} ({profile['seniority']})")
    print(f"  Região Alvo                : {profile['geography_choice']}")
    print(f"  Modo de Busca              : {search_mode.upper()}")
    print(f"  Status                     : {stop_reason}")
    print(f"  Buscas Realizadas          : {search_count}")
    print(f"  Tempo Total                : {runtime_minutes:.2f} minutos")
    print(f"  Total de Vagas Ingeridas   : {len(raw_combined)}")
    print(f"  Vagas Qualificadas Finais  : {len(final_df)}")
    if not final_df.empty and "cenario" in final_df.columns:
        cenarios_dict = final_df["cenario"].value_counts().to_dict()
        cenarios_desc = ", ".join(f"{count} {c}" for c, count in cenarios_dict.items())
        print(f"  Cenários Identificados     : {cenarios_desc}")
    if not final_df.empty and "match_type" in final_df.columns:
        match_types = final_df["match_type"].value_counts().to_dict()
        match_desc = ", ".join(f"{count} {mtype}" for mtype, count in match_types.items())
        print(f"  Classificação de Match     : {match_desc}")
    if not final_df.empty and "regime_contrato" in final_df.columns:
        regimes = final_df["regime_contrato"].value_counts().to_dict()
        regimes_desc = ", ".join(f"{count} {reg}" for reg, count in regimes.items())
        print(f"  Regimes Identificados      : {regimes_desc}")
    if not final_df.empty and "modalidade" in final_df.columns:
        modalidades = final_df["modalidade"].value_counts().to_dict()
        mod_desc = ", ".join(f"{count} {mod}" for mod, count in modalidades.items())
        print(f"  Modalidades                : {mod_desc}")
    if not final_df.empty and "visa_status" in final_df.columns:
        visa_count = len(final_df[final_df["visa_status"].isin(["SPONSORSHIP MENTIONED", "VISTO MENCIONADO"])])
        print(f"  Visto / Realocação         : {visa_count}")

    if not final_df.empty:
        print("\nMELHORES OPORTUNIDADES ENCONTRADAS:")
        print("-" * 78)
        cols = ["cenario", "priority", "match_type", "match_score", "regime_contrato", "modalidade", "title", "company", "location", "job_url"]
        cols = [c for c in cols if c in final_df.columns]
        print(final_df[cols].head(15).to_string(index=False))

    print("\nARQUIVO FINAL GERADO:")
    print(f"  ==> {output_filepath}")
    print("=" * 78 + "\n")

if __name__ == "__main__":
    main()
