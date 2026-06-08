import pandas as pd
from datetime import datetime
df = pd.read_parquet("upper_single_map_beta.parquet")
if 'Expiry Date' in df.columns:
    df['Expiry Date'] = pd.to_datetime(df['Expiry Date'], errors='coerce')
    expired = df[df['Expiry Date'] < datetime.now()]
    print("EXPIRED in UPPER parquet:")
    print(expired[['_UPPER_NAME', 'Expiry Date']])
else:
    print("No Expiry Date in upper parquet")
