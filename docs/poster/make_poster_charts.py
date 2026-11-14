"""
Poster charts and numbers (A10 / poster, Connor Slattery).

Reads data/ai_logs.csv (the dashboard data) and the A8 evaluation CSVs, and
writes vector charts (SVG, so they print sharp at 22x36) plus key_numbers.md
into this folder. Run it again after a new collect_ai_logs run:

    python docs/poster/make_poster_charts.py
"""

import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LOGS = ROOT / "data" / "ai_logs.csv"
A8 = ROOT / "rag_system" / "evaluation"

ENGINE_COLORS = {"local": "#2f5d8a", "ollama:smollm2:1.7b": "#7fa7cf", "ollama:qwen2.5:14b": "#6b8f3a",
                 "groq": "#c2662d"}
ENGINE_NAMES = {"local": "SmolLM2 (CPU)", "ollama:smollm2:1.7b": "SmolLM2 (GPU, Ollama)",
                "ollama:qwen2.5:14b": "Qwen2.5 14B (GPU, Ollama)", "groq": "Groq gpt-oss-20b"}


def engine_key(row):
    """Ollama rows are split by model, since we ran more than one model there."""
    if row["engine"] == "ollama":
        return f"ollama:{row['model_name']}"
    return row["engine"]

plt.rcParams.update({"font.size": 15, "axes.titlesize": 18, "axes.titleweight": "bold",
                     "axes.spines.top": False, "axes.spines.right": False, "svg.fonttype": "none"})


def load_logs():
    with LOGS.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for name in ("latency_ms", "retrieval_ms", "cost_usd"):
            row[name] = float(row[name])
        for name in ("prompt_tokens", "completion_tokens"):
            row[name] = int(row[name])
    return rows


def pct(values, p):
    data = sorted(values)
    k = (len(data) - 1) * p / 100
    low = int(k)
    high = min(low + 1, len(data) - 1)
    return data[low] + (data[high] - data[low]) * (k - low)


def latency_chart(rows):
    groups = defaultdict(list)
    for row in rows:
        if row["status"] != "error":
            groups[(row["feature"], engine_key(row))].append(row["latency_ms"] / 1000)
    keys = sorted(groups, key=lambda k: (k[0], list(ENGINE_COLORS).index(k[1])))
    fig, ax = plt.subplots(figsize=(9, 7))
    box = ax.boxplot([groups[k] for k in keys], orientation="horizontal", showfliers=False, patch_artist=True,
                     medianprops={"color": "black", "linewidth": 2})
    for patch, key in zip(box["boxes"], keys):
        patch.set_facecolor(ENGINE_COLORS[key[1]])
        patch.set_alpha(0.85)
    ax.set_yticks(range(1, len(keys) + 1), [f"{f.capitalize()}\n{ENGINE_NAMES[e]}" for f, e in keys])
    ax.set_xlabel("Seconds per request")
    ax.set_title("Latency by feature and engine")
    fig.tight_layout()
    fig.savefig(HERE / "fig_latency_by_engine.svg")
    plt.close(fig)
    return {k: (statistics.median(v), pct(v, 95), len(v)) for k, v in groups.items()}


