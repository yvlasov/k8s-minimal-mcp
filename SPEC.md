# SPEC: k8s-minimal-mcp — Implementation Specification

**Status:** Draft
**Derived from:** PRD.md v0.2.0
**Scope:** High-level implementation shape — module layout, data flow, and build guidelines. Not a task breakdown.

This document resolves PRD §14's open language question in favor of **Python + FastMCP**, since Python modules were requested. It does not re-litigate the design rules (R1–R12) — those are binding; this spec only maps them onto code structure.

Shipped-feature history and fix verification detail live in `CHANGELOG.md`, not here.

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
| Manifest parsing | `PyYAML` (`yaml.safe_load`) | `k_apply`/`k_patch` accept YAML manifests as a fallback when JSON parsing fails. Declared explicitly in `pyproject.toml`'s `dependencies` (see `CHANGELOG.md` Issue 37 — it was previously an undeclared transitive dependency). |

No JSON schema library beyond `pydantic` and stdlib `json`. No async runtime needed unless FastMCP requires it for transport — kubectl calls are synchronous subprocess calls; if FastMCP's transport is async, wrap subprocess calls with `asyncio.to_thread`.

---

## 2. Module Layout

```
k8s-minimal-mcp/
├── pyproject.toml
├── PRD.md
├── SPEC.md
├── CHANGELOG.md
├── KNOWN_ISSUES.md
├── src/
│   └── k8s_mcp/
│       ├── __init__.py
│       ├── server.py              # entrypoint: FastMCP app, startup flags, tool registration (R7)
│       ├── cli.py                 # argparse: --access-level, --allow-namespaces
│       │
│       ├── tools/                 # one module per verb — thin, delegates to core/
│       │   ├── __init__.py
│       │   ├── get.py             # k_get
│       │   ├── describe.py        # k_describe
│       │   ├── logs.py            # k_logs
│       │   ├── apply.py           # k_apply
│       │   ├── patch.py           # k_patch
│       │   ├── delete.py          # k_delete
│       │   ├── exec_.py           # k_exec (trailing underscore: `exec` is a builtin)
│       │   ├── contexts.py        # k_list_contexts
│       │   ├── list_resources.py  # k_list_resources (FR3)
│       │   ├── get_secret_to_file.py  # k_get_secret_to_file (FR9, admin-only, named R1 exception)
│       │   ├── get_helm_release.py    # k_get_helm_release (FR12, admin-only, named R1 exception)
│       │   └── auth_can_i.py          # k_auth_can_i (FR13, readonly)
│       │
│       ├── resolution/            # R2, R5, R6 — resource name -> GVK
│       │   ├── __init__.py
│       │   ├── core_table.py      # loads static core table (data file, not inline per PRD §14)
│       │   ├── discovery.py       # per-context `kubectl api-resources` cache, TTL (R5)
│       │   ├── resolver.py        # resolve(context, resource_name) per PRD §7 pseudocode
│       │   ├── models.py          # ResourceMeta: canonical name, shortnames, kind, group/version, namespaced, verbs
│       │   ├── annotation_selector.py  # FR2: parse/match annotation_selector query grammar
│       │   ├── jsonpath_validation.py  # FR8: nested-brace jsonpath syntax guard
│       │   └── grep_filter.py          # FR14: compile_grep_pattern()/filter_lines() for k_logs/k_describe/k_get
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
│       │   ├── pruning.py         # R9: strip managedFields/annotations/uid/generation/resourceVersion; Secret redaction; status retention rules
│       │   ├── bounding.py        # R10: tail/name-only/truncation defaults + R4 self-reporting
│       │   └── envelope.py        # wraps every tool response: context echo (R3), reduction-applied metadata
│       │
│       ├── errors/                # shared error-response contract (§7) — split into a package by
│       │   │                      # domain (FR19); errors/__init__.py re-exports every name so
│       │   │                      # `from ..errors import X` call sites are unchanged
│       │   ├── __init__.py        # re-exports core.py + files.py + helm.py's public names
│       │   ├── core.py            # ambiguous_resource, unknown_resource, object_not_found, verb_unsupported,
│       │   │                      # namespace_invalid, unknown_context, access_denied, kubectl_failure,
│       │   │                      # exec_failed, invalid_manifest, invalid_output, invalid_selector,
│       │   │                      # discovery_failure, invalid_jsonpath_template, invalid_grep_pattern
│       │   ├── files.py           # unsafe_path, file_exists, file_write_failed, file_read_failed (FR9/FR10)
│       │   └── helm.py            # helm_release_not_found, helm_release_decode_failed (FR12)
│       │
│       ├── access.py              # R7: access-level -> allowed verb set; registration-time filter, not per-call check
│       │
│       ├── prompts.py             # FR11: MCP prompts (ArgoCD/Cilium status guidance) — registered unconditionally, not gated by access level
│       ├── utils.py               # extract_named_entity() — free-text entity extraction (added for FR11's cilium_troubleshoot_connectivity, Issue 43 fix)
│       │
│       └── data/
│           └── core_resources.toml # R2 core table, version-controlled static data (PRD §14), NOT inline code
│
├── tests/
│   ├── unit/
│   │   ├── test_resolver.py       # R2/R6 resolution logic, ambiguous-match cases
│   │   ├── test_pruning.py        # R9 field stripping, status-retention allowlist, Secret redaction
│   │   ├── test_bounding.py       # R10 defaults + R4 reporting shape
│   │   ├── test_access.py         # R7 registration filtering per level
│   │   ├── test_errors.py         # §7 error contract shape for each code
│   │   ├── test_prompts.py        # FR11: exact resource=/field-path string assertions per prompt
│   │   ├── test_utils.py          # extract_named_entity() pattern coverage
│   │   ├── test_grep_filter.py    # FR14: compile_grep_pattern()/filter_lines() coverage
│   │   ├── test_tools_get_helm_release.py  # FR12: decode-chain, revision-selection, redaction-gap coverage
│   │   ├── test_tools_auth_can_i.py   # FR13: exit-code mapping, --as/--as-group ordering, --list parsing
│   │   ├── test_server.py             # _dispatch() smoke tests, every registered tool x every access level, using real handlers (only resolve/run_kubectl mocked)
│   │   └── test_runner.py             # kubectl/runner.py: --context/-o/stdin/timeout construction, real function body exercised, only subprocess.run mocked (Issue 47)
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
6. Register MCP prompts (FR11, `prompts.py`) unconditionally, via `@app.prompt(...)` — not gated by access level, since a prompt returns only guidance text; the tool calls it recommends still pass the normal gate when actually issued.
7. Start FastMCP server.

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
- **Passing `namespace` into `validate()` (R8) is not the same as passing it to kubectl** — each tool module must independently append `-n <namespace>` (or the ad hoc equivalent for a hand-built kubectl invocation) to its own `args`. `validate()` only performs the pre-execution namespaced/cluster-scoped check; it has no effect on the constructed command. This is not hypothetical: `k_exec` accepted, validated, and even echoed `namespace` in every error path, but never appended it to `args` — every call silently ran against the context's default namespace instead of the caller's, undetected because the existing tests asserted the resulting `args` list *without* `-n` as correct (see `CHANGELOG.md` Issue 46). When adding or reviewing a namespaced tool, grep `src/k8s_mcp/tools/*.py` for `"-n"` and confirm the new/changed tool is in that list.
- **Ambiguous resolution never guesses.** `resolver.py` returning multiple candidates is a normal, tested code path — not an exception path to be minimized away.
- **Every handler's tests must include at least one call through `_dispatch()`** (or the registered `@app.tool`/`@app.prompt` wrapper), not only direct calls to `handle_<tool>(...)`. `_dispatch()` injects `discovery_cache` (and, for mutating verbs, audit logging / namespace-allowlist checks) via `**kwargs` into every handler call — a handler whose signature doesn't accept what `_dispatch()` sends crashes on every real invocation, and a test suite that only calls the handler directly will never catch it (see `CHANGELOG.md` Issue 40/41). `tests/unit/test_server.py` is the smoke test that closes this gap structurally.
- **Tools build kubectl's resource argument from `resource_meta.fully_qualified_name`, never bare `.canonical`.** `fully_qualified_name` collapses to plain `canonical` when `group == ""` (the common case, zero behavior change), but includes `.group` when set — the only way a resolved group-qualification (R6's escape hatch) survives into the kubectl command instead of being silently discarded (see `CHANGELOG.md` Issue 38).
- **Error responses are constructed only via `errors.py` helpers** (e.g. `errors.ambiguous_resource(candidates, hint)`), never assembled ad hoc in a tool — guarantees the §7 shape stays identical everywhere.
- **`kubectl` subprocess calls set an explicit timeout** and capture stderr separately from stdout — required for `kubectl/errors.py` to map failures to §7 error codes rather than surfacing raw kubectl text.
- **Logging of mutating calls** (`apply`, `patch`, `delete`, `exec`) goes through a single logging call site in `server.py` — matching PRD §13's open "audit/logging sink" question; stub this now so it's one place to wire a real sink later, but don't over-build it until that question resolves.
- **Doc updates are part of "done," not a follow-up.** SPEC §2's Module Layout tree, PRD §6's Tool Specification table, and PRD §12's tool-count paragraph must be updated in the same change that ships a new tool/param — see `KNOWN_ISSUES.md`'s Definition of Done checklist (added after this drifted nine times — `CHANGELOG.md`'s "Documentation Process" section has the history).
- **Do not widen `disable_error_code` in `[tool.mypy]` to suppress a new failure.** Fix the annotation or narrow the type instead; a suppressed code category defeats the tool for every future file, not just the one that triggered it (see `KNOWN_ISSUES.md` Issue 49).

---

## 7. What This Spec Deliberately Leaves Open

Matching PRD §13, this spec does not resolve:

- Whether `k_describe` ships (module exists either way; registration is conditional).
- Whether `k_exec` ships at `admin` or is deferred further.
- Discovery cache refresh trigger (TTL-only vs. TTL+on-miss — spec assumes both per §7 pseudocode, but this is not locked).

Do not pre-decide these in code structure beyond what's needed to keep them cheaply reversible (i.e., conditional registration, not hardcoded tool lists).

---

## 8. Feature Requests / Improvements

Implementation shape for PRD §15's candidates. All listed below are shipped — status/verification history lives in `CHANGELOG.md`.

### FR1. `output=jsonpath` for `k_get`, `k_apply`, `k_patch`

Scope: `k_get`, `k_apply`, `k_patch`. `k_describe`/`k_logs` excluded — kubectl has no `-o`
flag for either. `k_delete` excluded — no realistic use case for jsonpath against an object
being deleted.

**Trigger.** All three tools keep a documented `"jsonpath"` value on their `output` param,
but the actual trigger for jsonpath mode is **presence of `jsonpath_template`** (truthy),
not `output == "jsonpath"` — passing the template alone is enough. The one surviving
validation case: `output == "jsonpath"` explicitly set with no `jsonpath_template` is still
an error (`invalid_output`).

- **`errors.py`:** `ERROR_INVALID_OUTPUT = "invalid_output"` + `invalid_output(context, output,
  *, detail=None)`. Shared by all three tools' fail-fast check.
- **`tools/get.py`:** `jsonpath_template: str | None = None` on `handle_get()`. Fail-fast if
  `output == "jsonpath"` and `jsonpath_template` falsy, before `resolve()`. If
  `jsonpath_template` truthy: `run_kubectl_checked(context, args, output_format=f"jsonpath=
  {jsonpath_template}")`, skip `json.loads`/`prune()`/`bound_get_names()`, return
  `{"data": result["stdout"], "jsonpath_template": jsonpath_template}`.
- **`tools/apply.py` / `tools/patch.py`:** same shape — `output`, `jsonpath_template` params,
  identical fail-fast check, early branch after building `args` returning the raw string plus
  echoed `dry_run`/`jsonpath_template`, bypassing `json.loads`/`prune()`.
- **`kubectl/runner.py`:** no change — the existing `output_format` parameter's
  `base_args.extend(["-o", output_format])` already produces the correct invocation for the
  single token `"jsonpath={.status.podIP}"`.
- **`output/bounding.py`:** no change — the jsonpath passthrough lives in each tool module as
  an early branch, not inside `apply_output_format()`.
- **`server.py`:** `"jsonpath"` added to the `output` enum in the tool description on all
  three wrappers; `output`/`jsonpath_template` as explicit typed parameters.

**Superseded by FR20:** `jsonpath_template` is renamed to `jsonpath`, `"jsonpath"` is dropped
from `output`'s documented enum, and the trigger condition changes from "template truthy,
unless `output` says otherwise" to "template truthy, unconditionally, `output` fully ignored."
This section stands as the as-originally-shipped record; implement from FR20 below, not this
section, for any future work in this area.

### FR2. `annotation_selector` for `k_get`

Note: a dedicated `k_events` tool was considered alongside this (PRD §11) and rejected —
`k_get resource="events"` + `field_selector` already covers the primary use case. The follow-up
from that decision (adding `events` to the R2 core table) is FR7.

- **`errors.py`** — `ERROR_INVALID_SELECTOR = "invalid_selector"` + `invalid_selector(context,
  selector, *, detail=None)` — distinct from `invalid_output` (malformed *query*, not malformed
  *output request*).
- **`resolution/annotation_selector.py`:** `parse_annotation_selector(selector: str) ->
  list[tuple[str, str, str]]` parses `key=value` / `key!=value` / bare-`key` grammar.
  `matches_annotation_selector(annotations: dict, terms) -> bool` applies parsed terms with
  AND semantics.
- **`tools/get.py`:** `annotation_selector: str | None = None` on `handle_get()`. Parsed
  before `resolve()` (fail-fast). When set: force a full `-o json` fetch (never
  `jsonpath`/`wide`), filter `data`/`data["items"]` by the parsed terms after `json.loads`,
  record `{"matched": N, "total": M}` as `_filtered`, then continue into the normal
  `prune()` → bounding pipeline on the filtered set.
- **Interaction with FR1:** `annotation_selector` + `jsonpath_template`/`output=wide` is
  rejected outright (`invalid_selector`) — jsonpath/wide narrow kubectl's own output before our
  client-side filter would ever see structured JSON.

### FR3. `k_list_resources` tool

- **`tools/list_resources.py`:** `handle_list_resources(context, *, search=None,
  discovery_cache=None) -> dict[str, Any]`.
  - `resources = discovery_cache.get(context)`; if `None`, call `discovery_cache.refresh(context)`
    — the same two-step trigger `resolve()` already uses in tier-2. If `refresh()` returns an
    error dict, propagate as `success=False`.
  - `search` filters by case-insensitive substring match against `canonical`/`kind`/`group` —
    a dedicated filter function, not `ResourceMeta.matches()` (that's exact-match lookup for
    name resolution, not substring search).
  - Serializes each `ResourceMeta`: `{"name": r.canonical, "shortnames": r.shortnames, "kind":
    r.kind, "api_version": r.api_version, "namespaced": r.namespaced, "verbs": r.verbs}`.
- **`access.py`:** `"list_resources"` in `READONLY`'s `_VERB_MAP` (and by extension
  readwrite/admin).
- **`server.py`:** registered at `readonly`, wired more like `k_list_contexts`'s direct call
  than the verb-tools' `_dispatch(...)` pattern — no `resource` param to resolve.

### FR4. Unit test coverage for `k_delete`, `k_describe`, `k_logs`, `k_exec`, `k_list_contexts`

Two bug fixes were part of this FR's scope (found while reading these modules to scope the
tests, fixed before writing the corresponding regression test — see `CHANGELOG.md` Issues 17/18):

- **`tools/exec_.py`:** `-c <container>` moved to before `--` in the arg list (was placed
  after, so kubectl never parsed it as its own flag).
- **`tools/contexts.py`:** `handle_list_contexts` now surfaces a `list_kubeconfig_contexts()`
  error via the standard error contract instead of silently returning an empty list.

Test files follow the `test_tools_apply.py`/`test_tools_patch.py` pattern (a `ResourceMeta`
fixture, `@patch` on `..tools.<module>.resolve` and `..tools.<module>.run_kubectl_checked`, one
test class per tool):

- **`test_tools_delete.py`:** `name` vs `label_selector` branch (`elif` — `name` wins);
  `dry_run` flag; JSON parse+prune success; non-JSON fallback to `{"message": ...}`;
  `resolve()`/`validate()`/kubectl error passthrough.
- **`test_tools_describe.py`:** args `["describe", resource_meta.canonical, name]` + `["-n",
  namespace]`; `run_kubectl_checked` called with `output_format=None`; `validate()` called
  with verb `"get"`, not `"describe"` (intentional — describe piggybacks on the `get`
  verb-support check, no separate `"describe"` entry in `ResourceMeta.verbs`); success shape
  `{"output": result["stdout"]}`.
- **`test_tools_logs.py`:** default `tail=100`; explicit `tail` overrides; `container`/
  `previous`/`since` flags; `bound_logs()` called with the *effective* tail; fixed
  `resolve(context, "pods", ...)` call (no `resource` param on this tool).
- **`test_tools_exec.py`:** written against the fixed arg order; `output_format=None`; the
  `exec_failed` vs. generic `kubectl_failure` branch; success shape `{"stdout", "stderr",
  "exit_code"}`.
- **`test_tools_contexts.py`:** written against the fixed error-surfacing behavior; happy path
  via `envelope_list_contexts`. (`kubeconfig_paths` no longer exists as a parameter — see
  `CHANGELOG.md` Issues 33/34.)

### FR5. Fix `k_get`'s `output=wide` no-op

- **`tools/get.py`:** early branch parallel to the `jsonpath_template` branch — `output ==
  "wide"` (and `jsonpath_template` not set) calls `run_kubectl_checked(context, args,
  output_format="wide")` with the same `args` already built, skips
  `json.loads`/`prune()`/`apply_output_format()`, returns `{"output": result["stdout"]}` —
  same key precedent as `k_describe`.
- **`output/bounding.py`:** removed the now-dead `"wide"` branch from `apply_output_format()`.
- **`server.py`:** no signature change needed — `"wide"` was already a documented enum value.

### FR6. Fix `k_apply`/`k_patch`'s non-functional `output=json`/`yaml`

- **`tools/apply.py` / `tools/patch.py`:** in the non-jsonpath success path, after `prune()`,
  `pruned = apply_output_format(pruned, output)` before building the response dict — a no-op
  when `output` is unset (`apply_output_format(data, None)` returns `data` unchanged).
- **`output="wide"` decision:** explicit `invalid_output` rejection on both tools, rather than
  a silent no-op — consistent with the fail-fast-on-nonsensical-combination pattern FR2 already
  established.

### FR7. Add `events` to the R2 core table

```toml
[[resource]]
canonical = "events"
shortnames = ["ev"]
kind = "Event"
group = ""
version = "v1"
namespaced = true
verbs = ["get"]
```

`verbs = ["get"]` only, matching the `endpoints` entry's pattern — no code change, `core_table.py`'s
loader reads every `[[resource]]` entry generically.

### FR8. Fail-fast validation for nested-brace `jsonpath_template` syntax

- **`errors.py`:** `ERROR_INVALID_JSONPATH_TEMPLATE = "invalid_jsonpath_template"` +
  `invalid_jsonpath_template(context, template, *, detail=None)`.
- **`resolution/jsonpath_validation.py`:** `check_nested_braces(template: str) -> str | None`.
  Scans left-to-right tracking brace depth (`{` increments, `}` decrements); depth exceeding
  `1` returns a detail string explaining bracket-list/`{range}...{end}` syntax; otherwise
  `None`. Pure string logic, no kubectl/resource awareness.
- **`tools/get.py` / `apply.py` / `patch.py`:** check placed alongside the existing
  `output == "jsonpath"` fail-fast, before `resolve()`.
- **`server.py`:** `jsonpath_template` description text updated on all three wrappers to
  proactively mention the bracket-list syntax.

**Unaffected by FR20's rename:** `check_nested_braces()` takes a plain string and has no
parameter-name awareness — only the call sites feeding it (now reading from `jsonpath` instead
of `jsonpath_template`) change.

### FR9. `k_get_secret_to_file`

The three "design decisions" flagged in PRD FR9 were resolved before implementation: absolute
path only (admin-only gate is sufficient, no directory allowlist); output format one JSON file
`{"data": {...}, "base64_keys": [...]}`; non-UTF-8 values written as-is with per-key
base64-passthrough (lossless).

- **`errors.py`:** `unsafe_path(context, path, *, detail=None)`, `file_exists(context, path)`,
  `file_write_failed(context, path, *, detail=None)`.
- **`tools/get_secret_to_file.py`:**
  ```python
  def handle_get_secret_to_file(
      context: str, name: str, namespace: str, dst_secret_file: str,
      *, overwrite: bool = False, discovery_cache: DiscoveryCache | None = None,
  ) -> dict[str, Any]:
  ```
  - Fail-fast: `os.path.isabs(dst_secret_file)` must be `True` → `unsafe_path` otherwise.
  - Fail-fast: exists and `overwrite` not `True` → `file_exists`.
  - Resolve `"secrets"`, standard R8 namespace `validate()` (Secrets always namespaced).
  - Fetch: `run_kubectl_checked(context, ["get", "secret", name, "-n", namespace],
    output_format="json")`.
  - Decode: `base64.b64decode(v, validate=True).decode("utf-8")` per key. On
    `binascii.Error`/`UnicodeDecodeError`: write the original value as-is, add the key to
    `base64_keys`.
  - Write: `os.open(dst_secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)` — never
    plain `open()` + separate `chmod()`, so the file is never briefly world-readable.
  - Filesystem error → `file_write_failed(context, dst_secret_file, detail=str(e))`.
  - Success: `{"written_to": dst_secret_file, "keys": list(decoded.keys())}` — `keys` is the
    only place any Secret shape info appears; no value anywhere in the response.
- **`access.py`:** `"get_secret_to_file"` in `_VERB_MAP`'s `ADMIN` tier only.
- **`server.py`:** registered conditionally on admin access, same pattern as `k_exec`; tool
  description states values never appear in the response.

### FR10. `src_file` for `k_apply`

Current `handle_apply()` always required `manifest: str`, used in two places
(`_parse_manifest(manifest)` for R8 `kind` validation, and `stdin=manifest` for the actual
apply) — both operate on the string content, not its source, which is what makes the change
minimal.

- **`errors.py`:** `file_read_failed(context, path, *, detail=None)`, mirroring
  `file_write_failed`. Reuses the existing `unsafe_path()` helper.
- **`tools/apply.py`:**
  ```python
  def handle_apply(
      context: str, manifest: str | None = None, *, src_file: str | None = None,
      namespace: str | None = None, dry_run: str = "none", output: str | None = None,
      jsonpath_template: str | None = None, discovery_cache: DiscoveryCache | None = None,
  ) -> dict[str, Any]:
  ```
  At the top: `(manifest is None) == (src_file is None)` (neither or both) → `invalid_manifest`.
  If `src_file` set: absolute-path check → `unsafe_path`; read it → `file_read_failed` on
  `OSError`. Every subsequent reference to `manifest` in the function body becomes
  `manifest_content` — a rename, not a logic change.
- **`server.py`:** `manifest` becomes optional, `src_file` added to the `apply()` wrapper and
  threaded through `_dispatch(...)`; tool description documents the mutual-exclusivity.

**Related, resolved via Issue 35:** `output/pruning.py`'s `prune()` had no `Secret`-specific
handling — `k_get`/`k_apply`/`k_patch`/`k_delete` all returned a Secret's full `.data` map
verbatim. Now: `.data`/`.stringData` → `{"redacted_keys": [...]}` when `kind == "Secret"`.

### FR11. Built-in MCP prompts for ArgoCD/Cilium status

- **`src/k8s_mcp/prompts.py`** — one function per prompt, each returning a single formatted
  `str` embedding the literal tool-call shape (exact `resource=` string, exact JSON field
  path), not a paraphrased description:
  - `argocd_app_health(name, namespace) -> str` — `k_get(resource="applications.argoproj.io",
    name=..., namespace=..., output="yaml")`, read `.status.sync.status`/
    `.status.health.status`/`.status.resources[]`; states the hierarchical resource tree, live
    git-vs-cluster diffs, and custom resource actions are **not** reachable this way (ArgoCD
    API server only).
  - `cilium_troubleshoot_connectivity(namespace, pod) -> str` — `k_get(resource=
    "ciliumendpoints", namespace=...)` → `k_get(resource="ciliumnetworkpolicies",
    namespace=...)` → `k_describe(resource="pods", name=pod, namespace=...)`; states Hubble
    flow/drop-verdict data is **not** reachable via any tool here (no backing API resource).
    Open correction pending — `KNOWN_ISSUES.md` Issue 43.
  - `rbac_effective_permissions(as_user, namespace) -> str` — points at `k_auth_can_i`.
- **`server.py`** — three `@app.prompt(name=..., description=...)` registrations, unconditional
  (outside every access-gating block) — a prompt performs no cluster access itself.
- Prompts do **not** validate `namespace` against `--allow-namespaces` — the functions take
  `namespace` only to interpolate into the guidance text; nothing checks it against the
  allowlist, since the prompt never touches the cluster.

### FR12. `k_get_helm_release`

- **`errors.py`** — `helm_release_not_found(context, release, namespace)`,
  `helm_release_decode_failed(context, release, namespace, *, stage, detail)` (`stage` ∈
  `{"base64", "gzip", "json"}`).
- **`tools/get_helm_release.py`:**
  - `resolve()`/`validate()` against `"secrets"` (identical R8 path to `get_secret_to_file.py`).
  - List candidates via Helm's own labels: `run_kubectl_checked(context, ["get", "secret",
    "-n", namespace, "-l", f"owner=helm,name={release}", "-o", "json"])`.
  - No matches → `helm_release_not_found`. Select by `revision` if given, else max
    `metadata.labels.version` (cast to int).
  - Decode chain on `.data.release`: `base64.b64decode` → `gzip.decompress` → `json.loads`,
    each stage's exception caught individually and mapped to `helm_release_decode_failed`.
  - Response: `{"release", "revision", "chart", "chart_version", "app_version", "status",
    "first_deployed", "last_deployed", "values"}`, plus `"manifest"` only when
    `include_manifest=True`.
- **`access.py`** — `"get_helm_release"` in the `ADMIN` tier's `_VERB_MAP` only (see Issue 39 —
  originally shipped in `READONLY`, moved to close an unredacted-`values` exposure).
- **`server.py`** — registered under the admin gate, same pattern as `k_get_secret_to_file`.

### FR13. `k_auth_can_i`

- **`tools/auth_can_i.py`:**
  - Single-check: build args in order `["auth", "can-i", verb, resource_with_name] +
    (["-n", namespace] if namespace) + (["--as", as_user] if as_user) + (["--as-group", g]
    for g in as_group or [])`; run via `run_kubectl` (**not** `_checked`); map exit code
    `{0: allowed, 1: denied}`, any other code → `kubectl_failure`.
  - List mode: same flag construction minus `verb`/`resource`, plus `--list`; dedicated parser
    (kubectl's `--list` table is a distinct format from the `api-resources -o wide` table) into
    `{resource: [verbs]}`.
  - `discovery_cache: DiscoveryCache | None = None` — required so `_dispatch()`'s unconditional
    kwarg injection doesn't crash the handler (see `CHANGELOG.md` Issue 40).
- **`access.py`** — `"auth_can_i"` in the `READONLY` tier's `_VERB_MAP`.
- **`server.py`** — registered under the readonly gate. `_dispatch()`'s first parameter is
  named `tool_verb` (not `verb`) specifically to avoid colliding with this tool's own `verb`
  domain argument (see `CHANGELOG.md` Issue 40).

### FR14. `grep` — server-side text-filtering for unstructured-text tool output — **Done**

**Status: Done** — implemented as planned below on `k_logs`, `k_describe`, and `k_get`
(`output="wide"` only). See PRD.md §15 FR14 and `CHANGELOG.md` for the verification record.

- **`errors.py`** — `ERROR_INVALID_GREP_PATTERN = "invalid_grep_pattern"` +
  `invalid_grep_pattern(context, pattern, *, detail=None)`, matching the
  `invalid_selector`/`invalid_jsonpath_template` shape exactly.
- **New shared helper, `resolution/grep_filter.py`** (colocated with
  `annotation_selector.py`/`jsonpath_validation.py` as the natural home — a third instance of
  "caller-supplied query syntax the server evaluates itself," not kubectl):
  `compile_grep_pattern(pattern: str, *, ignore_case: bool = False) -> re.Pattern | str` —
  returns a compiled pattern, or a detail string on `re.error` (mirrors
  `check_nested_braces()`'s return-`None`-or-detail-string convention). A second function,
  `filter_lines(text: str, compiled: re.Pattern) -> tuple[str, int, int]` — returns
  `(filtered_text, matched_count, total_count)`, applied identically by every caller below so
  `_filtered` reporting is byte-for-byte consistent across tools (same DRY reasoning
  `annotation_selector.py` already established for FR2).
- **`tools/logs.py`:** add `grep: str | None = None`, `grep_ignore_case: bool = False`.
  Fail-fast via `compile_grep_pattern()` before `resolve()` (same placement as every other
  fail-fast check in this project). After `bound_logs()` already applied `tail`/`limit_bytes`
  bounding (grep filters *within* that already-bounded window — see PRD §15 FR14's open
  question on this), apply `filter_lines()` to the `logs` string, add
  `_filtered: {"matched": N, "total": M}` alongside the existing `_bound` dict — two sibling
  metadata keys, not merged into one.
- **`tools/describe.py`:** add `grep`/`grep_ignore_case`. Same fail-fast check. Apply
  `filter_lines()` to the `{"output": ...}` string after the kubectl call, add `_filtered`
  alongside `output` in the response dict.
- **`tools/get.py`:** add `grep`/`grep_ignore_case`, but only meaningful when `output="wide"`
  (document this in the tool description — passing `grep` with any other `output` value is a
  no-op, not an error, since JSON output already has `annotation_selector`/`jsonpath_template`).
  Apply `filter_lines()` to the wide-table text the same way as the two tools above.
- **`server.py`:** add `grep`/`grep_ignore_case` to the `logs()`, `describe()`, and `get()`
  wrapper signatures and their `_dispatch(...)` kwargs; update all three tool descriptions.
  Update `k_logs`'s description to note that `grep` filters within the `tail`/`limit_bytes`
  window, not the full log history (per PRD §15 FR14's open question).
- **`tests/unit/test_grep_filter.py`** (new): `compile_grep_pattern()` valid/invalid regex,
  `ignore_case` behavior; `filter_lines()` matched/total counts on multi-line text, empty
  input, zero matches, all-match.
- **Per-tool tests** (`test_tools_logs.py`/`test_tools_describe.py`/`test_tools_get.py`): valid
  `grep` narrows the text and reports `_filtered`; malformed regex → `invalid_grep_pattern`,
  `resolve()`/kubectl never called; `grep_ignore_case` behavior; **regression test proving the
  ordering constraint PRD §15 FR14 requires** — construct a `k_logs` response where
  `_bound.message` (the byte-truncation hint) is present, apply a `grep` pattern that would not
  match the hint text if it were part of `logs`, and assert `_bound.message` is still present
  unchanged (i.e. `grep` never touches `_bound`, only the `logs` field) — this is the one test
  that would catch a future implementation mistakenly concatenating the hint into greppable
  text.
- **`tests/unit/test_server.py`:** update the `logs`/`describe`/`get` entries in
  `_TOOL_DEFINITIONS` with the new `grep`/`grep_ignore_case` kwargs, matching the real wrapper
  call shape exactly (see Issue 40/41 — this is the exact class of mismatch that test exists to
  catch).

### FR20. Rename `jsonpath_template`→`jsonpath`; drop `output="jsonpath"`; unconditional precedence over `output` — **Done**

**Status: Done** — implemented per the plan below. Motivating finding, full design rationale,
and success criteria are in `PRD.md` §15 FR20; this section was the file-by-file implementation
plan. See `CHANGELOG.md` FR20 for the verification record.

**Ordering principle that drives every change below:** in each of `get.py`/`apply.py`/
`patch.py`, the `jsonpath`-truthy check must now run — and short-circuit every `output`-value-
specific branch — *before* any check that inspects `output`'s value. Today the ordering is
reversed in `apply.py`/`patch.py` (the unconditional `output == "wide"` rejection runs before
the `jsonpath_template`-truthy trigger), which is exactly the bug this FR fixes as a side
effect of the rename.

- **`errors.py`:** no new error code — `invalid_output()` already accepts `detail`. This FR's
  job is populating it at every call site, plus one new caller for the legacy-value case.
- **`tools/get.py`:**
  - Rename the parameter `jsonpath_template` → `jsonpath` throughout `handle_get()`.
  - Reorder the fail-fast block: move the nested-brace check (`if jsonpath: check_nested_braces(jsonpath)`)
    and the `annotation_selector`+`jsonpath` incompatibility check to run first, keyed off
    `jsonpath` truthy — these are unaffected by `output`'s value and should fire regardless.
  - The `annotation_selector` + `output == "wide"` incompatibility check is unrelated to
    `jsonpath` and stays as-is, unchanged.
  - **New legacy-value check:** `if output == "jsonpath" and not jsonpath:` → `invalid_output(
    context, output, detail="'jsonpath' is no longer a valid output value — set the jsonpath "
    "parameter directly instead, e.g. jsonpath='{.metadata.name}'. output does not need to be "
    "set when jsonpath is.")`. This replaces today's detail-less version of the same check.
  - Execution: `if jsonpath:` branch (was `if jsonpath_template:`) is checked *before* the
    `output == "wide"` branch, same as today (no ordering bug existed here — `get.py`'s `wide`
    branch was never unconditional the way apply/patch's was) — just rename the variable and
    the echoed response key (`"jsonpath_template"` → `"jsonpath"`).
- **`tools/apply.py`:**
  - Rename `jsonpath_template` → `jsonpath`.
  - **Reorder:** move `if jsonpath: check_nested_braces(...)` to run immediately after the
    legacy-value check below, and move the `if output == "wide": return invalid_output(...)`
    rejection to only fire in an `elif`/nested branch reached when `jsonpath` is falsy — i.e.
    restructure the top of the function so the shape is: legacy-value check → (if `jsonpath`:
    nested-brace check, then proceed straight to the jsonpath execution branch further down,
    skipping the `wide` check entirely) → (else: existing `output == "wide"` rejection, now
    with `detail="output=wide has no meaning for k_apply — kubectl's -o wide is a get-only
    list-formatting flag"` added, since it was previously detail-less too).
  - **New legacy-value check:** same shape as `get.py`'s, adapted to `"k_apply"` as the tool
    name in the envelope.
  - Execution branch: `if jsonpath:` (was `if jsonpath_template:`), echoed key renamed.
- **`tools/patch.py`:** identical restructuring to `apply.py` (same current bug shape, same
  fix), with `detail="output=wide has no meaning for k_patch — ..."` and `"k_patch"` in the
  legacy-value check's envelope call.
- **`server.py`:** for the `get`, `apply`, `patch` wrapper functions — rename the
  `jsonpath_template` parameter to `jsonpath` in both the function signature and the
  `_dispatch(...)` kwargs; update each tool description: drop `jsonpath` from the `output` enum
  list text (keep `name`/`json`/`yaml`/`wide` as applicable per tool), and rephrase the
  `jsonpath` param's description to state it is the sole trigger and overrides `output`
  unconditionally when set, e.g. *"jsonpath: JsonPath template — setting this alone is
  sufficient to enable jsonpath mode and overrides any `output` value; `output='jsonpath'` is
  no longer valid, do not set it"*.
- **Tests:**
  - `tests/unit/test_tools_get.py` / `test_tools_apply.py` / `test_tools_patch.py`: rename every
    `jsonpath_template=` call keyword to `jsonpath=`; rename every assertion on the echoed
    `"jsonpath_template"` response key to `"jsonpath"`.
  - New cases per tool (mirroring PRD §15 FR20's success-criteria list): `jsonpath` set +
    `output="json"` → jsonpath path taken, `output` ignored; `jsonpath` set + `output="wide"`
    → succeeds on `k_get` (already worked) **and on `k_apply`/`k_patch`** (new — this is the
    regression-fix case, must assert success, not `invalid_output`); `output="jsonpath"` with no
    `jsonpath` → `invalid_output` with a non-empty `detail` mentioning `jsonpath`; `output="wide"`
    on `k_apply`/`k_patch` with **no** `jsonpath` set → still `invalid_output` (regression guard
    that the reorder didn't loosen the `wide`-rejection for the genuinely-`jsonpath`-absent case),
    now also asserting `detail` is non-empty.
  - `tests/unit/test_jsonpath_validation.py`: unaffected — `check_nested_braces()`'s own tests
    don't reference a parameter name at all.
  - `tests/unit/test_server.py`: update the `get`/`apply`/`patch` entries in `_TOOL_DEFINITIONS`
    (or equivalent fixture) from `jsonpath_template` to `jsonpath`, matching the renamed real
    wrapper kwargs exactly — this is the precise class of mismatch Issue 40/41 exists to catch;
    skipping this update would leave the dispatch-path smoke test silently exercising a stale
    kwarg name.
- **Docs (do in the same change, not a follow-up — see the Definition of Done checklist):**
  PRD.md §6's `k_get`/`k_apply`/`k_patch` rows updated to say `jsonpath` (not
  `jsonpath_template`) and drop `"jsonpath"` from the `output` value list in the description
  column, only once this actually ships — until then §6 continues to describe current
  (`jsonpath_template`) reality, per this project's own established convention of not
  pre-editing §6 for unimplemented FRs.

### FR21. Distinguishable error codes for timeout/connectivity, authentication vs. authorization, and kubectl-level argument failures

**Status: Done** — implemented and committed; see CHANGELOG.md FR21.

- **`errors/core.py`:** six new code constants + thin `_base()`-shaped helpers, same shape as
  every existing helper in this file (`context` first, code from `_base()`, optional `detail`):
  - `ERROR_KUBECTL_TIMEOUT = "kubectl_timeout"` + `kubectl_timeout(context, *, timeout, command,
    detail=None)`.
  - `ERROR_KUBECTL_NOT_INSTALLED = "kubectl_not_installed"` + `kubectl_not_installed(context, *,
    detail=None)`.
  - `ERROR_KUBECTL_EXEC_ERROR = "kubectl_exec_error"` + `kubectl_exec_error(context, *,
    detail)`.
  - `ERROR_KUBECTL_UNREACHABLE = "kubectl_unreachable"` + `kubectl_unreachable(context, *,
    raw_stderr)` — same parameter shape as the existing `object_not_found`/`kubectl_failure`
    helpers that already take `raw_stderr`/`stderr`.
  - `ERROR_AUTHENTICATION_FAILED = "authentication_failed"` + `authentication_failed(context, *,
    raw_stderr)`.
  - `ERROR_KUBECTL_INVALID_ARGUMENT = "kubectl_invalid_argument"` + `kubectl_invalid_argument(
    context, *, raw_stderr)`.
  - `ERROR_OBJECT_INVALID = "object_invalid"` + `object_invalid(context, *, raw_stderr)`.
- **`kubectl/runner.py`:** `run_kubectl()`'s three exception branches replaced:
  ```python
  except subprocess.TimeoutExpired:
      return kubectl_timeout(context, timeout=timeout, command=base_args)
  except FileNotFoundError:
      return kubectl_not_installed(context)
  except OSError as e:
      return kubectl_exec_error(context, detail=str(e))
  ```
  Import the three helpers from `..errors` (mirrors how `kubectl/errors.py` already imports
  `kubectl_failure`/`object_not_found` from the same module). No signature change to
  `run_kubectl()`/`run_kubectl_checked()` — only the exception-branch return values change
  shape, from ad hoc dicts to the standard `{"context", "error", ...}` shape every other code
  path already produces.
- **`kubectl/errors.py`:** `map_kubectl_error()`'s pattern list extended and reordered — checked
  in this order, first match wins, falling through to the existing `kubectl_failure` default
  unchanged:
  1. `"ambiguous"` → `ambiguous_resource` (unchanged, existing first check).
  2. `"notfound"` / `"not found"` → `object_not_found` (unchanged).
  3. **New:** `"unable to connect to the server"` / `"connection refused"` / `"no such host"` /
     `"dial tcp"` → `kubectl_unreachable(context, raw_stderr=stderr)`.
  4. **New:** `"x509:"` / `"must be logged in"`, or `"unauthorized"` **when `"forbidden"` is
     not also present** → `authentication_failed(context, raw_stderr=stderr)`. Must run before
     check 5 so a pure-authentication failure isn't miscaught by the broader authorization
     check; must explicitly exclude stderr that also contains `"forbidden"` so a combined
     message doesn't shadow the existing, more specific RBAC case.
  5. `"forbidden"` (or `"unauthorized"` when `"forbidden"` is also present) → `access_denied`
     (unchanged code, existing check — now runs after the authentication-only check above, not
     before).
  6. **New:** stderr starting with `"error: unknown flag"` / `"error: unknown shorthand flag"`
     / `"error: unknown command"` → `kubectl_invalid_argument(context, raw_stderr=stderr)`.
  7. **New:** `" is invalid: "` in stderr → `object_invalid(context, raw_stderr=stderr)`.
  8. Default (unchanged): `kubectl_failure`.
  All substring checks stay case-insensitive on `stderr.lower()`, matching the existing
  convention in this function. Exact substrings (especially the connectivity and x509 patterns)
  should be re-validated against real kubectl stderr samples during implementation — the set
  above is a reasoned starting point from documented kubectl error wording, not verified against
  a live cluster this session (see PRD §15 FR21's note on scope).
- **Tests:**
  - `tests/unit/test_runner.py`: `test_timeout_expired_error`/`test_file_not_found_error`/
    `test_oserror_error` (both `TestRunKubectl` and the `...Checked` passthrough variants)
    updated to assert `result["error"] == "kubectl_timeout"` /
    `"kubectl_not_installed"` / `"kubectl_exec_error"` and `result["context"] == "ctx"`,
    replacing the current free-text substring assertions.
  - `tests/unit/test_kubectl_errors.py`: `test_unauthorized` updated to assert
    `"authentication_failed"` (was `"access_denied"`) — this is the one intentional behavior
    change in the whole FR, called out explicitly so it isn't mistaken for a regression. New
    cases: `test_unreachable` (`"Unable to connect to the server: dial tcp ..."` →
    `kubectl_unreachable`), `test_forbidden_with_unauthorized_wording` (a combined message
    containing both `"forbidden"` and `"unauthorized"` → still `access_denied`, guarding the
    ordering rule), `test_invalid_argument` (`"error: unknown flag: --bogus"` →
    `kubectl_invalid_argument`), `test_object_invalid` (`'Deployment.apps "x" is invalid: spec.replicas: Invalid value'`
    → `object_invalid`). Existing `test_forbidden`/`test_not_found`/`test_ambiguous_resource`/
    `test_default_kubectl_failure` unchanged.
- **Docs (same change, not a follow-up — Definition of Done):** PRD.md §7's error-codes list
  gets the six new codes added; `kubectl_failure` (already implemented but never listed there)
  added at the same time, closing that pre-existing documentation gap.

### FR22. Emit multiline tool output as a JSON array of lines instead of an escaped string

**Status: Done** — implemented and committed; see CHANGELOG.md FR22.

- **`resolution/grep_filter.py`:** `filter_lines()`'s signature changes from
  `filter_lines(text: str, compiled: re.Pattern[str]) -> tuple[str, int, int]` to
  `filter_lines(lines: list[str], compiled: re.Pattern[str]) -> tuple[list[str], int, int]` —
  callers now pass an already-`.splitlines()`'d list instead of raw text, and get the matched
  lines back as a list instead of a `"\n"`-joined string. Internals: drop the
  `"\n".join(matched_lines)` call, return `matched_lines` directly. `total`/`matched` counts
  unchanged. This is the single shared seam FR14 established — one change here fixes the
  grep-filtered path for all three tools at once.
- **`tools/get.py`** (`output="wide"` branch, ~line 147-156): `response: dict[str, Any] =
  {"output": result["stdout"].splitlines()}`; the grep branch (~line 152-155) calls
  `filter_lines(result["stdout"].splitlines(), grep_compiled)` and assigns the returned list
  directly to `response["output"]`.
- **`tools/describe.py`** (~line 64-72): same pattern — `{"output":
  result["stdout"].splitlines()}`; the grep branch passes `result["stdout"].splitlines()` into
  `filter_lines()` and assigns the returned list to `response["output"]`.
- **`output/bounding.py`'s `bound_logs()`** (~line 50-90): `lines = stdout.splitlines()`
  already computed at line 61. Truncation branch (line 63-70): `logs_out = truncated_lines`
  (was `"\n".join(truncated_lines)` at line 65). No-truncation branch (line 71-76): `logs_out =
  lines` (was raw `stdout` at line 72). Return type's `"logs"` key changes from `str` to
  `list[str]`.
- **`tools/logs.py`** (~line 96-97): `bounded["logs"]` is already `list[str]` after the
  `bound_logs()` change above, so `filter_lines(bounded["logs"], grep_compiled)` passes it
  straight through — no `.splitlines()` needed at this call site.
- **Tests:**
  - `tests/unit/test_grep_filter.py`: `filter_lines()` unit tests updated to pass a `list[str]`
    in and assert a `list[str]` out, not a joined string.
  - `tests/unit/test_bounding.py`: `bound_logs()` tests updated to assert `result["logs"]` is a
    `list[str]` (e.g. `== stdout.splitlines()`), not a string, for both the truncated and
    untruncated branch.
  - `tests/unit/test_tools_get.py`: the `output="wide"` `isinstance(result["data"]["output"],
    str)` assertion (currently at line 343) flips to `list`; all 5 grep tests' filtered-output
    assertions updated from string equality/substring to list equality.
  - `tests/unit/test_tools_describe.py`: same treatment for its 4 grep tests plus the base
    (non-grep) `output` assertion.
  - `tests/unit/test_tools_logs.py`: same treatment for its 6 grep tests plus the base `logs`
    assertion.
- **Docs (Definition of Done):** PRD.md §6's Tool Specification table doesn't currently state a
  type for the `output`/`logs` fields, so no table-wording change is forced by this alone; if
  type wording is added while building this, keep it in sync with the `list[str]` shape at the
  same time — per this project's own established convention of not letting §6 drift from
  shipped reality (see FR20's closing note above for the same discipline applied there).

**Success Criteria (test coverage):**
1. `filter_lines()` unit tests assert `list[str]` in, `list[str]` out.
2. `k_get(output="wide")`, `k_describe`, and `k_logs` each return `list[str]` (not `str`) under
   their text field, in both the grep and non-grep path.
3. `bound_logs()` unit tests assert `list[str]` for both the truncated and untruncated branch.
4. Full suite passes with zero regressions outside the enumerated type-shape assertion changes
   above.

### FR23. Translate discovery's raw Kubernetes API verbs into this project's MCP-tool verb vocabulary; add `daemonsets` to the core table

**Status: Done** — implemented and committed; see CHANGELOG.md FR23.

- **`resolution/discovery.py`:** add a module-level translation table immediately above
  `_parse_api_resources()` (the function that parses the VERBS column, ~line 91, verb-parsing
  itself at ~line 177-181):
  ```python
  _API_VERB_TO_MCP_VERBS: dict[str, frozenset[str]] = {
      "get": frozenset({"get"}),
      "list": frozenset({"get"}),
      "create": frozenset({"apply"}),
      "update": frozenset({"apply"}),
      "patch": frozenset({"apply", "patch"}),
      "delete": frozenset({"delete"}),
      "watch": frozenset(),
      "deletecollection": frozenset(),
  }
  ```
  Replace the current verb-parsing line:
  ```python
  if verbs_str:
      verbs = [v.strip() for v in verbs_str.split(",") if v.strip()]
  else:
      verbs = ["get", "apply", "patch", "delete"]
  ```
  with:
  ```python
  if verbs_str:
      api_verbs = [v.strip() for v in verbs_str.split(",") if v.strip()]
      mcp_verbs: set[str] = set()
      for v in api_verbs:
          mcp_verbs |= _API_VERB_TO_MCP_VERBS.get(v, frozenset())
      verbs = sorted(mcp_verbs)
  else:
      verbs = ["get", "apply", "patch", "delete"]
  ```
  The `else` branch (empty VERBS column — kubectl reported nothing) keeps today's permissive
  fallback unchanged; this FR only changes behavior when kubectl *did* report a verb list.
  `sorted()` keeps output deterministic for tests/snapshots.
- **`data/core_resources.toml`:** new `[[resource]]` block, placed alongside the other apps/v1
  entries (after `replicasets`, ~line 50):
  ```toml
  [[resource]]
  canonical = "daemonsets"
  shortnames = ["ds"]
  kind = "DaemonSet"
  group = "apps"
  version = "v1"
  namespaced = true
  verbs = ["get", "apply", "patch", "delete"]
  ```
- **Tests:**
  - **New `tests/unit/test_discovery.py` cases** (or the existing discovery-parsing test file —
    confirm exact filename before adding): feed `_parse_api_resources()` a synthetic
    `kubectl api-resources -o wide` block with a CRD-shaped line whose VERBS column is
    `create,delete,get,list,patch,update,watch`; assert the resulting `ResourceMeta.verbs ==
    ["apply", "delete", "get", "patch"]` (sorted). A second case with VERBS `get,list,watch`
    only asserts `verbs == ["get"]` — proving `apply` is correctly absent, not a blanket grant.
  - **`tests/unit/test_resolver.py`** (or wherever `validate()` is unit-tested): a
    discovery-sourced `ResourceMeta` fixture with `verbs=["get", "apply", "patch", "delete"]`
    (post-translation shape) passes `validate(resource_meta, "apply", namespace)` — this is the
    exact regression case the bug report was built from; today's fixture (raw API verbs) fails
    it.
  - **`tests/unit/test_core_table.py`** (or equivalent core-table loader test): `daemonsets`
    resolves via `resolve(context, "daemonsets")` without touching the discovery cache/mock
    kubectl call at all — proving it's served from the static table, matching the existing
    assertion pattern for `deployments`/`statefulsets`.
  - **`tests/unit/test_tools_apply.py`** (or `test_tools_patch.py`/`test_tools_delete.py`): a
    `daemonsets` manifest through `handle_apply()`/`handle_patch()`/`handle_delete()` no longer
    returns `verb_unsupported` — add alongside the existing per-resource-type fixtures.
- **Docs (Definition of Done):** PRD.md §12's CRUD-coverage line updated from the "confirmed
  broken by code trace" wording (added as part of validating this FR) to reflect the fix once
  shipped, with the verification basis stated (code trace + the new discovery/resolver tests
  above — still not a live-cluster re-verification, call that out explicitly rather than
  overclaim).

**Success Criteria (test coverage):** see PRD.md §15 FR23's five-item list — mirrored exactly by
the test cases above, one-to-one.
