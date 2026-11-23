from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw")

for csv_file in sorted(RAW_DIR.glob("*.csv")):
    df = pd.read_csv(csv_file)
    print("=" * 70)
    print(f"FILE: {csv_file.name}")
    print(f"Rows: {len(df):,}   Columns: {len(df.columns)}")
    print("\nColumns and types:")
    print(df.dtypes.to_string())
    print("\nNull counts (only columns with nulls):")
    nulls = df.isnull().sum()
    print(nulls[nulls > 0].to_string() if nulls.any() else "None")
    print("\nFirst 3 rows:")
    print(df.head(3).to_string())
    print()
