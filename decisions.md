# AuraJobs Architecture, Execution Flow & Decision Records

> **Document Version**: 1.0  
> **Repository**: [lordpardonme/AuraJobs](https://github.com/lordpardonme/AuraJobs)  
> **Last Updated**: 2026-09-13  
> **Purpose**: Maintain an auditable, transparent engineering log of every architectural decision, library selection rationale, end-to-end execution flow trace, and codebase modification.

---

## 1. Architectural Decision Records (ADRs)

### ADR-001: Rebranding from "JobSpy" to "AuraJobs"
* **Context**: The original repository and script names referenced `JobSpy` (an underlying open-source scraping library `python-jobspy`).
* **Decision**: Rebrand the top-level identity, batch launchers, CLI banners, exported files, and source modules to **AuraJobs: Autonomous Career Intelligence Engine**, while keeping `python-jobspy` strictly as an internal dependency.
* **Why This Approach?**:
  - Distinguishes between the *library* (`python-jobspy`) and the *system* (an autonomous engine with multi-region scheduling, direct ATS integrations, visa detection, and deduplication).
  - Establishes a distinct, professional open-source brand identity on GitHub (`lordpardonme/AuraJobs`).

---

### ADR-002: Adapter-Based Multi-Board Wrapper (`MultiBoardAdapter`)
* **Context**: The engine previously imported `JobSpyAdapter` directly, tightly coupling the pipeline to a single library.
* **Decision**: Created [`sources/multiboard_adapter.py`](file:///d:/JobSpy/sources/multiboard_adapter.py) with the `MultiBoardAdapter` class, keeping `JobSpyAdapter = MultiBoardAdapter` as a backward-compatibility alias. Updated [`config/sources.yaml`](file:///d:/JobSpy/config/sources.yaml) and [`core/scheduler.py`](file:///d:/JobSpy/core/scheduler.py) to read `multiboard`.
* **Why This Approach?**:
  - Adheres to the *Adapter Design Pattern*. The core execution loop interacts with a unified interface (`search_single_site`), insulating the scheduler and main engine from upstream API breaking changes.
  - Allows swapping or augmenting underlying scrapers (e.g., integrating Scrapling or Playwright) without modifying `main.py`.

---

### ADR-003: Strict vs. Graceful Fallback Mode (The "Zero-Match" Solution)
* **Context**: In real-world searches (e.g., `HR Transformation Specialist (Senior)` in India), the scraper ingested 298 candidate jobs, but strict title matching filtered all 298 jobs down to 0, producing an empty CSV file.
* **Decision**: Implemented a two-tier classification strategy in [`main.py`](file:///d:/JobSpy/main.py):
  1. **Strict Match Tier**: If jobs pass exact/token-set title criteria, output them tagged as `match_type: "EXACT MATCH"`.
  2. **Graceful Fallback Tier**: If strict matches == 0 but candidate jobs were retrieved, automatically activate fallback mode. Filter out hard negative exclusions (e.g., graphic design, intern), retain broad domain opportunities, tag them as `match_type: "BROAD DOMAIN MATCH"`, rank them by match score, and populate the CSV.
* **Why This Approach?**:
  - *User Experience Principle*: A user who spends 5 minutes running a deep scan across 60 searches should never walk away with an empty sheet when relevant domain jobs exist.
  - *Data Transparency*: Clear labeling (`EXACT MATCH` vs. `BROAD DOMAIN MATCH`) prevents misleading the user while preserving high-signal discovery.

---

### ADR-004: Token-Set & Anchor Matching over Literal Substring (`RoleClassifier`)
* **Context**: Real job titles use diverse word order and punctuation: *"Specialist - HR Transformation"*, *"Senior Specialist, HR Transformation"*, *"Lead Consultant - HR Transformation"*. The previous classifier did a literal substring check `if pos in title`, which failed because the words were separated by dashes or commas.
* **Decision**: Updated [`core/classifier.py`](file:///d:/JobSpy/core/classifier.py) to implement token-set matching:
  - Normalizes text and strips punctuation.
  - Strips generic level nouns (`specialist`, `consultant`, `manager`, `lead`, `analyst`, `associate`).
  - Verifies that core domain tokens (e.g. `{"hr", "transformation"}`) exist as a subset in the job title tokens.
* **Why This Approach?**:
  - Eliminates false negatives caused by formatting differences without introducing regex performance penalties.
  - Preserves strict rejection of unrelated roles (*"Senior HR Manager"*, *"HR Business Partner"*, *"Recruiter"*).

---

### ADR-005: Location-First Interleaved Round-Robin Scheduler
* **Context**: When 195 regional queries were subsampled down to a 60-search budget using `step = len(plan) / budget` (3.25), the stride caused a sampling bias that consistently skipped major cities (Bengaluru, Delhi, Noida, Hyderabad, Kochi).
* **Decision**: Restructured `build_round_robin_plan` in [`core/scheduler.py`](file:///d:/JobSpy/core/scheduler.py) to interleave location-first:
  - Loop through all 13 locations sequentially on round 1, shifting sites and search terms dynamically.
  - Repeat across subsequent rounds.
* **Why This Approach?**:
  - Mathematically guarantees that every configured location is searched at least 4 to 5 times in a 60-search run.
  - Eliminates geographic blind spots.

---

### ADR-006: Expansion of Non-Tech & HRIS Role Presets
* **Context**: The system originally contained only digital/tech presets (Product Design, Frontend, Software Engineering, Data Science). Users searching for business, operations, or HR roles fell back to unoptimized dynamic expansions.
* **Decision**: Added 6 comprehensive business & enterprise presets to [`config/roles.yaml`](file:///d:/JobSpy/config/roles.yaml):
  1. `product_management` (Product Manager, Technical PM, Group PM)
  2. `growth_marketing` (Growth Lead, Performance Marketing, PMM)
  3. `operations_strategy` (Operations Manager, BizOps, Strategy & Ops)
  4. `people_talent_hr` (Technical Recruiter, HRBP, Talent Acquisition)
  5. `sales_business_development` (Account Executive, SDR/BDR, Customer Success)
  6. `hris_hr_tech` (HRIS Specialist, HR Transformation, Workday Specialist, HR Operations)
* **Why This Approach?**:
  - Bridges tech and enterprise domains.
  - Pre-configures verified skills, positive title aliases, and search terms, resulting in instant high match accuracy.

---

### ADR-007: Single Consolidated CSV Output (`OutputExporter`)
* **Context**: Older iterations generated 8+ sliced files per run (`JOBSPY_INDIA_...csv`, `JOBSPY_MIDDLE_EAST_...csv`, `JOBSPY_GLOBAL_...csv`, `JOBSPY_VISA_...csv`, `JOBSPY_RAW_...csv`, `SUMMARY.txt`).
* **Decision**: Standardized on **exactly one primary CSV** per search session:
  `AURAJOBS_{role_slug}_{geo_slug}_{timestamp}.csv`.
* **Why This Approach?**:
  - Eliminates file clutter in the output directory.
  - Users can easily filter, sort, or pivot columns (`region`, `priority`, `match_type`, `visa_status`) in Excel or Google Sheets.

---

### ADR-008: Stage 1 Expansion with Zero-Auth Public APIs (`FreeHire`, `Arbeitnow`, `AIJobs`)
* **Context**: Research into `public-apis/public-apis#jobs` identified 3 high-yield, zero-authentication job platforms: `freehire.me`, `arbeitnow.com`, and `artificialintelligencejobs.co`.
* **Decision**: Created dedicated adapters for all three:
  1. [`sources/freehire_adapter.py`](file:///d:/JobSpy/sources/freehire_adapter.py): Aggregates ATS job postings (Greenhouse, Lever, Freshteam, Recruitee) with native coverage of Indian tech metros (Bengaluru, Mumbai, Delhi, Hyderabad) and Global Remote.
  2. [`sources/arbeitnow_adapter.py`](file:///d:/JobSpy/sources/arbeitnow_adapter.py): Curated European and Global Remote tech listings with tags and pagination.
  3. [`sources/aijobs_adapter.py`](file:///d:/JobSpy/sources/aijobs_adapter.py): Live crawler indexing 260+ AI/ML startups with direct application URLs to Ashby and Greenhouse.
* **Why This Approach?**:
  - Expands Stage 1 from 4 to 7 concurrent, block-free feeds without API keys or token management.
  - Slashes reliance on HTML web scraping by ingesting thousands of direct ATS roles instantly in parallel.

---

### ADR-009: Cascading Anti-Bot Escalation via Scrapling & Patchright Engine
* **Context**: Target job boards like **Naukri** (HTTP 406 Not Acceptable recaptcha) and **Bayt** (international HTTP 403 Forbidden) block fast HTTP clients like `requests` and standard Playwright due to CDP and canvas leaks.
* **Decision**: Integrated [Scrapling](https://github.com/D4Vinci/Scrapling) (`StealthyFetcher` powered by `patchright`) into [`sources/scrapling_adapter.py`](file:///d:/JobSpy/sources/scrapling_adapter.py) with a **Cascading Escalation Strategy** inside [`sources/multiboard_adapter.py`](file:///d:/JobSpy/sources/multiboard_adapter.py):
  - Primary tier: Fast HTTP requests (`scrape_jobs`) execute first (preserving sub-second query speed).
  - Escalation tier: If bot detection (403/406/Turnstile) is encountered on Naukri or Bayt, the search transparently escalates to `StealthyFetcher` (`solve_cloudflare=True`, `hide_canvas=True`, `block_webrtc=True`, `network_idle=True`).
* **Why This Approach?**:
  - Avoids the high latency and memory overhead of launching a browser for every simple search.
  - Eliminates 0-match dead ends on bot-protected platforms while maintaining blazing-fast performance.

---

## 2. End-to-End Execution Flow Trace

This section traces exactly how code executes in AuraJobs, from the initial launcher invocation to the final CSV generation.

```
[run_aurajobs.bat]
        │
        ▼
[main.py: parse_args()] ──► [core/prompt.py: prompt_user_profile()]
                                    │
                                    ├──► [core/expander.py: build_search_profile()]
                                    │       ├── detect_and_strip_seniority()
                                    │       ├── find_preset()
                                    │       └── compile search_terms & positive_terms
                                    │
                                    ▼ (Profile JSON saved to logs/)
[main.py: Execution Pipeline]
        │
        ├──► Step 1: Initialize Scheduler & Queues
        │       └── [core/scheduler.py: generate_execution_queues()]
        │               ├── calculate_budgets() (India 45%, ME 30%, Global 25%)
        │               └── build_round_robin_plan() (Location-first interleaving)
        │
        ├──► Step 2: Checkpoint Check
        │       └── [core/checkpoint.py: load()] (Resume if interrupted)
        │
        ├──► Step 3: Stage 1 - 7-Worker Parallel Zero-Auth APIs & Direct ATS
        │       ├── [sources/remoteok_adapter.py: fetch_jobs()]
        │       ├── [sources/remotive_adapter.py: fetch_jobs()]
        │       ├── [sources/himalayas_adapter.py: fetch_jobs()]
        │       ├── [sources/ats_adapter.py: fetch_all_ats()] (Ashby + Greenhouse + Lever)
        │       ├── [sources/freehire_adapter.py: fetch_jobs()] (Greenhouse, Recruitee, Freshteam)
        │       ├── [sources/arbeitnow_adapter.py: fetch_jobs()] (Europe & Global Remote)
        │       └── [sources/aijobs_adapter.py: fetch_jobs()] (260+ AI Company ATS Crawler)
        │
        ├──► Step 4: Stage 2 - Cascading Multi-Board Scraper Queue
        │       └── While budget remaining:
        │               └── [sources/multiboard_adapter.py: search_single_site()]
        │                       ├── Level 1: Fast HTTP scrape_jobs(LinkedIn, Indeed, Google)
        │                       │       Did it return jobs?
        │                       │         ├─► YES: Yield results
        │                       │         └─► NO (403 / 406 Bot Block on Naukri / Bayt):
        │                       │               └── Level 2: [sources/scrapling_adapter.py]
        │                       │                       └── StealthyFetcher (Patchright + Turnstile Solver)
        │                       ├── CheckpointManager.save_progress()
        │                       └── Console progress bar & ETA update
        │
        └──► Step 5: Normalization, Scoring & Export
                └── [main.py: process_results()]
                        ├── [core/normalizer.py: normalize_dataframe()] (27 canonical cols)
                        ├── Calculate age_hours & apply freshness filter
                        ├── [core/classifier.py: filter_dataframe()]
                        │       ├── Strict match filter
                        │       └── Graceful fallback trigger if 0 matches
                        ├── [core/visa.py: detect_visa_sponsorship() & detect_relocation()]
                        ├── [core/scorer.py: calculate_score() & assign_priority()]
                        ├── [core/deduper.py: deduplicate_jobs()] (URL + fuzzy title)
                        └── [core/exporters.py: export_single_file()]
                                └── Write single AURAJOBS_*.csv with UTF-8 BOM
```

---

## 3. Function Call Graph & Component Map

| Order | Caller Function | Callee Function / Class | File Location | Responsibility |
| :---: | :--- | :--- | :--- | :--- |
| **1** | `run_aurajobs.bat` | `python main.py` | Root | Verifies Python 3.10+, installs missing deps, launches app. |
| **2** | `main.py:main()` | `parse_args()` | `main.py:33` | Parses CLI flags (`--role`, `--geo`, `--mode`, `--freshness`). |
| **3** | `main.py:main()` | `prompt_user_profile()` | `core/prompt.py:6` | Interactive terminal UI to collect role, seniority, skills, region. |
| **4** | `prompt_user_profile()` | `build_search_profile()` | `core/expander.py:76` | Parses role, queries presets in `roles.yaml`, builds query variations. |
| **5** | `build_search_profile()` | `detect_and_strip_seniority()` | `core/expander.py:44` | Extracts seniority prefix (`Senior`, `Lead`, `Staff`) from role title. |
| **6** | `main.py:main()` | `BalancedScheduler()` | `core/scheduler.py:11` | Loads `locations.yaml`, `sources.yaml`, and `settings.yaml`. |
| **7** | `main.py:main()` | `generate_execution_queues()` | `core/scheduler.py:125` | Builds interleaved, location-first query iterators. |
| **8** | `main.py:main()` | `CheckpointManager.load()` | `core/checkpoint.py:15` | Inspects `checkpoints/` for prior session recovery. |
| **9** | `main.py:main()` | `ThreadPoolExecutor(max_workers=7)` | `main.py:255` | Concurrently executes 7 Stage 1 direct API adapters. |
| **10** | Stage 1 Worker | `FreeHireAdapter.fetch_jobs()` | `sources/freehire_adapter.py` | Queries `freehire.me` ATS aggregator for India and Global jobs. |
| **11** | Stage 1 Worker | `ArbeitnowAdapter.fetch_jobs()` | `sources/arbeitnow_adapter.py` | Queries `arbeitnow.com` for EU/Remote technology vacancies. |
| **12** | Stage 1 Worker | `AIJobsAdapter.fetch_jobs()` | `sources/aijobs_adapter.py` | Queries `artificialintelligencejobs.co` for AI/ML roles. |
| **13** | Stage 1 Worker | `ATSAdapter.fetch_all_ats()` | `sources/ats_adapter.py` | Queries Ashby, Greenhouse, and Lever public job feeds. |
| **14** | Stage 2 Loop | `MultiBoardAdapter.search_single_site()` | `sources/multiboard_adapter.py:30` | Fast HTTP scrape with cascading fallback to Scrapling. |
| **15** | Stage 2 Escalation | `ScraplingStealthAdapter.scrape_naukri()` | `sources/scrapling_adapter.py:42` | Headless Patchright session solving Naukri 406 anti-bot challenges. |
| **16** | Stage 2 Escalation | `ScraplingStealthAdapter.scrape_bayt()` | `sources/scrapling_adapter.py:84` | Headless Patchright session bypassing Bayt 403 regional restrictions. |
| **17** | Stage 2 Loop | `CheckpointManager.save_progress()` | `core/checkpoint.py:28` | Saves intermediate search state every 5 searches. |
| **18** | `main.py:main()` | `process_results()` | `main.py:51` | Orchestrates cleaning, filtering, scoring, and deduplication. |
| **19** | `process_results()` | `normalize_dataframe()` | `core/normalizer.py:41` | Transforms raw heterogeneous columns into 27 canonical fields. |
| **20** | `process_results()` | `RoleClassifier.filter_dataframe()` | `core/classifier.py:58` | Applies token-set positive matching and strict exclusions. |
| **21** | `process_results()` | `detect_visa_sponsorship()` | `core/visa.py:10` | Regex scanner for H1B, sponsorship, and visa requirements. |
| **22** | `process_results()` | `MatchScorer.calculate_score()` | `core/scorer.py:28` | Computes 0–100 relevance score based on skill and title density. |
| **23** | `process_results()` | `deduplicate_jobs()` | `core/deduper.py:12` | Merges duplicate job postings across platforms. |
| **24** | `main.py:main()` | `OutputExporter.export_single_file()` | `core/exporters.py:20` | Writes single consolidated CSV with UTF-8 BOM encoding. |

---

## 4. Full Summary of Codebase Modifications by AI

Here is the exact record of every file changed, added, or removed during this development cycle:

| File Path | Action | Description of Modifications |
| :--- | :---: | :--- |
| `sources/freehire_adapter.py` | **[NEW]** | Created zero-auth direct ATS aggregator adapter (`freehire.me`) with India and Global remote coverage. |
| `sources/arbeitnow_adapter.py` | **[NEW]** | Created zero-auth EU and Global Remote tech listings adapter (`arbeitnow.com`). |
| `sources/aijobs_adapter.py` | **[NEW]** | Created zero-auth live AI/ML career page crawler adapter (`artificialintelligencejobs.co`). |
| `sources/scrapling_adapter.py` | **[NEW]** | Created `ScraplingStealthAdapter` utilizing `StealthyFetcher` (Patchright, Turnstile solver, canvas noise, WebRTC block). |
| `sources/multiboard_adapter.py` | **[MODIFIED]** | Added Cascading Anti-Bot Escalation hooking Scrapling when fast HTTP hits 406/403 blocks on Naukri or Bayt. |
| `sources/__init__.py` | **[MODIFIED]** | Exported `FreeHireAdapter`, `ArbeitnowAdapter`, `AIJobsAdapter`, and `ScraplingStealthAdapter`. |
| `config/sources.yaml` | **[MODIFIED]** | Added configuration sections and toggles for `freehire`, `arbeitnow`, `aijobs`, and `scrapling`. |
| `requirements.txt` | **[MODIFIED]** | Pinned `scrapling>=0.4.15` and `patchright>=1.62.0`. |
| `pyproject.toml` | **[MODIFIED]** | Added `scrapling` and `patchright` to build dependencies. |
| `main.py` | **[MODIFIED]** | Expanded Stage 1 parallel thread pool from 4 to 7 workers; updated CLI banner and status reporting. |
| `tests/test_new_adapters.py` | **[NEW]** | Created comprehensive unit test suite covering all 3 new adapters, Scrapling import, and escalation flags. |
| `decisions.md` | **[MODIFIED]** | Documented ADR-008, ADR-009, updated 7-worker Stage 1 execution flow diagram, and updated function call graph. |
| `run_aurajobs.bat` | **[NEW]** | Created modern 1-click launcher with UTF-8 codepage and auto-dependency setup. |
| `run_aurajobs_balanced.bat` | **[NEW]** | Created balanced batch runner for India + Middle East + Global scans. |
| `run_jobspy.bat` | **[DELETED]** | Removed legacy, hardcoded batch script. |
| `run_jobspy_balanced.bat` | **[DELETED]** | Removed legacy balanced batch script. |
| `search_jobs.py` | **[DELETED]** | Removed monolithic legacy script in favor of modular `main.py`. |
| `search_jobs_balanced.py` | **[DELETED]** | Removed monolithic legacy script in favor of modular `main.py`. |
| `sources/jobspy_adapter.py` | **[MODIFIED]** | Refactored into a backward-compatibility proxy pointing to `MultiBoardAdapter`. |
| `config/roles.yaml` | **[MODIFIED]** | Added 6 business & enterprise presets (`product_management`, `growth_marketing`, `operations_strategy`, `people_talent_hr`, `sales_business_development`, `hris_hr_tech`). |
| `core/expander.py` | **[MODIFIED]** | Added core domain extraction from multi-word roles; fixed senior prefix explosion; added self-exclusion guard for creative titles. |
| `core/classifier.py` | **[MODIFIED]** | Implemented token-set and word-order invariant matching; added `ROLE_LEVEL_NOUNS` filtering. |
| `core/scheduler.py` | **[MODIFIED]** | Implemented location-first interleaving to guarantee full coverage of all 13 configured cities. |
| `core/prompt.py` | **[MODIFIED]** | Rebranded CLI banner; updated placeholder examples to be multi-domain (Product, HRIS, Engineering). |
| `core/exporters.py` | **[MODIFIED]** | Updated output prefix to `AURAJOBS_*`; added `match_type` to priority column order. |
| `.gitignore` | **[NEW]** | Excluded all raw CSV dumps, test outputs, checkpoints, and caches. |
| `LICENSE` | **[NEW]** | Standard MIT License attributed to `lordpardonme`. |
| `README.md` | **[NEW]** | Comprehensive documentation with architecture diagram, quickstart, CLI reference, and badges. |
| `CONTRIBUTING.md` | **[NEW]** | Open-source contribution guidelines for taxonomies and adapters. |
| `SECURITY.md` | **[NEW]** | Responsible vulnerability disclosure policy. |
| `.github/workflows/ci.yml` | **[NEW]** | Automated CI workflow testing Python 3.10, 3.11, and 3.12. |
| `.github/workflows/codeql.yml` | **[NEW]** | CodeQL automated SAST security scan on push and pull requests. |
| `.github/dependabot.yml` | **[NEW]** | Weekly automated dependency vulnerability updates. |
| `.devcontainer/devcontainer.json` | **[NEW]** | 1-click cloud development environment for GitHub Codespaces. |
| `docs/wiki/*` | **[NEW]** | 5 complete documentation pages (`Home`, `Getting-Started`, `Role-Taxonomies`, `Geographic-Budgets`, `Extending-Adapters`). |
| `research_scrapling_deep_dive.md` | **[NEW]** | Comprehensive feasibility study and integration blueprint for Scrapling anti-bot bypass. |
