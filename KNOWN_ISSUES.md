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
| FR11 | Built-in MCP prompts (ArgoCD/Cilium status) | Done — see Issue 43 (open correction) | PRD §15 FR11, SPEC §8 FR11 |
| FR12 | `k_get_helm_release` | Done — see Issue 39 (resolved) | PRD §15 FR12, SPEC §8 FR12 |
| FR13 | `k_auth_can_i` | Done — see Issue 40 (resolved) | PRD §15 FR13, SPEC §8 FR13 |
| FR14 | `grep` — text-filtering for `k_logs`/`k_describe`/`k_get output=wide` | Proposed, plan ready | PRD §15 FR14, SPEC §8 FR14 |
| FR15 | Typing/naming consistency cleanup (`auth_can_i.py`'s `discovery_cache`, `k_logs`'s tail default) | Proposed, plan ready | PRD §15 FR15 |
| FR16 | Add `mypy` + `ruff` (lint/type-check tooling) | Proposed, plan ready | PRD §15 FR16 |
| FR17 | Pin `fastmcp` to a tested version range (currently unbounded `>=0.2`, ties to Issue 13) | Proposed, plan ready | PRD §15 FR17 |
| FR18 | Add CI (GitHub Actions) running the test suite on push/PR | Proposed, plan ready | PRD §15 FR18 |
| FR19 | Split `errors.py` (306 lines) into a package by error domain — low priority | Proposed, plan ready | PRD §15 FR19 |

---

## OPEN (not yet fixed)

---

## FIXED

Full detail for each of the following (root cause, fix, tests, verification, commit hash) is
in `CHANGELOG.md`.

| # | Title | File(s) |
|---|---|---|
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

**Issue 22 note:** unlike the others above, Issue 22 recurred 9 times before being addressed
structurally rather than patched once — see `CHANGELOG.md`'s "Documentation Process" section
for the full recurrence history and the resulting **Definition of Done** checklist (top of this
file), which is the actual fix and remains a live process rule, not closed history.
