"""
A4/A5 API demo 3: load DataPact's internal JSON API straight into a
pandas DataFrame and run a couple of real queries on it, the kind of
thing a data analyst on the team might actually do with this endpoint.

Run with the dev server up at http://127.0.0.1:8000/:
    python docs/demos/demo3_pandas.py
"""

import pandas as pd

API_URL = "http://127.0.0.1:8000/api/datasets/"


def main():
    df = pd.read_json(API_URL)
    datasets = pd.json_normalize(df["datasets"])

    print(f"Loaded {len(datasets)} datasets into a DataFrame\n")
    print(datasets[["name", "owner", "source_team"]])

    print("\nDataset count per source team:")
    print(datasets.groupby("source_team").size())

    print("\nDataset count per owner:")
    print(datasets.groupby("owner").size())


if __name__ == "__main__":
    main()