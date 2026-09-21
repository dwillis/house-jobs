# house-jobs: repair the pipeline, rebuild the corpus, classify everything

## Context

The repo archives U.S. House job/internship bulletins (PDF → text → LLM-parsed JSON)
and layers NLP analysis on top. It works, but three things have drifted apart:
the documentation describes a system that no longer exists, the parsed corpus has
split into two incomplete and inconsistent halves, and the documented `job_category`
enrichment has never been applied to a single listing.

The plan fixes the parser, re-parses all 1,244 bulletins with one model to produce a
single consistent corpus, classifies every listing, and brings the docs back in line
with reality. Everything runs through Ollama Cloud, which the code already targets.

## Current state (measured)

| | count |
|---|---|
| PDFs in `input/` / text in `output/` | 1,244 |
| `json/` (primary corpus) | 605 files / 10,499 jobs |
| `json_qwen/` (alt corpus) | 518 files / 10,743 jobs |
| Overlap between the two | **82** |
| Parsed by *either* | 1,041 |
| **Unparsed** | **203** (193 internship, 10 member) |
| Listings with `job_category` | **0 of 21,242** |

**Findings driving this plan**

1. **The corpus is split, not layered.** Neither directory is authoritative. Quality
   differs materially: null `location` 24.9% (json) vs 10.1% (qwen); null `salary_info`
   69.8% vs 43.5%. 28 `json_qwen/` files parsed to an empty array. 25 are untracked.

2. **203 bulletins unparsed**, including every bulletin from 2026-05-25 to 2026-07-27.

3. **Silent data-corruption bug**, [`parser.py:165`](parser.py:165). When a model returns
   a bare job object instead of an array, the dict-unwrap loop returns the first
   list-valued field — writing the `responsibilities` array as if it were the job list.
   Confirmed live against `qwen3.5:35b`.

4. **`is_bulletin()` is case-sensitive** ([`parser.py:177`](parser.py:177)). It tests
   `"Intern" in filename`, silently skipping 5 files named `..._internships_...`.

5. **The default model is ~7x slower than an equivalent one.** Benchmarked on a real
   chunk, with identical field-level output:

   | model | s/chunk (parse) | s/job (classify) |
   |---|---|---|
   | `qwen3.5:397b-cloud` (current default) | 67 | — |
   | **`deepseek-v4-flash:cloud`** | **10** | **1.6** |
   | `qwen3.5:35b` (local) | 164 | — |
   | `qwen3:4b` (local) | — | 14 |

   `gemini-3-flash-preview:cloud` is **retired** and errors on every call. Local models
   are not competitive: the small ones are reasoning models that burn tokens thinking,
   and the M3 Max advantage doesn't close a 16x gap.

6. **Sleeps and subprocesses dominate runtime.** `parser.py` defaults to 8s between
   chunks. `job_classifier.py` shells out to `uv run llm` *per job* — full process
   startup each time — plus a 2s sleep per job and 5s per file, and rewrites the whole
   JSON file after every single job.

7. **Docs describe a deleted system.** `db_loader.py` and `init_database.py` were removed
   in commit `0f671be`, but CLAUDE.md and `docs/research.md` still document
   `congress_jobs.db`, its schema, "two web interfaces", legislator enrichment, and
   `db_loader.py --load-dir`. Both also name Gemini; the code has used Ollama since `0bcee51`.

8. **`pdftotext` flags disagree.** Docs say `-layout`; the GitHub Action
   ([get_text.yml](.github/workflows/get_text.yml)) omits it.

## Work

### 1. Fix and speed up `parser.py`

- **Fix the dict-unwrap corruption.** Replace the "return the first list value" loop with:
  if the dict looks like a job (has `id`/`position_title`), return `[parsed]`; only treat
  a list value as the job array when it holds dicts. This is the highest-value fix — it
  silently produces garbage rather than failing.
- **Fix `is_bulletin()`** to match case-insensitively so the 5 `internships` files parse.
- **Default `MODEL_ID` to `deepseek-v4-flash:cloud`.**
- **Default `--sleep-chunk` and `--sleep-file` to 0.** Cloud models don't need them; keep
  the flags for anyone who hits limits.
- **Add `--concurrency` (default 6)** — a `ThreadPoolExecutor` over the chunks of a file,
  using `executor.map` so chunk order is preserved. Keep per-chunk failures non-fatal, as
  `process_chunk` already does.
- **Add retry** on empty/failed chunk results (one retry, then record the failure) — with
  25k chunks, transient cloud errors will otherwise silently drop listings.
- **Record provenance**: add a `source_model` field per listing so future A/B runs are
  traceable. Reuse the existing `--out`/`--files`/`--no-skip`/`--limit` flags as-is.

### 2. Re-parse all 1,244 bulletins into one corpus

