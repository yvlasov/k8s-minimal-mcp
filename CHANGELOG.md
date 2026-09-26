# Changelog

Full history of shipped feature requests and fixed defects for k8s-minimal-mcp. Root cause,
fix, tests, and verification detail live here. `PRD.md`, `SPEC.md`, and `KNOWN_ISSUES.md`
reference entries by number (`FR9`, `Issue 38`, ...) rather than duplicating this detail —
see those files for current design/spec and open work.

Ordered newest-first within each section, matching the order these were actually resolved.

---

## Feature Requests

### FR13 — `k_auth_can_i`

Thin wrapper over `kubectl auth can-i` (RBAC effective-permission checks). Single-check and
`--list` modes. Core exit-code logic (`run_kubectl`, not `_checked` — exit 1 means "denied,"
not "failed") was correct and well-tested from the start (`tests/unit/test_tools_auth_can_i.py`,
16 tests).

Getting the tool actually callable took two more rounds — see **Issue 40** below for the full
three-commit history (two independent dispatch-path bugs, two false "Verified" claims, finally
confirmed working end-to-end by building the real server and calling the registered tool
through FastMCP's own dispatch). Committed `c6d7e85`. Full suite at completion: 305 passed.

Tool-count check: shipped at `readonly`, bringing `admin` to 12/12 (PRD §12 ceiling) — met,
no violation. Access level: `readonly` (`access.py` `_VERB_MAP`).

### FR12 — `k_get_helm_release`

Decodes a Helm v3 release's storage Secret (`base64(gzip(json))` in `.data.release`, selected
by `owner=helm,name=<release>` labels, revision = highest `version` label unless specified)
into a bounded summary. Fetches the Secret directly via `run_kubectl_checked` (same pattern as
`k_get_secret_to_file`), bypassing Issue 35's generic Secret redaction — a deliberate, named
R1 exception.

Committed `98a4c14`; `tests/unit/test_tools_get_helm_release.py`, 13 tests (corrected from an
earlier miscount of 12); full suite 289 passed.

**Issue 39 (shipped-without-resolving finding):** the implementation plan explicitly flagged
"does `values` need redaction?" as an open decision before implementation — it shipped with no
decision made, `values` fully unredacted at `readonly` access level. Resolved 2026-09-25 via
Option B (raise the access gate, not add content redaction): moved `get_helm_release` from
`readonly` to `admin`-only in `access.py`'s `_VERB_MAP`. `values` is still returned unredacted
in full — the exposure was closed by access level, not by filtering. Added
`test_get_helm_release_admin_only` (readonly/readwrite: absent; admin: present); independently
live-verified by building the real server at all three access levels.

### FR11 — Built-in MCP prompts (ArgoCD / Cilium status guidance)

