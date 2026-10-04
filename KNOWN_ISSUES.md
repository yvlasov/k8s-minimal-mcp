# Known Issues

Full history (root cause, fix, tests, verification) for every entry below lives in
`CHANGELOG.md`. This file tracks current status only: what's still open, what shipped, and the
one process rule (Definition of Done) that governs when a Status line may say "implemented."

## FEATURE REQUESTS

Distinct from `## OPEN`/`## FIXED` below, which track code defects — this section tracks
proposed new capability. Full design/implementation plan lives in `PRD.md` §15 / `SPEC.md` §8;
shipped-feature history lives in `CHANGELOG.md`.

**Definition of Done** (added 2026-09-25 after the 8th recurrence of doc drift — Issue 22 — and
a shipped-but-broken tool — Issue 40 — both traced to the same root cause: a "Status:
implemented" label written before it was actually true). A Status line may not claim
"implemented" until all of the following hold:
1. **Tests exercise the real dispatch path** (`server.py`'s `_dispatch()`/the registered
   `@app.tool` wrapper), not just the handler function directly — see Issue 41/CHANGELOG.
2. **SPEC.md §2's Module Layout tree lists the new module(s).**
3. **PRD.md §6's Tool Specification table has a row for the new tool** (prompts are exempt —
   see FR11 — but anything registered via `@app.tool` is not).
4. **PRD.md §12's "Status against current `main`" paragraph is re-dated and re-counted** if the
   tool count changed.
5. **README.md's Available Tools table has a row for the new tool.**
6. **The Status line's test count and commit hash are verified by actually running the suite
   and checking `git log`**, not estimated or carried over from a draft.
