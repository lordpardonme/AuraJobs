# AuraJobs - Agentic Career Intelligence Engine

## Implementation Blueprint, Architecture, Source Strategy & Runtime Design

This document consolidates the job-search requirements developed in the conversation into a reusable, source-agnostic implementation plan. The key design decision is that the system must **not be hard-coded to Product/UX/UI**. Each run starts by asking the user what kind of job they are looking for, then builds the search profile for that job family.

## 1. Core Requirement

When the launcher is run, the system asks for the target job. The user can enter a role such as:

```text
Product Designer
Data Scientist
Frontend Engineer
Film Editor
```

The search engine then expands that target into relevant variants, applies the selected geography and freshness settings, and sends the resulting search profile through all enabled source adapters.

Example interaction:

```text
> Enter target job family: Product Designer
> Optional seniority: Any / Senior / Staff / Lead / Principal
> Optional skills: Figma, SaaS, B2B
> Optional exclusions: Graphic Design
> Geography: India + Middle East + Global
> Freshness: Last 72 hours
> Start search? Y
```

The target role, filters and generated query expansions should be written to a `SEARCH_PROFILE_<timestamp>.json` file so each run is reproducible.

---

## 2. Role Expansion

The Product Design profile used during the current build should cover the broad digital design family rather than only Product Designer/Senior Product Designer.

### Product Design

- Product Designer
- Senior Product Designer
- Staff Product Designer
- Lead Product Designer
- Principal Product Designer
- Product Design Lead
- Product Design Manager
- Product Design Director
- Head of Product Design
- VP Product Design
- Product Design

### Founding / Startup

- Founding Product Designer
- Founding Designer
- First Product Designer
- First Designer
- Startup Product Designer
- 0 to 1 Product Designer
- 0-1 Product Designer
- Zero to One Product Designer

### UX

- UX Designer
- Senior UX Designer
- Staff UX Designer
- Lead UX Designer
- Principal UX Designer
- UX Lead
- UX Design Lead
- UX Architect
- UX Specialist
- User Experience Designer

### UI / UIUX

- UI Designer
- Senior UI Designer
- Staff UI Designer
- Lead UI Designer
- Principal UI Designer
- UI/UX Designer
- UI UX Designer
- UX/UI Designer
- UX UI Designer
- Senior UI/UX Designer
- Senior UI UX Designer
- Lead UI/UX Designer
- Lead UI UX Designer

### Interaction / Experience

- Interaction Designer
- Senior Interaction Designer
- Lead Interaction Designer
- Interaction Design Lead
- Experience Designer
- Senior Experience Designer
- Lead Experience Designer
- Digital Product Designer
- Digital Experience Designer
- Service Designer

### Research / Specialist

- UX Researcher
- Senior UX Researcher
- Staff UX Researcher
- Lead UX Researcher
- Product Design Researcher
- User Researcher
- Design Systems Designer
- Design Systems Lead
- Design Systems Specialist
- Product UX Designer

`Craft Designer` should not be used as a blanket query because it can create unrelated physical/art/craft results. Prefer digital Product/UX/UI/Interaction/Experience/Design Systems terminology.

---

## 3. Exclusions

Role classification should reject obvious unrelated categories, especially when they appear in the job title:

- Graphic Designer / Graphic Design
- Fashion Designer / Fashion Design
- Apparel / Garment / Textile Design
- Interior Designer / Interior Design
- Architectural Design
- Landscape Design
- Kitchen Design
- Mechanical Design
- CAD Design / AutoCAD / SolidWorks
- Industrial Design
- Automotive Design
- Jewelry / Jewellery Design
- Costume Design
- Floral Design
- Visual Merchandising
- Production Designer / Set Designer
- Motion Graphics
- Video Designer / Video Editor / Film Editor
- 3D Designer / 3D Artist

The classifier should be title-led. A job should not become a Product/UX/UI result merely because an unrelated job description happens to mention UX or product design.

---

