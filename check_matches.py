import pandas as pd
df = pd.read_csv('signals/lgd_extraction_review_2026-04-30.csv')
no_id = df[df['DB_bylaw_id'].isna()]
print(f"No DB match: {len(no_id)}")
for _, r in no_id.iterrows():
    print(f"  - {r['Municipality']} ({r['County']})")
