# Contributing to AuraJobs

Thank you for your interest in contributing to **AuraJobs**! We welcome contributions to help make autonomous job discovery faster, more accurate, and more accessible.

## How to Contribute

### 1. Adding New Role Presets
Role taxonomies are defined in [`config/roles.yaml`](config/roles.yaml). You can contribute new preset families (e.g., DevOps, Cybersecurity, Mobile Development) by defining:
- Canonical role aliases
- Targeted search query variations
- Positive title filter terms
- Essential domain skills

### 2. Adding Direct Company ATS
We track companies that publish open roles via public applicant tracking APIs in [`config/companies.yaml`](config/companies.yaml). Supported platforms include:
- Ashby (`https://api.ashbyhq.com/posting-api/job-board/{slug}`)
- Greenhouse (`https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`)
- Lever (`https://api.lever.co/v0/postings/{slug}`)

### 3. Adding New Job Sources
New source adapters can be implemented in the `sources/` directory by inheriting from `BaseSourceAdapter` in [`sources/base.py`](sources/base.py).

## Pull Request Guidelines

1. Fork the repo and create a new feature branch from `main`.
2. Follow clean Python code formatting (PEP 8).
3. Ensure no local scrape CSV outputs or credentials are committed.
4. Run syntax verification:
   ```bash
   python -m py_compile main.py core/*.py sources/*.py
   ```
5. Submit your PR with a clear description of the enhancements.
