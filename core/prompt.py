import os
import json
from datetime import datetime
from .expander import RoleExpander

def prompt_user_profile(output_dir: str = None, non_interactive: bool = False,
                        default_role: str = "Analista de Infraestrutura", default_seniority: str = "Any") -> dict:
    """
    Solicita interativamente ao usuário a definição dos parâmetros de busca,
    gera o perfil de expansão do cargo e salva o perfil em JSON.
    """
    expander = RoleExpander()

    if non_interactive:
        target_role = default_role
        seniority = default_seniority
        skills = []
        exclusions = []
        geography_choice = "Ambos"
        freshness_hours = 24
        search_mode = "Express"
    else:
        print("\n" + "=" * 72)
        print("  AURAJOBS - MOTOR AUTÔNOMO DE INTELIGÊNCIA DE CARREIRAS E VAGAS")
        print("=" * 72)
        print("Defina os parâmetros da sua busca abaixo (pressione Enter para valores padrão):\n")

        # 1. Cargo alvo
        role_input = input(f"> Cargo ou área de atuação (ex: Analista de Infraestrutura, Analista de TI, Analista de Tecnologia) [padrão: {default_role}]: ").strip()
        target_role = role_input if role_input else default_role

        # 2. Senioridade
        print("\n> Nível de senioridade:")
        print("  [1] Qualquer nível / Todos os níveis [Padrão]")
        print("  [2] Estágio / Trainee / Iniciante")
        print("  [3] Júnior (0-2 anos)")
        print("  [4] Pleno (2-5 anos)")
        print("  [5] Sênior (5+ anos)")
        print("  [6] Especialista")
        print("  [7] Líder Técnico / Coordenação")
        print("  [8] Gerente / Diretor")
        sen_choice = input("> Selecione a senioridade [1-8 ou digite o nome, padrão: 1]: ").strip().lower()
        sen_map = {
            "1": "Any",
            "2": "Estágio",
            "3": "Júnior",
            "4": "Pleno",
            "5": "Sênior",
            "6": "Especialista",
            "7": "Líder",
            "8": "Gerente",
            "qualquer": "Any",
            "estagio": "Estágio",
            "estágio": "Estágio",
            "junior": "Júnior",
            "júnior": "Júnior",
            "jr": "Júnior",
            "pleno": "Pleno",
            "pl": "Pleno",
            "senior": "Sênior",
            "sênior": "Sênior",
            "sr": "Sênior",
        }
        seniority = sen_map.get(sen_choice, sen_choice.capitalize() if sen_choice else "Any")

        # 3. Habilidades
        skills_input = input("\n> Habilidades para impulsionar a pontuação (separadas por vírgula, ex: Linux, AWS, Redes, Docker, ITIL): ").strip()
        skills = [s.strip().lower() for s in skills_input.split(",") if s.strip()] if skills_input else []

        # 4. Exclusões
        excl_input = input("\n> Exclusões de cargos (separadas por vírgula, ex: Estágio, Vendas, Telemarketing): ").strip()
        exclusions = [e.strip().lower() for e in excl_input.split(",") if e.strip()] if excl_input else []

        # 5. Cenário de busca
        print("\n> Cenário de busca:")
        print("  [1] Ambos: Londrina/PR (Presencial, Híbrido ou Remoto) + Brasil (Somente Remoto) [Padrão]")
        print("  [2] Apenas Vagas Remotas no Brasil (100% Home Office)")
        print("  [3] Apenas Vagas em Londrina/PR (Presencial, Híbrido ou Remoto)")
        geo_choice = input("> Selecione o cenário [1-3, padrão: 1]: ").strip()
        geo_map = {"1": "Ambos", "2": "Remoto", "3": "Londrina"}
        geography_choice = geo_map.get(geo_choice, "Ambos")

        # 6. Janela de publicação
        print("\n> Janela de publicação: [1] Últimas 24 Horas [Padrão]  [2] Últimas 48 Horas  [3] Últimas 72 Horas")
        fresh_choice = input("> Selecione o período [1-3, padrão: 1]: ").strip()
        fresh_map = {"1": 24, "2": 48, "3": 72}
        freshness_hours = fresh_map.get(fresh_choice, 24)

        # 7. Modo de busca
        print("\n> Modo de Execução:")
        print("  [1] Expresso (APIs Instantâneas + Principais Polos do Brasil, ~1-2 min) [Padrão]")
        print("  [2] Varredura Completa (APIs + Rotação Exaustiva de Cidades, ~5-10 min)")
        mode_choice = input("> Selecione o modo [1-2, padrão: 1]: ").strip()
        search_mode = "Deep" if mode_choice == "2" else "Express"

        print("\n" + "-" * 72)
        print(f"Cargo Alvo:        {target_role}")
        print(f"Senioridade:       {seniority}")
        print(f"Habilidades Chave: {', '.join(skills) if skills else 'Padrão do cargo'}")
        print(f"Geografia:         {geography_choice}")
        print(f"Janela de Tempo:   Últimas {freshness_hours} horas")
        print(f"Modo de Busca:     {search_mode}")
        print("-" * 72)

        confirm = input("\n> Iniciar busca de vagas? [S/n]: ").strip().lower()
        if confirm and confirm not in ["s", "sim", "y", "yes"]:
            print("Busca cancelada pelo usuário.")
            return None

    # Generate the comprehensive expanded profile
    profile = expander.build_search_profile(
        target_role=target_role,
        seniority=seniority,
        skills=skills,
        exclusions=exclusions
    )
    profile["geography_choice"] = geography_choice
    profile["freshness_hours"] = freshness_hours
    profile["search_mode"] = search_mode


    # Save profile to logs directory to keep output directory clean for the user's jobs CSV
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    profile_path = os.path.join(logs_dir, f"SEARCH_PROFILE_{timestamp}.json")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    profile["saved_profile_path"] = profile_path

    return profile