## 4. Geography

### India

Search India nationwide plus these priority cities:

- India
- Delhi
- Noida
- Gurgaon
- Bengaluru
- Bangalore
- Pune
- Mumbai
- Chandigarh
- Hyderabad
- Mangalore
- Mangaluru
- Kochi

The nationwide `India` query is separate from the city queries so the search is not limited to the priority cities.

### Middle East

Use a dedicated Middle East region:

- Dubai, UAE
- Abu Dhabi, UAE
- Riyadh, Saudi Arabia
- Jeddah, Saudi Arabia
- Doha, Qatar
- Kuwait City, Kuwait
- Manama, Bahrain
- Muscat, Oman

Dubai/UAE is the primary Middle East target.

### Global / Rest of World

Use a separate Global region that searches worldwide while deliberately keeping India and Middle East as separate regions in the dataset. Global must have its own guaranteed search budget and its own output file/sheet.

---

## 5. Freshness

The canonical fresh-job window is **72 hours**.

```text
0-24 hours    -> LAST_24H
24-72 hours   -> 24_TO_72H
>72 hours     -> excluded from fresh datasets
```

Store:

- `date_posted`
- `scraped_at`
- `age_hours`
- `age_bucket`

JobSpy's `hours_old` should reduce retrieval volume, but the pipeline should calculate its own age before final filtering because sources expose dates differently.

Do not pretend that an `updated` timestamp is universally equivalent to a `posted` timestamp.

---

## 6. JobSpy as One Layer

JobSpy is the aggregator layer, not the entire job-search universe.

The relevant documented JobSpy sources for this setup are:

- LinkedIn
- Indeed
- Glassdoor
- Google
- Bayt
- Naukri
- ZipRecruiter

ZipRecruiter is primarily US/Canada-oriented and therefore should not consume India/Middle East search budget in the initial configuration.

### Source failure policy

A source failure must never terminate the full pipeline.

Known examples from testing:

```text
Naukri      -> 406 recaptcha_required
Glassdoor   -> 400 / location parsing problems
```

The system should log the error, mark source health, and continue.

Do **not** bypass CAPTCHA or anti-bot controls.

---

## 7. Wider Source Ecosystem

The long-term implementation should add high-value independent sources rather than trying to force every website into JobSpy.

### Startup / tech

- Wellfound

### India / regional

- Cutshort
- Instahyre
- Foundit

### Design-specialist

- Dribbble Jobs
- Behance Jobs
- Coroflot

### Remote / global

- Remote OK
- We Work Remotely
- Himalayas
- Remotive
- Working Nomads
- Arc

### Freelance / contract

- Contra

Keep freelance/contract as a separate employment-type stream.

### Aggregators

- Adzuna
- Jooble
- Talent.com

### Recruitment agencies

- Michael Page
- Randstad
- Hays
- Adecco
- Robert Walters
- Korn Ferry

### ATS / company career systems

- Greenhouse
- Lever
- Ashby
- Workday
- SmartRecruiters
- Teamtailor
- Personio
- Pinpoint
- Direct company career pages

Each non-JobSpy source should have its own adapter or source-specific retrieval method. Do not fabricate unsupported JobSpy source names.

---

## 8. ATS Is a Priority Layer

A significant amount of enterprise and startup hiring is hosted directly on applicant-tracking systems. The most valuable first ATS adapters are:

1. Greenhouse
2. Lever
3. Ashby
4. SmartRecruiters
5. Workday
6. Teamtailor
7. Personio
8. Pinpoint

Ashby documents a public Job Posting API for published job postings, including locations and optional compensation data. SmartRecruiters documents public Posting API endpoints for active company postings with query and location parameters. These make ATS adapters materially cleaner than page-by-page scraping.

---

## 9. Balanced Scheduling

The old search structure was effectively:

```python
for city:
    for term:
        for site:
            scrape()
```

This is wrong for a bounded search budget because Delhi can consume the entire run before the scraper reaches Noida, Gurgaon, Middle East, or Global.

