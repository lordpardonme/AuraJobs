# Extending Adapters & Adding Companies

AuraJobs is built on a modular adapter architecture, making it easy to add new hiring platforms and company ATS endpoints.

---

## 1. Adding Direct Company ATS (`config/companies.yaml`)

To monitor job postings directly from tech companies, add their ATS slug to [`config/companies.yaml`](../../config/companies.yaml):

```yaml
companies:
  ashby:
    - name: "Anthropic"
      slug: "anthropic"
    - name: "Linear"
      slug: "linear"

  greenhouse:
    - name: "Stripe"
      slug: "stripe"
    - name: "Figma"
      slug: "figma"

  lever:
    - name: "Netflix"
      slug: "netflix"
```

AuraJobs queries these APIs in parallel during Stage 1 of every execution without rate-limit penalties.

---

## 2. Implementing a Custom Source Adapter

Create a new file in `sources/` inheriting from `BaseSourceAdapter` (`sources/base.py`):

```python
import pandas as pd
from .base import BaseSourceAdapter

class MyCustomJobSourceAdapter(BaseSourceAdapter):
    def __init__(self):
        super().__init__(name="my_source")

    def search(self, term: str, location: str, region: str, country: str,
               hours_old: int = 72, results_wanted: int = 25) -> pd.DataFrame:
        # 1. Fetch raw jobs
        raw_data = fetch_external_jobs(term, location)

        # 2. Return DataFrame with canonical columns
        return pd.DataFrame(raw_data)
```

Export your adapter in `sources/__init__.py` and add it to the execution pool in `main.py`.