New module `src/k8s_mcp/prompts.py`: `argocd_app_health(name, namespace)`,
`cilium_troubleshoot_connectivity(namespace, pod)`, `rbac_effective_permissions(as_user,
namespace)`. Each returns a literal, exact tool-call shape (not paraphrased) plus an explicit
statement of what it does *not* cover. Registered unconditionally in `server.py` (no access
gate — a prompt performs no cluster access itself, consistent with R7's rationale).

`tests/unit/test_prompts.py`, 12 tests, asserting exact substrings (resource= values, field
paths). Full suite 276 passed.

**Issue 43 (open, filed against this FR):** `cilium_troubleshoot_connectivity`'s
`(namespace, pod)` signature doesn't fit diffuse/fleet-wide symptoms and never emits the
mandatory `context=` parameter — see `KNOWN_ISSUES.md` OPEN section for the live writeup and
requested `(cluster, issue_description)` correction. Not yet implemented.

### FR10 — `src_file` for `k_apply`

Added `src_file: str | None = None` as an alternative to `manifest` — exactly one of the two
required. Absolute-path-only (reuses `unsafe_path`), new `file_read_failed` error. Resolves a
single `manifest_content` string once at the top of `handle_apply()`.

Committed `c223fb5`; 6 new tests in `test_tools_apply.py` (JSON/YAML happy paths via real
`tmp_path` files, both/neither-set `invalid_manifest`, relative-path `unsafe_path`,
nonexistent-file `file_read_failed`). Full suite 253 passed.

Motivating gap found alongside this FR, resolved via **Issue 35**: `k_apply`'s response
already echoed a Secret's `.data` verbatim regardless of `src_file`, undercutting the whole
"route Secret content around the model" goal — fixed by Issue 35's hard-block redaction.

### FR9 — `k_get_secret_to_file`

New `admin`-only tool: decodes a Secret and writes it straight to a file on disk, returning
only key names and the file path — never values. Deliberate, named R1 exception (the one
resource type where R1's generic-verb shape is actively wrong).

Design decisions resolved before implementation: absolute-path-only (no directory allowlist —
the admin-only gate is sufficient); file written via `os.open(..., O_WRONLY|O_CREAT|O_TRUNC,
0o600)` (no wider-permission window); refuses to overwrite by default, `overwrite=True`
required; output format `{"data": {...}, "base64_keys": [...]}` with lossless per-key
base64-passthrough for non-UTF-8 values.

Committed `a30abbb` (docs), `d6c609c` (implementation); `tests/unit/test_tools_get_secret_to_file.py`,
11 tests, including a negative test that serializes the full response and searches for the
plaintext/base64 secret value to confirm it never appears. Full suite 240 passed.

### FR8 — Fail-fast validation for nested-brace `jsonpath_template` syntax

Added `resolution/jsonpath_validation.py::check_nested_braces()` — rejects nested `{...}`
groups (a proven-common mistake, see Issue 29) with a `invalid_jsonpath_template` error
explaining the correct bracket-list/`range` syntax, applied to `k_get`/`k_apply`/`k_patch`.
`tests/unit/test_jsonpath_validation.py`, 10 tests.

### FR7 — Add `events` to the R2 core table

Added `[[resource]]` entry (`canonical="events"`, `shortnames=["ev"]`, `kind="Event"`,
`verbs=["get"]`) to `data/core_resources.toml` — purely additive, no collision with existing
entries. See also Issue 24 (same change, filed independently as a latency gap before this FR
formalized it).

### FR6 — Fix `k_apply`/`k_patch`'s non-functional `output=json`/`yaml`

Added `apply_output_format()` call after `prune()` in both tools' non-jsonpath success paths.
`output="wide"` explicitly rejected via `invalid_output` (kubectl's `-o wide` has no meaning
for apply/patch) rather than silently accepted. 6 new tests. Same defect class as Issue 20;
tracked in detail as **Issue 23**.

### FR5 — Fix `k_get`'s `output=wide` no-op

`get.py` now invokes kubectl with the actual `-o wide` flag and returns the plain-text table
verbatim, instead of trying to derive it from JSON (`bound_get_names()`'s `"wide"` branch was
byte-identical to the default). Same defect tracked in detail as **Issue 20**.

### FR4 — Unit test coverage for `k_delete`/`k_describe`/`k_logs`/`k_exec`/`k_list_contexts`

Five new test files (133 tests). Two bugs found and fixed while writing the tests: `exec_.py`'s
`-c <container>` flag was placed after `--` (kubectl never parsed it — container selection
silently didn't work); `contexts.py` discarded kubeconfig-read errors, returning an empty
context list indistinguishable from "genuinely zero contexts." See **Issue 17** and
**Issue 18** for full detail.

### FR3 — `k_list_resources` tool

New `tools/list_resources.py`: exposes the discovery cache's `ResourceMeta` records to the
model directly (case-insensitive substring search over canonical/kind/group). `readonly`.
16 unit tests.

### FR2 — `annotation_selector` for `k_get`

Client-side annotation filtering (`key=value`/`key!=value`/bare-`key`, AND semantics) — kubectl
has no server-side annotation selector. Shipped with a bug (**Issue 19**: always returned zero
matches when combined with `name`) found and fixed alongside test-coverage work.

### FR1 — `output=jsonpath` for `k_get`/`k_apply`/`k_patch`

Added `jsonpath_template` param; presence of the template (not `output=="jsonpath"`) is the
actual trigger. Bypasses pruning/bounding, returns the raw kubectl jsonpath string.
`tests/unit/test_tools_apply.py`/`test_tools_patch.py` created new for this FR.

---

## Fixed Issues

### 48. `k_apply`/`k_patch`/`k_delete`/`k_logs`/`k_get_helm_release`'s tests never asserted `-n <namespace>` reaches kubectl args

**File:** `tests/unit/test_tools_apply.py`, `test_tools_patch.py`, `test_tools_delete.py`,
`test_tools_logs.py`, `test_tools_get_helm_release.py`
**Root cause:** the source code for all five tools was already correct (each properly threads
`namespace` into `-n` in its kubectl args), but every test that passed `namespace="default"`
asserted only on output shape/format, never on the constructed `args` — the same blind spot
that let Issue 46 ship, latent here too because nothing had exercised it yet.
**Fix:** added `assert "-n" in args` / `assert "default" in args` (or the equivalent
`mock_run.call_args[0][1]` form) to one existing namespace-carrying test in each file — minimal
diff, no new test classes needed.
**Verified:** full suite — 377 passed, 9 skipped.

### 47. `kubectl/runner.py` had zero direct test coverage on the seam enforcing R3's mandatory `--context`

**File:** `tests/unit/test_runner.py` (new, 16 tests)
**Root cause:** every existing test mocked `run_kubectl`/`run_kubectl_checked` away at the
tool-module boundary, so `run_kubectl()`'s actual body — where `base_args = ["kubectl",
"--context", context, ...]` is constructed — had never been executed by any test in the suite.
**Fix:** new `test_runner.py`, mocking only `subprocess.run` (the lowest seam) and calling the
real `run_kubectl()`/`run_kubectl_checked()`. Covers: `--context` placement and value fidelity
across distinct contexts; `-o <output_format>` present/omitted; `stdin`/`timeout` passthrough;
success result shape; all three exception paths (`TimeoutExpired`, `FileNotFoundError`,
`OSError`); `run_kubectl_checked()`'s zero/non-zero exit handling (asserting the real call into
`map_kubectl_error()`) and context preservation through the checked wrapper.
**Verified:** full suite — 377 passed, 9 skipped (16 new tests over the 361 baseline).

### 46. `k_exec` never passed `-n <namespace>` to kubectl

**File:** `src/k8s_mcp/tools/exec_.py`, `tests/unit/test_tools_exec.py`
**Root cause:** `handle_exec()` accepted `namespace`, passed it to `validate()`, and echoed it
into `exec_failed()`'s error dict, but never appended it to the constructed `args` — every call
ran against kubectl's default namespace instead of the caller's, producing false
`object_not_found` errors for real, running pods in any non-default namespace. Every sibling
tool already appended `-n` correctly; `exec_.py` was the sole exception.
**Fix:** added `if namespace: args.extend(["-n", namespace])` right after `args = ["exec",
pod]`, matching every sibling tool's pattern.
**Test:** `test_exec_with_container`/`test_exec_without_container` — previously asserted the
full `args` list *without* `-n` present (asserting the bug as correct, same shape as Issue 26's
precedent) — corrected to assert `-n`/`"default"` are present.
**Verified:** full suite — 361 passed (pre-Issue 47/48), 9 skipped.

### 45. `map_kubectl_error()`'s NotFound branch used `detail` instead of `raw_stderr`

**File:** `src/k8s_mcp/errors.py`, `src/k8s_mcp/kubectl/errors.py`, `tests/unit/test_errors.py`,
`tests/unit/test_kubectl_errors.py`
**Root cause:** `object_not_found()` named its raw-kubectl-stderr field `detail`, while the
sibling `ambiguous_resource`/`access_denied` ad hoc dicts in the same `map_kubectl_error()`
function used `raw_stderr` for the same conceptual content — found during review of Issue 42's
fix.
**Fix:** renamed `object_not_found()`'s keyword parameter from `detail` to `raw_stderr`
(`errors.py:283`); `kubectl/errors.py`'s NotFound branch now calls
`object_not_found(context=context, raw_stderr=stderr)`, matching the field name used by every
other branch in the function.
**Test:** `test_errors.py`/`test_kubectl_errors.py` updated to assert `raw_stderr` instead of
`detail`.
**Verified:** full suite — 361 passed, 9 skipped.
**Not addressed by this fix (still true):** the `ambiguous_resource`/`access_denied` branches
in `map_kubectl_error()` remain ad hoc dicts rather than calls to their existing `errors.py`
helpers — a pre-existing SPEC §6 guideline violation, unrelated to the field-naming issue this
fix closed.

### 44. `cilium_troubleshoot_connectivity`'s PromQL snippets had unquoted label-matcher values

**File:** `src/k8s_mcp/prompts.py`, `tests/unit/test_prompts.py`
**Root cause:** the generated Prometheus guidance text used `direction=INGRESS`/
`direction=EGRESS` — PromQL requires label matcher values to be quoted strings; unquoted, both
queries are a syntax error.
**Fix:** quoted both label values —
`cilium_drop_count_total{direction="INGRESS",reason!="policy-denied"}` and
`cilium_drop_count_total{direction="EGRESS"}`.
**Test:** `test_prompts.py` asserts the quoted literal form is present.
**Verified:** full suite — 361 passed, 9 skipped.

### 43. `cilium_troubleshoot_connectivity` prompt used `(namespace, pod)`, never emitted `context=`, and didn't fit fleet-wide symptoms

**File:** `src/k8s_mcp/prompts.py`, `src/k8s_mcp/server.py`, `src/k8s_mcp/utils.py` (new),
`tests/unit/test_prompts.py`, `tests/unit/test_utils.py` (new)
**Root cause:** the prompt's `(namespace, pod)` signature assumed a specific pod was already
known, and none of its three generated `k_get`/`k_describe` calls included `context=` despite
every tool requiring it as a mandatory parameter.
**Fix:** rewrote the prompt as `cilium_troubleshoot_connectivity(cluster, issue_description)`.
`cluster` is threaded into every generated call as `context=<cluster>`, closing the missing-
parameter gap. The body now always runs a cluster-wide triage path first (`ciliumnodes`,
`ciliumclusterwidenetworkpolicies`, `ciliumidentities`), then conditionally appends pod-specific
narrowing steps (`ciliumendpoints`, `ciliumnetworkpolicies`) only if a pod name is found in
`issue_description`. Pod-name extraction is a new, reusable `extract_named_entity(text,
entity_type)` helper in a new `src/k8s_mcp/utils.py` module (regex-based, k8s-naming-aware,
not scoped to Cilium specifically). Also retained: the explicit note that Cilium's own eBPF
drop-reason counters are Prometheus-exposed, not reachable via any `k_*` tool.
**Test:** `test_prompts.py` updated for the new signature (asserts every generated call
includes `context=`, asserts both the cluster-wide-only and pod-named-in-description paths);
new `test_utils.py` (12 cases) covering `extract_named_entity()`'s pattern matching, k8s-name
validation, and no-match cases.
**Verified:** full suite passed after the change (see Issue 42's entry below for the shared
verification run — both fixes landed close together).
**Follow-up found during review, since fixed:** the generated PromQL snippets in the Prometheus
note had unquoted label-matcher values — see Issue 44 above.

### 42. `map_kubectl_error()` conflated "resource type unresolvable" with "named object legitimately doesn't exist"

**File:** `src/k8s_mcp/errors.py`, `src/k8s_mcp/kubectl/errors.py`,
`tests/unit/test_kubectl_errors.py`, `tests/unit/test_errors.py`
**Root cause:** confirmed via `kubectl/runner.py`'s single call site that `map_kubectl_error()`
only ever runs *after* `resolve()`/`validate()` (R8) already succeeded — meaning the
"type doesn't resolve" case structurally never reaches this function at all (`resolve()`
already rejects it earlier, with its own `unknown_resource`, before kubectl ever runs). Every
`"not found"`/`"notfound"` stderr this function sees was therefore always the
resolved-type-but-missing-object case — not two shapes needing a heuristic to distinguish, only
one, previously mislabeled.
**Fix:** added `ERROR_OBJECT_NOT_FOUND = "object_not_found"` + `object_not_found(context,
resource=None, *, name=None, raw_stderr=None)` to `errors.py`. `kubectl/errors.py`'s `"not
found"`/`"notfound"` branch now returns `object_not_found(context=context, raw_stderr=stderr)`
instead of the old ad hoc `{"error": "unknown_resource", ...}` dict.
**Test:** `test_kubectl_errors.py`'s two tests that previously asserted `unknown_resource` for
this branch were corrected to assert `object_not_found` (not just supplemented — per the
Issue 26 precedent, a test asserting the old, wrong behavior as correct must not survive
alongside the fix). New `test_errors.py::test_object_not_found_with_all_fields`/
`test_object_not_found_minimal` cover the helper directly.
**Verified:** full suite — 360 passed, 9 skipped.
**Follow-up found during review, since fixed:** `object_not_found()`'s raw kubectl stderr text
was initially carried in a field named `detail`, inconsistent with the sibling branches'
`raw_stderr` — see Issue 45 above.

### 41. No test exercised `server.py`'s `_dispatch()` path — every unit test called handlers directly

**File:** `tests/unit/test_server.py` (new), `src/k8s_mcp/server.py`
**Severity:** High — the root cause that let Issue 40 ship with 14 passing tests and a
"committed" status.
**Fix:** Added a parametrized smoke test (`TestDispatchPathSmoke::test_dispatch_no_type_error`)
calling `_dispatch()` directly for every tool at every access level, with the exact kwargs each
`server.py` wrapper passes, mocking only `resolve`/`run_kubectl`/`run_kubectl_checked` at the
tool-module level. 33 cases (11 tools × 3 levels, 7 skipped for not-applicable tier combos).
Also fixed `_dispatch()`'s `discovery_cache` type annotation from `DiscoveryCache` to
`DiscoveryCache | None`.
**Verified:** `331 passed, 7 skipped`.

### 40. `k_auth_can_i` crashed on every real call — two independent bugs, three commits

**File:** `src/k8s_mcp/tools/auth_can_i.py:84`, `src/k8s_mcp/server.py:47,65,68,70`
**History (kept in full — the process failure is as instructive as the bug):**
1. Original bug: `handle_auth_can_i()` didn't accept the `discovery_cache` kwarg `_dispatch()`
   unconditionally sends every handler.
2. Commit `3115af3` added `discovery_cache: object | None = None` and a regression test that
   called the handler **directly** — passed, and the commit's own doc edit claimed "Verified"
   with an unfilled `<commit-hash>` placeholder. A live-server check then found the tool
   **still crashed**, on a second, unrelated bug: `_dispatch()`'s own first parameter was named
   `verb`, colliding with `k_auth_can_i`'s own `verb` domain argument
   (`TypeError: _dispatch() got multiple values for argument 'verb'`).
3. Commit `c6d7e85` renamed `_dispatch()`'s first parameter to `tool_verb`, updated all 12 call
   sites, added `test_dispatch_path_no_verb_collision` (genuinely calls `_dispatch()` itself) —
   again wrote a "Verified" claim with another unfilled placeholder.
**Independently verified, genuinely:** built the real FastMCP server via `server.main()`,
called the actual registered `k_auth_can_i` tool through FastMCP's own `call_tool()` dispatch
entry point, with `subprocess.run` mocked at the lowest seam. Both modes confirmed working, no
exception: single-check and `list_all=True`. Spot-checked `k_get`/`k_delete`/`k_list_resources`
the same way — no collateral breakage from the rename. Full suite: 305 passed. Committed
`c6d7e85` (both prior placeholders resolved by this entry).
**Process lesson (not closed out by the fix itself):** two consecutive "Verified" claims here
were false or unconfirmed, both sharing the same root cause — a regression test that calls a
handler directly instead of through `_dispatch()`. Issue 41's `test_server.py` closes this gap
structurally.

### 39. `k_get_helm_release` returned a chart's `values` block fully unredacted

**File:** `src/k8s_mcp/access.py`, `tests/unit/test_access.py`
**Severity:** High — a real shipping exposure (chart values commonly carry plaintext
credentials/API keys).
**Root cause:** `get_helm_release.py:169` — `"values": data.get("values", {})`, no filtering.
The implementation plan explicitly flagged this as an open decision; it was never made.
**Fix:** Option B — moved `get_helm_release` from `readonly` to `admin` in `access.py`'s
`_VERB_MAP`. Updated `test_access.py` and `test_server.py`'s `_ACCESS_TOOLS`, added
`test_get_helm_release_admin_only`.
**Verified:** 330 passed, 9 skipped.

### 38. Resolved `group`-qualification discarded before reaching kubectl

**File:** `src/k8s_mcp/tools/get.py:96`, `delete.py:44`, `describe.py:40`, `patch.py:72`
**Severity:** A real, live violation of PRD §12's "ambiguous-resource calls never silently
resolve to the wrong API group" criterion — canonical-name collisions (`nodes` vs.
`metrics.k8s.io`'s `NodeMetrics`; `pods`/`events` similarly) silently executed against the
wrong API group.
**Fix:** Replaced `resource_meta.canonical` with `resource_meta.fully_qualified_name` in all
four tools. `fully_qualified_name` collapses to plain `canonical` when `group == ""` (zero
behavior change for core-table entries), returns `f"{canonical}.{group}"` otherwise.
**Test:** 8 new tests across the four tool test files, each asserting groupful resources
produce the qualified name and groupless resources produce plain `canonical`.
**Verified:** confirmed in all four files; broader `grep` confirmed no other call site builds a
kubectl exec argument from bare `.canonical`. 264 tests pass. Committed `f1680db`.

### 37. `pyyaml` undeclared transitive dependency

**File:** `pyproject.toml`
**Fix:** Added `"pyyaml>=6.0"` to `dependencies` (previously present only via `fastmcp`'s
`jsonschema-path` transitive pull). No code change needed. Committed `f1680db`.

### 36. `apply.py`'s `_parse_manifest()` swallowed all YAML parse errors via bare `except Exception: pass`

**File:** `src/k8s_mcp/tools/apply.py:31-48`
**Fix:** Changed `_parse_manifest()` to return `(data, yaml_error_detail)`; `except Exception:
pass` replaced with `except yaml.YAMLError as e`, real parser message threaded into
`invalid_manifest`'s detail.
**Test:** 3 new tests in `TestHandleApplyYamlErrorDetail`.
**Verified:** traced `yaml.safe_load("bad: [")` end-to-end — raises a real
`yaml.parser.ParserError` whose message reaches the response unmodified. 256 tests pass.
Committed `583f431`. `grep -rn "except Exception" src/k8s_mcp/` confirmed this was the only
instance.

### 35. `prune()` had no `Secret`-specific handling

**File:** `src/k8s_mcp/output/pruning.py`
**Fix:** When `kind == "Secret"`, `.data`/`.stringData` replaced with
`{"redacted_keys": sorted(keys)}` — key names only, applied uniformly across `k_get`/
`k_apply`/`k_patch`/`k_delete`. Hard block, no opt-out parameter. `k_get_secret_to_file`
unaffected (separate fetch path, never calls `prune()`).
**Test:** 7 new tests in `TestPruneSecretRedaction`.
**Verified:** confirmed hard-block (no `reveal_secrets`-style parameter exists anywhere);
confirmed all four call sites route through the same shared `prune()`. Committed `c223fb5`.

### 1. `bound_get_names({})` returns `[{}]` instead of `[]`

**File:** `src/k8s_mcp/output/bounding.py:26` — added early return guard for empty dict.

### 2. `prune()` did not strip `last-applied-configuration` annotation

**File:** `src/k8s_mcp/output/pruning.py:62-64, 78-86` — target nested
`metadata["annotations"]` instead of `metadata` directly; deep-copy to prevent shared refs.

### 3. `matches()` operator precedence bug gates entire OR-chain behind `if self.group`

**File:** `src/k8s_mcp/resolution/models.py:46` — removed dead/redundant last clause.

### 4. `_fuzzy_suggest()` crashes on mixed `list[str | ResourceMeta]`

**File:** `src/k8s_mcp/resolution/resolver.py:98-101` — build unified `ResourceMeta` candidate
pool from core table + discovery cache, call once instead of twice with mixed types.

### 5. kubectl non-zero exit codes never detected — `map_kubectl_error()` was dead code

**File:** `src/k8s_mcp/kubectl/runner.py`, `errors.py`, `tools/*.py`
**Fix:** Added `run_kubectl_checked()` wrapper calling `map_kubectl_error()` on non-zero exit;
updated all tool call sites. Added `tests/unit/test_kubectl_errors.py` (6 tests).

### 6. `k_apply` skipped R8 pre-execution validation

**File:** `src/k8s_mcp/tools/apply.py` — added YAML parsing fallback, kind resolution via
`resolve()`, `validate()` call before execution.

### 7. `k_describe`/`k_exec` bypassed the namespace allowlist and audit logging

**File:** `src/k8s_mcp/server.py` — registered both through the shared dispatch path; added
`"describe"` to `_VERB_MAP`; added `"exec"` to the mutating-audit-log tuple.

### 8. `k_describe`/`k_exec` called `subprocess` directly instead of `kubectl/runner.py`

**File:** `src/k8s_mcp/tools/describe.py:45-53`, `exec_.py:51-59`
**Fix:** Made `-o json` opt-out in `run_kubectl` (`output_format: str | None = "json"`);
updated both tools to call `run_kubectl_checked(..., output_format=None)`.
**Residual gap (not reopened, low priority):** `contexts/kubeconfig.py` still calls
`subprocess.run()` directly — narrow, justified exception, never formally documented as such.

### 10. `k_logs` never applied its documented default `tail=100`

**File:** `src/k8s_mcp/tools/logs.py:26,46,56` — `effective_tail = tail if tail is not None
else 100`, always passed to kubectl and `bound_logs()`.

### 11. `access.py`'s `_VERB_MAP` omitted `"describe"`

**File:** `src/k8s_mcp/access.py:24-28`, `server.py` — added to all three tiers; new tests
`test_readonly_includes_describe`, `test_tool_name_describe`.

### 12. `kubectl/errors.py`: duplicated `"unauthorized"` check (dead condition)

**File:** `src/k8s_mcp/kubectl/errors.py:43` — removed duplicate clause.

### 13. Server failed to start — `FastMCP.add_tool()` API mismatch, plus a `**kwargs` schema incompatibility

**File:** `src/k8s_mcp/server.py`
**Fix (2 rounds):** Round 1 replaced `app.add_tool(...)` with `app.tool(...)` — fixed the
immediate crash but left `_build_tool_fn`'s `**kwargs`-shaped handler, which FastMCP 4.0.4
rejects when building a tool's schema. Round 2 replaced the generic loop entirely with
explicit, individually typed wrapper functions per tool, each calling a shared `_dispatch()`
helper.
**Verified:** booted the server directly at all three access levels, no traceback. 87/87 tests
pass.
**Residual gap at the time (later closed by Issue 41):** no `test_server.py` existed, so this
verification was manual.

### 14. `k_apply`'s validation errors assembled ad hoc, not via `errors.py`

**File:** `src/k8s_mcp/tools/apply.py:54-65`, `errors.py` — added `invalid_manifest()` helper,
replaced both ad hoc dicts.

### 9. Discovery cache parser mis-mapped columns — silently corrupted `ResourceMeta`

**File:** `src/k8s_mcp/resolution/discovery.py:83-158`
**Fix:** Replaced fixed-position column indexing with regex-based parsing matching the real
`kubectl api-resources -o wide` header format. APIVERSION split on `/` for group/version;
VERBS bracket span located via regex; empty SHORTNAMES handled.
**Test:** `tests/unit/test_discovery.py`, 16 tests, new fixture
`tests/fixtures/kubectl_outputs/api_resources_wide.txt`.

### 15. `k_get` crashed with `'bytes' object has no attribute 'read'` on `pods`

**File:** `src/k8s_mcp/resolution/core_table.py:20-24` — blocked all resource operations.
**Fix:** `_load_toml()` changed from `tomllib.load(raw)` to
`tomllib.loads(raw.decode("utf-8"))`.
**Test:** `tests/unit/test_core_table.py`, 5 tests against the real `data/core_resources.toml`.

### 16. `k_get` with `all_namespaces=true` rejected `pods` — required explicit `namespace`

**File:** `src/k8s_mcp/resolution/resolver.py:107-142`, `tools/get.py:44` — added
`all_namespaces: bool = False` to `validate()`, allows `namespace=None` when `True`.

### 17. `k_exec`'s `-c <container>` flag placed after the `--` separator

**File:** `src/k8s_mcp/tools/exec_.py:44-49` — container selection silently did nothing;
kubectl requires `-c` before `--`. Reordered args. New `tests/unit/test_tools_exec.py`
(7 tests) asserting the exact resulting arg list.

### 18. `k_list_contexts` silently swallowed kubeconfig-read errors

**File:** `src/k8s_mcp/tools/contexts.py:24-26` — a real read failure was indistinguishable
from "legitimately zero contexts." Fixed to propagate as `success=False`.

### 19. `k_get`'s `annotation_selector` always returned zero matches combined with `name`

**File:** `src/k8s_mcp/tools/get.py` (filtering block)
**Root cause:** `items = data.get("items", [data] if "kind" not in data else [])` — every real
object has `"kind"`, so single-resource fetches always took the `else` branch, producing `[]`.
**Fix:** `is_list = "items" in data; items = data["items"] if is_list else [data]`.
**Test:** `test_annotation_selector_single_resource_match`/`_no_match`, asserting actual match
content.

### 20. `k_get`'s `output=wide` was byte-identical to the default output

**File:** `src/k8s_mcp/output/bounding.py` — the `"wide"` branch just called
`bound_get_names(data)`, same as no `output` at all.
**Fix:** `get.py` now invokes kubectl with the actual `-o wide` flag, returns the plain-text
table verbatim as `{"output": ...}`. Dead `"wide"` branch removed from `bounding.py`.

### 21. `annotation_selector` + `output=wide` silently dropped the selector

**File:** `src/k8s_mcp/tools/get.py` — added explicit fail-fast rejection (`invalid_selector`),
mirroring the existing `jsonpath_template` incompatibility check.

### 23. `k_apply`/`k_patch`'s `output=json`/`yaml` was non-functional

**File:** `src/k8s_mcp/tools/apply.py:114`, `patch.py:80` — same class as Issue 20. Fixed via
`apply_output_format()` call after `prune()`; `output="wide"` explicitly rejected. 6 new tests.

### 24. `events` resource required per-context discovery on every call

**File:** `src/k8s_mcp/data/core_resources.toml` — added core-table entry (`canonical="events"`,
`shortnames=["ev"]`, `kind="Event"`, `verbs=["get"]`). Cold-start/TTL latency only, not a
correctness bug.

### 25. Discovery cache never refreshed on cold/TTL-expired cache

**File:** `src/k8s_mcp/resolution/resolver.py:70-95`
**Root cause:** the "attempt discovery refresh" block was nested inside `if cached is not
None:` — `DiscoveryCache.get()` returns `None` on cold cache and TTL expiry, so `refresh()`
was never called.
**Fix:** restructured tier-2 logic to call `refresh()` first when `cached is None`.
**Test:** `test_resolve_with_discovery_cache_cold_refresh`,
`test_resolve_with_discovery_cache_cold_resource_not_found`. 208 tests pass.

### 26. A passing test asserted Issue 25's broken behavior as correct

**File:** `tests/unit/test_resolver.py:118-124` — the one test exercising the cold-cache path
never mocked `refresh()`, so it couldn't distinguish "gave up after trying" from "never
attempted." Replaced with two tests that do mock `refresh()`.

### 27. `k_list_resources` returned an empty list against a live cluster

**File:** `src/k8s_mcp/resolution/discovery.py:68-81`
**Root cause:** `_parse_api_resources()` returning `[]` on an unrecognized output shape was
silently cached as a legitimate empty success.
**Fix:** Added `discovery_failure()` error helper; `refresh()` now returns it when kubectl
succeeds but the parser finds zero resources. 210 tests pass.

### 28. `_parse_api_resources()` regex expected `[bracketed]` verbs/categories — actual output is plain comma-separated text

**File:** `src/k8s_mcp/resolution/discovery.py:132-141,174-177`
**Fix:** Regex changed from `\s+\[([^\]]*)\]` to `\s+(\S+)` (VERBS) / `(?:\s+(\S+))?`
(CATEGORIES); verbs-split changed from space-split to comma-split.
**Verified:** `_parse_api_resources()` now returns 254 resources (previously 0).

### 29. `jsonpath_template` gave a cryptic error for nested-brace multi-field syntax

**File:** `errors.py`, `resolution/jsonpath_validation.py`, `tools/get.py`/`apply.py`/
`patch.py`, `server.py` — not a code defect (kubectl correctly rejected it), but the raw
kubectl error gave zero actionable guidance for a proven-common mistake. See FR8 above for the
fix (same change).

### 30. `k_logs` completely broken — `unknown shorthand flag: 'o' in -o`

**File:** `src/k8s_mcp/tools/logs.py:61` — `kubectl logs` has no `-o`/`--output` flag at all;
`handle_logs()` fell through to the function's default `output_format="json"`.
**Fix:** `run_kubectl_checked(context, args, output_format=None)`. Same class as Issue 8,
missed at the time.

### 31. `k_delete` completely broken — kubectl rejects `-o json` (`delete` only supports `-o name`)

**File:** `src/k8s_mcp/tools/delete.py:56` — same root cause as Issue 30, different tool.
**Fix:** `output_format=None`. Non-JSON stdout falls back to `{"message": ...}` (already
handled). Verified red/green: new test fails against pre-fix code, passes with fix.

### 32. `discovery.py`'s `refresh()` built a redundant `-o json -o wide` invocation

**File:** `src/k8s_mcp/resolution/discovery.py:73` — same bug class as 8/30/31, but confirmed
cosmetic: pflag last-value-wins semantics meant the trailing `-o wide` always won; diffed both
invocations byte-for-byte against a real cluster, identical. Fixed anyway (`output_format=None`)
since relying on undocumented flag-override behavior is fragile.

### 33. `--kubeconfig` silently ignored by every tool except `k_list_contexts`

**File:** `src/k8s_mcp/kubectl/runner.py`, `cli.py`, `server.py`, `contexts/kubeconfig.py`,
`tools/contexts.py`
**Root cause:** `run_kubectl()` never included `--kubeconfig` regardless of what the server was
started with; only `k_list_contexts` ever received the resolved paths.
**Resolution:** removed `--kubeconfig` entirely rather than threading it through every handler
— the flag's only legitimate use case (multiple kubeconfig files) is already solved by
kubectl's own `$KUBECONFIG` env var. See PRD §11's rejected-alternatives entry for the
decision. 229 tests pass (224 after removing 5 obsolete + 5 new in `test_kubeconfig.py`).

### 34. `list_kubeconfig_contexts()` didn't merge contexts across multiple `--kubeconfig` paths

**File:** `src/k8s_mcp/contexts/kubeconfig.py` — moot by Issue 33's resolution (the multi-path
case no longer exists). Resolved by the same removal.

---

## Documentation Process

### Issue 22 — chronic PRD/SPEC drift behind shipped code (9 recorded recurrences)

Recurred at every FR shipped in this project's active-development window: `k_get`'s
`output=wide`/`annotation_selector` rows (1st, 2nd); `k_apply`'s `src_file` Required-column
formatting and a stale SPEC status line (3rd, 4th); FR11's stale "decision needed" blurbs plus
an un-updated Module Layout tree (5th); FR12's missing module-tree entries and missing PRD §6
row (6th, 7th); FR13's missing module-tree entry, missing PRD §6 row, and a stale PRD §12
status paragraph, across four locations at once (8th); and — notably, on the exact commit that
fixed Issue 39 itself — five more stale references left behind in `PRD.md`/`SPEC.md` by
commit `5ce466b` (9th), including SPEC §2 flatly stating `test_server.py` "does NOT exist yet"
after it had already shipped.

**Resolution:** rather than patch a 10th recurrence individually, added a **Definition of
Done** checklist to `KNOWN_ISSUES.md` (2026-09-25) — a Status line may not claim "implemented"
until dispatch-path tests exist, SPEC §2's module tree lists the new module, PRD §6 has a row
for the tool, PRD §12's tool-count paragraph is re-dated, README's tool table has a row, and
the test count/commit hash are independently verified, not estimated. This checklist remains
the live process guideline — see `KNOWN_ISSUES.md`.
