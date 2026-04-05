---
always: false
version: 0.6.1
description: Dual-mode artifact optimizer with cross-run pattern reuse and conservative iterative improvement. Optimizes instruction artifacts (binary checks) and executable artifacts (deterministic tests) using the strongest available evaluator.
---

# Skill Autoresearch

Optimization loop for Hermes-style artifacts. Optimizes **artifacts**, not model weights.

Supported targets:
- **Instruction artifacts**: `SKILL.md`, prompts, policies, system instructions
- **Executable artifacts**: scripts, validators, CLI tools, parsers, testable configs

Core loop: identify target → choose evaluator → build/load tests → baseline → diagnose → external verification → archive lookup → patch strategy → patch → re-evaluate → keep/revert → report → archive export.

## When to Use

Use when asked to optimize, benchmark, or improve a skill, prompt, script, or validator.

## Target Mode and Evaluator Selection

Detect mode before evaluation:
- **Instruction mode**: natural-language artifact → binary behavior checks + structured LLM judge
- **Code mode**: executable artifact → deterministic tests (exit code, stdout, assertions)

Evaluator priority: deterministic tests > parser/regex checks > structured LLM judge > scalar rubric.

If unclear, prefer the mode with the more deterministic evaluator.

For hybrid targets (e.g. SKILL.md with helper scripts), evaluate each component with its strongest available evaluator and aggregate decisions conservatively. Deterministic failures in executable components cannot be overridden by instruction-only gains.

## Core Principles

1. **One focused patch per iteration** — small, testable, interpretable
2. **Freeze the benchmark** — generate tests once, do not rewrite mid-run
3. **Use the strongest evaluator** — deterministic when possible
4. **Protect against regressions** — never keep a patch that breaks a Must-Have
5. **Separate performance from protocol** — `performance_keep` vs `protocol_keep`
6. **Be conservative** — prefer revert when borderline

## Before You Start

1. Create run directory: `runs/<target_name>/<timestamp>/`
2. Save clean snapshot before any edit
3. Detect target mode and choose evaluator
4. Save `judge_config.json` with model, temperature, date, mode
5. If target already performs strongly with no failures, report `already strong`

## Mandatory Checks

Every eval plan MUST include these checks regardless of target type:
- `no_hardcoded_pii` — no real names, emails, phone numbers, addresses, or credentials in examples. Use placeholders (`<name>`, `<email>`, `example.com`).
- `no_hardcoded_secrets` — no tokens, passwords, API keys, or connection strings.
These are Must-Have checks that block KEEP if they fail.

## Optimization Loop

1. **Identify target** — path, type, mode, evaluator, risks
2. **Snapshot** — save restorable pre-run copy
3. **Build eval plan** — must-pass behaviors, should-have, failure modes, regression risks
4. **Load or generate tests** — freeze dev + holdout sets
5. **Baseline** — evaluate untouched target on dev + holdout, save results
6. **Diagnose** — use failing checks/tests to identify one patchable weakness (dev only)
7. **External verification** — if target references external tools/APIs/CLIs, verify commands, flags, URLs against official docs or `--help` output. Record discrepancies as high-priority diagnosis items. Skip if target is purely internal.
8. **Archive lookup** — search prior runs for reusable patterns (see Archive section)
9. **Patch** — one focused change only
10. **Re-evaluate** — same frozen tests
11. **KEEP/REVERT** — mode-specific rules, write decision artifact
12. **Iterate** — up to 5 (3 in fast mode), stop early if no improvement for 2 consecutive iterations

---

# Instruction Mode

For `SKILL.md`, prompts, policies, and text instructions.

## Binary Checks

Each check must be: atomic, observable, binary (T/F), tied to a `source_rule`.

Examples: `uses_web_extract_for_url`, `verifies_output_not_empty`, `does_not_claim_success_without_verification`

**Must-Have**: required for acceptable behavior. Failure blocks KEEP.
**Should-Have**: useful but not blocking.

## Check Generation