### Correct structure

Use region quotas and round-robin execution:

```text
India -> Middle East -> Global -> India -> Middle East -> Global -> ...
```

Inside each region, rotate locations rather than exhausting one location first.

Initial test allocation for a 500-search run:

```text
India        45% = 225 searches
Middle East  30% = 150 searches
Global       25% = 125 searches
```

This is a safety/testing allocation, not a permanent optimum.

### Hard limits

```python
MAX_SEARCHES = 500
MAX_RUNTIME_MINUTES = 90
```

These are guardrails, not geography-selection rules.

The run stops when the first limit is reached, when the entire scheduled plan completes, or immediately when the user presses `Ctrl+C`.

---

## 10. Even Distribution Within a Region

Even after regional quotas are created, a region can still be starved by a bad ordering.

The scheduler should:

1. Build a complete plan for the region.
2. Select an evenly distributed subset up to that region's budget.
3. Rotate location order between query families.
4. Interleave region queues.

This produces deliberate coverage rather than accidental coverage.

---

## 11. Visa Sponsorship and Relocation

For international jobs, add:

```text
Sponsorship:
  SPONSORSHIP MENTIONED
  NO SPONSORSHIP
  UNKNOWN

Relocation:
  RELOCATION MENTIONED
  UNKNOWN
```

`UNKNOWN` is not equivalent to `NO`.

Positive sponsorship signals include:

- visa sponsorship
- visa sponsor
- sponsorship available
- sponsorship provided
- work visa sponsorship
- employment visa sponsorship
- company sponsored visa
- company sponsorship
- visa support
- work permit sponsorship
- work permit support
- employment visa
- relocation and visa
- relocation assistance and visa
- visa assistance
- sponsor work visa
- sponsor your visa

Negative signals include:

- no visa sponsorship
- visa sponsorship not available
- visa sponsorship unavailable
- unable to sponsor
- cannot sponsor
- will not sponsor
- we do not sponsor
- does not sponsor
- not able to sponsor
- must already have the right to work
- must have the right to work
- right to work required
- valid work authorization required
- valid work permit required
- without sponsorship

Relocation signals include:

- relocation assistance
- relocation support
- relocation package
- relocation provided
- relocation available
- relocation offered
- relocation assistance available
- relocation support available

Future version: store `visa_evidence` and `relocation_evidence`, the short phrase that triggered the classification.

---

## 12. Match Scoring

Scoring ranks jobs; it does not prove suitability.

Useful signals:

- target role similarity
- seniority
- skill overlap
- freshness
- sponsorship
- relocation
- relevant product/design keywords
- remote status
- employment type

For Product Design, high-value seniority roles include:

- Founding
- Principal
- Staff
- Senior
- Lead
- Head
- Director

The score should be configurable per job family rather than hard-coded to design.

---

## 13. Normalized Job Schema

Every adapter should return the same schema:

- `job_id`
- `source_job_id`
- `source`
- `source_url`
- `job_url`
- `company`
- `title`
- `location`
- `country`
- `region`
- `description`
- `date_posted`
- `scraped_at`
- `age_hours`
- `age_bucket`
- `employment_type`
- `remote_status`
- `salary_min`
- `salary_max`
- `currency`
- `visa_status`
- `visa_evidence`
- `relocation_status`
- `relocation_evidence`
- `match_score`
- `priority`
- `query_used`
- `search_location`

---

## 14. Deduplication

A vacancy may appear on LinkedIn, Indeed, an ATS, and a recruitment-agency site.

Deduplicate in stages:

1. Exact job URL.
2. Normalized title + company + location.
3. Stronger similarity or stable IDs when available.

Do not throw away source provenance. A canonical job should retain the list of sources where it was discovered.

---

## 15. Run Outputs

Every run gets a new timestamped output set. Never overwrite previous runs.

