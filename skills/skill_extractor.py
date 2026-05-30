#!/usr/bin/env python3
"""
skill_extractor.py — Extract and analyze skill demand from Congressional job listings.

Reads JSON files from json/ directory, extracts structured skill signals from
description/responsibilities/qualifications text, and outputs:

  skills_raw.csv      one row per skill×job mention
  skill_trends.csv    annual job-count pivot (skill × year)
  skill_trends.png    trend chart for top skills over time
  skill_categories.png  bar chart of mentions by skill category

Usage:
    python skill_extractor.py
    python skill_extractor.py --dir json_qwen   # alternate source dir
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# Repo root is the parent of this file's directory (skills/)
REPO_ROOT = Path(__file__).parent.parent
OUT_DIR   = Path(__file__).parent

sys.path.insert(0, str(REPO_ROOT))
from config import JSON_DIR

JSON_DIR = str(REPO_ROOT / JSON_DIR)

# ---------------------------------------------------------------------------
# Skill definitions
# Each entry: (canonical_name, category, [regex_patterns])
# Patterns are matched case-insensitively against concatenated text fields.
# ---------------------------------------------------------------------------

SKILLS = [
    # --- Software & Tools ---
    ("Salesforce",              "software",    [r"\bsalesforce\b"]),
    ("VAN / NGP",               "software",    [r"\bvan\b", r"\bngp\b"]),
    ("Adobe InDesign",          "software",    [r"\bindesign\b"]),
    ("Adobe Photoshop",         "software",    [r"\bphotoshop\b"]),
    ("Adobe Premiere",          "software",    [r"\bpremiere\b"]),
    ("Adobe Illustrator",       "software",    [r"\billustrator\b"]),
    ("Canva",                   "software",    [r"\bcanva\b"]),
    ("Microsoft Excel",         "software",    [r"\bexcel\b"]),
    ("Microsoft Office Suite",  "software",    [r"\bmicrosoft\s+office\b", r"\bms\s+office\b", r"\boffice\s+suite\b"]),
    ("Quorum",                  "software",    [r"\bquorum\b"]),
    ("iConstituent",            "software",    [r"\biconstituent\b"]),
    ("Final Cut Pro",           "software",    [r"\bfinal\s+cut\b"]),
    ("MailChimp / Constant Contact", "software", [r"\bmailchimp\b", r"\bconstant\s+contact\b"]),
    ("Zoom / Webinar Platforms","software",    [r"\bzoom\b", r"\bwebinar\b"]),
    ("CMS / Website Management","software",    [r"\bcms\b", r"\bcontent\s+management\s+system\b", r"\bwordpress\b"]),
    ("Google Analytics",        "software",    [r"\bgoogle\s+analytics\b"]),
    ("Data Analysis Software",  "software",    [r"\bspss\b", r"\bstata\b", r"\br\s+programming\b", r"\bpython\b(?=.*data|.*analys)", r"\bsql\b"]),

    # --- Security Clearances ---
    ("TS/SCI Clearance",        "clearance",   [r"\bts[/\s]sci\b", r"\btop\s+secret[/\s]sci\b"]),
    ("Top Secret Clearance",    "clearance",   [r"\btop\s+secret\b"]),
    ("Security Clearance (any)","clearance",   [r"\bsecurity\s+clearance\b", r"\bactive\s+clearance\b"]),

    # --- Languages ---
    ("Spanish",                 "language",    [r"\bspanish\b"]),
    ("Mandarin / Chinese",      "language",    [r"\bmandarin\b", r"\bchinese\b"]),
    ("Vietnamese",              "language",    [r"\bvietnamese\b"]),
    ("Korean",                  "language",    [r"\bkorean\b"]),
    ("Tagalog / Filipino",      "language",    [r"\btagalog\b", r"\bfilipino\b"]),
    ("Arabic",                  "language",    [r"\barabic\b"]),
    ("Bilingual (any)",         "language",    [r"\bbilingual\b"]),
    ("Haitian Creole",          "language",    [r"\bhaitian\s+creole\b", r"\bcreole\b"]),
    ("Portuguese",              "language",    [r"\bportuguese\b"]),
    ("French",                  "language",    [r"\bfrench\b(?=.*(?:fluent|proficien|bilingual|speaker|language))"]),

    # --- Experience Types ---
    ("Capitol Hill Experience", "experience",  [r"\bcapitol\s+hill\b", r"\bhill\s+experience\b", r"\bcongressional\s+experience\b", r"\bhill\s+background\b", r"\bhill\s+staffer\b"]),
    ("Campaign Experience",     "experience",  [r"\bcampaign\s+experience\b", r"\bpolitical\s+campaign\b"]),
    ("Non-profit Experience",   "experience",  [r"\bnon.?profit\b"]),
    ("Government Affairs",      "experience",  [r"\bgovernment\s+affairs?\b", r"\bpublic\s+affairs?\b(?=.*experience|.*background)"]),

    # --- Writing & Communications ---
    ("Press Releases / Statements", "communications", [r"\bpress\s+releases?\b", r"\bwrit(?:e|ing)\s+statements?\b", r"\bdraft(?:ing)?\s+statements?\b"]),
    ("Speechwriting",           "communications",    [r"\bspeechwriting\b", r"\bspeech.{0,10}writ\b", r"\bwriting\s+speeches\b"]),
    ("Op-Ed Writing",           "communications",    [r"\bop.?ed\b", r"\bopinion\s+pieces?\b"]),
    ("Talking Points",          "communications",    [r"\btalking\s+points?\b"]),
    ("Social Media",            "communications",    [r"\bsocial\s+media\b"]),
    ("Twitter / X",             "communications",    [r"\btwitter\b", r"\bx\.com\b"]),
    ("Instagram",               "communications",    [r"\binstagram\b"]),
    ("TikTok",                  "communications",    [r"\btiktok\b"]),
    ("Video Production",        "communications",    [r"\bvideo\s+(?:production|editing|content)\b", r"\b(?:editing|producing)\s+videos?\b", r"\bvideograph\b"]),
    ("Graphic Design",          "communications",    [r"\bgraphic\s+design\b"]),
    ("Media Relations",         "communications",    [r"\bmedia\s+relations?\b", r"\bpress\s+relations?\b"]),
    ("Digital Strategy",        "communications",    [r"\bdigital\s+strateg\b", r"\bdigital\s+communications?\b", r"\bdigital\s+media\b"]),
    ("Podcast Production",      "communications",    [r"\bpodcast\b"]),
    ("Newsletter",              "communications",    [r"\bnewsletter\b"]),

    # --- Policy Areas ---
    ("Appropriations / Budget", "policy",      [r"\bappropriations\b", r"\bfederal\s+budget\b"]),
    ("Defense / National Security", "policy",  [r"\bnational\s+security\b", r"\bdefense\s+policy\b", r"\bdefense\s+issues?\b", r"\barmed\s+services\b"]),
    ("Healthcare Policy",       "policy",      [r"\bhealth(?:care)?\s+policy\b", r"\bhealth\s+issues?\b", r"\bmedicare\b", r"\bmedicaid\b", r"\baffordable\s+care\s+act\b"]),
    ("Immigration",             "policy",      [r"\bimmigration\b"]),
    ("Foreign Policy",          "policy",      [r"\bforeign\s+policy\b", r"\binternational\s+affairs?\b", r"\bforeign\s+affairs?\b"]),
    ("Veterans Affairs",        "policy",      [r"\bveterans?\b"]),
    ("Education Policy",        "policy",      [r"\beducation\s+policy\b", r"\bhigher\s+education\b"]),
    ("Environment / Climate",   "policy",      [r"\benvironmental\s+policy\b", r"\bclimate\s+(?:change|policy)\b", r"\benergy\s+policy\b", r"\bclean\s+energy\b"]),
    ("Finance / Tax Policy",    "policy",      [r"\btax\s+policy\b", r"\bfinancial\s+services\b", r"\bways\s+and\s+means\b"]),
    ("Agriculture",             "policy",      [r"\bagriculture\b"]),
    ("Transportation",          "policy",      [r"\btransportation\b"]),
    ("Judiciary / Legal",       "policy",      [r"\bjudiciary\b", r"\bcivil\s+rights\b", r"\bconstitutional\s+law\b"]),
    ("Small Business",          "policy",      [r"\bsmall\s+business\b"]),
    ("Housing",                 "policy",      [r"\bhousing\s+policy\b", r"\baffordable\s+housing\b"]),
    ("Technology / Innovation", "policy",      [r"\btechnology\s+policy\b", r"\btech\s+policy\b", r"\binnovation\s+policy\b", r"\bartificial\s+intelligence\b", r"\b\bAI\b(?=.*policy)"]),

    # --- Education / Credentials ---
    ("JD / Law Degree",         "credential",  [r"\bj\.?d\.?\b", r"\blaw\s+degree\b", r"\bjuris\s+doctor\b"]),
    ("Master's Degree",         "credential",  [r"\bmaster'?s?\s+degree\b", r"\bm\.?[as]\.?\b\s+(?:in|degree|required|preferred)"]),
    ("Bar Admission",           "credential",  [r"\badmitted\s+to\s+(?:the\s+)?bar\b", r"\bbar\s+(?:member|admission|licensed)\b"]),

    # --- Constituent Services ---
    ("Casework",                "constituent", [r"\bcasework\b"]),
    ("Community Outreach",      "constituent", [r"\bcommunity\s+outreach\b", r"\boutreach\s+(?:to\s+)?(?:the\s+)?community\b"]),
    ("Constituent Services",    "constituent", [r"\bconstituent\s+services?\b"]),
    ("Town Halls / Events",     "constituent", [r"\btown\s+halls?\b", r"\bcommunity\s+events?\b"]),

    # --- Legislative Process ---
    ("Legislative Research",    "legislative", [r"\blegislative\s+research\b", r"\bpolicy\s+research\b"]),
    ("Bill Drafting",           "legislative", [r"\bbill\s+drafting\b", r"\bdrafting\s+legislation\b", r"\blegal\s+drafting\b"]),
    ("Committee Work",          "legislative", [r"\bcommittee\s+(?:work|experience|staff|hearing)\b"]),
    ("Floor Procedure",         "legislative", [r"\bfloor\s+(?:procedure|management|action)\b", r"\bhouse\s+floor\b"]),
    ("Coalition Building",      "legislative", [r"\bcoalition.{0,10}build\b", r"\bcoalition\s+management\b"]),
    ("Regulatory / Federal Agency", "legislative", [r"\bfederal\s+regulat\b", r"\brulemaking\b", r"\badministrative\s+law\b"]),

    # --- Soft Skills (explicitly stated) ---
    ("Project Management",      "soft_skill",  [r"\bproject\s+management\b"]),
    ("Budget Management",       "soft_skill",  [r"\bbudget\s+management\b", r"\bmanaging\s+(?:a\s+)?budget\b", r"\boffice\s+budget\b"]),
    ("Supervisory / Management","soft_skill",  [r"\bsupervis(?:e|ing|ory)\b", r"\bmanaging\s+staff\b", r"\bstaff\s+management\b"]),
    ("Strong Writing Skills",   "soft_skill",  [r"\bstrong\s+writ(?:ten|ing)\b", r"\bexcellent\s+writ(?:ten|ing)\b"]),
    ("Attention to Detail",     "soft_skill",  [r"\battention\s+to\s+detail\b"]),
    ("Fast-Paced Environment",  "soft_skill",  [r"\bfast.?paced\b"]),
    ("Driver's License",        "soft_skill",  [r"\bdriver'?s?\s+license\b", r"\bvalid\s+(?:driver'?s?\s+)?license\b"]),
]

# Compile all patterns once at import time
COMPILED_SKILLS: list[tuple[str, str, list[re.Pattern]]] = [
    (name, cat, [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns])
    for name, cat, patterns in SKILLS
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_text(job: dict) -> str:
    """Concatenate all searchable text fields of a job record."""
    parts: list[str] = []
    for field in ("position_title", "description"):
        val = job.get(field)
        if val:
            parts.append(str(val))
    for field in ("responsibilities", "qualifications"):
        val = job.get(field)
        if isinstance(val, list):
            parts.extend(str(v) for v in val if v)
        elif isinstance(val, str) and val:
            parts.append(val)
    return "\n".join(parts)


_DATE_PATTERNS = [
    # HVAPS_Template_Members_2025_01_06... or 2025_01_06_2025
    (re.compile(r'(\d{4})_(\d{2})_(\d{2})'), lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
    # MM-DD-YY at start: 01-06-14_
    (re.compile(r'^(\d{1,2})-(\d{2})-(\d{2})_'),
        lambda m: "{}-{}-{}".format(
            f"20{m.group(3)}" if int(m.group(3)) < 50 else f"19{m.group(3)}",
            m.group(1).zfill(2), m.group(2)
        )),
    # M.DD.YYYY: 1.26.2015
    (re.compile(r'(\d{1,2})\.(\d{2})\.(\d{4})'),
        lambda m: f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2)}"),
]


def date_from_filename(filename: str) -> str | None:
    stem = Path(filename).stem
    for pattern, formatter in _DATE_PATTERNS:
        m = pattern.search(stem)
        if m:
            return formatter(m)
    return None


def safe_year(date_str: str | None) -> int | None:
    if not date_str or len(date_str) < 4:
        return None
    try:
        yr = int(date_str[:4])
        return yr if 2010 <= yr <= 2030 else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_directory(json_dir: str) -> list[dict]:
    json_path = Path(json_dir)
    files = sorted(json_path.glob("*.json"))
    print(f"  Processing {len(files)} files in {json_dir}/...")

    # Pass 1: collect all job records; keep only the earliest appearance per job_id.
    # Use "9999-99-99" as a sentinel so jobs with no date sort last (i.e. are
    # superseded by any real date).
    # Stored tuple: (sort_key, real_date, job_dict, source_filename)
    best: dict[str, tuple[str, str, dict, str]] = {}

    for filepath in files:
        fn_date = date_from_filename(filepath.name)

        try:
            with open(filepath, encoding="utf-8") as f:
                jobs = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"  SKIP {filepath.name}: {e}", file=sys.stderr)
            continue

        if not isinstance(jobs, list):
            continue

        for job in jobs:
            job_id = job.get("id", "")
            if not job_id:
                continue
            date = fn_date or job.get("posting_date") or ""
            sort_key = date if date else "9999-99-99"
            if job_id not in best or sort_key < best[job_id][0]:
                best[job_id] = (sort_key, date, job, filepath.name)

    print(f"  {len(best):,} unique job IDs (deduplicated to first appearance).")

    # Pass 2: extract skills only from the first-appearance record of each job.
    rows: list[dict] = []
    for job_id, (_, date, job, source_file) in best.items():
        office = job.get("office", "")
        title  = job.get("position_title", "")
        year   = safe_year(date)
        text   = extract_text(job)
        if not text.strip():
            continue

        for skill_name, category, compiled_patterns in COMPILED_SKILLS:
            for pattern in compiled_patterns:
                if pattern.search(text):
                    rows.append({
                        "job_id":         job_id,
                        "office":         office,
                        "position_title": title,
                        "date":           date,
                        "year":           year,
                        "skill":          skill_name,
                        "skill_category": category,
                        "source_file":    source_file,
                    })
                    break  # one match per skill is enough

    return rows


# ---------------------------------------------------------------------------
# Visualizations
# ---------------------------------------------------------------------------

CATEGORY_COLORS = {
    "software":       "#4e79a7",
    "clearance":      "#e15759",
    "language":       "#59a14f",
    "experience":     "#f28e2b",
    "communications": "#76b7b2",
    "policy":         "#edc948",
    "credential":     "#b07aa1",
    "constituent":    "#ff9da7",
    "legislative":    "#9c755f",
    "soft_skill":     "#bab0ac",
}


def plot_top_skill_trends(skill_year: pd.DataFrame, out_path: str, n: int = 15) -> None:
    top_skills = (
        skill_year.groupby("skill")["job_count"]
        .sum()
        .nlargest(n)
        .index.tolist()
    )
    plot_df = skill_year[skill_year["skill"].isin(top_skills)]
    pivot = plot_df.pivot(index="year", columns="skill", values="job_count").fillna(0)

    fig, ax = plt.subplots(figsize=(15, 7))
    for skill in top_skills:
        if skill in pivot.columns:
            ax.plot(pivot.index, pivot[skill], marker="o", markersize=3,
                    linewidth=1.8, label=skill)

    ax.set_xlabel("Year", fontsize=11)
    ax.set_ylabel("Distinct Jobs Mentioning Skill", fontsize=11)
    ax.set_title("Top 15 Skills in U.S. House Job Listings (2013–2026)", fontsize=13)
    ax.legend(fontsize=8, ncol=2, loc="upper left", framealpha=0.8)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Wrote {out_path}")


def plot_category_totals(df: pd.DataFrame, out_path: str) -> None:
    cat_counts = (
        df.drop_duplicates(subset=["job_id", "skill"])
        .groupby("skill_category")["job_id"]
        .count()
        .sort_values(ascending=True)
    )
    colors = [CATEGORY_COLORS.get(c, "#cccccc") for c in cat_counts.index]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(cat_counts.index, cat_counts.values, color=colors)
    ax.bar_label(bars, padding=3, fontsize=9)
    ax.set_xlabel("Skill Mentions (distinct per job)")
    ax.set_title("Skill Category Distribution — House Job Listings 2013–2026")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Wrote {out_path}")


def plot_emerging_skills(skill_year: pd.DataFrame, jobs_per_year: pd.Series,
                         out_path: str) -> None:
    """Bar chart of skills ranked by change in *prevalence* (% of jobs that mention
    the skill) between the early (2013-2018) and late (2019-2026) periods.
    Normalising by total jobs in each period removes the effect of the corpus
    simply getting larger over time."""
    total_early = jobs_per_year[jobs_per_year.index <= 2018].sum()
    total_late  = jobs_per_year[jobs_per_year.index >= 2019].sum()

    raw_early = skill_year[skill_year["year"] <= 2018].groupby("skill")["job_count"].sum()
    raw_late  = skill_year[skill_year["year"] >= 2019].groupby("skill")["job_count"].sum()

    combined = pd.DataFrame({"early": raw_early, "late": raw_late}).fillna(0)
    # Express as percentage of all jobs in each period
    combined["pct_early"] = combined["early"] / total_early * 100
    combined["pct_late"]  = combined["late"]  / total_late  * 100
    combined["pct_change"] = combined["pct_late"] - combined["pct_early"]

    top = combined.nlargest(12, "pct_change")

    fig, ax = plt.subplots(figsize=(12, 6))
    x = range(len(top))
    ax.bar([i - 0.2 for i in x], top["pct_early"], width=0.4, label=f"2013–2018 (n={total_early:,} jobs)",
           color="#aec7e8")
    ax.bar([i + 0.2 for i in x], top["pct_late"],  width=0.4, label=f"2019–2026 (n={total_late:,} jobs)",
           color="#1f77b4")
    ax.set_xticks(list(x))
    ax.set_xticklabels(top.index, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("% of Jobs Mentioning Skill")
    ax.set_title("Skills With Largest Increase in Prevalence: 2013–2018 vs 2019–2026\n"
                 "(normalised by total job listings in each period)")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Wrote {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(json_dir: str = JSON_DIR) -> None:
    print(f"Scanning {json_dir}/ for job files...")
    rows = process_directory(json_dir)
    print(f"Found {len(rows):,} skill mentions across all jobs.")

    if not rows:
        print("No data found. Check that JSON_DIR is correct.")
        return

    df = pd.DataFrame(rows)

    # --- Raw output ---
    raw_path = OUT_DIR / "skills_raw.csv"
    df.to_csv(raw_path, index=False)
    print(f"Wrote {raw_path}  ({len(df):,} rows)")

    # --- Annual trend pivot ---
    year_df = df[df["year"].notna()].copy()
    year_df["year"] = year_df["year"].astype(int)

    skill_year = (
        year_df.groupby(["year", "skill"])["job_id"]
        .nunique()
        .reset_index(name="job_count")
    )
    pivot = skill_year.pivot(index="year", columns="skill", values="job_count").fillna(0)
    trends_path = OUT_DIR / "skill_trends.csv"
    pivot.to_csv(trends_path)
    print(f"Wrote {trends_path}  ({pivot.shape[0]} years × {pivot.shape[1]} skills)")

    # Total distinct jobs per year (for prevalence normalisation)
    jobs_per_year = (
        year_df.drop_duplicates(subset=["year", "job_id"])
        .groupby("year")["job_id"]
        .nunique()
    )

    # --- Charts ---
    plot_top_skill_trends(skill_year, str(OUT_DIR / "skill_trends.png"))
    plot_category_totals(df, str(OUT_DIR / "skill_categories.png"))
    plot_emerging_skills(skill_year, jobs_per_year, str(OUT_DIR / "skill_emerging.png"))

    # --- Console summary ---
    print("\n=== Top 25 Most-Demanded Skills (all years) ===")
    totals = skill_year.groupby("skill")["job_count"].sum().sort_values(ascending=False)
    print(totals.head(25).to_string())

    print("\n=== Top 12 Skills by Increase in Prevalence (2019–2026 vs 2013–2018) ===")
    total_early = jobs_per_year[jobs_per_year.index <= 2018].sum()
    total_late  = jobs_per_year[jobs_per_year.index >= 2019].sum()
    raw_early = skill_year[skill_year["year"] <= 2018].groupby("skill")["job_count"].sum()
    raw_late  = skill_year[skill_year["year"] >= 2019].groupby("skill")["job_count"].sum()
    combined = pd.DataFrame({"jobs (2013-18)": raw_early, "jobs (2019-26)": raw_late}).fillna(0)
    combined["% (2013-18)"] = (combined["jobs (2013-18)"] / total_early * 100).round(1)
    combined["% (2019-26)"] = (combined["jobs (2019-26)"] / total_late  * 100).round(1)
    combined["pct_change"]  = (combined["% (2019-26)"] - combined["% (2013-18)"]).round(1)
    print(f"  (normalised: {total_early} jobs 2013-18, {total_late} jobs 2019-26)")
    print(combined.nlargest(12, "pct_change").to_string())

    print("\n=== Language Demand Over Time ===")
    lang_df = skill_year[skill_year["skill"].isin(
        [s for s, c, _ in SKILLS if c == "language"]
    )]
    lang_pivot = lang_df.pivot(index="year", columns="skill", values="job_count").fillna(0)
    print(lang_pivot.to_string())

    print("\n=== Policy Area Demand (total jobs, all years) ===")
    policy_skills = [s for s, c, _ in SKILLS if c == "policy"]
    policy_df = skill_year[skill_year["skill"].isin(policy_skills)]
    print(policy_df.groupby("skill")["job_count"].sum().sort_values(ascending=False).to_string())


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--dir":
        target = str(REPO_ROOT / sys.argv[2])
    else:
        target = JSON_DIR
    main(target)
