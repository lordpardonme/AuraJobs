# Role Taxonomies & Custom Expansion

AuraJobs features a 2-layer role processing pipeline: **Handcrafted Presets** and a **Dynamic Custom Expander**.

---

## 1. Handcrafted Presets (`config/roles.yaml`)

Each preset defines aliases, query variations, positive title matching tokens, and core skill keywords:

| Preset Name | Domain | Typical Titles | Key Skills Monitored |
| :--- | :--- | :--- | :--- |
| **Product Design** | Tech / Design | Product Designer, UX Designer, UI Designer, UX Researcher, Design Systems Lead | Figma, Design Systems, Prototyping, Wireframing, UX Research, Interaction Design |
| **Data Science & AI/ML** | Tech | Data Scientist, Machine Learning Engineer, AI Engineer, Applied Scientist | Python, PyTorch, TensorFlow, SQL, LLMs, NLP, Computer Vision, MLOps |
| **Frontend Engineering** | Tech | Frontend Engineer, Frontend Developer, React Developer, UI Engineer | React, TypeScript, Next.js, Vue, Redux, GraphQL, CSS/HTML, Tailwind |
| **Software Engineering** | Tech | Software Engineer, Backend Engineer, Full Stack Engineer, Founding Engineer | Python, Java, Go, Node.js, Distributed Systems, Microservices, AWS, Docker, Kubernetes, SQL |
| **Product Management** | Non-Tech / Business | Product Manager, Technical PM, Associate PM, Group PM, Head of Product | Roadmapping, Agile, Scrum, PRD, User Stories, Product Analytics, A/B Testing, SQL, JIRA |
| **Growth & Marketing** | Non-Tech / Business | Marketing Manager, Growth Manager, Performance Marketer, Product Marketing | SEO, SEM, Google Ads, Meta Ads, Google Analytics, HubSpot, CRO, Email Marketing |
| **Operations & Strategy** | Non-Tech / Business | Operations Manager, BizOps, Strategy & Operations, Chief of Staff | Process Optimization, Data Analysis, Excel, SQL, Project Management, KPIs |
| **People & Talent / HR** | Non-Tech / Business | Technical Recruiter, Talent Acquisition Specialist, HRBP, People Operations | Recruiting, Sourcing, ATS (Greenhouse, Lever), Employer Branding, HR Policies |
| **Sales & Business Dev** | Non-Tech / Business | Account Executive, Business Development Manager, Sales Manager, SDR/BDR | B2B Sales, Salesforce, CRM, Cold Outreach, Lead Gen, Pipeline Management |

---

## 2. Dynamic Custom Expander (`core/expander.py`)

If you search for any role outside the presets (e.g. *DevOps Engineer*, *Legal Counsel*, *Financial Controller*):
1. **Seniority Parsing**: Automatically strips prefixes (`Intern`, `Junior`, `Mid`, `Senior`, `Staff`, `Lead`, `Principal`, `Director`, `VP`).
2. **Expansion**: Generates level-specific search phrases.
3. **Collision Avoidance**: If you select `Senior`, the expander excludes junior/intern postings automatically.
4. **Self-Exclusion Protection**: Filters out global design exclusions if the user explicitly searches for creative keywords.
