# Design: `cicaid context` — deterministic repo context for LLM coders

Status: design, no implementation. Supersedes nothing; it is the concrete
build-out of Stage 1/3 of
[issue-worm-pro `docs/design-rag-retrieval.md`](https://github.com/leonarduk/issue-worm-pro/blob/main/docs/design-rag-retrieval.md),
whose staging and non-goals still hold.

**Recommendation: build it here, in `cicaid`, as `cicaid context`.
Deterministic signals only in v1 — no vector DB, no embedding model, no
daemon. Build the eval harness before the ranker.**

## The premise, restated and corrected

The prompt for this work was: *a local coder model tops out at ~200K
context, which is too small for some repos, so we need RAG so the coder has
access to all the code.* Three parts of that need adjusting before any
design follows from it.

### 1. The 200K window is not 200K of usable budget

`laptop-egpu-llm`'s own `docs/model-picker.md` records what that window
costs on the 23.83 GB rig: `qwen3.8-216k` is 11.29 GB of weights plus
**~8 GB of KV cache reserved on every load**, because Ollama reserves for
the manifest's `num_ctx` whether or not the request uses it. That doc puts
the total at **~18–19 GB of the 23.83 GB**, gone before a single token is
generated and paid on short prompts too.

So the choice is not "200K, or RAG". It is "pay ~8 GB and accept degraded
long-context recall, or run a smaller window with better weights or a
better quant". Retrieval that lets a 30–60K window do the job of a 200K one
reclaims most of that ~8 GB — which on this hardware is a whole
quantisation tier. **That is a stronger argument for retrieval than 'the
repo doesn't fit', and it is the one to make.**

### 2. On these repos, it is a file-size problem, not a retrieval problem

Tracked source, current checkouts:

| Repo | Tracked files | Non-test source |
|---|---|---|
| `cicaid` | 66 | ~108K tok (incl. docs) |
| `cicaid-pro` | 131 | ~230K tok (incl. docs) |
| `issue-worm` | 57 | ~188K tok (incl. docs) |
| `issue-worm-pro` | 226 | ~375K tok (`*.py`, tests excluded) |

Only `issue-worm-pro` exceeds the window, and it does so lopsidedly:

```
ui_server.py   520,526 bytes  (11,154 lines)  ~130K tok
scheduler.py   240,849 bytes  ( 5,432 lines)  ~60K tok
```

**Two files are ~half the non-test source.** No retriever fixes that: a
30-60K window cannot hold `ui_server.py` at all, so every signal this
design produces is moot for the file most likely to need changing.

> **Correction (2026-09-22).** An earlier revision of this section claimed
> a Coder must emit the whole of `ui_server.py` back under a `MODE: FULL`
> contract, at ~130K output tokens. **That is wrong for the shipping pro
> path.** `issue-worm-pro`'s `agents/coder.py` already defaults
> `large_file_mode = MODE_EDIT` for files at or above
> `SIZE_THRESHOLD = 10_000` bytes, and `issue-worm`'s `workspace.py`
> already parses and applies those SEARCH/REPLACE blocks
> (`_parse_search_replace_blocks`, `_apply_search_replace`). At 520KB
> `ui_server.py` is far above that threshold, so `NativeCoder` asks for
> targeted edits, and output scales with the change rather than the file.
> The `MODE: FULL` claim holds only for the **free shell**, whose
> `coder.py` hardcodes "Always use MODE: FULL" regardless of size — a
> narrower defect, tracked as leonarduk/issue-worm#462.

That correction weakens the case for splitting these files but does not
remove it: the *input* side is untouched, since a Coder editing
`ui_server.py` is still sent its ~130K tokens of content whatever edit
format it replies in. Splitting remains worth doing, on input budget and
on ordinary maintainability grounds, but it is no longer the output-cost
emergency this section originally described. Treat it as Stage -1 — still
ahead of the ranker, no longer ahead of everything.

### 3. The Coder cannot use "all the code", by construction

`workspace.parse_coder_output` still raises on an undeclared path:

```python
if path not in declared:
    raise MalformedOutputError(
        f"coder output touches undeclared file {path!r} ..."
    )
```

Handing the Coder more files does not let it edit them; it spends input
budget on material the model must read and then not touch, while still
owing a full rewrite of the target. The prior design doc's warning stands:
read-only retrieved context in the Coder prompt could plausibly *lower*
pass rates.

There is a real need hiding in the request, though, and it is narrower than
"all the code": a Coder editing `orchestrator.py` needs to **see the
signature and contract of `workspace.parse_coder_output`** without
rewriting it. That is not chunks and not embeddings. It is an
AST-derived signature skeleton — Tier B in the packing model below — and
it is cheap enough to always send.

So the three consumers, in descending order of value:

1. **Triage's `FILES:` selection** — the real gate. A wrong list is
   unrecoverable: `run_orchestration` holds it fixed across every retry.
2. **The Coder's read-only reference context** — signatures, not bodies.
3. **A human triaging `needs-info`** — "did you mean these files?"

## Where it goes: `cicaid`, not a new repo

| Option | Verdict |
|---|---|
| **New repo** | No. An index with no caller is dead weight, and it adds a release + pin-update cycle (`scripts/update_dependency_pins.py`, `.github/scripts/update_cicaid_pins.py`) for a few hundred lines of stdlib code. Revisit only if it grows a daemon. |
| **`cicaid-pro`** | No. The ranker is deterministic — git, lexical scoring, `ast`. Nothing in it is an LLM call, so it does not belong in the LLM engine, and putting it there hides it from `cicaid`'s own commands. |
| **`issue-worm-pro`** | No. Would make the most obvious consumer the only possible one, and `cicaid-pro`'s reviewers want the same ranking. |
| **`cicaid`** ✅ | Yes. It is deterministic GitHub/git plumbing, which is exactly this repo's charter. Everything downstream already depends on it (`cicaid-pro` since #472; `issue-worm` shells out to it), so no new dependency edge appears anywhere. It merges into the `cicaid_devtools` PEP 420 namespace. And it is where the Graphify producer already lives. |

The free/paid split survives: deterministic ranking is free-tier, and any
later LLM-assisted reranking is a `cicaid-pro` command that calls into it.

**Dependency constraint:** v1 must stay stdlib-only (`sqlite3`, `ast`,
`subprocess`, `re`). `cicaid`'s runtime deps are three packages and the
product promise is a light install. If embeddings ever land, they go behind
`pip install cicaid-devtools[context-embed]` or move to `cicaid-pro` —
never into the base install.

## Shape

```
src/cicaid_devtools/context/
  store.py      # sqlite, keyed on git blob SHA
  symbols.py    # ast pass: defs, classes, imports, docstring first lines
  lexical.py    # BM25 over a code-aware tokenizer
  cochange.py   # git log --name-only -> co-change counts
  graph.py      # import edges (ast) and, optionally, graphify's graph.json
  rank.py       # signal fusion -> ranked paths with reasons
  pack.py       # budget-aware prompt assembly
  eval.py       # replay merged PRs as labelled examples
  cli.py        # cicaid context {index,rank,pack,eval,explain}
```

Entry point alongside the others in `[project.scripts]`, and a
`"context"` row in `cli.py`'s dispatch table under "CI & repo tooling".

### Store and freshness

SQLite at **`$GIT_DIR/cicaid/context.sqlite`** — inside `.git/`, so it is
never committed, never needs `ensure_gitignored`, and is discarded with the
checkout.

Every row is keyed on the **git blob SHA** from `git ls-files -s`, which
gives content hashes for free. `workspace.refresh_to_main()` resets the
workspace on every pass and the pipeline itself opens PRs that change the
code, so the index goes stale continuously — blob-SHA keying makes a
refresh O(changed files), typically single digits. This is the point the
original RAG proposal missed entirely and it is non-negotiable.

Concurrency: the scheduler runs parallel workers (#159). One SQLite file
per workspace, WAL mode, and treat a locked DB as "index unavailable" and
fall back to the unranked listing. Degraded context is not a failure.

### Signals

The mistake to avoid is treating these as five independent rankers to
blend. They are **seeds** and **expansions**:

**Seeds** — high precision, nearly certain:
- `path`: a literal path or filename appearing in the issue body or
  comments. On this backlog that is common and close to ground truth.
- `lex`: BM25 over the issue text against a code-aware tokenizer — split
  `snake_case` and `camelCase` into parts *and* keep the original token, so
  `_load_role_config` matches both itself and `load role config`. Index
  identifiers, path components, docstring first lines, and string literals.

This is the signal embeddings are worst at and BM25 is best at. Real issue
titles from this backlog — *"config.py's `_load_role_config()` falls back
from `{ROLE}_OLLAMA_MODEL`…"* — are dense with exact identifiers. Dense
retrieval blurs exactly those. Lexical first, alone, is the correct v1.

**Expansions** — applied *over* the seeds, never scored independently:
- `cochange`: files that historically land in the same commit as a seed
  (`git log --name-only`, normalised by each file's own churn so that
  `README.md` does not win everything). The best single predictor of "what
  else does this change touch", and it costs one git command.
- `graph`: 1 hop in and 1 hop out of a seed on the import graph (`ast`).
- `recency`: a weak prior, tie-break only.

**Fusion: reciprocal rank fusion**, not a weighted sum. Weighted sums need
per-signal calibration you cannot do without labels; RRF needs none and is
robust to one signal being garbage on a given issue. Revisit only if the
eval harness says a learned weighting beats it.

**Output is paths, with reasons.** Chunk-level scores aggregate up to the
file (max, plus a normalised sum) because Triage's deliverable is a path
list and the Coder rewrites whole files. Retrieving half a function is not
actionable here. Every returned path carries its reasons —
`["path-mention", "cochange 0.81 with orchestrator.py"]` — so the
`needs-info` comment can explain itself and the whole thing stays
inspectable, which is what `design-deterministic-review-analysis.md`
values.

**Bias toward recall.** A missing file is fatal (the lock freezes it across
every retry); a spurious one is merely wasteful. Score threshold with a
small cap, not a fixed top-k — most issues here touch 1–3 files.

### Packing: the part that answers the context question

`cicaid context pack --budget N` fills tiers in order and stops:

| Tier | Content | Cost |
|---|---|---|
| A | Every tracked path | ~5 tok/path; 226 files ≈ 1.5K tok. **Always send all of it.** |
| B | AST signature skeleton of ranked files — class/def lines, arguments, docstring first line | ~5–10% of file size |
| C | Full bodies of top-ranked files | the expensive tier |
| D | Matched chunks only, from the tail | fallback |

Tier A retires the truncation question outright: paths are nearly free, and
`_summarise_repo`'s sampling exists only because the window was small.

**Tier B is the highest value-per-token item in the system and the thing
embedding RAG never gives you.** It is also the honest answer to "the coder
should have access to all the code": at ~7% of source size, the *signature
skeleton of all of `issue-worm-pro`* is ~26K tokens. That fits a 30K
window. The coder genuinely can see the whole repo — just not every line
of it.

Default budget should be **30K, not 200K**, with the reasoning from §1
written into the help text. Prompt order must put stable content first
(Tier A, then B, then bodies, then the volatile task/feedback last) so
prefix caching works on the metered backends — the prompt-ordering bug the
prior doc identified applies here too.

## Build the eval harness first

This is the highest-leverage piece in the document and it is nearly free.

**Every merged PR is a labelled example.** `(issue body) → (files the
linked PR changed)` is exactly the retrieval task, and `cicaid` already has
`lib/linked_issue.py` to resolve the link. Across six repos there are
hundreds to thousands of labelled examples, costing zero LLM calls to
collect.

```
cicaid context eval --repo leonarduk/issue-worm-pro --since 2026-01-01
```

Replays each closed issue against the tree **as of the PR's base commit**
(not today's HEAD — otherwise the ranker sees files the fix created) and
reports recall@1/3/5/10 and MRR per ranker, with an ablation per signal.

This settles the prior doc's decision rule without an end-to-end pipeline
run, and it is the only thing that makes the embeddings question
answerable rather than a matter of taste. Two cautions it must carry:

- Recall@k is a **proxy**. It can improve while end-to-end pass rate does
  not. Adopt on pass rate; use recall to iterate quickly between pass-rate
  runs.
- Issues whose PR touched only `ui_server.py` will dominate the corpus and
  flatter any ranker. Report stratified by target file.

## Would Graphify help?

`cicaid` already ships `graphify_repos.py` (`cicaid graphify-repos`), which
clones a configured repo list, runs `graphify .` in each, and collects
`graph.json` into one directory.

**Nothing reads `graph.json`.** It is a producer with no consumer. That is
the single most useful fact about the Graphify question: the graph is
already being generated and the missing half is exactly the ranker
described here.

What a graph is genuinely good at is the question the other signals answer
badly: *what breaks if this changes* — blast radius, and paths between two
symbols. That is Triage's second-order problem, and it maps directly onto
the `graph` expansion signal.

Three reasons not to make it the foundation:

1. **`ast` gives you the same edges for a Python repo, for free.** Imports,
   definitions and call sites, stdlib only, no tree-sitter, no extra
   install, no cross-repo output directory to keep fresh. Build against an
   internal `graph.py` interface and treat `graph.json` as one possible
   *backend* behind it.
2. **The semantic pass costs tokens and privacy.** `graphify .` without
   `--code-only` sends the corpus to an LLM backend to infer `INFERRED`
   edges — `graphify_repos.py` already guards this behind an API-key check
   for good reason. A local-first product cannot make whole-repo upload a
   default, and the doc's own privacy section says so.
3. **Freshness.** A combined output directory regenerated by a separate
   command is stale the moment `refresh_to_main()` runs. The blob-SHA store
   is not.

**Verdict: keep `cicaid graphify-repos` as-is; make `graph.py` able to read
its `graph.json` as an optional edge source, with `ast` as the default.**
That gets the EXTRACTED edges for free where the graph exists, keeps the
`--code-only` path as the only one on by default, and becomes the obvious
route if the target repos ever stop being Python-only — which is the one
scenario where Graphify clearly wins over a hand-rolled `ast` pass.

## Staging

- **Stage -1 — split `ui_server.py` and `scheduler.py`.** Independent of
  all of this and a prerequisite for measuring it: 760KB across two files
  is what a 30-60K window cannot hold. (Per the correction in §2 this is
  an *input*-budget argument; the pro Coder already emits targeted edits,
  so it is not the output-cost emergency an earlier revision claimed.)
- **Stage 0 — `cicaid context eval`.** Harness + corpus, no ranker. Baseline
  = today's behaviour (`_summarise_repo`'s sampled listing). Also run
  `benchmark_loop.py`'s arm 5 `triage_scoped`, which the prior doc notes
  has still never been run, and add task variants with `files` omitted.
- **Stage 1 — `index` + `rank`, lexical + path seeds only.** No expansions.
  Establishes how much of the win is plain BM25 — plausibly most of it.
- **Stage 2 — cochange and import-graph expansion.** Cheap, git- and
  `ast`-only. Wire `graph.json` as an optional backend here.
- **Stage 3 — `pack`, Tier A/B.** Signature skeletons into the Coder's
  prompt. Measure pass rate, because the prior doc's warning that
  read-only context can *hurt* applies and must be falsified, not assumed.
- **Stage 4 — embeddings, only if Stage 1–3 numbers demand it.** Local
  model only; hybrid with BM25; `sqlite-vec` or a NumPy array in the same
  store; behind an optional extra. **Adopt only if it beats Stage 2 on the
  Stage 0 harness by a margin worth the install weight.**

## Non-goals

- A vector database service. One SQLite file per workspace, or nothing.
  A shared service turns a local lookup into distributed state across the
  scheduler's parallel workers.
- Cloud embedding APIs. They ship the *entire* repository to a third party,
  including files no issue ever touches — a categorical expansion of data
  exposure against a local-first promise.
- Retrieval replacing the `FILES:` lock. Softening that lock to a
  request-an-additional-file path is worth more than improving the initial
  guess, and it is a separate change.
- Chunk-level output. Paths with reasons, aggregated from chunk scores.

## Open questions

- Does better file selection convert to pass rate? The 2026-09-14 re-run
  scored 10/10 native, so the task set is currently too easy to show it.
  Stage 0's `files`-omitted variants exist to answer this.
- Is the ranker free-tier or a `cicaid-pro` differentiator? Recommended
  free, on the deterministic/LLM split — but it is a business call, and it
  is the one decision here that is not technical.
