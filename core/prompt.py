import os
import json
from datetime import datetime
from .expander import RoleExpander

def prompt_user_profile(output_dir: str = None, non_interactive: bool = False,
                        default_role: str = "Product Designer", default_seniority: str = "Any") -> dict:
    """
    Interactively prompts the user to define their search parameters,
    builds the role expansion profile, and saves the profile to JSON.
    """
    expander = RoleExpander()

    if non_interactive:
        target_role = default_role
        seniority = default_seniority
        skills = []
        exclusions = []
        geography_choice = "All"
        freshness_hours = 72
        search_mode = "Express"
    else:
        print("\n" + "=" * 70)
        print("  AURAJOBS - AUTONOMOUS CAREER INTELLIGENCE ENGINE")
        print("=" * 70)
        print("Define your target job parameters below (press Enter for defaults):\n")

        # 1. Role family
        role_input = input(f"> Enter target job family [default: {default_role}]: ").strip()
        target_role = role_input if role_input else default_role

        # 2. Seniority
        print("\n> Seniority level:")
        print("  [1] Any / All Levels [Default]")
        print("  [2] Intern / Trainee / Student")
        print("  [3] Junior / Entry-Level (0-2 yrs)")
        print("  [4] Mid-Level / Associate (2-5 yrs)")
        print("  [5] Senior (5+ yrs)")
        print("  [6] Staff")
        print("  [7] Lead / Team Lead")
        print("  [8] Principal / Director / VP")
        sen_choice = input("> Select seniority [1-8 or type name, default: 1]: ").strip().lower()
        sen_map = {
            "1": "Any",
            "2": "Intern",
            "3": "Junior",
            "4": "Mid-Level",
            "5": "Senior",
            "6": "Staff",
            "7": "Lead",
            "8": "Principal",
        }
        seniority = sen_map.get(sen_choice, sen_choice.capitalize() if sen_choice else "Any")

        # 3. Skills
        skills_input = input("\n> Optional skills to boost (comma-separated, e.g. Figma, SaaS, B2B): ").strip()
        skills = [s.strip().lower() for s in skills_input.split(",") if s.strip()] if skills_input else []

        # 4. Exclusions
        excl_input = input("\n> Additional role exclusions (comma-separated, e.g. Graphic Design): ").strip()
        exclusions = [e.strip().lower() for e in excl_input.split(",") if e.strip()] if excl_input else []

        # 5. Geography
        print("\n> Geographies:")
        print("  [1] India + Middle East + Global (Balanced Allocation) [Default]")
        print("  [2] India Only")
        print("  [3] Middle East Only")
        print("  [4] Global Only")
        geo_choice = input("> Select geography [1-4]: ").strip()
        geo_map = {"1": "All", "2": "India", "3": "Middle East", "4": "Global"}
        geography_choice = geo_map.get(geo_choice, "All")

        # 6. Freshness
        print("\n> Freshness window: [1] 72 Hours (Default)  [2] 24 Hours  [3] 48 Hours")
        fresh_choice = input("> Select freshness [1-3]: ").strip()
        fresh_map = {"1": 72, "2": 24, "3": 48}
        freshness_hours = fresh_map.get(fresh_choice, 72)

        # 7. Speed / Search Mode
        print("\n> Search Mode:")
        print("  [1] Express (Instant APIs + Top Regional Hubs, ~1-2 mins) [Default]")
        print("  [2] Deep Scan (Instant APIs + Full Exhaustive City Rotation, ~5-10 mins)")
        mode_choice = input("> Select mode [1-2]: ").strip()
        search_mode = "Deep" if mode_choice == "2" else "Express"

        print("\n" + "-" * 70)
        print(f"Target Role:    {target_role}")
        print(f"Seniority:      {seniority}")
        print(f"Key Skills:     {', '.join(skills) if skills else 'Preset defaults'}")
        print(f"Geography:      {geography_choice}")
        print(f"Freshness:      Last {freshness_hours} hours")
        print(f"Search Mode:    {search_mode}")
        print("-" * 70)

        confirm = input("\n> Start search? [Y/n]: ").strip().lower()
        if confirm and confirm != "y":
            print("Search cancelled by user.")
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