7. **`CHANGELOG.md` has an entry** (root cause/fix/test, or the FR's shipped-status writeup).
   Added 2026-09-26 after this recurred a third time in a row (Issues 42/43, then 44/45, then
   46/47/48 — nine fix commits total, zero of them touching `CHANGELOG.md`) despite items 1–6
   above all being satisfied each time. `KNOWN_ISSUES.md`'s FIXED table explicitly promises
   "full detail... in `CHANGELOG.md`" for every row — a fix commit is not done until that
   promise is true for its own row, not left for the next review pass to notice and backfill.
8. **`uv lock` was run after any `pyproject.toml` version/dependency change** (added 2026-10-04
   after the v0.3.0 release — Issue 64). `uv.lock` is intentionally gitignored (`.gitignore`), so a
   stale lock is invisible to CI and reviewers: the next plain `uv run` startup re-resolves online,
   and with the MCP host's `HTTPS_PROXY=socks5://…` that hang surfaces as a silent "Request timed
   out" in the client, not as the version-discipline error it is. Run `uv lock && uv sync --extra
   dev` before the release commit; MCP hosts should start the server with `uv run --frozen` so a
   future stale lock fails instantly instead of hanging (SPEC §9 is the full procedure).

| FR | Feature | Status | Spec |
|---|---|---|---|
| FR1 | `output=jsonpath` for `k_get`/`k_apply`/`k_patch` | Done | PRD §15 FR1, SPEC §8 FR1 |
| FR2 | `annotation_selector` for `k_get` | Done | PRD §15 FR2, SPEC §8 FR2 |
| FR3 | `k_list_resources` tool | Done | PRD §15 FR3, SPEC §8 FR3 |
| FR4 | Test coverage for `k_delete`/`k_describe`/`k_logs`/`k_exec`/`k_list_contexts` | Done | PRD §15 FR4, SPEC §8 FR4 |
| FR5 | Fix `k_get`'s `output=wide` no-op | Done | PRD §15 FR5, SPEC §8 FR5 |
| FR6 | Fix `k_apply`/`k_patch`'s non-functional `output=json`/`yaml` | Done | PRD §15 FR6, SPEC §8 FR6 |
| FR7 | Add `events` to the R2 core table | Done | PRD §15 FR7, SPEC §8 FR7 |
| FR8 | Fail-fast nested-brace `jsonpath_template` validation | Done | PRD §15 FR8, SPEC §8 FR8 |
| FR9 | `k_get_secret_to_file` | Done | PRD §15 FR9, SPEC §8 FR9 |
| FR10 | `src_file` for `k_apply` | Done | PRD §15 FR10, SPEC §8 FR10 |
| FR11 | Built-in MCP prompts (ArgoCD/Cilium status) | Done — see Issue 43 (resolved) | PRD §15 FR11, SPEC §8 FR11 |
| FR12 | `k_get_helm_release` | Done — see Issue 39 (resolved) | PRD §15 FR12, SPEC §8 FR12 |
| FR13 | `k_auth_can_i` | Done — see Issue 40 (resolved) | PRD §15 FR13, SPEC §8 FR13 |
| FR14 | `grep` — text-filtering for `k_logs`/`k_describe`/`k_get output=wide` | Done — see CHANGELOG.md | PRD §15 FR14, SPEC §8 FR14 |
| FR15 | Typing/naming consistency cleanup (`auth_can_i.py`'s `discovery_cache`, `k_logs`'s tail default) | Done — see CHANGELOG.md | PRD §15 FR15 |
| FR16 | Add `mypy` + `ruff` (lint/type-check tooling) | Done — see CHANGELOG.md | PRD §15 FR16 |
| FR17 | Pin `fastmcp` to a tested version range (currently unbounded `>=0.2`, ties to Issue 13) | Done — see CHANGELOG.md | PRD §15 FR17 |
| FR18 | Add CI (GitHub Actions) running the test suite on push/PR | Done — see CHANGELOG.md | PRD §15 FR18 |
| FR19 | Split `errors.py` (306 lines) into a package by error domain — low priority | Done — see CHANGELOG.md | PRD §15 FR19 |
| FR20 | Rename `jsonpath_template`→`jsonpath`, drop `output="jsonpath"`, unconditional precedence over `output` | Done | PRD §15 FR20, SPEC §8 FR20 |
| FR21 | Distinguishable error codes: timeout/connectivity, authentication vs. authorization, kubectl-level argument failures | Done — see CHANGELOG.md | PRD §15 FR21, SPEC §8 FR21 |
| FR22 | Emit multiline tool output (`data.output`) as a JSON array of lines instead of an escaped string — the escaped form defeats grep/line-addressable reads on spilled-over tool-output files | Done — see CHANGELOG.md | PRD §15 FR22, SPEC §8 FR22 |
| FR23 | Translate discovery's raw Kubernetes API verbs into this project's MCP verb vocabulary (`apply` is structurally unavailable on every CRD today, not just daemonsets); add `daemonsets` to the core table | Done — see CHANGELOG.md (commit `73bef0d`) | PRD §15 FR23, SPEC §8 FR23 |
| FR24 | Multi-resource operations: add `names: list[str]` param to `k_get`/`k_delete`/`k_patch`/`k_describe` to support batch operations on multiple resource instances at once | Done — shipped `fbf7782`; dispatch-path tests closed via Issue 56 (2026-10-04) | PRD §15 FR24, SPEC §8 FR24 |
| FR25 | Add RBAC resources (`serviceaccounts`, `roles`, `clusterroles`, `rolebindings`, `clusterrolebindings`) and scheduling/resource management resources (`priorityclasses`, `poddisruptionbudgets`, `limitranges`, `resourcequotas`, `horizontalpodautoscalers`, `validatingwebhookconfigurations`, `mutatingwebhookconfigurations`) to the core table | Done — see CHANGELOG.md | PRD §15 FR25, SPEC §8 FR25 |

**FR23 — broadened 2026-09-28 from its original narrow framing, shipped same day.** Originally
submitted as "add `daemonsets` to the core table" (valid — `k_apply` on a DaemonSet manifest
failed with `{"error":"verb_unsupported","resource":"daemonsets","verb":"apply"}`, and
`daemonsets` was genuinely absent from `data/core_resources.toml`). Validated against source and
found the same root cause was more general than the original framing: `resolution/discovery.py`
parsed kubectl's live VERBS column **verbatim** into `ResourceMeta.verbs`, but that field's own
docstring (`resolution/models.py`) documents it as "subset of {get, logs, apply, patch, delete,
exec}" — this project's tool-verb vocabulary, not raw Kubernetes API verbs. `"apply"` is not a
literal API verb (kubectl apply is a client-side create-or-patch composite), so it could never
appear in kubectl's reported VERBS column — meaning `k_apply` was structurally broken for every
CRD resolved via discovery, not just DaemonSets, regardless of the caller's actual RBAC. This
contradicted PRD §12's "CRUD coverage of an arbitrary CRD" success criterion, corrected there
to state the write-path status accurately. Full root cause, the verb-translation design, and the
daemonsets table-row fix are written up in PRD.md §15 FR23 / SPEC.md §8 FR23 (not duplicated here
per this file's pointer-only convention).

**Residual gap, found 2026-09-28 during Done-status verification:** SPEC §8 FR23's test list and
PRD §15 FR23's Success Criteria item 4 both call for a dedicated test proving `daemonsets`
resolves via the static core table (not discovery) and that `k_apply`/`k_patch`/`k_delete`
succeed against it. No such test exists — `grep -r daemonset tests/` matches only an unrelated
pre-existing discovery fixture line (`tests/fixtures/kubectl_outputs/api_resources_wide.txt:19`).
The general verb-translation logic is tested (`test_discovery.py` gained cases), and the suite's
passing count went up in the same commit, which is likely why this specific promised test's
absence wasn't caught — the count increase looked like coverage for the whole FR. Add one test
(`test_tools_apply.py` or `test_core_table.py`) asserting `daemonsets` resolves without touching
the discovery cache/mock kubectl call, matching the existing `deployments`/`statefulsets`
assertion pattern, before considering this FR's Definition-of-Done item 1 fully satisfied.

**FR24 — multi-resource operations proposal, 2026-10-01; shipped `fbf7782` the same day, tests
closed via Issue 56 (2026-10-04).** Status was stale in this file and `SPEC.md` §8 for three days
while `PRD.md`/`CHANGELOG.md` already said Done — the three-way inconsistency itself is item 1 of
Issue 60. Original proposal text follows, kept for rationale:

Current kubectl-equivalent tools take a single `name` parameter (`k_get name=...`, `k_delete name=...`,
`k_patch name=...`, `k_describe name=...`). `kubectl` itself supports multiple names in a single invocation
(`kubectl get pods pod1 pod2 pod3`, `kubectl delete pods pod1 pod2 pod3`, etc.), but the MCP
tools do not expose this pattern. Proposed fix: add a `names: list[str] | None` parameter to the
4 tools above. Validation constraint: exactly one of `name` or `names` must be set; `names` is
incompatible with `all_namespaces` (for `k_get`) and `label_selector` (for `k_delete`).
Implementation: the kubectl args list is extended with all names from the list instead of a
single name. PRD §15 FR24 / SPEC §8 FR24 contains the full design rationale and implementation
plan.

---

## OPEN (not yet fixed)

Issues 56-61 were fixed 2026-10-04 and moved to the FIXED table (full root cause/fix/tests/
verification history in `CHANGELOG.md`). Issues 63 (`dry_run` enum, found while implementing
Issue 59) and 64 (stale-gitignored-`uv.lock` release hazard — the docs requirement this session's
release exposed) were filed and fixed the same day per the user's decisions and recorded directly
in FIXED/CHANGELOG.

| # | Title | File(s) |
|---|---|---|
| 62 | 22 functions exceed the 35-line guideline (`handle_get` 194, `handle_apply` 148, `register_tools` 146, `handle_patch` 142, `_parse_api_resources` 122); the `name`/`names` exactly-one-of chain is duplicated across 4 tools and the `dry_run` enum check now exists in 3 | `tools/*.py`, `server.py`, `resolution/discovery.py` |

**Issue 62 detail:** Measured 2026-10-04 by AST pass over `src/` (line span per function): 22
functions > 35 lines. Largest: `handle_get` (194), `handle_apply` (148), `register_tools` (146 —
Issue 56's extraction moved `main()`'s registration body here; `main()` itself is now ~20 lines),
`handle_patch` (142), `_parse_api_resources` (122). No class exceeds 300 lines. The dominant
pattern is long fail-fast guard chains of identical
`return envelope(errors.x(...), context, "k_<tool>", success=False)` blocks — the
`name`/`names` exactly-one-of chain is verbatim-duplicated in all four FR24 tools, and the
`_VALID_DRY_RUNS` check now exists three times (`apply.py`, `patch.py`, `delete.py` — local
constants chosen deliberately per the Issue 59 pattern, with consolidation deferred here).
Fix direction: shared validators + extract-then-compose; pure refactor, no behavior change.
**Deferred per user decision 2026-10-04** — belongs in its own PIV cycle, not stacked onto
behavior-fix sessions.

---

## TODO

Actionable checklists for the OPEN issue and Proposed FRs above. These are distilled from the
full plans, not a second copy of them — see the cross-referenced section for rationale and
exact code shape before implementing.

**Issue 51** — `jsonpath_template`→`jsonpath` field-name miss (fixed, see FIXED table):
- [x] `errors/core.py`: `out["jsonpath_template"] = template` → `out["jsonpath"] = template`;
      fix the docstring's stale `jsonpath_template` reference
- [x] `test_tools_get.py`/`test_tools_apply.py`/`test_tools_patch.py`: assert the response's
      `jsonpath` key (not `jsonpath_template`) carries the template string
- [x] Grep `errors/` for any other `_template` remnants before closing

**FR21** — distinguishable error codes (done, see CHANGELOG.md):
- [x] `errors/core.py`: add the 7 new error codes + `_base()`-shaped helpers
- [x] `kubectl/runner.py`: route `TimeoutExpired`/`FileNotFoundError`/`OSError` through the new
      helpers instead of ad hoc dicts (closes the missing-`context` gap)
- [x] `kubectl/errors.py`: reorder/extend `map_kubectl_error()`'s pattern list per the 8-step
      ordering (authentication check before forbidden, new unreachable/invalid-argument/
      object-invalid checks before the `kubectl_failure` fallback)
- [x] `test_runner.py` (3 assertions) and `test_kubectl_errors.py` (1 changed + 4 new cases)
      updated per SPEC.md §8 FR21
- [x] PRD.md §7: add the 7 new error codes and backfill the pre-existing `kubectl_failure` gap

**FR22** — `data.output`/`logs` as JSON array of lines (done, see CHANGELOG.md):
- [x] `resolution/grep_filter.py`: `filter_lines()` takes/returns `list[str]` instead of a
      joined `str`
- [x] `tools/get.py`, `tools/describe.py`: emit `result["stdout"].splitlines()` instead of the
      raw `stdout` string under `output`
- [x] `output/bounding.py`'s `bound_logs()`: emit `list[str]` under `logs` instead of
      `"\n".join(...)` / raw `stdout`
- [x] `tools/logs.py`: pass the already-split `bounded["logs"]` straight into `filter_lines()`
- [x] Update `test_grep_filter.py`, `test_bounding.py`, `test_tools_get.py`,
      `test_tools_describe.py`, `test_tools_logs.py` — all currently assert string output

**Issue 56** — restore the coverage gate (fixed 2026-10-04, see CHANGELOG.md):
- [x] Extract `register_tools(app, access_level, discovery_cache, allow_namespaces)` from
      `main()`; `main()` becomes parse → logging → build app → `register_tools(...)` → `app.run()`
- [x] Fake-app registration test: collect `@app.tool(name=...)` per level, assert 6/9/12 and the
      exact name sets (readonly/readwrite/admin)
- [x] Wrapper drive-through test: call each registered wrapper function from the fake app with
      `run_kubectl_checked` mocked, assert it reaches `_dispatch()` (closes DoD item 1's "the
      registered `@app.tool` wrapper" wording structurally for every tool)
- [x] FR24 tests — validation branches ×4 tools: neither `name` nor `names` → error; both set →
      error; exactly-one happy path
- [x] FR24 tests — args construction: `names=["a","b"]` → both appear in kubectl args position,
      for `get`/`delete`/`patch`/`describe`
- [x] FR24 tests — incompatibility: `names` + `all_namespaces` (get), `names` + `label_selector`
      (delete) → fail-fast before subprocess
- [x] FR24 tests — `prune()` recursion on List items (multi-resource responses prune each item)
- [x] Re-run `pytest -q --cov=src --cov-report=term-missing --cov-fail-under=90`; record actual
      count + coverage in the CHANGELOG entry (DoD item 6); do not lower the threshold

**Issue 57** — kubeconfig through the runner seam (fixed 2026-10-04, see CHANGELOG.md):
- [x] Read `kubectl/runner.py` arg composition; decide how `config get-contexts` (a local read)
      threads through it without a spurious `--context` (or accept the nominal-context convention)
- [x] Replace `subprocess.run` with `run_kubectl`/`run_kubectl_checked`; timeout preserved
- [x] Errors via `errors` helpers (`kubectl_failure`/`kubectl_timeout`/`kubectl_not_installed`)
      with `context`; drop the prose-in-`error` dicts
- [x] Update `tests/unit/test_kubeconfig.py` (and `test_tools_contexts.py` if its mock path moves)
- [x] `grep -rn subprocess src/k8s_mcp` → only `kubectl/runner.py`

**Issue 58** — ad-hoc error dicts → helpers (fixed 2026-10-04, see CHANGELOG.md):
- [x] `errors/core.py`: new `unexpected_output(context, raw, ...)` code + helper (and an
      ambiguous-from-stderr variant if `ambiguous_resource`'s `candidates`/`hint` shape can't fit)
- [x] `tools/get.py:182` → helper call; `kubectl/errors.py:39-44,:67-72` → helpers
- [x] PRD §7 error-code list: add new code(s) (doc-part-of-done)
- [x] Update `test_tools_get.py`, `test_kubectl_errors.py`; assert helper-shaped responses
      (`context` present, code not prose)

**Issue 59** — validate `k_patch`'s `type` (fixed 2026-10-04, see CHANGELOG.md):
- [x] Fail-fast enum check (`strategic`/`merge`/`json`) alongside existing param validations
- [x] Route the rejection through a common `errors` helper (pick existing or add
      `invalid_patch_type`; if new → PRD §7)
- [x] Tests: each bad value rejected before `run_kubectl_checked`; each good value passes through
      to args unchanged

**Issue 60** — docs-drift sweep (fixed 2026-10-04, see CHANGELOG.md — 13th spot found
during the sweep: a fourth placeholder hash):
- [x] FR24 status: this file's row + proposal block + `SPEC.md:869` → "Done" AFTER Issue 56
      lands (until then "shipped-untested, see Issue 56")
- [x] FR11 "(open correction)" note here; PRD §6 prompts paragraph signature → `(cluster,
      issue_description)` per `server.py:223`
- [x] FIXED row 53 file list → `resolution/annotation_selector.py` (verify `git show --stat
      37d7dee`)
- [x] FR25 shortnames in CHANGELOG:125/127 + SPEC:940-948 → match `core_resources.toml`
      (`limits`; webhooks none) (verify `f2b4772`)
- [x] CHANGELOG "Committed `TODO`." placeholders (`:145`, `:159`) → real hashes via `git log`
- [x] CHANGELOG entry for `3d98645` (kubectl env-var passing) — backfill with issue number
- [x] PRD §12 status paragraph: add date; PRD §13: check off `k_describe`/`k_exec` questions
      (verify `_SHIP_*` flags + §12 count include both); align `SPEC.md` §7 wording; refresh
      `server.py:42-44` comments
- [x] FR21 TODO checklist "6" → "7" error codes (this file, `:131`)
- [x] README: `ruff check src` → `ruff check src tests`; intro tool bullets → 12-tool surface;
      CHANGELOG:94 "module-level" → function-local (verify in `resolution/discovery.py`)

**Issue 61** — startup fail-fast vs spec amendment: **resolved 2026-10-04** — user chose
amend-SPEC; `SPEC.md` §4 rewritten to the shipped lazy reality (see CHANGELOG.md).

**Issue 62** — oversized functions / duplicated validators: **deferred per user decision
2026-10-04**; its own future PIV cycle.

---

## FIXED

Full detail for each of the following (root cause, fix, tests, verification, commit hash) is
in `CHANGELOG.md`.

| # | Title | File(s) |
|---|---|---|
| 64 | v0.3.0 released with `pyproject` bumped but gitignored `uv.lock` left at 0.2.0 — next `uv run` re-resolves online, hangs behind the socks proxy, presents as MCP "Request timed out"; DoD item 8 + SPEC §9 codify `uv lock` before the release commit and `uv run --frozen` for MCP hosts | `KNOWN_ISSUES.md`, `SPEC.md`, `README.md`, `CHANGELOG.md` |
| 63 | `dry_run` outside `none`/`client`/`server` passed verbatim into kubectl `--dry-run` on `k_apply`/`k_patch`/`k_delete` — no fail-fast enum check (found while implementing Issue 59) | `tools/apply.py`, `tools/patch.py`, `tools/delete.py`, `errors/core.py`, `errors/__init__.py`, `server.py`, `PRD.md` §6/§7, `test_tools_apply.py`, `test_tools_patch.py`, `test_tools_delete.py`, `test_errors.py` |
| 61 | SPEC §4's startup sequence never matched the shipped lazy behavior — spec amended to code reality (docs-only, user decision 2026-10-04) | `SPEC.md`, `server.py` (docstring) |
| 60 | Docs-drift cluster (12 spots + 1 found during the sweep) from the 2026-10-04 review — stale FR24 status (three-way inconsistent), stale Issue-43 notes, wrong Issue-53 file list, stale FR25 shortnames, 4 unfilled placeholder hashes, missing CHANGELOG entry for `3d98645`, PRD §12 undated / §13 unchecked, "6 vs 7 error codes", README staleness | `SPEC.md`, `PRD.md`, `README.md`, `CHANGELOG.md`, `KNOWN_ISSUES.md`, `server.py`, `tools/describe.py` |
| 59 | `k_patch`'s `type` validated nowhere — arbitrary string reached kubectl `--type`; fail-fast enum via new `invalid_patch_type` | `tools/patch.py`, `errors/core.py`, `errors/__init__.py`, `PRD.md` §6/§7, `test_tools_patch.py`, `test_errors.py` |
| 58 | Three ad-hoc error dicts violated SPEC §6's helpers-only rule — new `unexpected_output` code + `kubectl_access_denied`/`kubectl_ambiguous_resource` stderr-variant helpers | `tools/get.py`, `kubectl/errors.py`, `errors/core.py`, `errors/__init__.py`, `PRD.md` §7, `test_tools_get.py`, `test_errors.py` |
| 57 | `contexts/kubeconfig.py` bypassed the runner's single-subprocess seam and returned prose-in-`error` dicts off the §7 contract | `contexts/kubeconfig.py`, `tools/contexts.py`, `test_kubeconfig.py`, `test_tools_contexts.py` |
| 56 | Coverage gate red at HEAD (89.58% < 90%): FR24 shipped with zero tests (DoD item 1) + every `@app.tool` wrapper nested inside `main()` unreachable from tests (`server.py` 23%) — extracted `register_tools()`, 27 tests added, gate restored at 94.69% without lowering it | `server.py`, `tests/unit/test_server.py`, `test_tools_get.py`, `test_tools_patch.py`, `test_tools_delete.py`, `test_tools_describe.py`, `test_pruning.py` |
| 55 | `bound_logs()`'s docstring still describes its `logs` return value as a string — stale since FR22 changed it to `list[str]` (renumbered from 53) | `output/bounding.py` |
| 54 | Code-quality audit: test-suite lint debt + no coverage gate + version drift + Issue 53 number de-conflicted (2026-10-02) | `tests/unit/*`, `.github/workflows/test.yml`, `pyproject.toml`, `KNOWN_ISSUES.md` |
| 53 | `annotation_selector` fails to match annotations with dots in key names (e.g., `prometheus.io/scrape=true`) | `resolution/annotation_selector.py` (file list corrected per Issue 60 item 4 — was `resolution/models.py`, `tools/get.py`; `git show --stat 37d7dee` never touched either) |
| 52 | `k_get_helm_release` fails to decode any real Helm v3 release — missing a second base64 layer before gzip | `tools/get_helm_release.py`, `test_tools_get_helm_release.py` |
| 51 | FR20's `jsonpath_template`→`jsonpath` rename missed `invalid_jsonpath_template()`'s response field and docstring | `errors/core.py`, `test_tools_get.py`, `test_tools_apply.py`, `test_tools_patch.py` |
| 49 | FR16's `mypy` config disabled its own error codes, silently defeating `disallow_untyped_defs`/`warn_return_any` | `pyproject.toml`, `resolution/resolver.py`, `tools/*.py`, `resolution/core_table.py`, `tools/list_resources.py`, `server.py` |
| 41 | No test exercised `server.py`'s `_dispatch()` path | `tests/unit/test_server.py`, `server.py` |
| 40 | `k_auth_can_i` crashed on every real call (two bugs, three commits) | `tools/auth_can_i.py`, `server.py` |
| 39 | `k_get_helm_release` returned `values` fully unredacted | `access.py` |
| 38 | Resolved `group`-qualification discarded before reaching kubectl | `tools/get.py`, `delete.py`, `describe.py`, `patch.py` |
| 37 | `pyyaml` undeclared transitive dependency | `pyproject.toml` |
| 36 | `apply.py` swallowed YAML parse errors via bare `except Exception` | `tools/apply.py` |
| 35 | `prune()` had no `Secret`-specific redaction | `output/pruning.py` |
| 1 | `bound_get_names({})` returns `[{}]` instead of `[]` | `output/bounding.py` |
| 2 | `prune()` did not strip `last-applied-configuration` annotation | `output/pruning.py` |
| 3 | `matches()` operator precedence bug | `resolution/models.py` |
| 4 | `_fuzzy_suggest()` crashes on mixed `list[str \| ResourceMeta]` | `resolution/resolver.py` |
| 5 | kubectl non-zero exit codes never detected | `kubectl/runner.py`, `errors.py` |
| 6 | `k_apply` skipped R8 pre-execution validation | `tools/apply.py` |
| 7 | `k_describe`/`k_exec` bypassed namespace allowlist and audit logging | `server.py` |
| 8 | `k_describe`/`k_exec` called `subprocess` directly | `tools/describe.py`, `exec_.py` |
| 10 | `k_logs` never applied its documented default `tail=100` | `tools/logs.py` |
| 11 | `access.py`'s `_VERB_MAP` omitted `"describe"` | `access.py` |
| 12 | `kubectl/errors.py`: duplicated `"unauthorized"` check | `kubectl/errors.py` |
| 13 | Server failed to start — FastMCP API mismatch + `**kwargs` schema incompatibility | `server.py` |
| 14 | `k_apply`'s validation errors assembled ad hoc, not via `errors.py` | `tools/apply.py`, `errors.py` |
| 9 | Discovery cache parser mis-mapped columns | `resolution/discovery.py` |
| 15 | `k_get` crashed with `'bytes' object has no attribute 'read'` | `resolution/core_table.py` |
| 16 | `k_get` with `all_namespaces=true` rejected `pods` | `resolution/resolver.py`, `tools/get.py` |
| 17 | `k_exec`'s `-c <container>` flag placed after `--` | `tools/exec_.py` |
| 18 | `k_list_contexts` silently swallowed kubeconfig-read errors | `tools/contexts.py` |
| 19 | `annotation_selector` always returned zero matches combined with `name` | `tools/get.py` |
| 20 | `output=wide` was byte-identical to default output | `output/bounding.py`, `tools/get.py` |
| 21 | `annotation_selector` + `output=wide` silently dropped the selector | `tools/get.py` |
| 22 | Chronic PRD/SPEC doc drift (9 recurrences) — see Documentation Process below | `PRD.md`, `SPEC.md` |
| 23 | `k_apply`/`k_patch`'s `output=json`/`yaml` non-functional | `tools/apply.py`, `patch.py` |
| 24 | `events` required per-context discovery on every call | `data/core_resources.toml` |
| 25 | Discovery cache never refreshed on cold/TTL-expired cache | `resolution/resolver.py` |
| 26 | A passing test asserted Issue 25's broken behavior as correct | `tests/unit/test_resolver.py` |
| 27 | `k_list_resources` returned an empty list against a live cluster | `resolution/discovery.py` |
| 28 | `_parse_api_resources()` regex expected bracketed verbs/categories | `resolution/discovery.py` |
| 29 | `jsonpath_template` gave a cryptic error for nested-brace syntax | `errors.py`, `resolution/jsonpath_validation.py` |
| 30 | `k_logs` completely broken (`unknown shorthand flag: 'o'`) | `tools/logs.py` |
| 31 | `k_delete` completely broken (kubectl rejects `-o json`) | `tools/delete.py` |
| 32 | `discovery.py` built a redundant `-o json -o wide` invocation | `resolution/discovery.py` |
| 33 | `--kubeconfig` silently ignored by every tool except `k_list_contexts` | `kubectl/runner.py`, `cli.py`, `server.py`, `contexts/kubeconfig.py` |
| 34 | `list_kubeconfig_contexts()` didn't merge multi-path contexts | `contexts/kubeconfig.py` |
| 42 | `map_kubectl_error()` conflated "object not found" with "resource type unresolvable" — both returned `unknown_resource` | `errors.py`, `kubectl/errors.py`, `test_kubectl_errors.py`, `test_errors.py` |
| 43 | `cilium_troubleshoot_connectivity` prompt used `(namespace, pod)` signature, missing `context=` in all calls | `prompts.py`, `server.py`, `utils.py`, `test_prompts.py`, `test_utils.py` |
| 44 | `cilium_troubleshoot_connectivity`'s PromQL snippets had unquoted label-matcher values | `prompts.py`, `test_prompts.py` |
| 45 | `map_kubectl_error()`'s NotFound branch used `detail` instead of `raw_stderr` | `errors.py`, `kubectl/errors.py`, `test_errors.py`, `test_kubectl_errors.py` |
| 46 | `k_exec` never passes `-n <namespace>` to kubectl — every call runs against the context's default namespace | `tools/exec_.py`, `test_tools_exec.py` |
| 47 | `kubectl/runner.py` — the single seam that enforces R3's mandatory `--context` — had zero direct test coverage | `tests/unit/test_runner.py` |
| 48 | `k_apply`/`k_patch`/`k_delete`/`k_logs`'s tests never asserted `-n <namespace>` reaches kubectl args — latent test gap | `tests/unit/test_tools_apply.py`, `test_tools_patch.py`, `test_tools_delete.py`, `test_tools_logs.py`, `test_tools_get_helm_release.py` |
| 50 | `.gitignore`'s `kubeconfig.*` pattern excluded `src/k8s_mcp/contexts/kubeconfig.py` from every commit since the initial commit — published repo never actually importable | `.gitignore`, `src/k8s_mcp/contexts/kubeconfig.py` |

**Issue 22 note:** unlike the others above, Issue 22 recurred 9 times before being addressed
structurally rather than patched once — see `CHANGELOG.md`'s "Documentation Process" section
for the full recurrence history and the resulting **Definition of Done** checklist (top of this
file), which is the actual fix and remains a live process rule, not closed history.