Extract normative rules from target (always/must/never/if-then/verify/fallback). For each:
1. identify trigger and expected action
2. classify: `must/always/never` → Must-Have; `prefer/recommend` → Should-Have; ambiguous → Should-Have
3. compile one observable binary check with `source_rule`

Only create checks for externally observable behavior. No checks for intent or reasoning.

**Limits**: 3–5 Must-Have + 2–4 Should-Have per case. Deduplicate: if two checks test the same behavior, merge and list both source rules.

## Structured Judge Output

```json
{
  "case_id": "hold_03",
  "checks": [
    {"id": "uses_web_extract_for_url", "must_have": true, "result": true, "evidence": "Used web_extract on the URL."},
    {"id": "verifies_output_not_empty", "must_have": true, "result": false, "evidence": "No verification step."}
  ],
  "must_have_pass_rate": 0.5,
  "total_pass_rate": 0.67
}
```

Judge rules: if not explicit/observable → `false`. No charitable inference. Short concrete evidence.

## KEEP/REVERT (Instruction)

**REVERT** if: any Must-Have regresses, must_have_pass_rate drops, new critical failure, unstable judge results.
**KEEP** only if: no Must-Have regressions AND at least one of:
- `must_have_pass_rate` increases, or
- at least 2 distinct `should_have` checks improve with no regressions, or
- one previously failing high-impact scenario now passes end-to-end.

A `high-impact scenario` is one that touches a Must-Have rule, a safety-critical behavior, a commonly occurring user path, or a failure mode explicitly listed in the eval plan as high-priority.

If KEEP/REVERT depends on a single disputed check or <10% total delta, rerun judging once with identical config. If results disagree, mark `low_confidence_boundary_case` and prefer REVERT.

If multiple instruction cases show disputed or unstable judge outcomes within the same run, lower confidence for the run and prefer `needs human review` over strong KEEP claims.

---

# Code Mode

For scripts, validators, CLI tools, parsers, and small programs.

## Deterministic Tests

Use executable tests as primary evaluator. Preferred signals: exit code, stdout/stderr match, output diff, regex assertions.

Do not use LLM judging when deterministic evaluation is available.

## Test Trust Hierarchy

1. Existing project test suite (highest trust)
2. User-provided tests/fixtures
3. Generated dev tests
4. Generated holdout tests (lowest trust)

Never rewrite trusted tests. If only generated tests exist, mark conclusions as preliminary.

## Code Test Case Format

```json
{
  "id": "hold_03",
  "command": "python validate_ksef.py missing_nip.xml",
  "input_files": ["missing_nip.xml"],
  "expected_exit_code": 1,
  "stdout_must_match": ["NIP", "missing"],
  "stderr_must_not_match": ["Traceback"],
  "must_pass": true
}
```

## Baseline & Diagnosis (Code)

Run each test, capture exit code + stdout + stderr, record pass/fail. Diagnose from failing test IDs and observable failure modes — not guesswork.

## Patch Rules (Code)

One focused patch per iteration. Do not modify trusted tests. Do not hardcode fixture names or expected outputs. Prefer minimal, explainable patches.

## KEEP/REVERT (Code)

**REVERT** if: any holdout Must-Have regresses, holdout pass rate drops, patch is brittle/test-specific, flaky results.
**KEEP** only if: no regressions, holdout improves or critical failure resolved, patch is small and interpretable.
If only dev improves but holdout flat → prefer REVERT, unless the patch resolves a clearly diagnosed critical failure and holdout coverage for that failure mode is absent or weak.

## Flaky Test Protocol

If a test produces inconsistent results across runs:
1. Rerun the failing case 3 times with identical config
2. If results are inconsistent, mark the case as `unstable`
3. Do not use unstable cases as evidence for KEEP
4. Only use them if an independent deterministic signal confirms the result

## Benchmark Validity

If a frozen test is shown to contradict the target specification or a trusted external source:
1. Stop the run immediately
2. Mark the run as `benchmark_invalid` in the final report
3. Do not patch toward the faulty test
4. Record the contradiction evidence
5. Start a new run only after fixing the benchmark

