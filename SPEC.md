# SPEC: k8s-minimal-mcp — Implementation Specification

**Status:** Draft
**Derived from:** PRD.md v0.2.0
**Scope:** High-level implementation shape — module layout, data flow, and build guidelines. Not a task breakdown.

This document resolves PRD §14's open language question in favor of **Python + FastMCP**, since Python modules were requested. It does not re-litigate the design rules (R1–R12) — those are binding; this spec only maps them onto code structure.

---

## 1. Runtime & Dependencies

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Type hints (`X \| Y`), `tomllib`, match statements — useful for verb dispatch and error-contract shaping. |
| MCP framework | `fastmcp` | Decorator-based tool registration; supports conditional registration needed for R7's access-level filtering. |
| kubectl invocation | `subprocess` (stdlib) | R11 mandates shelling out, not a client library. No extra dependency. |
| Data validation | `pydantic` v2 | Tool input/output schemas, error contract shapes (§7), core-table row schema. |
| Config | `tomllib` (read) + CLI args via `argparse` | Core resource table and startup flags (access level, namespace allowlist). |
| Testing | `pytest` + `pytest-mock` | Subprocess calls must be mockable — never shell out in unit tests. |

No YAML/JSON schema library beyond what `pydantic` and stdlib `json` provide. No async runtime needed unless FastMCP requires it for transport — kubectl calls are synchronous subprocess calls; if FastMCP's transport is async, wrap subprocess calls with `asyncio.to_thread`.

---

## 2. Module Layout

```
k8s-minimal-mcp/
├── pyproject.toml
├── PRD.md
├── SPEC.md
├── src/
│   └── k8s_mcp/
│       ├── __init__.py
│       ├── server.py              # entrypoint: FastMCP app, startup flags, tool registration (R7)
│       ├── cli.py                 # argparse: --access-level, --allow-namespaces
│       │
│       ├── tools/                 # one module per verb — thin, delegates to core/
│       │   ├── __init__.py
│       │   ├── get.py             # k_get
│       │   ├── describe.py        # k_describe (pending PRD §13 — implement behind flag)
│       │   ├── logs.py            # k_logs
│       │   ├── apply.py           # k_apply
│       │   ├── patch.py           # k_patch
│       │   ├── delete.py          # k_delete
│       │   ├── exec_.py           # k_exec (trailing underscore: `exec` is a builtin)
│       │   └── contexts.py        # k_list_contexts
│       │
│       ├── resolution/            # R2, R5, R6 — resource name -> GVK
│       │   ├── __init__.py
│       │   ├── core_table.py      # loads static core table (data file, not inline per PRD §14)
│       │   ├── discovery.py       # per-context `kubectl api-resources` cache, TTL (R5)
│       │   ├── resolver.py        # resolve(context, resource_name) per PRD §7 pseudocode
│       │   └── models.py          # ResourceMeta: canonical name, shortnames, kind, group/version, namespaced, verbs
│       │
│       ├── kubectl/               # R11 — subprocess boundary, isolated for mockability
│       │   ├── __init__.py
│       │   ├── runner.py          # run(context, args) -> CompletedProcess; timeout, error capture
│       │   └── errors.py          # maps kubectl stderr/exit codes -> internal error codes (§7)
│       │
│       ├── contexts/              # kubeconfig handling
│       │   ├── __init__.py
│       │   └── kubeconfig.py      # enumerate contexts via kubectl's own default resolution (no --kubeconfig flag, PRD §11)
│       │
│       ├── output/                # R4, R9, R10 — response shaping, applied uniformly at the boundary
│       │   ├── __init__.py
│       │   ├── pruning.py         # R9: strip managedFields/annotations/uid/generation/resourceVersion; status retention rules
│       │   ├── bounding.py        # R10: tail/name-only/truncation defaults + R4 self-reporting
│       │   └── envelope.py        # wraps every tool response: context echo (R3), reduction-applied metadata
│       │
│       ├── errors.py              # shared error-response contract (§7): ambiguous_resource, unknown_resource,
│       │                          # verb_unsupported, namespace_invalid, unknown_context, access_denied
│       │
│       ├── access.py              # R7: access-level -> allowed verb set; registration-time filter, not per-call check
│       │
│       └── data/
│           └── core_resources.toml # R2 core table, version-controlled static data (PRD §14), NOT inline code
│
├── tests/
│   ├── unit/
│   │   ├── test_resolver.py       # R2/R6 resolution logic, ambiguous-match cases
│   │   ├── test_pruning.py        # R9 field stripping, status-retention allowlist
│   │   ├── test_bounding.py       # R10 defaults + R4 reporting shape
│   │   ├── test_access.py         # R7 registration filtering per level
│   │   └── test_errors.py         # §7 error contract shape for each code
│   ├── integration/
│   │   └── test_tools_against_kind.py  # optional: real kubectl against a kind/minikube cluster
│   └── fixtures/
│       └── kubectl_outputs/       # captured `kubectl -o json` samples for mocked runner tests
│
└── scripts/
    └── gen_core_table.py          # optional helper: regenerate core_resources.toml from a live cluster's api-resources
```

### Rationale for boundaries

- **`resolution/` is isolated from `tools/`** so R2/R5/R6 logic (the hardest part — ambiguity, caching, fallback) is unit-testable without invoking kubectl or MCP at all.
- **`kubectl/runner.py` is the single subprocess boundary.** Every tool goes through it. This is what R11 asks for structurally, and it's the one seam every test mocks.
- **`output/` is a pipeline applied uniformly**, not per-tool logic (explicit PRD §14 instruction for R9). Every tool's raw kubectl JSON passes through `pruning.py` → `bounding.py` → `envelope.py` before returning to the model.
- **`access.py` filters at registration time in `server.py`**, not inside each tool function — R7 explicitly rejects per-call `dry_run`-style gating in favor of the model never seeing disallowed tools.
- **`errors.py` is shared**, not duplicated per tool, since the error contract shape (§7) is identical across all tools and must stay identical.

