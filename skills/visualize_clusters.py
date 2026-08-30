#!/usr/bin/env python3
"""Visualize the HDBSCAN job-listing clusters produced by cluster_jobs.py.

Three subcommands (or `all`):
  explorer  — self-contained interactive HTML (skills/cluster_explorer.html)
  trends    — per-cluster share of postings by year (small-multiples PNG)
  map       — annotated publication scatter (PNG + SVG)

Reads the per-listing-type cluster CSVs and summary files written by
cluster_jobs.py, joins job_category from json_v3/, and uses hand-editable names
from cluster_names.json. Run cluster_jobs.py first:

    uv run python skills/cluster_jobs.py --dir json_v3 --listing-type staff \
        --min-cluster-size 10 --min-samples 3
    uv run python skills/cluster_jobs.py --dir json_v3 --listing-type internship \
        --role-focused --min-cluster-size 15 --min-samples 3

Then:
    uv run python skills/visualize_clusters.py all

Colors follow the project dataviz palette. Cluster coloring is a *composite*
encoding — UMAP position is the primary identity carrier; color is a secondary
locator and the hover/panel/labels give authoritative identity — so the 20+
cluster hues intentionally exceed the categorical-palette cap. job_category
coloring uses a validated 4-hue set (blue/orange/aqua/violet, all-pairs light).
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).parent
REPO_ROOT = OUT_DIR.parent

LISTING_TYPES = ("staff", "internship")
CSV_NAME = {"staff": "job_embeddings_staff.csv", "internship": "job_embeddings_role_internship.csv"}
SUMMARY_NAME = {"staff": "cluster_summary_staff.txt", "internship": "cluster_summary_role_internship.txt"}
RECLUSTER_CMD = {
    "staff": "uv run python skills/cluster_jobs.py --dir json_v3 --listing-type staff "
             "--min-cluster-size 10 --min-samples 3",
    "internship": "uv run python skills/cluster_jobs.py --dir json_v3 --listing-type internship "
                  "--role-focused --min-cluster-size 15 --min-samples 3",
}

# job_category palette — validated all-pairs (light) blue/orange/aqua/violet.
CATEGORY_COLORS = {
    "administrative": "#2a78d6",
    "legislative": "#eb6834",
    "communications": "#1baf7a",
    "constituent_services": "#4a3aa7",
    "unknown": "#898781",
}
CATEGORY_ORDER = ["administrative", "legislative", "communications", "constituent_services", "unknown"]

# Cluster locator cycle (composite encoding; position is primary). 20 distinct hues.
CLUSTER_CYCLE = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7", "#008300", "#e34948",
    "#7f5539", "#00a5b5", "#b5179e", "#5a8f00", "#8d6bd8", "#d1495b", "#0f7fa6", "#c98500",
    "#3a7d44", "#9c6644", "#c05299", "#41708c",
]
NOISE_COLOR = "#c9c8c2"

# Chart chrome
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
REF_LINE = "#c9c8c2"

SUMMARY_RE = re.compile(r"^C(\d+):\s*(.*?)\s{2,}(\d+)\s+([\d.]+)%\s*$")


# --------------------------------------------------------------------------
# Data layer
# --------------------------------------------------------------------------
def _require(path: Path, listing_type: str) -> None:
    if not path.exists():
        sys.exit(
            f"Missing {path.name}. Run clustering for '{listing_type}' first:\n    {RECLUSTER_CMD[listing_type]}"
        )


def load_points(listing_type: str) -> pd.DataFrame:
    path = OUT_DIR / CSV_NAME[listing_type]
    _require(path, listing_type)
    df = pd.read_csv(path)
    df["cluster"] = df["cluster"].astype(int)
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    return df


def load_json_meta(json_dir: str) -> dict[str, str]:
    """id -> job_category (first occurrence wins; values are consistent per id)."""
    meta: dict[str, str] = {}
    for path in sorted(Path(json_dir).glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            jobs = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(jobs, list):
            continue
        for job in jobs:
            jid = job.get("id")
            if jid and jid not in meta:
                meta[jid] = job.get("job_category") or "unknown"
    return meta


def load_cluster_terms(listing_type: str) -> dict[int, list[str]]:
    path = OUT_DIR / SUMMARY_NAME[listing_type]
    _require(path, listing_type)
    terms: dict[int, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("C") or ":" not in line:
            continue
        m = SUMMARY_RE.match(line)
        if not m:
            sys.exit(f"Unparseable summary line in {path.name}:\n  {line!r}")
        cid = int(m.group(1))
        terms[cid] = [t.strip() for t in m.group(2).split(",") if t.strip()]
    return terms


def load_cluster_names(listing_type: str, names_path: Path, terms: dict[int, list[str]]) -> dict[int, str]:
    data = json.loads(names_path.read_text(encoding="utf-8")).get(listing_type, {})
    names: dict[int, str] = {-1: "Unclustered"}
    for cid, tlist in terms.items():
        if str(cid) in data:
            names[cid] = data[str(cid)]
        else:
            names[cid] = " / ".join(tlist[:2]) if tlist else f"Cluster {cid}"
    return names


def assemble(listing_type: str, json_meta: dict[str, str], names_path: Path):
    """Return (df with job_category, terms dict, names dict)."""
    df = load_points(listing_type)
    df["job_category"] = df["job_id"].map(json_meta).fillna("unknown")
    coverage = (df["job_id"].isin(json_meta)).mean()
    if coverage < 0.95:
        print(f"  warning: only {coverage:.1%} of {listing_type} ids matched json_v3 metadata")
    terms = load_cluster_terms(listing_type)
    names = load_cluster_names(listing_type, names_path, terms)
    # sanity: every non-noise cluster id in the CSV has a name + terms
    for cid in sorted(c for c in df["cluster"].unique() if c != -1):
        assert cid in names and cid in terms, f"cluster {cid} missing name/terms for {listing_type}"
    return df, terms, names


# --------------------------------------------------------------------------
# map subcommand
# --------------------------------------------------------------------------
# Editable callouts: (listing_type, cluster_id) -> annotation text.
CALLOUTS = {
    ("staff", 12): "Press & digital media is the single largest staff cluster (15% of clustered jobs).",
    ("staff", 20): "Schedulers form a tight, well-separated cluster.",
    ("staff", 7): "Committee oversight & investigations roles sit apart from member-office jobs.",
    ("internship", 21): "Press/digital interns are the clearest internship theme.",
    ("internship", 1): "Law-clerk internships separate cleanly on required legal skills.",
}


def _cluster_color(cid: int) -> str:
    return NOISE_COLOR if cid == -1 else CLUSTER_CYCLE[cid % len(CLUSTER_CYCLE)]


def plot_map(df: pd.DataFrame, names: dict[int, str], listing_type: str) -> None:
    fig, ax = plt.subplots(figsize=(14, 11))
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    noise = df[df["cluster"] == -1]
    ax.scatter(noise["umap_x"], noise["umap_y"], s=3, c=NOISE_COLOR, alpha=0.25, linewidths=0)

    clustered = df[df["cluster"] != -1]
    cluster_ids = sorted(clustered["cluster"].unique())
    for cid in cluster_ids:
        pts = clustered[clustered["cluster"] == cid]
        ax.scatter(pts["umap_x"], pts["umap_y"], s=10, c=_cluster_color(cid), alpha=0.75, linewidths=0)

    # Centroid labels with iterative box-overlap resolution (width-aware, vertical push).
    xr = clustered["umap_x"].max() - clustered["umap_x"].min()
    yr = clustered["umap_y"].max() - clustered["umap_y"].min()
    labels = []  # (cid, anchor_x, anchor_y, label_x, label_y, half_w, half_h)
    for cid in sorted(cluster_ids, key=lambda c: -len(clustered[clustered["cluster"] == c])):
        pts = clustered[clustered["cluster"] == cid]
        cx, cy = float(pts["umap_x"].median()), float(pts["umap_y"].median())
        name = names.get(cid, str(cid))
        hw = max(len(name), 6) * 0.0075 * xr
        hh = 0.022 * yr
        labels.append([cid, cx, cy, cx, cy, hw, hh])

    for _ in range(120):
        moved = False
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                a, b = labels[i], labels[j]
                dx, dy = abs(a[3] - b[3]), abs(a[4] - b[4])
                if dx < a[5] + b[5] and dy < a[6] + b[6]:
                    push = (a[6] + b[6] - dy) / 2 + 0.01 * yr
                    if a[4] <= b[4]:
                        a[4] -= push; b[4] += push
                    else:
                        a[4] += push; b[4] -= push
                    moved = True
        if not moved:
            break

    for cid, ax_, ay, lx, ly, hw, hh in labels:
        if abs(ly - ay) > 0.03 * yr:
            ax.plot([ax_, lx], [ay, ly], color=MUTED, lw=0.5, alpha=0.6, zorder=2)
        ax.annotate(
            names.get(cid, str(cid)), (lx, ly),
            fontsize=8, color=INK, ha="center", va="center", fontweight="bold", zorder=6,
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=_cluster_color(cid), lw=1.1, alpha=0.95),
        )

    for (lt, cid), text in CALLOUTS.items():
        if lt != listing_type or cid not in cluster_ids:
            continue
        pts = clustered[clustered["cluster"] == cid]
        cx, cy = pts["umap_x"].median(), pts["umap_y"].median()
        ax.annotate(
            text,
            xy=(cx, cy),
            xytext=(0.02, 0.02 + 0.06 * (cid % 3)),
            textcoords="axes fraction",
            fontsize=8.5,
            color=INK_SECONDARY,
            wrap=True,
            arrowprops=dict(arrowstyle="->", color=MUTED, lw=1),
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GRID, lw=1),
        )

    n_clusters = len(cluster_ids)
    n_noise = int((df["cluster"] == -1).sum())
    ax.set_title(
        f"Congressional {listing_type} job clusters — {len(df):,} unique listings, "
        f"{n_clusters} clusters ({n_noise/len(df):.0%} unclustered)",
        fontsize=14, color=INK, fontweight="bold", loc="left", pad=14,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(
        0.5, -0.02,
        "UMAP projection of Ollama embeddings; axes are not meaningful.  "
        "Source: House job bulletins 2013–2026 (json_v3).",
        transform=ax.transAxes, ha="center", va="top", fontsize=8, color=MUTED,
    )
    fig.tight_layout()
    for ext in ("png", "svg"):
        out = OUT_DIR / f"cluster_map_{listing_type}.{ext}"
        fig.savefig(out, dpi=300 if ext == "png" else None, facecolor=SURFACE, bbox_inches="tight")
        print(f"Wrote {out}")
    plt.close(fig)


# --------------------------------------------------------------------------
# trends subcommand
# --------------------------------------------------------------------------
def plot_trends(df: pd.DataFrame, names: dict[int, str], listing_type: str, min_n: int = 0) -> None:
    clustered = df[(df["cluster"] != -1) & df["year"].notna()].copy()
    clustered["year"] = clustered["year"].astype(int)
    years = list(range(int(clustered["year"].min()), int(clustered["year"].max()) + 1))
    max_year = max(years)

    # share of each year's clustered postings held by each cluster
    per_year_total = clustered.groupby("year").size()
    counts = clustered.groupby(["cluster", "year"]).size().unstack(fill_value=0).reindex(columns=years, fill_value=0)
    share = counts.div(per_year_total.reindex(years).values, axis=1) * 100

    sizes = clustered.groupby("cluster").size()
    keep = [c for c in share.index if sizes.get(c, 0) >= min_n]
    # sort by trend slope (growers first)
    def slope(c):
        y = share.loc[c].values.astype(float)
        return np.polyfit(range(len(y)), y, 1)[0]
    keep = sorted(keep, key=slope, reverse=True)

    n = len(keep)
    ncols = 3 if n <= 24 else 4
    nrows = (n + ncols - 1) // ncols
    # Free y-axis per panel: cluster shares span 60% (press) to <5%, so a shared
    # scale flattens most panels. Each panel shows its own trajectory; the peak
    # value is labeled so magnitude stays legible.
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.4, nrows * 2.0 + 0.5), sharex=True)
    fig.patch.set_facecolor(SURFACE)
    axes = np.array(axes).reshape(-1)

    for i, cid in enumerate(keep):
        ax = axes[i]
        ax.set_facecolor(SURFACE)
        y = share.loc[cid].values.astype(float)
        panel_max = max(float(y.max()), 1.0)
        ax.plot(years[:-1], y[:-1], color=_cluster_color(cid), lw=2, zorder=3)
        ax.plot(years[-2:], y[-2:], color=_cluster_color(cid), lw=2, ls=":", zorder=3)  # partial final year
        ax.plot([max_year], [y[-1]], marker="o", mfc="white", mec=_cluster_color(cid), mew=1.5, ms=5, zorder=4)
        ax.set_ylim(0, panel_max * 1.25)
        ax.text(0.97, 0.92, f"peak {panel_max:.0f}%", transform=ax.transAxes, ha="right", va="top",
                fontsize=6.5, color=MUTED)
        ax.set_title(f"{names.get(cid, cid)}  (n={sizes.get(cid,0)})", fontsize=8, color=INK, loc="left")
        ax.tick_params(labelsize=7, colors=MUTED)
        ax.set_xticks([years[0], years[len(years)//2], max_year])
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color(GRID)
        ax.grid(axis="y", color=GRID, lw=0.5)

    for j in range(n, len(axes)):
        axes[j].set_visible(False)

    n_noise_pct = (df["cluster"] == -1).mean()
    cut = f"  Clusters with n≥{min_n} shown." if min_n else ""
    fig.suptitle(
        f"Congressional {listing_type} clusters — share of each year's clustered postings",
        fontsize=13, color=INK, fontweight="bold", x=0.01, ha="left", y=0.995,
    )
    fig.text(
        0.01, 0.965,
        f"Sorted by trend (growing first). Each panel has its own y-scale (peak labeled); dotted segment + hollow "
        f"marker = {max_year} (partial year). {n_noise_pct:.0%} of {listing_type} jobs are unclustered and "
        f"excluded.{cut}",
        fontsize=8, color=MUTED, ha="left",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.945])
    out = OUT_DIR / f"cluster_trends_{listing_type}.png"
    fig.savefig(out, dpi=200, facecolor=SURFACE, bbox_inches="tight")
    print(f"Wrote {out}")
    plt.close(fig)


# --------------------------------------------------------------------------
# explorer subcommand
# --------------------------------------------------------------------------
def _build_payload(df: pd.DataFrame, terms: dict[int, list[str]], names: dict[int, str]) -> dict:
    cats = CATEGORY_ORDER
    cat_idx = {c: i for i, c in enumerate(cats)}
    points = []
    for r in df.itertuples(index=False):
        points.append([
            round(float(r.umap_x), 3), round(float(r.umap_y), 3),
            int(r.cluster), cat_idx.get(r.job_category, cat_idx["unknown"]),
            str(r.position_title or ""), str(r.office or ""), str(r.date or ""),
        ])
    clusters = {}
    for cid in sorted(c for c in df["cluster"].unique() if c != -1):
        clusters[str(cid)] = {
            "name": names.get(cid, str(cid)),
            "terms": terms.get(cid, [])[:5],
            "size": int((df["cluster"] == cid).sum()),
            "color": _cluster_color(cid),
        }
    return {"clusters": clusters, "categories": cats,
            "category_colors": [CATEGORY_COLORS[c] for c in cats], "points": points}


def build_explorer(payloads: dict[str, dict]) -> None:
    html = (
        _EXPLORER_HTML
        .replace("__DATA_JSON__", json.dumps(payloads, separators=(",", ":")))
        .replace("__NOISE_COLOR__", NOISE_COLOR)
        .replace("__SURFACE__", SURFACE)
    )
    out = OUT_DIR / "cluster_explorer.html"
    out.write_text(html, encoding="utf-8")
    size_mb = out.stat().st_size / 1e6
    print(f"Wrote {out}  ({size_mb:.1f} MB)")


_EXPLORER_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Congressional Job Clusters</title>
<style>
  :root {
    --surface: __SURFACE__; --ink: #0b0b0b; --ink2: #52514e; --muted: #898781;
    --grid: #e1e0d9; --border: rgba(11,11,11,0.10); --noise: __NOISE_COLOR__;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background: #f9f9f7; color: var(--ink); }
  header { padding: 14px 18px 10px; }
  h1 { font-size: 18px; margin: 0 0 2px; }
  .sub { font-size: 12px; color: var(--muted); }
  .bar { display: flex; flex-wrap: wrap; gap: 14px; align-items: center;
    padding: 8px 18px; border-bottom: 1px solid var(--border); }
  .bar .group { display: flex; gap: 6px; align-items: center; font-size: 13px; }
  button, input { font: inherit; }
  .tab, .toggle { border: 1px solid var(--border); background: #fff; color: var(--ink2);
    padding: 4px 10px; border-radius: 6px; cursor: pointer; }
  .tab.active, .toggle.active { background: var(--ink); color: #fff; border-color: var(--ink); }
  input[type=search] { border: 1px solid var(--border); border-radius: 6px; padding: 4px 8px; width: 200px; }
  .main { display: flex; height: calc(100vh - 96px); }
  .canvas-wrap { position: relative; flex: 1; min-width: 0; }
  canvas { display: block; width: 100%; height: 100%; background: var(--surface); }
  #tooltip { position: absolute; pointer-events: none; background: #fff; border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 8px; font-size: 12px; max-width: 260px; box-shadow: 0 2px 8px rgba(0,0,0,.12);
    display: none; z-index: 5; }
  #tooltip .t { font-weight: 600; }
  #tooltip .o { color: var(--ink2); }
  #tooltip .c { color: var(--muted); margin-top: 3px; }
  aside { width: 320px; border-left: 1px solid var(--border); overflow-y: auto; padding: 12px 14px;
    background: #fff; }
  aside h2 { font-size: 15px; margin: 0 0 2px; }
  aside .meta { font-size: 12px; color: var(--muted); margin-bottom: 8px; }
  .terms { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
  .term { background: #f0efec; border-radius: 4px; padding: 2px 6px; font-size: 11px; color: var(--ink2); }
  .joblist { font-size: 12px; }
  .joblist .job { padding: 4px 0; border-bottom: 1px solid var(--grid); }
  .joblist .job .jt { font-weight: 600; }
  .joblist .job .jo { color: var(--ink2); }
  .joblist .job .jd { color: var(--muted); }
  .legend { font-size: 12px; }
  .legend .row { display: flex; align-items: center; gap: 6px; padding: 2px 0; cursor: pointer; }
  .legend .row:hover { background: #f5f5f2; }
  .legend .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .legend .nm { flex: 1; }
  .legend .sz { color: var(--muted); font-variant-numeric: tabular-nums; }
  .hint { font-size: 11px; color: var(--muted); margin-top: 6px; }
</style>
</head>
<body>
<header>
  <h1>Congressional Job Clusters</h1>
  <div class="sub">UMAP + HDBSCAN over House job bulletins, 2013–2026 (json_v3). Hover a point; click to inspect its cluster.</div>
</header>
<div class="bar">
  <div class="group"><span>View:</span>
    <button class="tab active" data-view="staff">Staff</button>
    <button class="tab" data-view="internship">Internships</button>
  </div>
  <div class="group"><span>Color:</span>
    <button class="toggle active" data-color="cluster">Cluster</button>
    <button class="toggle" data-color="category">Job category</button>
  </div>
  <div class="group"><input type="search" id="search" placeholder="search title / office…"></div>
  <div class="group"><button class="toggle" id="clear">Clear selection</button></div>
</div>
<div class="main">
  <div class="canvas-wrap">
    <canvas id="cv"></canvas>
    <div id="tooltip"></div>
  </div>
  <aside id="panel"></aside>
</div>
<script>
const DATA = __DATA_JSON__;
const NOISE = "__NOISE_COLOR__";
let view = "staff", colorMode = "cluster", selected = null, query = "";

const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
const tip = document.getElementById("tooltip"), panel = document.getElementById("panel");
let tf = null; // {ox, oy, s} data->pixel

function pts() { return DATA[view].points; }
function clusters() { return DATA[view].clusters; }

function computeTransform() {
  const p = pts(); let minx=1e9,miny=1e9,maxx=-1e9,maxy=-1e9;
  for (const q of p){ if(q[0]<minx)minx=q[0]; if(q[0]>maxx)maxx=q[0]; if(q[1]<miny)miny=q[1]; if(q[1]>maxy)maxy=q[1]; }
  const w = cv.width, h = cv.height, pad = 30*dpr;
  const s = Math.min((w-2*pad)/(maxx-minx||1),(h-2*pad)/(maxy-miny||1));
  tf = { ox: pad + (w-2*pad - s*(maxx-minx))/2 - s*minx,
         oy: pad + (h-2*pad - s*(maxy-miny))/2 - s*miny, s, flip:h };
}
function px(q){ return [tf.ox + tf.s*q[0], tf.flip - (tf.oy + tf.s*q[1])]; }

let dpr = window.devicePixelRatio || 1;
function resize(){ dpr = window.devicePixelRatio||1;
  cv.width = cv.clientWidth*dpr; cv.height = cv.clientHeight*dpr; computeTransform(); draw(); }

function colorFor(q){
  if (colorMode === "category") return DATA[view].category_colors[q[3]];
  const cl = clusters()[q[2]]; return cl ? cl.color : NOISE;
}
function matches(q){ if(!query) return true;
  return (q[4]+" "+q[5]).toLowerCase().includes(query); }

function draw(){
  ctx.clearRect(0,0,cv.width,cv.height);
  ctx.fillStyle = getComputedStyle(document.body).getPropertyValue("--surface");
  const p = pts(), r = 2.2*dpr;
  // noise first
  for (const q of p){ if(q[2]!==-1) continue; drawPt(q,r,true); }
  for (const q of p){ if(q[2]===-1) continue; drawPt(q,r,false); }
}
function drawPt(q,r,isNoise){
  const dim = (selected!==null && q[2]!==selected) || !matches(q);
  const [x,y] = px(q);
  ctx.globalAlpha = isNoise ? (dim?0.06:0.28) : (dim?0.12:0.9);
  ctx.fillStyle = isNoise ? NOISE : colorFor(q);
  ctx.beginPath(); ctx.arc(x,y,r,0,6.2832); ctx.fill();
}
ctx.globalAlpha = 1;

function nearest(mx,my){
  const p = pts(); let best=null, bd=8*dpr*8*dpr;
  for (const q of p){ if(!matches(q)) continue; const [x,y]=px(q);
    const d=(x-mx)*(x-mx)+(y-my)*(y-my); if(d<bd){bd=d; best=q;} }
  return best;
}
cv.addEventListener("mousemove", e=>{
  const rect=cv.getBoundingClientRect();
  const mx=(e.clientX-rect.left)*dpr, my=(e.clientY-rect.top)*dpr;
  const q=nearest(mx,my);
  if(!q){ tip.style.display="none"; return; }
  const cl = q[2]===-1?"Unclustered":clusters()[q[2]].name;
  tip.innerHTML = `<div class="t">${esc(q[4])}</div><div class="o">${esc(q[5])}</div><div class="c">${q[6]} · ${esc(cl)}</div>`;
  tip.style.display="block"; tip.style.left=(e.clientX-rect.left+12)+"px"; tip.style.top=(e.clientY-rect.top+12)+"px";
});
cv.addEventListener("mouseleave", ()=> tip.style.display="none");
cv.addEventListener("click", e=>{
  const rect=cv.getBoundingClientRect();
  const q=nearest((e.clientX-rect.left)*dpr,(e.clientY-rect.top)*dpr);
  if(q && q[2]!==-1){ selected=q[2]; showCluster(q[2], q); } else { selected=null; showLegend(); }
  draw();
});

function esc(s){ return String(s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

function showCluster(cid, focus){
  const cl = clusters()[cid];
  const jobs = pts().filter(q=>q[2]===cid);
  let html = `<h2>${esc(cl.name)}</h2><div class="meta">${cl.size} listings · cluster ${cid}</div>`;
  html += `<div class="terms">`+cl.terms.map(t=>`<span class="term">${esc(t)}</span>`).join("")+`</div>`;
  html += `<div class="joblist">`+jobs.slice(0,400).map(q=>{
    const hl = focus && q===focus ? ' style="background:#fff6d6"' : '';
    return `<div class="job"${hl}><span class="jt">${esc(q[4])}</span> · <span class="jo">${esc(q[5])}</span> <span class="jd">${q[6]}</span></div>`;
  }).join("")+`</div>`;
  if(jobs.length>400) html += `<div class="hint">Showing first 400 of ${jobs.length}.</div>`;
  panel.innerHTML = html;
}
function showLegend(){
  const cl = clusters();
  const ids = Object.keys(cl).sort((a,b)=>cl[b].size-cl[a].size);
  let html = `<h2>Clusters</h2><div class="meta">${ids.length} clusters · click to inspect</div><div class="legend">`;
  for(const id of ids){
    html += `<div class="row" data-cid="${id}"><span class="dot" style="background:${cl[id].color}"></span>`
          + `<span class="nm">${esc(cl[id].name)}</span><span class="sz">${cl[id].size}</span></div>`;
  }
  html += `</div><div class="hint">Grey = unclustered (noise).</div>`;
  panel.innerHTML = html;
  panel.querySelectorAll(".row").forEach(r=> r.onclick=()=>{ selected=+r.dataset.cid; showCluster(selected); draw(); });
}

document.querySelectorAll(".tab").forEach(b=> b.onclick=()=>{
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
  b.classList.add("active"); view=b.dataset.view; selected=null;
  computeTransform(); draw(); showLegend();
});
document.querySelectorAll(".toggle[data-color]").forEach(b=> b.onclick=()=>{
  document.querySelectorAll(".toggle[data-color]").forEach(x=>x.classList.remove("active"));
  b.classList.add("active"); colorMode=b.dataset.color; draw();
});
document.getElementById("search").addEventListener("input", e=>{ query=e.target.value.toLowerCase().trim(); draw(); });
document.getElementById("clear").onclick=()=>{ selected=null; showLegend(); draw(); };

window.addEventListener("resize", resize);
resize(); showLegend();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# site subcommand — assemble a static GitHub Pages site
# --------------------------------------------------------------------------
_INDEX_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Congressional Job Clusters</title>
<style>
  :root {{ --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --border:rgba(11,11,11,.10); }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; color:var(--ink);
    background:#f9f9f7; line-height:1.5; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:32px 20px 64px; }}
  h1 {{ font-size:26px; margin:0 0 6px; }}
  .lede {{ color:var(--ink2); font-size:15px; margin:0 0 8px; }}
  .meta {{ color:var(--muted); font-size:13px; margin:0 0 24px; }}
  .cta {{ display:inline-block; background:var(--ink); color:#fff; text-decoration:none;
    padding:10px 18px; border-radius:8px; font-weight:600; font-size:15px; }}
  .cta:hover {{ opacity:.9; }}
  h2 {{ font-size:19px; margin:40px 0 4px; border-top:1px solid var(--border); padding-top:24px; }}
  .cap {{ color:var(--muted); font-size:13px; margin:0 0 12px; }}
  figure {{ margin:0 0 28px; }}
  img {{ width:100%; height:auto; border:1px solid var(--border); border-radius:8px; background:#fff; }}
  figcaption {{ color:var(--ink2); font-size:13px; margin-top:6px; }}
  footer {{ color:var(--muted); font-size:12px; margin-top:40px; border-top:1px solid var(--border); padding-top:16px; }}
  a {{ color:#2a78d6; }}
</style></head>
<body><div class="wrap">
  <h1>Congressional Job Clusters</h1>
  <p class="lede">Semantic clusters of U.S. House job and internship listings, 2013–2026.</p>
  <p class="meta">{n_jobs:,} classified listings from ~1,250 weekly bulletins, embedded and clustered with
    UMAP + HDBSCAN. Staff and internships are clustered separately.</p>
  <p><a class="cta" href="cluster_explorer.html">Open the interactive explorer →</a></p>

  <h2>Staff roles</h2>
  <p class="cap">{n_staff:,} unique staff listings, {c_staff} clusters.</p>
  <figure><img src="cluster_map_staff.png" alt="Annotated map of staff job clusters">
    <figcaption>Annotated cluster map — role and policy-area groups.</figcaption></figure>
  <figure><img src="cluster_trends_staff.png" alt="Staff cluster trends over time">
    <figcaption>Each cluster's share of postings per year (own scale per panel).</figcaption></figure>

  <h2>Internships</h2>
  <p class="cap">{n_intern:,} unique internship listings, {c_intern} clusters.</p>
  <figure><img src="cluster_map_internship.png" alt="Annotated map of internship clusters">
    <figcaption>Annotated cluster map — internship themes.</figcaption></figure>
  <figure><img src="cluster_trends_internship.png" alt="Internship cluster trends over time">
    <figcaption>Larger internship clusters' share of postings per year.</figcaption></figure>

  <footer>Built from <a href="https://github.com/dwillis/house-jobs">dwillis/house-jobs</a>.
    UMAP axes are not meaningful. Cluster names are hand-curated and may shift when the corpus is re-clustered.</footer>
</div></body></html>
"""


