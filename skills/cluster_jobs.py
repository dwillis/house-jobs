#!/usr/bin/env python3
"""
cluster_jobs.py — Embed, cluster, and visualise Congressional job listings.

Pipeline:
  1. Load deduplicated jobs from json/ (same dedup logic as skill_extractor.py)
  2. Embed each job description via the Ollama API (default: qwen3-embedding:latest)
  3. Reduce to 2-D with UMAP for visualisation
  4. Cluster with HDBSCAN on the full-dimensional embeddings
  5. Auto-label each cluster by its most distinctive tf-idf terms
  6. Write outputs:
       skills/job_embeddings.csv   — job metadata + 2-D coords + cluster label
       skills/clusters.png         — UMAP scatter coloured by cluster
       skills/cluster_drift.png    — cluster composition shift over time
       skills/cluster_summary.txt  — cluster sizes and top terms

Usage:
    uv run python skills/cluster_jobs.py
    uv run python skills/cluster_jobs.py --model embeddinggemma
    uv run python skills/cluster_jobs.py --dir json_qwen
    uv run python skills/cluster_jobs.py --no-cache   # re-embed even if cache exists

Requires Ollama running locally (ollama serve).
"""

import json
import re
import sys
import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.lines import Line2D

REPO_ROOT = Path(__file__).parent.parent
OUT_DIR   = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))
from config import JSON_DIR as _JSON_DIR
DEFAULT_JSON_DIR = str(REPO_ROOT / _JSON_DIR)

DEFAULT_EMBED_MODEL = "qwen3-embedding:latest"
CACHE_PATH = OUT_DIR / "embeddings_cache.npz"

# ---------------------------------------------------------------------------
# Date / dedup helpers (same logic as skill_extractor.py)
# ---------------------------------------------------------------------------
_DATE_PATTERNS = [
    (re.compile(r'(\d{4})_(\d{2})_(\d{2})'),
     lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
    (re.compile(r'^(\d{1,2})-(\d{2})-(\d{2})_'),
     lambda m: "{}-{}-{}".format(
         f"20{m.group(3)}" if int(m.group(3)) < 50 else f"19{m.group(3)}",
         m.group(1).zfill(2), m.group(2)
     )),
    (re.compile(r'(\d{1,2})\.(\d{2})\.(\d{4})'),
     lambda m: f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2)}"),
]

def _date_from_filename(name: str) -> str | None:
    stem = Path(name).stem
    for pat, fmt in _DATE_PATTERNS:
        m = pat.search(stem)
        if m:
            return fmt(m)
    return None

def _safe_year(date: str | None) -> int | None:
    if not date or len(date) < 4:
        return None
    try:
        y = int(date[:4])
        return y if 2010 <= y <= 2030 else None
    except ValueError:
        return None

def _job_text(job: dict) -> str:
    parts: list[str] = []
    for f in ("position_title", "description"):
        v = job.get(f)
        if v:
            parts.append(str(v))
    for f in ("responsibilities", "qualifications"):
        v = job.get(f)
        if isinstance(v, list):
            parts.extend(str(x) for x in v if x)
        elif isinstance(v, str) and v:
            parts.append(v)
    return " ".join(parts)