---

## 3. Data Flow (per call)

```
MCP call (context, resource, ...)
        │
        ▼
tools/<verb>.py                    — validates required params present, calls resolver
        │
        ▼
resolution/resolver.py             — R2/R6: core_table.py first, discovery.py fallback
        │                             on ambiguity/unknown -> raises typed error (errors.py)
        ▼
kubectl/runner.py                  — R11: subprocess exec, -o json, per-context
        │                             on kubectl failure -> kubectl/errors.py maps to §7 contract
        ▼
output/pruning.py -> bounding.py -> envelope.py   — R9, R10, R4, R3
        │
        ▼
MCP response (context echoed, reduction bounds reported, pruned JSON)
```

Pre-execution validation (R8 — namespaced/cluster-scoped check, verb-support check) happens in `resolver.py` using `ResourceMeta`, **before** `kubectl/runner.py` is invoked — this is what lets R8 fail fast with a structured error instead of parsing a kubectl stderr string.

---

## 4. Startup Sequence (`server.py`)

1. Parse CLI args (`cli.py`): `--access-level {readonly,readwrite,admin}` (default `readonly`), `--allow-namespaces` (comma list, empty = all). No `--kubeconfig` flag — see PRD §11.
2. Load core resource table (`resolution/core_table.py` reads `data/core_resources.toml`).
3. Enumerate kubeconfig contexts (`contexts/kubeconfig.py`, via kubectl's own default kubeconfig resolution) — fail fast if none found.
4. Compute allowed verb set from access level (`access.py`).
5. Register only the tools whose verb is in the allowed set (R7) — conditional `@app.tool` registration, not runtime rejection.
6. Start FastMCP server.

Namespace allowlist (§8) is enforced inside each mutating/read tool by checking the resolved `namespace` param against the allowlist before calling `kubectl/runner.py` — it's an orthogonal axis to access level, so it doesn't affect tool registration, only per-call validation (alongside R8).

---

## 5. Core Resource Table Format (`data/core_resources.toml`)

One entry per PRD R2's hardcoded list (pod, deployment, statefulset, ...). Example shape:

```toml
[[resource]]
canonical = "pods"
shortnames = ["po"]
kind = "Pod"
group = ""
version = "v1"
namespaced = true
verbs = ["get", "logs", "delete", "patch", "exec"]

[[resource]]
canonical = "networkpolicies"
shortnames = ["netpol"]
kind = "NetworkPolicy"
group = "networking.k8s.io"
version = "v1"
namespaced = true
verbs = ["get", "apply", "patch", "delete"]
```

Loaded once at startup into `list[ResourceMeta]`. Discovery-cache entries (`resolution/discovery.py`) populate the same `ResourceMeta` shape from `kubectl api-resources -o wide` output, per-context, TTL 5–10 min (PRD §7) with on-miss refresh-once-then-fail.

---

## 6. Guidelines for Implementation

- **Every tool function signature mirrors PRD §6's table exactly** — required/optional params as named there. Don't add convenience params not in the PRD; scope is fixed by the spec, not by implementation convenience.
- **No tool function calls `subprocess` directly.** Always through `kubectl/runner.py`. This is the enforcement point for R11 and the only thing integration tests need to swap for a fake.
- **No tool function does field pruning or truncation itself.** Always through `output/`. Keeps R9/R10 uniform per PRD §14 and avoids drift between tools.
- **`context` is threaded explicitly through every function call** in the chain above — never stored on a class instance, never module-level state. This is the code-level enforcement of R3 ("no session-scoped state").
- **Ambiguous resolution never guesses.** `resolver.py` returning multiple candidates is a normal, tested code path — not an exception path to be minimized away.
- **Error responses are constructed only via `errors.py` helpers** (e.g. `errors.ambiguous_resource(candidates, hint)`), never assembled ad hoc in a tool — guarantees the §7 shape stays identical everywhere.
- **`k_describe` and `k_exec` are implemented behind explicit conditionals** tied to the still-open PRD §13 questions — keep them isolated enough to delete or gate without touching other tools if the open questions resolve against shipping them.
- **`kubectl` subprocess calls set an explicit timeout** and capture stderr separately from stdout — required for `kubectl/errors.py` to map failures to §7 error codes rather than surfacing raw kubectl text.
- **Logging of mutating calls** (`apply`, `patch`, `delete`, `exec`) goes through a single logging call site in `server.py` or a thin `audit.py`, matching PRD §13's open "audit/logging sink" question — stub this now so it's one place to wire a real sink later, but don't over-build it (no log shipping, no structured sink selection) until that question resolves.

---

## 7. What This Spec Deliberately Leaves Open

Matching PRD §13, this spec does not resolve:

- Whether `k_describe` ships (module exists either way; registration is conditional).
- Whether `k_exec` ships at `admin` or is deferred further.
- Discovery cache refresh trigger (TTL-only vs. TTL+on-miss — spec assumes both per §7 pseudocode, but this is not locked).

Do not pre-decide these in code structure beyond what's needed to keep them cheaply reversible (i.e., conditional registration, not hardcoded tool lists).

---

## 8. Feature Requests / Improvements

Implementation shape for PRD §15's candidates. Not part of v1 scope — do not build until the corresponding PRD entry is accepted.

### FR1. `output=jsonpath` for `k_get`, `k_apply`, `k_patch` (PRD §15 FR1) ✅ DONE

Scope: `k_get`, `k_apply`, `k_patch`. `k_describe`/`k_logs` excluded — kubectl has no `-o`
flag for either. `k_delete` excluded — no realistic use case for jsonpath against an object
being deleted.

**Trigger.** All three tools keep a documented `"jsonpath"` value on their `output` param,
but the actual trigger for jsonpath mode is **presence of `jsonpath_template`** (truthy),
not `output == "jsonpath"` — passing the template alone is enough; the caller does not
also need to set `output="jsonpath"`. The one surviving validation case: `output ==
"jsonpath"` explicitly set with no `jsonpath_template` is still an error (`invalid_output`)
— catches the "asked for jsonpath but forgot the template" typo without requiring the
pairing in the common case.

- **`errors.py`:** add `ERROR_INVALID_OUTPUT = "invalid_output"` and a helper
  `invalid_output(context, output, *, detail=None)`. Shared by all three tools' fail-fast
  check — one helper, not three (R9-style DRY at the error-contract layer, same spirit as
  `invalid_manifest`). ✅
- **`tools/get.py`:** add `jsonpath_template: str | None = None` to `handle_get()`. At the
  top of the function, before `resolve()`: if `output == "jsonpath"` and `jsonpath_template`
  is falsy, return `envelope(invalid_output(...), context, "k_get", success=False)` (R8-style
  fail-fast — same pattern as `apply.py`'s manifest/kind checks). After building kubectl
  `args` (existing code unchanged): if `jsonpath_template` is truthy (regardless of
  `output`), call `run_kubectl_checked(context, args, output_format=f"jsonpath=
  {jsonpath_template}")`, skip `json.loads`/`prune()`/`bound_get_names()` entirely, and
  return `envelope({"data": result["stdout"], "jsonpath_template": jsonpath_template}, ...)`.
  The existing `None`/`json`/`yaml`/`wide` path is reached only when `jsonpath_template`
  is not set, and is otherwise untouched. ✅
- **`tools/apply.py`:** add `output: str | None = None`, `jsonpath_template: str | None =
  None` to `handle_apply()`. Same fail-fast check at the top of the function, before
  manifest parsing. After building `args` (`["apply", "-f", "-", ...]`): if
  `jsonpath_template` is truthy, call `run_kubectl_checked(context, args, stdin=manifest,
  output_format=f"jsonpath={jsonpath_template}")`, skip the `json.loads`/`prune()` step, and
  return `envelope({"data": result["stdout"], "dry_run": ..., "jsonpath_template":
  jsonpath_template}, ...)` — `dry_run` is still echoed exactly as in the non-jsonpath path.
  The existing json+prune branch is reached only when `jsonpath_template` is not set. ✅
- **`tools/patch.py`:** same shape as `apply.py` — add `output`, `jsonpath_template` params,
  identical fail-fast check, and an early branch (triggered by `jsonpath_template` truthy)
  after building `args` that calls `run_kubectl_checked(context, args, stdin=patch,
  output_format=f"jsonpath={jsonpath_template}")`, returning the raw string + echoed
  `dry_run`/`jsonpath_template`, bypassing `json.loads`/`prune()`. ✅
- **`kubectl/runner.py`: no change.** `run_kubectl`'s existing `output_format` parameter
  already does `base_args.extend(["-o", output_format])` — passing the single token
  `"jsonpath={.status.podIP}"` already produces the correct `-o jsonpath={.status.podIP}`
  invocation for `get`/`apply`/`patch` alike. (An earlier draft of this entry assumed
  `runner.py` needed extending for a dedicated `jsonpath` kwarg; verified during planning
  that it doesn't — R11's single `-o`-constructing site is unaffected.) ✅
- **`output/bounding.py`: no change.** The jsonpath passthrough lives in each tool module
  (`get.py`/`apply.py`/`patch.py`) as an early branch, not inside `apply_output_format()`,
  which currently assumes JSON-shaped input for its `wide`/`yaml` branches and would need
  to special-case a plain-string passthrough otherwise. ✅
- **`server.py`:** for each of the `k_get`, `k_apply`, `k_patch` wrapper functions — add
  `"jsonpath"` to the `output` enum in the tool description, and add `output`/
  `jsonpath_template` (whichever the tool doesn't already have) as new explicit typed
  parameters, per the Issue #13 fix (tool parameters are individually typed function
  signatures, not `**kwargs`) — same treatment as every other param on these wrappers. ✅
- **Tests:** ✅
  - `tests/unit/test_tools_get.py` — extend with a `TestHandleGetJsonpath` class:
    `jsonpath_template` alone (no `output` set) builds the correct `-o jsonpath=...` args,
    returns raw string `data`, echoes `jsonpath_template` (the auto-trigger case);
    `output="jsonpath"` + template gives the same result (explicit form still works);
    `output="jsonpath"` with no template fails with `invalid_output` before `resolve()`/
    `run_kubectl_checked` are ever called; jsonpath stdout that looks JSON-ish is passed
    through untouched (not run through `prune()`/`bound_get_names()`).
  - `tests/unit/test_tools_apply.py` — **new file** (no existing `apply.py` unit tests
    today); needs its own fixtures (a `ResourceMeta`, a minimal valid manifest string) plus
    a happy-path test (existing behavior unaffected) alongside the jsonpath cases above.
  - `tests/unit/test_tools_patch.py` — **new file** (same gap), mirroring the apply tests
    for `handle_patch()`.

### FR2. `annotation_selector` for `k_get` (PRD §15 FR2)

**Status: Done** — fixed single-resource fetch bug (`3d3b3d6`), added regression tests.

Note: a dedicated `k_events` tool was considered alongside this (see PRD §11's rejected-
alternatives table) and rejected — `k_get resource="events"` + `field_selector` already
covers the primary use case. The follow-up from that decision — adding `events` to the R2
core table so `resource="events"` resolves instantly instead of falling through to
per-context discovery — is now tracked separately as FR7, below. Small, separable change,
independent of this FR.

- **`errors.py`** — add `ERROR_INVALID_SELECTOR = "invalid_selector"` + helper
  `invalid_selector(context, selector, *, detail=None)` — distinct from `invalid_output`
  (FR1) because this is a malformed *query*, not a malformed *output request*.
- **New module** (pick one location, don't scatter selector-parsing logic —
  `resolution/annotation_selector.py` is the natural home since it's a query-parsing
  concern, not an output-shaping one): `parse_annotation_selector(selector: str) ->
  list[tuple[str, str, str]]` parses the `key=value` / `key!=value` / bare-`key` grammar
  from PRD FR2, raising/returning a parse error the caller turns into `invalid_selector`.
  `matches_annotation_selector(annotations: dict, terms) -> bool` applies parsed terms with
  AND semantics.
- **`tools/get.py`:** add `annotation_selector: str | None = None` to `handle_get()`. Parse
  it *before* `resolve()` (R8-style fail-fast, same placement as FR1's jsonpath check) — a
  malformed selector never reaches kubectl. When set: force the kubectl call to always
  fetch full JSON (never a `jsonpath`/`wide` `output_format` for the *fetch* itself —
  filtering needs full objects to inspect `metadata.annotations`), filter `data`/
  `data["items"]` by the parsed terms immediately after `json.loads`, record `{"matched":
  N, "total": M}`, *then* continue into the existing `prune()` →
  `bound_get_names()`/`apply_output_format()` pipeline on the filtered set unchanged.
  `_filtered` metadata merges into the same response dict as `_bound` (both are R4-style
  self-reporting; no reason for the two to diverge in shape).
- **Interaction with FR1:** `annotation_selector` + `jsonpath_template` together is a valid
  combination in principle (filter first, then jsonpath-project the filtered set) — but
  jsonpath is applied by kubectl's own `-o` flag *before* our client-side filter would ever
  see structured JSON (jsonpath already narrows kubectl's output to a possibly-non-JSON
  string). Decide at implementation time whether to reject this combination outright
  (simplest — one clear error) or evaluate jsonpath server-side against the already-filtered
  items in Python instead of via kubectl's `-o` flag when both are set. Flagging now so it
  isn't discovered mid-implementation.
- **Tests** — new cases in `tests/unit/test_tools_get.py`: valid selector narrows `items`
  correctly (equality/inequality/existence terms, comma-separated AND); malformed selector
  syntax fails via `invalid_selector` before `resolve()`/kubectl are ever called;
  `annotation_selector` forces a full JSON fetch even when `output=name`/`wide` was
  requested (assert the `output_format` passed to `run_kubectl_checked`); `_filtered`
  metadata present and accurate on both matching and non-matching cases.

### FR3. `k_list_resources` tool (PRD §15 FR3)

**Status: ✅ DONE** — new `tools/list_resources.py` with cache hit/miss paths, case-insensitive substring search (canonical/kind/group), `ResourceMeta` serialization, access level wiring (`readonly`), and server registration. 16 unit tests.

- **New file `tools/list_resources.py`:** `handle_list_resources(context, *, search=None,
  discovery_cache=None) -> dict[str, Any]`.
  - `resources = discovery_cache.get(context)`; if `None`, call
    `discovery_cache.refresh(context)` — the same two-step trigger `resolve()` already uses
    in `resolution/resolver.py`'s tier-2 branch, not a new discovery path. If `refresh()`
    returns an error dict, `return envelope(result, context, "k_list_resources",
    success=False)`.
  - If `discovery_cache` is `None` (shouldn't happen — `server.py` always constructs one via
    `_dispatch`'s existing plumbing — but every other tool module defends against it too):
    treat as an empty result rather than raising.
  - If `search` is set, filter `resources` by case-insensitive substring match against
    `canonical`, `kind`, and `group`. This needs its own predicate — `ResourceMeta.matches()`
    (`resolution/models.py`) is exact-match lookup for name resolution, not a substring
    search, so don't reuse it here; write a small dedicated filter function instead.
  - Serialize each `ResourceMeta` to a plain dict: `{"name": r.canonical, "shortnames":
    r.shortnames, "kind": r.kind, "api_version": r.api_version, "namespaced": r.namespaced,
    "verbs": r.verbs}` — reuses the existing `api_version` property rather than
    re-deriving group/version formatting.
  - Return `envelope({"resources": [...], "count": len(...)}, context, "k_list_resources",
    success=True)`.
- **`resolution/discovery.py` / `core_table.py`:** no change — reuse both read paths as-is
  (`DiscoveryCache.get`/`.refresh`; `load_core_table()` only if PRD FR3's open question
  resolves toward merging core-table entries in).
- **`access.py`:** add `"list_resources"` to `_VERB_MAP`'s `READONLY` frozenset (and by
  extension `READWRITE`/`ADMIN`, which both include the readonly set).
- **`server.py`:** register `k_list_resources` at `readonly`. This tool does **not** go
  through `_dispatch()`'s resource-resolution machinery (`resolve()`/`validate()`) the way
  `k_get`/`k_apply`/etc. do — it has no `resource` param to resolve — so wire it more like
  `k_list_contexts`'s direct call than like the verb-tools' `_dispatch(...)` pattern.
- **Tests** — new `tests/unit/test_tools_list_resources.py`:
  - cache-hit path: `discovery_cache.get()` returns data, `refresh()` never called.
  - cache-miss path: `get()` returns `None`, `refresh()` called once, its result used.
  - `refresh()` returning an error dict propagates as `success=False` without raising.
  - `search` filters correctly (substring, case-insensitive) against name/kind/group.
  - response shape matches `ResourceMeta` fields exactly (no extra/missing keys).

### FR4. Unit test coverage for `k_delete`, `k_describe`, `k_logs`, `k_exec`, `k_list_contexts` (PRD §15 FR4)

**Status: ✅ DONE** — 5 new test files (133 tests), 2 bug fixes applied:
- `exec_.py`: `-c` flag placement fixed (moved before `--`)
- `contexts.py`: error surfacing fixed (no longer silently returns empty list)

Two bug fixes are part of this FR's scope, both found while reading these modules to write
this spec — fix before writing the regression test, not after:

- **`tools/exec_.py`:** current code —
  ```python
  args = ["exec", pod, "--"]
  if container:
      args.extend(["-c", container])
  args.extend(command)
  ```
  places `-c <container>` after `--`, so kubectl never parses it as the container flag —
  it becomes part of the executed command instead. Fix:
  ```python
  args = ["exec", pod]
  if container:
      args.extend(["-c", container])
  args.append("--")
  args.extend(command)
  ```
- **`tools/contexts.py`:** `handle_list_contexts` currently does:
  ```python
  result = list_kubeconfig_contexts(kubeconfig_paths)
  if isinstance(result, dict) and "error" in result:
      return envelope_list_contexts([], context)
  ```
  discarding the error. Fix: surface it through the standard error contract instead of
  silently returning an empty list — e.g. `return envelope(result, context,
  "k_list_contexts", success=False)` (check `envelope_list_contexts`'s signature in
  `output/envelope.py` — it may need a `success`/error-passthrough parameter added, or this
  may need to call the plain `envelope()` helper instead of
  `envelope_list_contexts()` for the error case specifically, since the success-shape
  helper is presumably tailored to a `{"contexts": [...]}` body that doesn't fit an error dict).

Test files — each follows the `test_tools_apply.py`/`test_tools_patch.py` pattern already
in the repo (`ResourceMeta` fixture, `@patch` on `..tools.<module>.resolve` and
`..tools.<module>.run_kubectl_checked`, one test class per tool):

- **`tests/unit/test_tools_delete.py`:** `handle_delete` — `name` set → appended directly;
  `label_selector` set with no `name` → `-l <selector>` appended (the `elif` means only one
  of the two ever reaches `args`, confirm `name` wins when both are somehow set);
  `dry_run="server"`/`"client"` → `--dry-run <value>` appended, `dry_run="none"` (default)
  → no flag; kubectl stdout parses as JSON → `prune()` applied, response `data` is the
  pruned object; non-JSON stdout (or empty) → falls back to `{"message": result["stdout"]}`
  without raising; `resolve()` error, `validate()` error, and `run_kubectl_checked` error
  all propagate as `success=False` with the tool name `"k_delete"` in the envelope.
- **`tests/unit/test_tools_describe.py`:** `handle_describe` — args built as
  `["describe", resource_meta.canonical, name]` plus `["-n", namespace]` when set;
  `run_kubectl_checked` called with `output_format=None` (assert this explicitly — it's the
  detail that makes describe's plain-text output work at all); **assert `validate()` is
  called with verb `"get"`, not `"describe"`** (`describe.py:34`) — this is existing,
  intentional-looking behavior (describe piggybacks on the `get` verb-support check since
  there's no separate `"describe"` entry in `ResourceMeta.verbs`) but was never written down
  anywhere — name the test something like
  `test_validates_against_get_verb_not_describe` so the next reader isn't left guessing
  whether this is a bug; success shape is `{"output": result["stdout"]}`; `resolve()`/
  `validate()`/kubectl error passthrough.
- **`tests/unit/test_tools_logs.py`:** `handle_logs` — `tail=None` (default) → effective
  tail `100`, passed as `["--tail", "100"]`; explicit `tail=N` overrides; `container` → `-c`;
  `previous=True` → `--previous`; `since` → `--since <value>`; `bound_logs()` is called with
  the *effective* tail (not the raw possibly-`None` input) and its `_bound`/truncation
  metadata passes through into the envelope unchanged; `resolve()`/`validate()`/kubectl
  error passthrough (pods resource is always resolved via `resolve(context, "pods", ...)`,
  never the caller's `resource` — there is no such param on this tool, confirm the fixed
  `"pods"` resolve call rather than parameterizing it in the test).
- **`tests/unit/test_tools_exec.py`:** `handle_exec` — **write against the fixed arg
  order above**: `container` set → args are `["exec", pod, "-c", container, "--", *command]`;
  no container → `["exec", pod, "--", *command]`; `run_kubectl_checked` called with
  `output_format=None`; the two distinct error branches in `exec_.py:52-66` both need a
  case — `result.get("error") == "kubectl_failure"` maps to the `exec_failed(...)` shape
  (pod/namespace/command/stderr/exit_code fields), any *other* error dict (e.g. a Python-level
  exception from `run_kubectl`) passes through unchanged, not wrapped as `exec_failed`;
  success shape is `{"stdout", "stderr", "exit_code"}` pulled directly from the
  `KubectlResult` fields.
- **`tests/unit/test_tools_contexts.py`:** `handle_list_contexts` — **write against the
  fixed error-surfacing behavior above**: `list_kubeconfig_contexts()` returning an error
  dict propagates as a visible `success=False` error in the response, not a silently empty
  `{"contexts": []}`; `kubeconfig_paths=None` (the default) is normalized to `[]` before
  calling `list_kubeconfig_contexts`; happy path wraps the enumerated contexts via
  `envelope_list_contexts` — assert the exact shape that helper produces (check
  `output/envelope.py`) rather than assuming.

  **Superseded note:** the `kubeconfig_paths` parameter described in this FR4 entry (and in
  `list_kubeconfig_contexts(kubeconfig_paths)`'s signature above) was removed entirely —
  see PRD §11's rejected-alternatives entry and `KNOWN_ISSUES.md` Issues 33/34.
  `handle_list_contexts(context)` and `list_kubeconfig_contexts()` now both take no
  kubeconfig-path argument at all; resolution is left to kubectl's own default behavior.
  Left this FR4 text as-is otherwise since it's a historical record of what was actually
  built at the time, not a live spec.

No changes to `errors.py`/`output/` needed beyond what the two bug fixes require (likely
none — `envelope()` and `exec_failed()` already exist and cover both fixes).

### FR5. Fix `k_get`'s `output=wide` no-op (PRD §15 FR5)

**Status: Done** (`aaed71e`) — early branch in `get.py` calls kubectl with `-o wide`, returns raw text; removed dead `"wide"` branch from `bounding.py`.

- **`tools/get.py`:** add an early branch parallel to the existing `jsonpath_template`
  branch — when `output == "wide"` and `jsonpath_template` is not set (jsonpath takes
  precedence if somehow both are set, since it already narrows to a single value that a
  table format can't wrap around): call `run_kubectl_checked(context, args,
  output_format="wide")` using the exact same `args` already built (resource/name/
  namespace/selectors — unaffected by this change), skip `json.loads`/`prune()`/
  `apply_output_format()` entirely (kubectl's `-o wide` output is a plain-text table, not
  JSON), and return `envelope({"output": result["stdout"]}, context, "k_get",
  success=True)` — same key precedent as `k_describe`.
- **`output/bounding.py`:** remove `apply_output_format()`'s now-dead `"wide"` branch
  (currently lines 112-114, `if output_format == "wide": return bound_get_names(data)`) —
  once `get.py`'s early branch exists, this path is never reached from `handle_get()`;
  leaving it in place is unreachable dead code that still returns the old, wrong
  (identical-to-default) behavior if anything ever calls `apply_output_format()` directly
  (e.g. a test exercising the function in isolation, or a future caller).
- **`server.py`:** no signature change needed — `"wide"` is already a documented `output`
  enum value on `k_get`'s wrapper; only check whether the tool description's own wording
  implies parity with `name`/`json` and correct it if so.
- **Tests:**
  - `tests/unit/test_tools_get.py` — `output="wide"` → `run_kubectl_checked` called with
    `output_format="wide"` (not the default `"json"`); response is `{"output": <raw
    text>}`, untouched by `prune()`/`bound_get_names()`; `output="wide"` combined with
    `all_namespaces`/`label_selector`/`field_selector` still builds the same `args` as the
    `json`/default paths — only `output_format` differs.
  - `tests/unit/test_bounding.py` — check whether a test currently asserts
    `apply_output_format(data, "wide") == bound_get_names(data)` (that would be asserting
    exactly the bug this FR fixes) before deleting the `"wide"` branch; update or remove
    it, don't leave it passing against removed code.

### FR6. Fix `k_apply`/`k_patch`'s non-functional `output=json`/`yaml` (PRD §15 FR6)

**Status: ✅ DONE** — added `apply_output_format()` call in both tools' non-jsonpath success paths, explicit `invalid_output` rejection for `output="wide"`, 6 new tests (yaml/json/wide for each tool).

- **`tools/apply.py`:** in the non-jsonpath success path (currently lines 111-121), after
  `pruned = prune(data, kind=resource_meta.kind)`, add `pruned = apply_output_format(pruned,
  output)` before building the response dict. Import `apply_output_format` from `..output`
  (already imported there for other tools; `apply.py` currently only imports `prune,
  envelope` from `..output` — add it to that import). Since `apply_output_format(data,
  None)` returns `data` unchanged, this is a no-op when `output` is unset — zero behavior
  change for the default case.
- **`tools/patch.py`:** identical change, same line shape (currently lines 77-83).
- **Explicit decision needed on `output="wide"`:** `apply_output_format()` currently has no
  `"wide"` branch at all (removed by FR5) — it falls through to `return data` unchanged for
  any unrecognized `output_format` value, same as `None`. That means `output="wide"` on
  `k_apply`/`k_patch` would silently behave like `output=None`/`"json"` once this fix lands,
  which is arguably still "silently accepts and does nothing" for that one value — just
  no longer true for `json`/`yaml`. Decide: leave `wide` as a silent no-op (lowest effort,
  matches kubectl's own semantics where `-o wide` isn't a meaningful concept for
  `apply`/`patch` anyway), or add an explicit `invalid_output` rejection for
  `output="wide"` on these two tools specifically, mirroring the fail-fast pattern already
  used for `output="jsonpath"` with no template. Recommend the latter for consistency — an
  explicit error is more honest than a silent no-op, and this codebase has already
  established the fail-fast-on-nonsensical-combination pattern (FR2's `annotation_selector`
  + `jsonpath_template`/`output=wide` rejections) rather than defaulting into silent
  pass-through.
- **`server.py`:** no signature change needed — `output` already exists on both wrappers;
  only the tool descriptions' wording may need a one-line correction once the actual
  behavior is decided (does `json`/`yaml` work now; is `wide` explicitly rejected or a
  silent no-op).
- **Tests:**
  - `tests/unit/test_tools_apply.py` — `output="yaml"` on a successful apply → response
    `data` is `{"_yaml": <string>}`, not the raw pruned dict; `output="json"` → unchanged
    from current behavior (explicit test, not just relying on the default case); whatever
    `output="wide"` decision is made above gets its own explicit test rather than being
    left unspecified.
  - `tests/unit/test_tools_patch.py` — same three cases, mirrored for `handle_patch()`.

### FR7. Add `events` to the R2 core table (PRD §15 FR7)

**Status: ✅ DONE** — appended `[[resource]]` entry to `core_resources.toml` (`canonical="events"`, `shortnames=["ev"]`, `kind="Event"`, `verbs=["get"]`), added assertions in `test_core_table.py` and `test_resolver.py` (canonical, shortname, kind, namespaced, verbs resolution).

- **`src/k8s_mcp/data/core_resources.toml`:** append one `[[resource]]` entry (see PRD FR7
  for the exact fields — `canonical = "events"`, `shortnames = ["ev"]`, `kind = "Event"`,
  `group = ""`, `version = "v1"`, `namespaced = true`, `verbs = ["get"]`). Follow the file's
  existing entries as the formatting template (e.g. the `endpoints` entry immediately
  above it in the current file, which has the same single-verb `["get"]` shape).
- **No code change** — `resolution/core_table.py`'s loader reads every `[[resource]]` entry
  generically; adding a row requires no logic change, only the data file.
- **Tests:** `tests/unit/test_core_table.py` (existing file, added in the fix for a prior
  discovery-parser issue — see `KNOWN_ISSUES.md` Issue 15) already calls `load_core_table()`
  unmocked against the real `data/core_resources.toml` and asserts specific resources exist
  with correct metadata (`pods`, `deployments`, `services`) — add `events` as one more
  asserted resource in that same style: canonical name, `kind == "Event"`, `namespaced is
  True`, `verbs == ["get"]`. Also worth one assertion in `tests/unit/test_resolver.py` that
  `resolve(context, "events", discovery_cache=None)` succeeds (i.e. resolves from the core
  table alone, no discovery cache needed) — this is the actual behavior change being
  verified, not just that the TOML parses.
- **R6 collision check (do this before merging, not as a test):** confirm `events`/`ev`/
  `Event` don't collide with any existing core-table `canonical`/`shortnames`/`kind` —
  quick manual scan of the current 15 entries is sufficient, no tooling needed for a
  16-row table.

### FR8. Fail-fast validation for nested-brace `jsonpath_template` syntax (PRD §15 FR8)

**Status: Done**

- **`errors.py`:** added `ERROR_INVALID_JSONPATH_TEMPLATE = "invalid_jsonpath_template"` and
  a helper `invalid_jsonpath_template(context, template, *, detail=None)`, following the
  exact shape of `invalid_output`/`invalid_selector`.
- **New module `resolution/jsonpath_validation.py`** (colocated with
  `resolution/annotation_selector.py` as the natural home — both are "caller-supplied
  query/template syntax validation" concerns, not output-shaping ones): `check_nested_braces(template: str) -> str | None`. Scans the template
  left-to-right tracking brace depth (`{` increments, `}` decrements); if depth would ever
  exceed `1`, return a detail string explaining the correct syntax (bracket-list form or
  `{range}...{end}`); otherwise return `None`. Pure string logic — no kubectl, no resource
  awareness, trivially unit-testable in isolation.
- **`tools/get.py`:** right alongside the existing `output == "jsonpath" and not
  jsonpath_template` fail-fast check (before `resolve()`): if `jsonpath_template` is set,
  call `check_nested_braces(jsonpath_template)`; if it returns a non-`None` detail string,
  `return envelope(invalid_jsonpath_template(context, jsonpath_template, detail=detail),
  context, "k_get", success=False)`.
- **`tools/apply.py` / `tools/patch.py`:** identical check, same placement pattern FR1 used
  for these two tools (before manifest parsing / before `resolve()`).
- **`server.py`:** updated the `jsonpath_template` description text on all three wrapper
  functions (`get`, `apply`, `patch`) to mention the bracket-list syntax proactively, e.g.
  "...for multiple fields per item use `{.items[*]['field1','field2']}` or a
  `{range}...{end}` loop — nested `{...}` groups are not supported."
- **PRD §6:** updated `k_get`/`k_apply`/`k_patch`'s rows to mention the new `invalid_jsonpath_template` rejection.
- **Tests:**
  - New test module `tests/unit/test_jsonpath_validation.py` covering `check_nested_braces()` directly (10 tests): `{.field}` → valid (`None`); sibling blocks `{.a}{.b}` →
    valid; `{range .items[*]}{.a}{end}` → valid; `{.items[*].{a,b}}` → invalid (detail
    returned); a deeper nesting case → invalid.
  - `tests/unit/test_tools_get.py` / `test_tools_apply.py` / `test_tools_patch.py`: a
    nested-brace `jsonpath_template` → `invalid_jsonpath_template` error, `resolve()`/
    `run_kubectl_checked` never called (fail-fast, matching FR1's own test pattern); a
    valid multi-block template is NOT rejected (negative case, guards against the
    depth-check being over-eager).

### FR9. `k_get_secret_to_file` (PRD §15 FR9)

**Status: Not started.** The three "design decisions" flagged in PRD FR9 (path safety,
overwrite behavior, output format) need explicit answers before or during implementation —
this spec assumes a reasonable default for each so implementation isn't blocked, but flags
each as a decision, not a silent given.

- **`errors.py`:** add three new error codes/helpers, following the existing
  `invalid_output`/`invalid_selector`/`invalid_jsonpath_template` shape:
  - `ERROR_UNSAFE_PATH = "unsafe_path"` — `unsafe_path(context, path, *, detail=None)`.
  - `ERROR_FILE_EXISTS = "file_exists"` — `file_exists(context, path)`.
  - `ERROR_FILE_WRITE_FAILED = "file_write_failed"` — `file_write_failed(context, path, *, detail=None)`.
- **New module `tools/get_secret_to_file.py`:**
  ```python
  def handle_get_secret_to_file(
      context: str,
      name: str,
      namespace: str,
      dst_secret_file: str,
      *,
      overwrite: bool = False,
      discovery_cache: DiscoveryCache | None = None,
  ) -> dict[str, Any]:
  ```
  - **Path-safety check (fail-fast, before anything else):** reject relative paths outright
    (`os.path.isabs(dst_secret_file)` must be `True`) — this is the minimum bar regardless
    of which stance PRD FR9's open question resolves to; a relative path's target depends on
    the server process's CWD, which the caller has no visibility into, so it's never
    meaningfully safe. Whether to additionally restrict to a configured allowlist directory
    is the open question — implement the absolute-path check unconditionally, add a
    directory allowlist only if that question resolves toward requiring one.
  - **Overwrite check (fail-fast):** if `dst_secret_file` exists on disk and `overwrite` is
    not `True`, return `file_exists`. Default `overwrite=False` matches PRD FR9's proposed
    safer-by-default posture.
  - Resolve `"secrets"` via `resolve()` (always in the core table) and run the standard R8
    `validate()` namespace check — Secrets are namespaced, so this is unconditional, not
    optional like `k_get`'s `all_namespaces` path.
  - Fetch: `run_kubectl_checked(context, ["get", "secret", name, "-n", namespace], output_format="json")`
    (this is a plain, explicit `-o json` fetch of one object — no need for `k_get`'s
    name/output-format machinery here, this tool only ever fetches one Secret one way).
  - Decode: `base64.b64decode(v).decode("utf-8", errors="replace")` for each key in the
    fetched object's `.data` (note: `errors="replace"` rather than raising, since some
    Secret values are legitimately binary/non-UTF-8 — decide at implementation time whether
    non-UTF-8 values should instead be written base64-encoded-as-is with a per-key flag, or
    whether `errors="replace"` silently corrupting binary content is acceptable given this
    tool's primary use case is credential/config strings, not arbitrary binary blobs).
  - Write: `json.dumps({key: decoded_value, ...})` to `dst_secret_file`, then
    `os.chmod(dst_secret_file, 0o600)` immediately after creation (write via a mode that
    never exposes a wider-permission window — e.g. open with `os.open(path, os.O_WRONLY |
    os.O_CREAT | os.O_TRUNC, 0o600)` rather than plain `open()` + a separate `chmod()`
    call, so the file is never briefly world-readable between creation and the permission
    fix).
  - On any filesystem error (permission denied, missing parent directory): catch and return
    `file_write_failed(context, dst_secret_file, detail=str(e))`, not a raw traceback.
  - Success response: `envelope({"written_to": dst_secret_file, "keys": list(decoded.keys())},
    context, "k_get_secret_to_file", success=True)` — the `keys` list is the *only* place
    any information about the Secret's shape appears in the response; no key ever maps to
    a value anywhere in the returned dict.
- **`access.py`:** add `"get_secret_to_file"` to `_VERB_MAP`'s `ADMIN` tier only (not
  `READONLY`/`READWRITE`).
- **`server.py`:** register `k_get_secret_to_file` conditionally on `"get_secret_to_file" in
  allowed` (same pattern as `k_exec`'s admin-gated registration), with a tool description
  that explicitly states values never appear in the response — this is as much a
  documented contract for the calling model as an implementation detail.
- **Tests:** new `tests/unit/test_tools_get_secret_to_file.py`:
  - happy path: mocked kubectl JSON with a multi-key `.data` map → file written with
    correctly decoded values (assert against the actual file content, not just that a
    write call happened) → response contains `keys` but no value anywhere, `written_to`
    matches the input path.
  - relative `dst_secret_file` → `unsafe_path` error, kubectl never called.
  - `dst_secret_file` already exists, `overwrite` not set → `file_exists` error, kubectl
    never called; `overwrite=True` → succeeds and replaces the file.
  - file permissions: assert the written file's mode is `0o600` (use `tmp_path` fixture,
    not a mocked filesystem, so real `os.stat()` can verify this).
  - filesystem write failure (e.g. point `dst_secret_file` at a non-existent parent
    directory) → `file_write_failed`, not an unhandled exception.
  - `resolve()`/`validate()`/`kubectl_failure` passthrough, matching every other tool's
    error-propagation tests.
  - **Negative test proving the actual security property:** assert that no test fixture's
    known secret value ever appears as a substring anywhere in the returned response dict
    (serialize the response and search for the plaintext value) — this is the property the
    whole tool exists for, so it deserves its own explicit assertion, not just "the response
    happens not to include a `data` key."