def build_site(data: dict, site_dir: Path) -> None:
    for lt in LISTING_TYPES:
        plot_map(data[lt][0], data[lt][2], lt)
    plot_trends(*[data["staff"][i] for i in (0, 2)], "staff", min_n=0)
    plot_trends(*[data["internship"][i] for i in (0, 2)], "internship", min_n=30)
    payloads = {lt: _build_payload(data[lt][0], data[lt][1], data[lt][2]) for lt in LISTING_TYPES}
    build_explorer(payloads)

    site_dir.mkdir(parents=True, exist_ok=True)
    assets = ["cluster_explorer.html", "cluster_map_staff.png", "cluster_map_internship.png",
              "cluster_trends_staff.png", "cluster_trends_internship.png"]
    for name in assets:
        shutil.copy(OUT_DIR / name, site_dir / name)

    staff_df, intern_df = data["staff"][0], data["internship"][0]
    index = _INDEX_HTML.format(
        n_jobs=25655,
        n_staff=len(staff_df), c_staff=len([c for c in staff_df["cluster"].unique() if c != -1]),
        n_intern=len(intern_df), c_intern=len([c for c in intern_df["cluster"].unique() if c != -1]),
    )
    (site_dir / "index.html").write_text(index, encoding="utf-8")
    print(f"Wrote static site to {site_dir}/ ({len(assets)+1} files)")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["explorer", "trends", "map", "all", "site"])
    p.add_argument("--json-dir", default="json_v3")
    p.add_argument("--names", default=str(OUT_DIR / "cluster_names.json"))
    p.add_argument("--site-dir", default="_site", help="output directory for the `site` command")
    args = p.parse_args()

    names_path = Path(args.names)
    print("Loading json_v3 metadata …")
    json_meta = load_json_meta(args.json_dir)

    data = {}
    for lt in LISTING_TYPES:
        df, terms, names = assemble(lt, json_meta, names_path)
        data[lt] = (df, terms, names)
        print(f"  {lt}: {len(df):,} points, {len(terms)} clusters")

    if args.command == "site":
        build_site(data, Path(args.site_dir))
        return
    if args.command in ("map", "all"):
        for lt in LISTING_TYPES:
            plot_map(data[lt][0], data[lt][2], lt)
    if args.command in ("trends", "all"):
        plot_trends(*[data["staff"][i] for i in (0, 2)], "staff", min_n=0)
        plot_trends(*[data["internship"][i] for i in (0, 2)], "internship", min_n=30)
    if args.command in ("explorer", "all"):
        payloads = {lt: _build_payload(data[lt][0], data[lt][1], data[lt][2]) for lt in LISTING_TYPES}
        build_explorer(payloads)


if __name__ == "__main__":
    main()
