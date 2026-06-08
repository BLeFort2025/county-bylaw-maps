import pandas as pd
from datetime import datetime
df = pd.read_parquet("lower_single_map_beta.parquet")
df['Expiry Date'] = pd.to_datetime(df['Expiry Date'], errors='coerce')
expired = df[df['Expiry Date'] < datetime.now()]
print("EXPIRED in parquet:")
print(expired[['_MUNI_NAME', 'Expiry Date']])
