# Geographic Budgets & Scheduling

AuraJobs implements an interleaved round-robin scheduler to balance query budgets across three distinct geographic spheres.

---

## 🗺️ Geographic Tiers

### 1. India (Allocated 45% Budget)
- **Metros Covered**: Bengaluru, Delhi, Noida, Gurgaon, Mumbai, Pune, Hyderabad, Chandigarh, Kochi, Mangalore.
- **Platforms**: LinkedIn, Indeed India, Google Jobs India, Glassdoor, Naukri.

### 2. Middle East / GCC (Allocated 30% Budget)
- **Hubs Covered**:
  - UAE: Dubai, Abu Dhabi
  - Saudi Arabia: Riyadh, Jeddah
  - Qatar: Doha
  - Kuwait: Kuwait City
  - Bahrain: Manama
  - Oman: Muscat
- **Platforms**: LinkedIn ME, Indeed regional endpoints, Google Jobs ME.

### 3. Global & Remote (Allocated 25% Budget)
- **Remote Networks**: RemoteOK, Remotive, Himalayas.
- **Direct ATS**: Ashby, Greenhouse, Lever.
- **Worldwide Search**: Global LinkedIn and Google Jobs endpoints.

---

## ⚡ Execution Modes

| Mode | Duration | Query Depth | Use Case |
| :--- | :--- | :--- | :--- |
| **Express Mode** | ~1–2 minutes | Instant APIs + Top Tier Metros (Bengaluru, Delhi, Dubai, Riyadh) | Daily rapid checks |
| **Deep Scan Mode** | ~5–10 minutes | Exhaustive rotation across all 20+ cities | Comprehensive weekly sweeps |
