import pandas as pd
import sys

sys.stdout.reconfigure(encoding='utf-8')
csv_path = r"C:\Users\ben.lefort\Downloads\multi_keyword_scan_2026-06-15.csv"

try:
    df = pd.read_csv(csv_path)
    print("Columns:", df.columns.tolist())
    print("\nFirst 3 rows:")
    for i, row in df.head(3).iterrows():
        print(f"--- Row {i} ---")
        for col in df.columns:
            val = str(row[col])
            # truncate long snippets for terminal viewing
            if len(val) > 200:
                val = val[:200] + "..."
            print(f"{col}: {val}")
except Exception as e:
    print(f"Error reading CSV: {e}")
