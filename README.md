# AuraJobs 🌐🚀
### Autonomous Multi-Board Career Intelligence & Job Aggregation Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Platforms: Cross-Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg?style=flat-square)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](CONTRIBUTING.md)
[![Status: Active](https://img.shields.io/badge/Status-Active-success.svg?style=flat-square)]()

**AuraJobs** is a modern, modular, agentic career intelligence platform that federates job listings across major boards, remote networks, and direct applicant tracking systems (ATS). Built with smart taxonomy expansion, multi-region budget scheduling, intelligent deduplication, and visa-sponsorship detection, AuraJobs delivers a single clean, high-signal CSV of verified career opportunities.

---

## ⚡ Key Highlights

* **Federated Multi-Source Discovery**: Aggregates from **LinkedIn**, **Indeed**, **Google Jobs**, and **Glassdoor** via resilient adapters.
* **Direct Company ATS Pipelines**: Direct real-time endpoints for **Ashby**, **Greenhouse**, and **Lever**, fetching official open postings from top tech and AI pioneers (OpenAI, Anthropic, Stripe, Figma, Notion, Linear, etc.).
* **Specialized Remote Networks**: Built-in parallel scrapers for **RemoteOK**, **Remotive**, and **Himalayas**.
* **Universal Role Taxonomy & Dynamic Expander**:
  * **9 Deep Presets**: *Product Design (UI/UX)*, *Data Science & AI/ML*, *Frontend Engineering*, *Software Engineering*, *Product Management*, *Growth & Marketing*, *Operations & Strategy*, *People & HR*, and *Sales & BizDev*.
  * **Dynamic Custom Mode**: Handles any custom title with automated seniority parsing (`Intern` → `Principal`/`VP`) and conflict exclusions.
* **Intelligent 3-Tier Geographic Rotation**:
  * **India**: 12 key tech metros (Bengaluru, Delhi-NCR, Mumbai, Pune, Hyderabad, Kochi, etc.).
  * **Middle East / GCC**: 8 financial and tech hubs (Dubai, Abu Dhabi, Riyadh, Jeddah, Doha, etc.).
  * **Global / Remote**: Worldwide remote pipelines.
* **Smart Deduplication & Match Scoring**: Merges identical postings across platforms using URL normalization, fuzzy title matching, and company tokens. Computes a 0–100 relevance score based on skill density and title seniority.
* **Visa Sponsorship & Relocation AI**: Scans job descriptions for H1B, global relocation, work authorization requirements, and sponsorship flags.
* **Consolidated Output**: Generates exactly **one** clean, structured CSV per search session (`AURAJOBS_{Role}_{Region}_{Timestamp}.csv`).

---

## 🏗️ Architecture Overview

```
                               ┌──────────────────────────┐
                               │   AuraJobs CLI / Prompt  │
                               └────────────┬─────────────┘
                                            │
                               ┌────────────▼─────────────┐
                               │       RoleExpander       │
                               │ (Seniority + Taxonomies) │
                               └────────────┬─────────────┘
                                            │
                        ┌───────────────────┴───────────────────┐
                        │           BalancedScheduler           │
                        │    (India, Middle East, Global)       │
                        └───────────────────┬───────────────────┘
                                            │
       ┌────────────────────────┬───────────┴────────────┬────────────────────────┐
       │                        │                        │                        │
┌──────▼──────┐          ┌──────▼──────┐          ┌──────▼──────┐          ┌──────▼──────┐
│ Multi-Board │          │  Direct ATS │          │   RemoteOK  │          │  Himalayas  │
│  (LinkedIn, │          │   (Ashby,   │          │  & Remotive │          │  API Engine │
│   Indeed,   │          │ Greenhouse, │          │   (Remote)  │          │   (Remote)  │
│   Google)   │          │   Lever)    │          │             │          │             │
└──────┬──────┘          └──────┬──────┘          └──────┬──────┘          └──────┬──────┘
       │                        │                        │                        │
       └────────────────────────┼────────────────────────┴────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │ Normalizer & Cleaner  │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │ Role Filter & Scorer  │
                    │  (Match Score 0-100)  │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Deduplication Engine │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │ OutputExporter (.CSV) │
                    └───────────────────────┘
```

---

## 🚀 Quickstart

### Prerequisites
* Python 3.10 or higher
* Git

### Installation

```bash
# Clone the repository
git clone https://github.com/lordpardonme/AuraJobs.git
cd AuraJobs

# Install dependencies
pip install -r requirements.txt
```

### 1-Click Launchers (Windows)
* **Interactive Launcher**: Double-click `run_aurajobs.bat`
* **Balanced 3-Region Runner**: Double-click `run_aurajobs_balanced.bat`

---

## 💻 CLI Usage

Launch AuraJobs with interactive prompting:
```bash
python main.py
```

Or pass direct flags for automated/headless execution:
```bash
# Search for Senior Data Scientists across all regions in Express mode
python main.py --role "Data Scientist" --seniority Senior --geo All --mode Express --freshness 48

# Search for Product Designers in India in Deep Scan mode
python main.py --role "Product Designer" --geo India --mode Deep --freshness 72

# Search for remote Software Engineers globally
python main.py --role "Software Engineer" --geo Global --freshness 24 --non-interactive
```

### CLI Arguments

| Flag | Options | Default | Description |
| :--- | :--- | :--- | :--- |
| `--role` | *Text* (e.g. `Product Manager`) | `Product Designer` | Target job family |
| `--seniority` | `Any`, `Intern`, `Junior`, `Mid`, `Senior`, `Staff`, `Lead`, `Principal` | `Any` | Seniority filter |
| `--geo` | `All`, `India`, `Middle East`, `Global` | `All` | Regional scope |
| `--freshness` | Hours (e.g. `24`, `48`, `72`) | `72` | Max posting age |
| `--mode` | `Express` (~1 min) or `Deep` (~10 mins) | `Express` | Execution intensity |
| `--max-searches`| Integer | Config default | Hard cap on queries |
| `--max-runtime` | Minutes | Config default | Hard cap on execution time |
| `--non-interactive` | Flag | `False` | Run without prompts |

---

## 📁 Project Structure

```
AuraJobs/
├── config/
│   ├── companies.yaml       # Curated companies with direct ATS pipelines
│   ├── locations.yaml       # City & country mappings (India, ME, Global)
│   ├── roles.yaml           # Deep role taxonomy & skill dictionaries
│   ├── settings.yaml        # Rate limits, search caps, and runtime configs
│   └── sources.yaml         # Adapter toggles & site endpoints
├── core/
│   ├── checkpoint.py        # Safe search state resumption
│   ├── classifier.py        # Title and keyword filtering
│   ├── deduper.py           # Cross-platform URL & fuzzy deduplication
│   ├── expander.py          # Dynamic seniority & taxonomy expander
│   ├── exporters.py         # Consolidated CSV output generator
│   ├── normalizer.py        # Canonical 27-column data schema
│   ├── prompt.py            # Terminal interactive UI launcher
│   ├── scheduler.py         # Balanced multi-region budget scheduler
│   ├── scorer.py            # 0-100 relevance and match scoring
│   └── visa.py              # Visa sponsorship & relocation detector
├── sources/
│   ├── ats_adapter.py       # Ashby, Greenhouse & Lever direct API adapters
│   ├── himalayas_adapter.py # Himalayas remote jobs adapter
│   ├── multiboard_adapter.py# Multi-board scraper (LinkedIn, Indeed, Google)
│   ├── remoteok_adapter.py  # RemoteOK API adapter
│   └── remotive_adapter.py  # Remotive API adapter
├── main.py                  # Primary entry point & CLI pipeline
├── requirements.txt         # Package dependencies
├── pyproject.toml           # Packaging metadata
└── run_aurajobs.bat         # 1-click Windows runner
```

---

## ⚙️ Configuration & Customization

AuraJobs is entirely data-driven via YAML configuration in `config/`:

* **Add New Roles & Skills**: Edit [`config/roles.yaml`](config/roles.yaml) to customize presets or add negative exclusions.
* **Add Direct Company ATS**: Edit [`config/companies.yaml`](config/companies.yaml) to track hiring directly from company boards.
* **Expand Target Locations**: Edit [`config/locations.yaml`](config/locations.yaml) to add new cities, countries, or regional groupings.

---

## ⚖️ Legal & Ethical Compliance

AuraJobs is designed to operate responsibly:
* Direct APIs (Ashby, Greenhouse, Himalayas, RemoteOK, Remotive) are preferred wherever available.
* Scrapers enforce rate-limiting (`request_delay_seconds`) to prevent server overload.
* For more information on ethical usage, see [`LEGAL_AND_ETHICAL_COMPLIANCE_GUIDE.md`](LEGAL_AND_ETHICAL_COMPLIANCE_GUIDE.md).

---

## 🤝 Contributing

Contributions, bug reports, and feature requests are welcome!
1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📜 License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for more information.

---

## 👤 Author

* **lordpardonme** ([@lordpardonme](https://github.com/lordpardonme))