def cost_chart(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[engine_key(row)].append(row["cost_usd"])
    engines = [e for e in ENGINE_COLORS if e in groups]
    per_1000 = [sum(groups[e]) / len(groups[e]) * 1000 for e in engines]
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh([ENGINE_NAMES[e] for e in engines], per_1000, color=[ENGINE_COLORS[e] for e in engines])
    ax.bar_label(bars, labels=[f"${v:.3f}" for v in per_1000], padding=6)
    ax.set_xlabel("Dollars per 1,000 requests")
    ax.set_title("Cost per 1,000 requests")
    ax.set_xlim(0, max(per_1000) * 1.3)
    fig.text(0.01, 0.01, "Local = electricity only (CPU 150 W, GPU 355 W, $0.15/kWh); no hardware or hosting.",
             fontsize=11, color="#555")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(HERE / "fig_cost_per_1000.svg")
    plt.close(fig)
    return dict(zip(engines, per_1000))


def rag_chart():
    with (A8 / "improvement_manual.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    names = {"baseline": "Baseline", "top_k_1": "Top-1 passage", "top_k_5": "Top-5 passages",
             "strict_prompt": "Strict prompt"}
    labels = [names.get(r["variant"], r["variant"]) for r in rows]
    scores = [float(r["answer_score (manual)"]) for r in rows]
    colors = ["#2f5d8a" if r["variant"] == "strict_prompt" else "#9bb3cc" for r in rows]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(labels, scores, color=colors)
    ax.bar_label(bars, labels=[f"{s:.1f}" for s in scores], padding=4)
    ax.set_ylabel("Answer score (manual, %)")
    ax.set_ylim(0, 75)
    ax.set_title("RAG answer quality by setup (A8, 12 questions)")
    fig.tight_layout()
    fig.savefig(HERE / "fig_rag_improvement.svg")
    plt.close(fig)
    return rows


def main():
    rows = load_logs()
    latency = latency_chart(rows)
    cost = cost_chart(rows)
    rag = rag_chart()

    handbook = [r for r in rows if r["feature"] == "handbook"]
    by_status = defaultdict(int)
    for r in handbook:
        by_status[r["status"]] += 1
    out_scope = [r for r in handbook if r["query_type"] == "out_of_scope"]
    handbook_local = [r for r in handbook if r["engine"] == "local" and r["status"] != "error" and r["retrieval_ms"]]
    retrieval_share = (statistics.median(r["retrieval_ms"] / r["latency_ms"] for r in handbook_local) * 100
                       if handbook_local else 0)
    sources = sorted({r["source"] for r in rows})

    lines = ["# Poster key numbers", "",
             f"Generated from data/ai_logs.csv ({len(rows)} requests, source: {', '.join(sources)}).",
             "Re-run make_poster_charts.py after a new collect_ai_logs run.", "",
             "## Latency (seconds, answered requests)", "",
             "| Feature | Engine | Median | p95 | Requests |", "|---|---|---|---|---|"]
    for (feature, engine), (median, p95, n) in sorted(latency.items()):
        lines.append(f"| {feature} | {ENGINE_NAMES[engine]} | {median:.2f} | {p95:.2f} | {n} |")
    lines += ["", "## Cost per 1,000 requests", "", "| Engine | $ per 1,000 |", "|---|---|"]
    lines += [f"| {ENGINE_NAMES[e]} | ${v:.4f} |" for e, v in cost.items()]
    lines += ["", "## Handbook outcomes", "", "| Outcome | Requests | Share |", "|---|---|---|"]
    lines += [f"| {status} | {n} | {n / len(handbook) * 100:.1f}% |" for status, n in sorted(by_status.items())]
    if out_scope:
        failed = sum(1 for r in out_scope if r["status"] != "ok")
        lines += ["", f"Out-of-scope (pricing/support/legal) questions: {len(out_scope)} "
                      f"({len(out_scope) / len(handbook) * 100:.1f}% of handbook traffic); "
                      f"{failed / len(out_scope) * 100:.0f}% not answered."]
    lines += ["", f"Retrieval is {retrieval_share:.1f}% of handbook latency (median); generation is the rest.",
              "", "## A8 RAG improvement (manual grades)", "",
              "| Setup | Answer score | Wrong refusals |", "|---|---|---|"]
    lines += [f"| {r['variant']} | {r['answer_score (manual)']} | {r['wrong refusals']} |" for r in rag]
    (HERE / "key_numbers.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote fig_latency_by_engine.svg, fig_cost_per_1000.svg, fig_rag_improvement.svg, key_numbers.md")


if __name__ == "__main__":
    main()
