"""
A4/A5 API demo 2: consume DataPact's internal JSON API from a plain
Python script using the requests library, the same library our own
external-API view (dataset_lookup_api) uses internally.

Run with the dev server up at http://127.0.0.1:8000/:
    python docs/demos/demo2_requests.py
"""

import requests

API_URL = "http://127.0.0.1:8000/api/datasets/"


def main():
    response = requests.get(API_URL, timeout=5)
    response.raise_for_status()
    data = response.json()

    print(f"Fetched {data['count']} datasets from {API_URL}\n")

    for dataset in data["datasets"]:
        print(f"- {dataset['name']} (owned by {dataset['owner']}, "
              f"team: {dataset['source_team']})")

    teams = {}
    for dataset in data["datasets"]:
        team = dataset["source_team"]
        teams[team] = teams.get(team, 0) + 1

    print("\nDatasets per source team:")
    for team, count in sorted(teams.items()):
        print(f"  {team}: {count}")


if __name__ == "__main__":
    main()