## Safety Constraints

- Isolated workspace when possible
- Snapshot before patching
- Execution timeouts and resource limits
- No network unless explicitly required
- No destructive commands or privileged operations
- Restrict writes to target workspace
- Flaky/environment-sensitive tests = lower confidence

If safe execution cannot be ensured, do not run autonomous code optimization.

---

# Decision Artifacts

Each iteration writes `iter_<n>_decision.json`:

```json
{
  "decision": "keep",
  "decision_class": "performance_keep",
  "must_have_pass_rate_before": 0.67,
  "must_have_pass_rate_after": 1.0,
  "must_have_regressions": [],
  "reason": "Must-have pass rate improved with no regressions."
}
```

Classes: `performance_keep` (behavior improved), `protocol_keep` (methodology/process improved without changing behavior-facing content), `revert`.
`KEEP`/`REVERT` is the action outcome; `decision_class` explains why the outcome was chosen.
`protocol_keep` is allowed only for changes to run process, evaluation setup, or documentation structure — never for changes that alter the target's observable behavior.
For code mode also include: `failing_test_ids_before`, `failing_test_ids_after`, `trusted_test_source_used`.

---

# Reporting and Confidence

Final report includes: target mode, evaluator, baseline/final metrics, kept/reverted patches, regressions, confidence note, recommendation.

**Confidence** depends on evaluator strength + test source trust:
- Code mode with trusted tests: highest confidence
- Instruction mode with good checks: moderate confidence
- Generated-only tests: preliminary — recommend rerun with larger/trusted set

**Recommendations**: `already strong` / `improved and worth keeping` / `needs human review` / `benchmark too weak to conclude`

If holdout reaches 100%: "Possible benchmark saturation — expand holdout before claiming maturity."

---

# Graceful Degradation

- Instruction: if structured judging unavailable → simpler checks, lower confidence
- Code: if test suite unavailable → command-based fixtures; if only generated tests → preliminary; if unsafe → stop

---

# Never Do These

- Never patch multiple weaknesses in one iteration
- Never keep a patch with a new Must-Have regression
- Never rewrite trusted tests to pass
- Never use vague scoring when a stronger evaluator exists
- Never claim success from dev-only gains
- Never hide regressions behind aggregates
- Never run code optimization without safety constraints
- Never hardcode fixtures into patches

---

# Files

Store in `runs/<target_name>/<timestamp>/`:
- `target_snapshot_before.*`, `judge_config.json`
- `dev_cases.json`, `holdout_cases.json`
- `baseline_dev.json`, `baseline_holdout.json`
- `iter_<n>_patch.md`, `iter_<n>_dev.json`, `iter_<n>_holdout.json`, `iter_<n>_decision.json`
- `diagnosis.md`, `final_report.md`

---

# Cross-Run Archive and Pattern Reuse

Purpose: reuse reliable improvement patterns from prior runs without changing the current run's benchmark, evaluator, or safety rules.

## Archive Files

- `autoresearch_archive/success_patterns.jsonl` — global archive
- `autoresearch_archive/by_target/<target_slug>.jsonl` — per-target archive
- `runs/<target>/<timestamp>/archive_export.json` — per-run export
- `runs/<target>/<timestamp>/archive_lookup.json` — per-run lookup report

Create `autoresearch_archive/` if it does not exist.

## Archive Record Format

Each line in JSONL files is one JSON object:

