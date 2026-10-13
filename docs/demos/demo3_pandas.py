"""
A5 API demo 3: load DataPact's public run-outcomes API straight into
a pandas DataFrame and run a couple of real queries on it.

Uses /api/run-outcomes/, the anonymous-access public endpoint for A5.

Run with the dev server up at http://127.0.0.1:8000/:
    python docs/demos/demo3_pandas.py
"""

import pandas as pd

API_URL = "https://tjaggi.pythonanywhere.com/api/run-outcomes/"

print(f"Calling production API: {API_URL}")


def main():
    df = pd.read_json(API_URL)

    print(f"Loaded {len(df)} outcome rows into a DataFrame\n")
    print(df)

    print(f"\nTotal runs across all outcomes: {df['runs'].sum()}")

    pass_rate = df.loc[df["outcome"] == "Passed", "runs"].sum() / df["runs"].sum()
    print(f"Pass rate: {pass_rate:.1%}")


if __name__ == "__main__":
    main()