def load_jobs(json_dir: str) -> list[dict]:
    """Load deduplicated jobs, keeping only the first appearance of each ID."""
    best: dict[str, tuple[str, str, dict]] = {}
    for filepath in sorted(Path(json_dir).glob("*.json")):
        fn_date = _date_from_filename(filepath.name)
        try:
            jobs = json.loads(filepath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(jobs, list):
            continue
        for job in jobs:
            jid = job.get("id", "")
            if not jid:
                continue
            date = fn_date or job.get("posting_date") or ""
            key  = date if date else "9999-99-99"
            if jid not in best or key < best[jid][0]:
                best[jid] = (key, date, job)

    records = []
    for jid, (_, date, job) in best.items():
        text = _job_text(job).strip()
        if not text:
            continue
        records.append({
            "job_id":         jid,
            "office":         job.get("office", ""),
            "position_title": job.get("position_title", ""),
            "date":           date,
            "year":           _safe_year(date),
            "text":           text,
        })
    print(f"  Loaded {len(records):,} unique jobs from {json_dir}/")
    return records


# ---------------------------------------------------------------------------
# Embedding via Ollama (with file-based cache keyed on model + corpus)
# ---------------------------------------------------------------------------

def _corpus_hash(texts: list[str], model_name: str) -> str:
    h = hashlib.md5()
    h.update(model_name.encode())
    for t in texts:
        h.update(t.encode("utf-8", errors="replace"))
    return h.hexdigest()


def _ollama_embed_batch(texts: list[str], model_name: str,
                        batch_size: int = 32) -> np.ndarray:
    """Embed texts in batches using the Ollama Python client."""
    import ollama

    all_vecs: list[list[float]] = []
    total = len(texts)
    for i in range(0, total, batch_size):
        batch = texts[i : i + batch_size]
        pct   = min(i + batch_size, total)
        print(f"  \r  Embedding {pct}/{total} …", end="", flush=True)
        response = ollama.embed(model=model_name, input=batch)
        all_vecs.extend(response["embeddings"])
    print()  # newline after progress
    return np.array(all_vecs, dtype=np.float32)


def embed(texts: list[str], model_name: str = DEFAULT_EMBED_MODEL,
          cache: bool = True) -> np.ndarray:
    corpus_hash = _corpus_hash(texts, model_name)

    if cache and CACHE_PATH.exists():
        stored = np.load(CACHE_PATH, allow_pickle=True)
        if str(stored.get("hash", "")) == corpus_hash:
            print(f"  Loaded embeddings from cache ({CACHE_PATH.name})")
            return stored["embeddings"]

    print(f"  Embedding {len(texts):,} texts with Ollama model '{model_name}' …")
    embeddings = _ollama_embed_batch(texts, model_name)

    # L2-normalise so cosine similarity == dot product
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    embeddings = embeddings / norms

    if cache:
        np.savez_compressed(CACHE_PATH, embeddings=embeddings, hash=corpus_hash)
        print(f"  Saved embedding cache → {CACHE_PATH.name}")
    return embeddings


# ---------------------------------------------------------------------------
# UMAP reduction
# ---------------------------------------------------------------------------

def reduce_umap(embeddings: np.ndarray, n_neighbors: int = 15,
                min_dist: float = 0.05) -> np.ndarray:
    print("  Running UMAP …")
    from umap import UMAP
    reducer = UMAP(n_components=2, n_neighbors=n_neighbors,
                   min_dist=min_dist, metric="cosine", random_state=42)
    return reducer.fit_transform(embeddings)


# ---------------------------------------------------------------------------
# HDBSCAN clustering
# ---------------------------------------------------------------------------

def cluster_hdbscan(embeddings: np.ndarray, min_cluster_size: int = 20,
                    min_samples: int = 5) -> np.ndarray:
    print("  Running HDBSCAN …")
    import hdbscan
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
    )
    return clusterer.fit_predict(embeddings)


# ---------------------------------------------------------------------------
# Cluster labelling via tf-idf top terms
# ---------------------------------------------------------------------------

def label_clusters(df: pd.DataFrame, n_terms: int = 5) -> dict[int, str]:
    from sklearn.feature_extraction.text import TfidfVectorizer

    labels: dict[int, str] = {}
    cluster_ids = sorted(df["cluster"].unique())

    all_texts = df["text"].tolist()
    # Fit on full corpus so idf is meaningful
    vec = TfidfVectorizer(
        max_features=8000,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=3,
    )
    tfidf_matrix = vec.fit_transform(all_texts)
    feature_names = np.array(vec.get_feature_names_out())

    for cid in cluster_ids:
        if cid == -1:
            labels[-1] = "noise"
            continue
        mask = (df["cluster"] == cid).values
        cluster_tfidf = tfidf_matrix[mask].mean(axis=0)
        # Convert to flat array
        scores = np.asarray(cluster_tfidf).flatten()
        top_idx = scores.argsort()[-n_terms:][::-1]
        top_terms = ", ".join(feature_names[top_idx])
        labels[cid] = f"C{cid}: {top_terms}"

    return labels


# ---------------------------------------------------------------------------
# Visualisations
# ---------------------------------------------------------------------------

def _cluster_colors(n_clusters: int) -> list:
    cmap = cm.get_cmap("tab20", max(n_clusters, 1))
    return [cmap(i) for i in range(n_clusters)]


def plot_umap_scatter(df: pd.DataFrame, cluster_labels: dict[int, str],
                      out_path: str) -> None:
    cluster_ids = sorted(c for c in df["cluster"].unique() if c != -1)
    colors = _cluster_colors(len(cluster_ids))
    color_map = {cid: colors[i] for i, cid in enumerate(cluster_ids)}
    color_map[-1] = (0.7, 0.7, 0.7, 0.3)  # noise = translucent grey

    fig, ax = plt.subplots(figsize=(16, 12))

    # Noise first (background)
    noise = df[df["cluster"] == -1]
    ax.scatter(noise["umap_x"], noise["umap_y"], c=[color_map[-1]],
               s=4, linewidths=0, label=None)

    for cid in cluster_ids:
        sub = df[df["cluster"] == cid]
        ax.scatter(sub["umap_x"], sub["umap_y"], c=[color_map[cid]],
                   s=10, linewidths=0, alpha=0.8)
        # Label at centroid
        cx, cy = sub["umap_x"].mean(), sub["umap_y"].mean()
        short = cluster_labels[cid].split(":")[0]  # "C3"
        ax.annotate(short, (cx, cy), fontsize=7, ha="center",
                    color="black", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.6, lw=0))

    legend_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=color_map[c],
               markersize=7, label=cluster_labels[c][:60])
        for c in cluster_ids
    ]
    ax.legend(handles=legend_handles, fontsize=6.5, ncol=2,
              loc="lower left", framealpha=0.85)
    ax.set_title("Congressional Job Listings — UMAP + HDBSCAN Clusters (2013–2026)",
                 fontsize=13)
    ax.set_xlabel("UMAP-1"); ax.set_ylabel("UMAP-2")
    ax.grid(alpha=0.15)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Wrote {out_path}")