```json
{
  "schema_version": "1",
  "record_id": "uuid-or-timestamp-hash",
  "created_at": "ISO-8601 UTC",
  "source_run": "runs/<target>/<timestamp>/",
  "target_slug": "string",
  "target_type": "instruction|code",
  "domain_tags": ["ocr", "vat", "kpir", "classification"],
  "artifact_paths": ["relative/path/to/edited/file"],
  "problem_summary": "1-3 sentence diagnosis of the pre-patch weakness",
  "patch_summary": "1-3 sentence summary of the successful change",
  "patch_kind": "prompt-constraint|example-addition|decision-rule|validator-fix|regex-fix|test-harness-fix|other",
  "failure_mode_tags": ["missed-edge-case", "format-drift", "must-have-risk"],
  "preconditions": ["facts that were true when this patch worked"],
  "do_not_apply_when": ["conditions where this patch is likely harmful"],
  "evaluator_type": "deterministic|parser|regex|llm_judge|scalar_rubric",
  "benchmark_fingerprint": "stable hash or textual fingerprint of frozen tests",
  "must_have_status_before": {"passed": 0, "failed": 0},
  "must_have_status_after": {"passed": 0, "failed": 0},
  "metrics_before": {"primary": 0, "secondary": {}},
  "metrics_after": {"primary": 0, "secondary": {}},
  "improvement_delta": {"primary": 0, "secondary": {}},
  "keep_reason": "why this patch was kept",
  "confidence": "high|medium|low",
  "generalization_note": "what likely transfers to future runs"
}
```

## When to Write Archive Records

Write ONLY if ALL true:
1. Final decision is KEEP
2. No Must-Have check regressed
3. Benchmark was frozen before patching and not rewritten mid-run
4. Improvement is attributable to the patch, not evaluator instability
5. Patch summary and diagnosis are specific enough to reuse

Do NOT archive: reverted patches, ties with no gain, evaluator instability, formatting-only gains, post-baseline test modifications.

## External Verification Step (detailed)

This step is part of the main Optimization Loop (step 7). Full procedure:

1. Identify all external tool commands, flags, URLs, and behaviors mentioned in the target
2. Verify each against the tool's official documentation, `--help` output, or release pages
3. Record discrepancies as high-priority diagnosis items (wrong syntax, missing features, outdated URLs, redundant workarounds where native commands exist)
4. Treat official docs as higher authority than the target's current content

Skip this step only if the target is purely internal (prompts, policies, workflows with no external tool references).

## Archive Lookup Step

Insert after external verification, before first patch: `diagnosis → external verification → archive lookup → patch strategy → patch`

1. Read up to 50 recent records from global archive + 20 from per-target archive
2. Score each record using text matching only (no embeddings):

```
transfer_score =
  +4 if target_type matches
  +4 if same target_slug
  +3 for each overlapping domain tag (max +6)
  +3 for each overlapping failure_mode tag (max +6)
  +2 if patch_kind suits current diagnosis
  +2 if evaluator_type matches
  +2 if benchmark/problem shape is similar
  -5 for each matching do_not_apply_when condition
  -3 if confidence == low
```

3. Select at most 5 records with `transfer_score >= 6`. Require at least one match from `failure_mode_tags` or `patch_kind` — domain tags alone are insufficient.
4. Write to `runs/<target>/<timestamp>/archive_lookup.json`, including which features drove each record's score.

Note: This scoring is a bootstrap heuristic, not a semantic similarity measure. Log the top-10 ranked records even when selecting only top-5. When transfer scores are tied or close, prefer records with higher confidence, more recent creation date, and stronger evaluator types (deterministic > parser/regex > llm_judge > scalar_rubric).

## How Archive Records May Influence a Run

Archive records are advisory only. They MAY: sharpen diagnosis, choose patch kinds, prioritize fixes, avoid harmful patterns, generate candidate strategies.

They MUST NOT: rewrite frozen benchmark, lower Must-Have thresholds, skip baseline, skip snapshot, justify KEEP without fresh evaluation.

## Transfer Hints in Patch Strategy

When archive matches exist, include:

```md
### Transfer hints from prior runs
- Record: <record_id>
- Why relevant: <1-2 lines>
- Reusable idea: <1 line>
- Guardrail: <1 line from do_not_apply_when or preconditions>
```

Prefer high-score archive patterns unless current diagnosis conflicts with their preconditions.

## Per-Run Export

At run end, always write `archive_export.json` with: whether archive-worthy, the exact record to append, or reason not to archive. If worthy, append to both global and per-target JSONL.