```text
JOBSPY_ALL_72H_<timestamp>.csv
JOBSPY_LAST_24H_<timestamp>.csv
JOBSPY_24_TO_72H_<timestamp>.csv
JOBSPY_INDIA_<timestamp>.csv
JOBSPY_MIDDLE_EAST_<timestamp>.csv
JOBSPY_GLOBAL_REST_OF_WORLD_<timestamp>.csv
JOBSPY_VISA_SPONSORSHIP_<timestamp>.csv
JOBSPY_RAW_<timestamp>.csv
JOBSPY_RUN_SUMMARY_<timestamp>.csv
JOBSPY_RUN_SUMMARY_<timestamp>.txt
JOBSPY_RUN_<timestamp>.xlsx
JOBSPY_SEARCH_PROFILE_<timestamp>.json
```

The run summary should contain:

- start time
- finish time
- runtime
- stop reason
- searches completed
- raw results
- relevant 72h jobs
- last 24h jobs
- 24-72h jobs
- India count
- Middle East count
- Global count
- visa sponsorship count
- source health/errors

---

## 16. Excel Workbook

Recommended sheets:

- `RAW_RESULTS`
- `ALL_72H`
- `LAST_24H`
- `24_TO_72H`
- `INDIA`
- `MIDDLE_EAST`
- `GLOBAL`
- `VISA_SPONSORSHIP`
- `SOURCE_HEALTH`
- `RUN_SUMMARY`

---

## 17. Runtime / Exit Strategy

The runtime behavior must be explicit.

### Normal completion

All planned searches finish and the process exits.

### Search limit

When `SEARCH_COUNT >= MAX_SEARCHES`, the scheduler stops before starting another request.

### Runtime limit

When elapsed runtime reaches `MAX_RUNTIME_MINUTES`, the scheduler stops before starting another request.

### Manual stop

`Ctrl+C` stops immediately.

### Source failure

A source exception is logged and the next source continues.

### Recommended future improvement

Write checkpoints after each search or small batch so an interrupted run can resume without repeating already-completed work.

---

## 18. Launcher Behavior

The launcher must not hard-code Product Design.

Conceptually:

```bat
@echo off
cd /d C:\JobSpy
python main.py
cmd /k
```

`main.py` asks the user what type of job they are looking for and builds the search profile.

The terminal remains open after completion/error so tracebacks can be inspected.

---

## 19. Project Structure

```text
C:\JobSpy\
  main.py
  run_job_hunt.bat
  config\
    roles.yaml
    locations.yaml
    sources.yaml
  core\
    scheduler.py
    normalizer.py
    deduper.py
    classifier.py
    scorer.py
    visa.py
    freshness.py
    exporters.py
    checkpoint.py
  sources\
    jobspy_adapter.py
    wellfound.py
    greenhouse.py
    lever.py
    ashby.py
    smartrecruiters.py
    workday.py
    recruiter_sites.py
    design_boards.py
    remote_boards.py
  output\
  logs\
  checkpoints\
```

The main rule is that a source adapter should be replaceable without changing the scheduling, normalization, scoring, or export layers.

---

## 20. Development Phases

### Phase 1 - Stable JobSpy Core

Implement:

- user-entered target role
- query expansion
- India / Middle East / Global regions
- balanced region budgets
- round-robin locations
- 72-hour freshness
- 0-24 and 24-72 buckets
- visa/relocation classification
- deduplication
- timestamped CSV/Excel outputs
- run summary
- source error isolation

### Phase 2 - High-Value Specialist Sources

Add:

- Wellfound
- Cutshort
- Instahyre
- Foundit
- Dribbble
- Behance
- Coroflot
- selected remote boards

### Phase 3 - ATS Engine

Add:

- Greenhouse
- Lever
- Ashby
- SmartRecruiters
- Workday
- Teamtailor
- Personio
- Pinpoint
- direct company career pages

### Phase 4 - Recruitment Agencies

Add:

- Michael Page
- Randstad
- Hays
- Adecco
- Robert Walters
- Korn Ferry
- high-value regional recruiters