def plot_cluster_drift(df: pd.DataFrame, cluster_labels: dict[int, str],
                       out_path: str) -> None:
    """Stacked area chart: share of each cluster per year."""
    year_df = df[(df["year"].notna()) & (df["cluster"] != -1)].copy()
    year_df["year"] = year_df["year"].astype(int)
    cluster_ids = sorted(year_df["cluster"].unique())

    pivot = (
        year_df.groupby(["year", "cluster"])["job_id"]
        .count()
        .unstack(fill_value=0)
    )
    # Normalise to share
    pivot = pivot.div(pivot.sum(axis=1), axis=0) * 100

    colors = _cluster_colors(len(cluster_ids))
    fig, ax = plt.subplots(figsize=(14, 6))
    pivot.plot.area(ax=ax, color=colors, alpha=0.8, linewidth=0)

    # Rewrite legend with cluster labels
    handles, _ = ax.get_legend_handles_labels()
    new_labels = [cluster_labels.get(int(c), str(c))[:55] for c in pivot.columns]
    ax.legend(handles, new_labels, fontsize=6.5, ncol=2,
              loc="upper left", framealpha=0.85)
    ax.set_xlabel("Year"); ax.set_ylabel("% of Jobs")
    ax.set_title("Job Type Composition Over Time (share of cluster per year)")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Wrote {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(json_dir: str, embed_model: str = DEFAULT_EMBED_MODEL,
         use_cache: bool = True) -> None:
    print(f"\n1. Loading jobs from {json_dir} …")
    records = load_jobs(json_dir)
    if not records:
        print("No jobs found. Check --dir path.")
        return

    texts = [r["text"] for r in records]

    print(f"\n2. Embedding with '{embed_model}' …")
    embeddings = embed(texts, model_name=embed_model, cache=use_cache)

    print("\n3. UMAP dimensionality reduction …")
    coords_2d = reduce_umap(embeddings)

    print("\n4. HDBSCAN clustering …")
    cluster_ids = cluster_hdbscan(embeddings)

    df = pd.DataFrame(records)
    df["umap_x"]  = coords_2d[:, 0]
    df["umap_y"]  = coords_2d[:, 1]
    df["cluster"] = cluster_ids

    n_clusters = int((cluster_ids >= 0).sum() > 0 and cluster_ids.max() + 1)
    n_noise    = int((cluster_ids == -1).sum())
    print(f"  → {n_clusters} clusters, {n_noise} noise points "
          f"({n_noise/len(cluster_ids)*100:.1f}% of corpus)")

    print("\n5. Labelling clusters via tf-idf …")
    cluster_labels = label_clusters(df)

    print("\n6. Writing outputs …")
    # CSV
    csv_path = OUT_DIR / "job_embeddings.csv"
    df.drop(columns=["text"]).to_csv(csv_path, index=False)
    print(f"Wrote {csv_path}")

    # Plots
    plot_umap_scatter(df, cluster_labels, str(OUT_DIR / "clusters.png"))
    plot_cluster_drift(df, cluster_labels, str(OUT_DIR / "cluster_drift.png"))

    # Summary text
    summary_path = OUT_DIR / "cluster_summary.txt"
    lines = [
        f"HDBSCAN Clusters — {len(records):,} unique jobs\n",
        f"{'Cluster':<8} {'Size':>6}  {'% of corpus':>12}  Top terms\n",
        "-" * 90,
    ]
    for cid in sorted(cluster_labels):
        if cid == -1:
            continue
        size = int((df["cluster"] == cid).sum())
        pct  = size / len(df) * 100
        lines.append(f"{cluster_labels[cid]:<70}  {size:>5}  {pct:>5.1f}%")
    noise_pct = n_noise / len(df) * 100
    lines.append(f"\n{'noise':<70}  {n_noise:>5}  {noise_pct:>5.1f}%")
    summary_path.write_text("\n".join(lines))
    print(f"Wrote {summary_path}")

    print("\n=== Cluster Summary ===")
    for line in lines:
        print(line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed and cluster House job listings.")
    parser.add_argument("--dir", default=DEFAULT_JSON_DIR,
                        help="Path to JSON directory (default: json/)")
    parser.add_argument("--model", default=DEFAULT_EMBED_MODEL,
                        help=f"Ollama embedding model (default: {DEFAULT_EMBED_MODEL})")
    parser.add_argument("--no-cache", action="store_true",
                        help="Re-embed even if cache exists")
    args = parser.parse_args()

    json_dir = str(REPO_ROOT / args.dir) if not Path(args.dir).is_absolute() else args.dir
    main(json_dir, embed_model=args.model, use_cache=not args.no_cache)