## Authority Order

1. Current frozen benchmark and evaluator results
2. Existing project tests
3. User-provided tests
4. Archive transfer hints
5. Newly generated hypotheses

If archive advice conflicts with current run evidence, prefer current run evidence.

## Goodhart Guardrails for Archive

- Never copy prior numeric thresholds unless current evaluator independently supports them
- Never treat repeated patterns as sufficient proof in regulated domains
- Never archive gains from narrower formatting while semantic correctness stayed flat
- For accounting/tax/VAT/KPiR/OCR/booking skills, prefer records that improved deterministic checks over LLM-judge-only improvements
- If reused pattern increases judge score but weakens deterministic/Must-Have coverage, REVERT and mark suspicious

---

# Scope Limitations

This skill is designed for small to medium artifacts. Not suitable for autonomous use on:
- Multi-service distributed systems
- Stateful production migrations
- Security-critical refactors without trusted external tests
- Changes requiring privileged or destructive operations
- Codebases where a single patch can affect thousands of lines

For these cases, use autoresearch only as an advisory tool with mandatory human review of every KEEP decision.

---

# Self-Modification Mode (Meta-Optimization)

Purpose: allow skill-autoresearch to improve its own improvement procedure with the same safety guarantees it applies to other targets.

## Eligibility

Self-modification MAY run only if ALL conditions hold:
1. At least 10 completed runs exist under `runs/` across any targets
2. At least 5 completed runs contain decision artifacts with KEEP/REVERT outcomes
3. Current invocation explicitly targets `skill-autoresearch` itself
4. Snapshot of current SKILL.md created before any edit
5. Frozen meta-benchmark assembled before any self-patch

If any condition fails, write a report describing why ineligible. Do not self-modify.

## Meta-Run Files

- `runs/skill-autoresearch/<timestamp>/meta_corpus.json`
- `runs/skill-autoresearch/<timestamp>/meta_diagnosis.md`
- `runs/skill-autoresearch/<timestamp>/meta_benchmark.json`
- `runs/skill-autoresearch/<timestamp>/meta_patch_plan.md`
- `runs/skill-autoresearch/<timestamp>/meta_decision.json`

## Constitutional Rules (NOT Editable)

These rules are NEVER modifiable by self-modification:
- Must-Have regression blocking
- Frozen benchmark requirement
- Snapshot-before-patch requirement
- Keep/revert requirement
- Trust hierarchy preferring deterministic evidence over judge-only
- Iteration cap (unless deterministic meta-benchmark explicitly measures net benefit)

## Editable Procedure Sections

Self-modification MAY edit:
- Diagnosis procedure
- Evaluator selection rules
- Archive lookup and transfer rules
- Patch proposal rules
- Decision criteria (within constitutional bounds)
- Reporting rules
- Self-modification eligibility thresholds

## Meta-Corpus Assembly

Before proposing any self-patch, assemble from past runs:
- target slug, target type, evaluator type
- baseline/final metrics, KEEP/REVERT outcome
- Must-Have before/after, iteration count
- patch summaries, failure mode notes
- archive export data, decision artifacts

Write to `meta_corpus.json`. When assembling the meta-corpus, prefer more recent runs if older runs used weaker evaluators, incomplete decision artifacts, or pre-constitutional procedures.

## Meta-Diagnosis

Analyze meta-corpus for recurring procedural weaknesses:
- evaluator mis-selection
- poor patch targeting
- wasted iterations
- recurring revert causes
- archive underuse
- overreliance on LLM judge
- poor diagnosis/patch separation
- insufficient accounting-domain guardrails
- repeated failure modes across domains

MUST cite concrete counts (revert rate by evaluator, average gain by patch kind, Must-Have near-miss frequency, etc). Write to `meta_diagnosis.md`.

## Meta-Benchmark (Frozen Before Self-Patch)

### A. Constitutional Safety Checks
Binary checks that patched SKILL.md still preserves all constitutional rules.