### Phase 5 - Agentic Application Workflow

Move beyond discovery:

```text
Discover
  -> Qualify
  -> Open job source
  -> Extract requirements
  -> Tailor resume / cover letter
  -> Prepare application
  -> Log application
  -> Schedule follow-up
```

Application automation must remain compliant with site terms, authentication requirements, CAPTCHA and anti-bot controls.

---

## 21. Agentic End State

The system ultimately becomes a personal job-search engine:

```text
USER QUERY
   -> SEARCH PROFILE
   -> REGION / SOURCE SCHEDULER
   -> SOURCE ADAPTERS
   -> NORMALIZATION
   -> DEDUPLICATION
   -> ROLE CLASSIFICATION
   -> FRESHNESS FILTER
   -> VISA / RELOCATION
   -> MATCH SCORING
   -> INDIA / MIDDLE EAST / GLOBAL
   -> CSV / EXCEL / LOG / DATABASE
   -> APPLICATION WORKFLOW
```

The goal is not to scrape a fixed number of listings. The goal is to consistently surface the best fresh opportunities for whatever job family the user enters, across a broad source ecosystem, while preserving location, freshness, sponsorship, source provenance and application URLs.

---

## 22. Source Research Notes

Current official documentation reviewed during preparation:

- JobSpy repository: https://github.com/speedyapply/JobSpy
- Ashby Public Job Posting API: https://developers.ashbyhq.com/docs/public-job-posting-api
- Ashby job posting documentation: https://developers.ashbyhq.com/reference/jobpostinglist
- SmartRecruiters Posting API: https://developers.smartrecruiters.com/docs/posting-api
- SmartRecruiters endpoints: https://developers.smartrecruiters.com/docs/endpoints
- Wellfound Jobs Terms: https://wellfound.com/terms/jobs

Important: the broader source list is a prioritized integration roadmap, not a claim that every named site currently exposes a public scraping API. Each source must be checked individually when implementing its adapter.

---

## 23. Recommended Initial Configuration

```python
MAX_SEARCHES = 500
MAX_RUNTIME_MINUTES = 90
MAX_HOURS = 72

INDIA_SHARE = 0.45
MIDDLE_EAST_SHARE = 0.30
GLOBAL_SHARE = 0.25

RESULTS_PER_SITE = 25
REQUEST_DELAY = 2.5
```

This is a controlled test setup. Increase the total budget only after observing actual source health and runtime.

---

## 24. Acceptance Tests

The implementation is considered correct only when:

1. The launcher asks the user for the target job family.
2. Changing the target job does not require modifying source code.
3. India, Middle East and Global all receive explicit budgets.
4. Delhi cannot consume the entire India allocation.
5. Noida and Gurgaon are explicitly searched.
6. Global has a guaranteed search allocation.
7. Naukri CAPTCHA does not terminate the run.
8. Glassdoor parser/location errors do not terminate the run.
9. Fresh datasets contain no jobs older than 72 hours.
10. Last-24h and 24-72h datasets are separate.
11. Every run creates timestamped files.
12. Every run creates a run summary showing date/time and counts.
13. Visa sponsorship is classified separately from unknown.
14. Duplicate jobs across sources collapse into a canonical record.
15. Source provenance is retained.
16. `Ctrl+C` stops cleanly.
17. Search/runtime hard limits stop the run safely.

---

## 25. Final Design Principle

JobSpy should be treated as **one ingestion adapter among many**.

The durable implementation is a modular search engine with:

- a user-configurable query profile,
- region-aware scheduling,
- source-aware adapters,
- freshness calculation,
- classification,
- visa/relocation extraction,
- deduplication,
- scoring,
- timestamped run artifacts,
- checkpoints,
- and eventually an agentic application layer.

This design avoids the failure mode discovered during testing: a large city-first loop that burns the entire search budget before the scraper ever reaches the Middle East or Global search.