- Parse to a **fresh `json_v2/` directory**, not in place — `json/` and `json_qwen/` stay
  intact on disk until the new corpus is validated.
- **Workload: 25,198 chunks ≈ 12h at 6-way concurrency** (70h sequential). Run it in
  batches (`--limit`) and resume via the existing skip-if-exists logic.
- Validate with `uv run python validate.py json_v2/`, then compare against the old corpora
  with the existing [`compare_parses.py`](compare_parses.py): `uv run python compare_parses.py json/ json_v2/`.
- Check for empty parses (the failure mode that produced 28 empty `json_qwen/` files) and
  re-run those files before promoting.
- **Promote only after validation**: replace `json/` with `json_v2/` and delete
  `json_qwen/` in one commit, so the swap is a single reviewable change.

### 3. Rewrite `job_classifier.py`

- **Drop the `subprocess`/`uv run llm` call** ([`job_classifier.py:68`](job_classifier.py:68))
  and use the `llm` Python API the way [`parser.py`](parser.py) does.
- Use `deepseek-v4-flash:cloud`; add `--model` and `--concurrency` flags to match the parser.
- **Save once per file**, not once per job — the current per-job rewrite is O(n²) I/O.
- Keep the existing resume behaviour (skip jobs that already have `job_category`) and the
  fuzzy category extraction; both are sound.
- **Add a small labelled validation set.** Benchmarking surfaced a genuine ambiguity —
  "Staff Assistant" classified as `constituent_services` by one model and `administrative`
  by another. Hand-label ~50 listings and report accuracy before committing 21k labels.
- **Runtime: ~1.2h at 8-way concurrency** for the full corpus.

### 4. Docs and CI

- **`CLAUDE.md`**: delete the database sections (data-flow diagram, `db_loader.py` /
  `init_database.py` steps, date-extraction notes, congress-legislators dependency, the
  "~37% enrichment" claim). Correct the model references from Gemini to the Ollama models
  actually used. Update the rate-limiting section to the new defaults.
- **`docs/research.md`**: rewrite around the JSON corpus and `skills/` analysis. Remove the
  schema, "two web interfaces", and `db_loader.py` command sections.
- **`README.md`**: correct model names and the file-count figure; note `job_category` is now
  populated rather than optional.
- **`pdftotext -layout`**: run a spike first — extract 3–5 bulletins both ways and parse
  each with the fixed parser. If `-layout` doesn't measurably improve field extraction,
  drop `-layout` from the docs to match the Action. Only regenerate `output/` if the spike
  shows a real gain; that would be a 1,244-file diff and should be its own commit.

## Sequencing

Step 1 must land before step 2 (the parser bug would otherwise corrupt the new corpus).
Step 3 depends on step 2 only for the final full-corpus run — the rewrite and validation
set can be built and tested against `json/` in parallel. Step 4 is independent.

## Verification

```bash
# 1. Parser fixes — bare-object handling must yield one job, not a responsibilities array
uv run python parser.py --model qwen3.5:35b --files HVAPS_Template_Internships_2026_07_27_26.txt \
  --out /tmp/parse_check --no-skip --sleep-chunk 0 --sleep-file 0
uv run python -c "import json;d=json.load(open('/tmp/parse_check/HVAPS_Template_Internships_2026_07_27_26.json'));print(len(d), type(d[0]), d[0].get('id'))"
# expect: dicts with MEM-XXX-26 ids, not bare strings

# 2. is_bulletin case-fix picks up the 5 lowercase files
uv run python -c "from parser import is_bulletin; print(is_bulletin('HVAPS_Template_internships_2024_11_18.txt'))"  # expect True

# 3. Small end-to-end batch before the long run
uv run python parser.py --out json_v2 --limit 5
uv run python validate.py json_v2/
uv run python compare_parses.py json/ json_v2/

# 4. Corpus completeness after the full run (expect 1,244 files, 0 empty)
uv run python -c "
import json,glob
f=glob.glob('json_v2/*.json'); e=[x for x in f if json.load(open(x))==[]]
print('files',len(f),'empty',len(e),'jobs',sum(len(json.load(open(x))) for x in f))"

# 5. Classifier accuracy against the hand-labelled set, then full-corpus coverage
uv run python job_classifier.py --limit 50
uv run python -c "
import json,glob
j=[x for f in glob.glob('json/*.json') for x in json.load(open(f))]
print('classified', sum(1 for x in j if x.get('job_category')), 'of', len(j))"

# 6. Analysis layer still runs on the rebuilt corpus
uv run python skills/skill_extractor.py
uv run python analyze_classifications.py
```

## Note on cost

The full re-parse is ~25,200 cloud calls and the classification ~21,200 more. Worth
confirming the Ollama Cloud plan covers that volume before kicking off the long run;
`--limit` makes it easy to run in batches and stop.