### B. Procedure Quality Checks
- Correctly identifies relevant vs irrelevant archive evidence?
- Prefers deterministic over judge-only evidence?
- Forbids changing benchmarks mid-run?
- Separates diagnosis from patch proposal?
- Defines clear self-modification eligibility?
- Includes anti-Goodhart language?

### C. Replay Checks
Use 5-10 prior decision artifacts. For each, evaluate whether the proposed change would have: reduced avoidable reverts, improved diagnosis specificity, avoided weak evidence reliance, or made no difference. Advisory only — cannot override constitutional checks.

### D. Diff-Boundedness
- One focused procedural change per iteration
- No broad rewrite
- No removal of core safety language

Store in `meta_benchmark.json`.

## Self-Patch Rules

Same one-focused-patch rule as normal runs. Each proposal MUST include:
- exact procedural weakness addressed
- expected benefit and safety impact
- sections to edit
- why this is local, not a rewrite
- how success is measured on frozen meta-benchmark

Allowed: improve archive scoring, add judge-overfitting guardrail, require stronger diagnosis evidence, improve decision artifact schema.

Disallowed: removing regression blocks, allowing benchmark rewrites, replacing deterministic tests with judge-only, weakening snapshot/revert rules, vague "be smarter" edits.

## Keep/Revert for Self-Modification

KEEP only if ALL true:
1. All constitutional safety checks pass
2. No constitutional rule weakened, deleted, or made ambiguous
3. Frozen meta-benchmark shows clear net improvement
4. Replay checks show non-negative effect overall
5. Change is narrow enough to attribute gain to patch
6. Human-readable rationale explains why patched procedure is less gameable, not merely more permissive

Otherwise REVERT.

## Goodhart Protections

- Meta-benchmark frozen before any self-patch proposed
- Self-patch cannot modify files inside current run directory
- Self-patch cannot edit current run's meta-benchmark, replay sample, or constitutional checklist
- Wording-only improvements that don't add operational clarity = metric gaming → REVERT
- If procedure quality improves only on judge checks but becomes less strict on deterministic evidence = failure
- For regulated accounting: any self-patch broadening acceptance criteria, weakening evidence standards, or reducing rollback conservatism is presumed unsafe unless a stronger deterministic safeguard is added elsewhere in the same patch
- Prefer self-patches increasing specificity, observability, auditability over flexibility

## Self-Modification Run Flow

`eligibility → snapshot → meta-corpus assembly → meta-diagnosis → freeze meta-benchmark → baseline meta-evaluation → propose one self-patch → apply → re-evaluate → KEEP or REVERT → report`

## Meta Decision Artifact

```json
{
  "schema_version": "1",
  "target": "skill-autoresearch",
  "timestamp": "ISO-8601 UTC",
  "eligible": true,
  "constitutional_checks_before": {},
  "constitutional_checks_after": {},
  "meta_benchmark_fingerprint": "string",
  "baseline_meta_score": {"primary": 0, "secondary": {}},
  "patched_meta_score": {"primary": 0, "secondary": {}},
  "replay_summary": {"sample_size": 0, "positive": 0, "neutral": 0, "negative": 0},
  "self_patch_summary": "string",
  "procedural_weakness_addressed": "string",
  "goodhart_risk_review": {"risk_found": false, "notes": []},
  "final_decision": "KEEP|REVERT",
  "decision_reason": "string"
}
```

## Self-Modification Report

MUST include: eligibility reason, repeated weakness that triggered meta-optimization, constitutional checks used, what changed in SKILL.md, whether procedure quality improved, why result is not just easier scoring, final KEEP or REVERT.

## Archive Interaction

Successful self-modifications MAY be archived with:
- `target_type = "instruction"`
- `domain_tags` includes `"meta-optimization"` and `"autoresearch"`
- `do_not_apply_when` must include: `"when constitutional rules would be weakened"`, `"when replay sample is absent or too small"`

Self-modification archive records are lower authority than target-specific empirical evidence.
