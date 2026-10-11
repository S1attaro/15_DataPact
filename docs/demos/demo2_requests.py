"""
A5 API demo 2: consume DataPact's public internal JSON API from a
plain Python script using the requests library.

Uses /api/run-outcomes/, which is unauthenticated by design (the
anonymous-access public endpoint for A5), unlike /api/datasets/, which
is now access-controlled.

Run with the dev server up at http://127.0.0.1:8000/:
    python docs/demos/demo2_requests.py
"""

import requests

API_URL = "http://127.0.0.1:8000/api/run-outcomes/"


def main():
    response = requests.get(API_URL, timeout=5)
    response.raise_for_status()
    rows = response.json()

    print(f"Fetched {len(rows)} outcome rows from {API_URL}\n")

    total_runs = 0
    for row in rows:
        print(f"- {row['outcome']}: {row['runs']} runs")
        total_runs += row["runs"]

    print(f"\nTotal validation runs: {total_runs}")


if __name__ == "__main__":
    main()