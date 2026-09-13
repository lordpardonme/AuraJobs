# Getting Started with AuraJobs

## System Requirements
- Python 3.10, 3.11, or 3.12
- Internet access (for querying public boards and ATS APIs)

---

## 🚀 Installation

```bash
git clone https://github.com/lordpardonme/AuraJobs.git
cd AuraJobs
pip install -r requirements.txt
```

---

## 🖥️ Running on Windows
Double-click [`run_aurajobs.bat`](../run_aurajobs.bat) to launch the interactive configuration assistant.

Or run the balanced batch search across all three regions:
```cmd
run_aurajobs_balanced.bat
```

---

## 🐧 Running on macOS / Linux / Codespaces

```bash
python main.py
```

### Direct CLI Examples:

```bash
# 1. Search for Staff Product Designers in India (last 48 hours)
python main.py --role "Product Designer" --seniority Staff --geo India --freshness 48

# 2. Search for AI / Machine Learning Engineers in Deep Scan mode
python main.py --role "Machine Learning Engineer" --mode Deep --freshness 72

# 3. Non-interactive automated run for Product Managers
python main.py --role "Product Manager" --geo All --non-interactive
```

---

## 📊 Output Deliverable
Every run generates a single consolidated CSV in `output/`:
`AURAJOBS_{Role}_{Region}_{Timestamp}.csv`

### Canonical Attributes Included:
- `priority`: High / Medium / Low match priority
- `match_score`: 0–100 calculated relevance score
- `title` & `company`
- `location`, `country`, `region`
- `source`: Platform where discovered (LinkedIn, Indeed, Ashby, etc.)
- `job_url`: Direct link to apply
- `visa_status` & `visa_evidence`: Sponsorship detection
- `relocation_status` & `relocation_evidence`
- `age_hours` & `date_posted`
- `salary_min`, `salary_max`, `currency`
- `remote_status`: Remote / Hybrid / On-site
