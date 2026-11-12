"""Create a simulated A/B test dataset (one row per user).

Scenario: Zillow-style listing page. The new design ("treatment") moves the
"Contact agent" button higher on the page. Did more users contact an agent?

Run: python generate_data.py   ->  data/experiment_users.csv
"""
import numpy as np
import pandas as pd

rng = np.random.default_rng(seed=1)
N = 120_000

variant = rng.choice(["control", "treatment"], size=N)
device = rng.choice(["mobile", "desktop", "tablet"], size=N, p=[0.60, 0.35, 0.05])
sessions = 1 + rng.poisson(1.5, size=N)

# Chance of contacting an agent: 10% baseline, a bit higher for heavy users.
base = 0.08 + 0.01 * np.minimum(sessions, 4)
# True effect of the new design (hidden from the analysis):
# +9% relative on mobile, +1% on desktop, +4% on tablet.
lift = np.select([device == "mobile", device == "desktop"], [0.09, 0.01], 0.04)
p = np.where(variant == "treatment", base * (1 + lift), base)
contacted_agent = (rng.random(N) < p).astype(int)

# Guardrail: the new page is slightly heavier (~30 ms slower).
page_load_ms = rng.normal(1300, 250, N) + np.where(variant == "treatment", 30, 0)

df = pd.DataFrame({
    "user_id": np.arange(1, N + 1),
    "variant": variant,
    "device": device,
    "sessions": sessions,
    "contacted_agent": contacted_agent,
    "page_load_ms": page_load_ms.round().astype(int),
})
df.to_csv("data/experiment_users.csv", index=False)
print(f"Saved {len(df):,} users to data/experiment_users.csv")
