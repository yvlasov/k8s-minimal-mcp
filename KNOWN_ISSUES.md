# Known Issues

## OPEN (not yet fixed)

### 32. `discovery.py`'s `refresh()` builds a redundant/conflicting `-o json` + `-o wide` kubectl invocation — suspected, not yet live-confirmed

**File:** `src/k8s_mcp/resolution/discovery.py:73`
**Severity:** Unconfirmed — likely low/harmless in practice, but undocumented and untested. Same bug *class* as Issues 8/30/31 (a call site relying on `run_kubectl`'s default `output_format="json"` when the subcommand doesn't want JSON), found by code reading after fixing those three, not by a live failure report — flagging honestly as lower-confidence than those.
**Suspected root cause:** `refresh()` calls `run_kubectl(context, ["api-resources", "-o", "wide"])` without overriding `output_format`, so the default `output_format="json"` still applies, producing `kubectl --context <ctx> -o json api-resources -o wide` — two `-o` flags in one invocation. Unlike Issues 8/30/31 (where the subcommand accepts zero or a single fixed `-o` value, so the lone unwanted `-o json` was rejected outright), here a *second*, intentional `-o wide` follows it in `args`. kubectl's flag library (pflag) uses last-value-wins semantics for a repeated string flag, so `-o wide` likely silently overrides the leading `-o json` — which would also explain why Issues 27/28's live testing surfaced a *parsing* problem (bad regex) rather than a *command-rejected* problem: the command probably succeeded throughout, shaped by `-o wide` as intended, with the leading `-o json` silently discarded.

**Plan — confirm before fixing:**
1. Run `kubectl api-resources -o wide` normally, then `kubectl -o json api-resources -o wide` against any real cluster (or a local `kind`/`minikube`/`docker-desktop`) and diff the two outputs byte-for-byte.
2. If identical: confirms last-value-wins, this has been cosmetic/harmless all along. If different, or if the second command errors: this is a live bug of the same severity as Issues 8/30/31 and should be re-filed as confirmed, not left at this severity.

**Plan — fix (do regardless of step 1's outcome — relying on undocumented flag-override behavior is fragile either way):**
1. `discovery.py:73` → `run_kubectl(context, ["api-resources", "-o", "wide"], output_format=None)` — makes the single intended `-o wide` explicit, removes the redundant/conflicting duplicate.
2. Add a test to `tests/unit/test_discovery.py` asserting `run_kubectl` is called with `output_format=None`. This closes a real, separate gap: the file currently has **zero** assertions on what arguments/kwargs actually reach `run_kubectl` — only the mocked return value's `stdout`/`error` are ever checked — which is exactly the class of blind spot that let Issues 25-28 (and this one) go unnoticed for as long as they did.
3. Run the full suite to confirm no regression.

**Status:** open — not yet fixed, not yet empirically confirmed either way.

---

## FIXED

### 1. `bound_get_names({})` returns `[{}]` instead of `[]`

**File:** `src/k8s_mcp/output/bounding.py:26`
**Fix:** Added early return guard for empty dict before the `"kind"` check.

---

### 2. `prune()` does not strip `last-applied-configuration` annotation

**File:** `src/k8s_mcp/output/pruning.py:62-64, 78-86`
**Fix:** Target nested `metadata["annotations"]` dict instead of `metadata` directly; deep-copy annotations in `_deep_copy_dict()` to prevent shared references.

---

### 3. `matches()` operator precedence bug gates entire OR-chain behind `if self.group`

**File:** `src/k8s_mcp/resolution/models.py:46`
**Fix:** Removed the dead/redundant last clause — `fully_qualified_name` already covers every case.

---

### 4. `_fuzzy_suggest()` crashes on mixed `list[str | ResourceMeta]`

**File:** `src/k8s_mcp/resolution/resolver.py:98-101`
**Fix:** Build unified `ResourceMeta` candidate pool from core table + discovery cache, call `_fuzzy_suggest` once instead of twice with mixed types.

---

### 5. kubectl non-zero exit codes are never detected — `map_kubectl_error()` is dead code

**File:** `src/k8s_mcp/kubectl/runner.py`, `src/k8s_mcp/kubectl/errors.py`, `src/k8s_mcp/tools/*.py`
**Fix:** Added `run_kubectl_checked()` wrapper that calls `map_kubectl_error()` on non-zero exit codes; updated all tool call sites (`get.py`, `logs.py`, `apply.py`, `patch.py`, `delete.py`, and later `describe.py`/`exec_.py` via Issue 8) to use it; added `tests/unit/test_kubectl_errors.py`.
**Verified:** confirmed by reading `runner.py`/`errors.py` and every tool call site directly — all route through `run_kubectl_checked`; 6/6 new tests in `test_kubectl_errors.py` pass.

---

### 6. `k_apply` skips R8 pre-execution validation

**File:** `src/k8s_mcp/tools/apply.py`
**Fix:** Added YAML parsing fallback (`yaml.safe_load`), kind resolution via `resolve()`, and `validate()` call before execution.
**Verified:** confirmed directly — `handle_apply()` now resolves `kind` → `ResourceMeta` and calls `validate()` before touching `run_kubectl_checked`, matching every other mutating tool. The two validation error paths this fix originally added as ad hoc dicts were subsequently moved onto `errors.py` helpers — see Issue 14.

---

### 7. `k_describe` / `k_exec` bypass the namespace allowlist and audit logging

**File:** `src/k8s_mcp/server.py`
**Fix:** Registered `k_describe` and `k_exec` through the same shared dispatch path as every other tool; added `"describe"` to `_VERB_MAP`; added `"exec"` to the mutating-audit-log tuple.
**Verified:** confirmed directly in `server.py` — both tools route through `_dispatch(...)` (the successor to the original `_build_tool_fn`, see Issue 13), `"exec"` is in the audit-log tuple.

---

### 8. `k_describe` / `k_exec` call `subprocess` directly instead of `kubectl/runner.py`

**File:** `src/k8s_mcp/tools/describe.py:45-53`, `src/k8s_mcp/tools/exec_.py:51-59`
**Fix:** Made `-o json` opt-out in `run_kubectl` (`output_format: str | None = "json"` parameter); updated `describe.py` and `exec_.py` to call `run_kubectl_checked(context, args, output_format=None)` instead of `subprocess.run()` directly.
**Verified:** confirmed directly — neither file imports `subprocess` anymore. **Residual gap (not reopened, just flagged):** `src/k8s_mcp/contexts/kubeconfig.py:9,23` still calls `subprocess.run()` directly and remains untouched — the original solution plan's option (b) ("explicitly document this file as a narrow, justified exception... and leave it as is") would resolve this with a one-line comment, but that comment was never added. Low priority; the higher-risk call sites (describe/exec, which run arbitrary/mutating-adjacent commands) are fixed.

---

### 10. `k_logs` never applies its documented default `tail=100`

**File:** `src/k8s_mcp/tools/logs.py:26,46,56`
**Fix:** Applied default `tail=100` at the tool boundary — `handle_logs()` now resolves `effective_tail = tail if tail is not None else 100` and always passes `--tail` to kubectl and `bound_logs()`.
**Verified:** confirmed directly in `logs.py`.

---

### 11. `access.py`'s `_VERB_MAP` omits `"describe"`, drifting from R7's stated source of truth

**File:** `src/k8s_mcp/access.py:24-28`, `src/k8s_mcp/server.py`
**Fix:** Added `"describe"` to all three tiers in `_VERB_MAP`; updated `server.py` registration to check `"describe" in allowed`; added `test_readonly_includes_describe` and `test_tool_name_describe` to `tests/unit/test_access.py`.
**Verified:** confirmed directly in `access.py`; both new tests pass.

---

### 12. `kubectl/errors.py`: duplicated `"unauthorized"` check (dead condition)

**File:** `src/k8s_mcp/kubectl/errors.py:43`
**Fix:** Removed the duplicate `"unauthorized" in stderr_lower` clause.
**Verified:** confirmed directly.

---

### 13. Server fails to start at all — `FastMCP.add_tool()` API mismatch, plus a deeper `**kwargs` schema incompatibility

**File:** `src/k8s_mcp/server.py`
**Fix (2 rounds):** Round 1 replaced `app.add_tool(wrapped, name=..., description=...)` with `app.tool(wrapped, name=..., description=...)` — fixed the immediate crash, but left `_build_tool_fn`'s `**kwargs`-shaped handler in place, which FastMCP 4.0.4 rejects when building a tool's schema (`ValueError: Functions with **kwargs are not supported as tools`) — round 1 was reopened after this was reproduced live. Round 2 replaced the generic `_build_tool_fn`/`_TOOL_DEFS` loop entirely with explicit, individually typed wrapper functions per tool (`get`, `logs`, `apply`, `patch`, `delete`, `describe`, `exec_cmd`), each registered via `@app.tool(name=..., description=...)`, with shared allowlist/audit-log/discovery-cache logic factored into a `_dispatch()` helper each wrapper calls.
**Verified:** booted the server myself, `uv run k8s-mcp --access-level {readonly,readwrite,admin}` — all three start cleanly and reach `"Starting MCP server 'k8s-minimal-mcp' with transport 'stdio'"` with no traceback. 87/87 tests pass. Genuinely fixed.
**Still open (low priority, not re-blocking):** no `tests/unit/test_server.py` was added, so this verification was manual, not automated — a future regression here wouldn't be caught by the suite. `pyproject.toml`'s `fastmcp` pin is also still unbounded (`fastmcp>=0.2`) rather than pinned to a tested range.

---

### 14. `k_apply`'s new validation errors are assembled ad hoc, not via `errors.py`

**File:** `src/k8s_mcp/tools/apply.py:54-65`, `src/k8s_mcp/errors.py`
**Fix:** Added `invalid_manifest(context: str, detail: str)` helper to `errors.py` with new `ERROR_INVALID_MANIFEST = "invalid_manifest"` constant. Replaced both ad hoc dicts in `apply.py` with calls to the new helper.
**Verified:** confirmed directly — `apply.py` imports and calls `invalid_manifest(...)` for both the empty-manifest and missing-`kind` cases; `errors.py` has the new helper matching the existing pattern. 87/87 tests pass.

---

### 9. Discovery cache parser still mis-maps columns — now produces silently-corrupted `ResourceMeta`, not just an empty result

**File:** `src/k8s_mcp/resolution/discovery.py:83-158`
**Fix:** Replaced fixed-position column indexing with regex-based parsing that correctly handles the real `kubectl api-resources -o wide` header format (`NAME SHORTNAMES APIVERSION NAMESPACED KIND VERBS CATEGORIES`). APIVERSION is split on `/` to recover group/version. VERBS bracket span is located via regex. Empty SHORTNAMES columns are handled correctly.
**Test:** Added `tests/unit/test_discovery.py` with 16 tests covering core resources, apps resources, CRDs, cluster-scoped resources, empty output, separator lines, and edge cases. Created fixture at `tests/fixtures/kubectl_outputs/api_resources_wide.txt`.
**Verified:** 103/103 tests pass (87 original + 16 new).

---

### 15. `k_get` crashes with `'bytes' object has no attribute 'read'` on `pods` resource

**File:** `src/k8s_mcp/resolution/core_table.py:20-24`
**Severity:** Blocks all resource operations — `load_core_table()` fails unconditionally on first call, affecting every tool that calls `resolve()` (`k_get`, `k_logs`, `k_apply`, `k_patch`, `k_delete`, `k_describe`, `k_exec`). Only `k_list_contexts` is unaffected.
**Fix:** Changed `_load_toml()` from `tomllib.load(raw)` (expects file object) to `tomllib.loads(raw.decode("utf-8"))` (correct for already-in-memory bytes).
**Test:** Added `tests/unit/test_core_table.py` with 5 tests calling `load_core_table()` unmocked against the real `data/core_resources.toml`, asserting non-empty result and specific resources (`pods`, `deployments`, `services`) with correct metadata.
**Verified:** 108/108 tests pass (103 original + 5 new).

---

### 16. `k_get` with `all_namespaces=true` rejects `pods` resource — requires explicit `namespace`

**File:** `src/k8s_mcp/resolution/resolver.py:107-142`, `src/k8s_mcp/tools/get.py:44`
**Severity:** Blocks cross-namespace pod listing
**Fix:** Added `all_namespaces: bool = False` parameter to `validate()` in `resolver.py`; updated namespace-scope check to allow `namespace=None` when `all_namespaces=True`; updated `get.py:44` to pass `all_namespaces=all_namespaces` to `validate()`.
**Test:** Added 2 tests in `tests/unit/test_resolver.py` (`test_validate_namespaced_with_all_namespaces`, `test_validate_namespaced_without_all_namespaces_still_rejects`); added `tests/unit/test_tools_get.py` with 3 tests for `handle_get` with `all_namespaces=True/False`.
**Verified:** 113/113 tests pass (108 original + 5 new).

---

### 17. `k_exec`'s `-c <container>` flag placed after the `--` separator — container selection silently doesn't work

**File:** `src/k8s_mcp/tools/exec_.py:44-49`
**Severity:** `k_exec`'s documented `container` param (PRD §6) never actually selected a container — kubectl requires `-c <container>` *before* `--`; the original code appended it *after*, so it was passed through as part of the executed command instead of being parsed as kubectl's own flag.
**Fix:** Reordered args to `["exec", pod]` → `["-c", container]` (if set) → `"--"` → `command`.
**Test:** Added `tests/unit/test_tools_exec.py` (new file, 7 tests) — `test_container_flag_placed_before_separator` asserts the exact resulting arg list `["exec", "mypod", "-c", "sidecar", "--", "ls", "-l"]`.
**Verified:** confirmed directly in `exec_.py`; found while scoping test coverage for previously-untested tool modules (FR4), fixed alongside adding the tests rather than left as a documented gap.

---

### 18. `k_list_contexts` silently swallows kubeconfig-read errors, returning an empty context list

**File:** `src/k8s_mcp/tools/contexts.py:24-26`
**Severity:** A real kubeconfig-read failure was indistinguishable from "this kubeconfig legitimately has zero contexts" — the model had no way to tell the two apart.
**Fix:** `handle_list_contexts` now returns `envelope(result, context, "k_list_contexts", success=False)` on error instead of `envelope_list_contexts([], context)`.
**Test:** Added `tests/unit/test_tools_contexts.py` (new file) asserting an error from `list_kubeconfig_contexts()` propagates as a visible `success=False` response, not a silently empty list.
**Verified:** confirmed directly; found and fixed alongside Issue 17 as part of the same FR4 test-coverage pass.

---

### 19. `k_get`'s `annotation_selector` always returns zero matches when combined with `name` (single-resource fetch)

**File:** `src/k8s_mcp/tools/get.py` (filtering block, now at lines 119-135)
**Severity:** Shipped broken in the initial `annotation_selector` implementation — the feature was completely non-functional for `k_get <resource> <name> annotation_selector=...`, arguably the single most natural way to use it, while working correctly for unnamed/list queries. Shipped with 9 passing tests, none of which exercised the single-resource path.
**Root cause:** `items = data.get("items", [data] if "kind" not in data else [])` — every real k8s object has a `"kind"` field, so for a single-resource fetch (no `"items"` key present) the ternary always took the `else` branch, producing `[]` instead of the intended `[data]`. The condition was inverted.
**Fix:** Replaced with `is_list = "items" in data; items = data["items"] if is_list else [data]`, and rebuilt the surrounding block to construct a corrected `data` shape for all three cases (list, single-match, single-no-match) instead of mutating the original object in place.
**Test:** Added `test_annotation_selector_single_resource_match` and `test_annotation_selector_single_resource_no_match` to `tests/unit/test_tools_get.py`, asserting actual match content (`matched == 1`, `items[0]["name"] == "mypod"`), not just absence of a crash — verified these would have caught the original bug (under the old code, the "match" test's assertion would have failed).
**Verified:** confirmed by tracing execution against all three response shapes by hand, not just re-reading the diff.

---

### 20. `k_get`'s `output=wide` was byte-identical to the default (unrequested) output — not a distinct format at all

**File:** `src/k8s_mcp/output/bounding.py` (formerly lines 112-114 of `apply_output_format`)
**Severity:** Documented in PRD §6 as a distinct on-request alternative to name-only output; in practice a caller requesting `output=wide` got nothing beyond the default — `apply_output_format`'s `"wide"` branch just called `bound_get_names(data)`, the same function used when no `output` was given at all.
**Root cause:** kubectl's real `-o wide` output is resource-kind-specific (computed columns like pod `AGE`/`STATUS`/`IP`, entirely different for a deployment or node) — reproducing it generically from already-fetched JSON would mean reimplementing kubectl's own per-kind table-printer logic in Python, which was never attempted; the `"wide"` branch was a stub that fell back to the name-only shape instead.
**Fix:** `tools/get.py` now has an early branch — `output == "wide"` invokes kubectl with the actual `-o wide` flag (`run_kubectl_checked(context, args, output_format="wide")`) and returns kubectl's own plain-text table verbatim as `{"output": result["stdout"]}`, same precedent as `k_describe`'s text passthrough, instead of trying to derive it from the default `-o json` fetch. The now-dead `"wide"` branch in `bounding.py` was removed.
**Test:** Added `TestHandleGetWide` in `tests/unit/test_tools_get.py` — asserts `run_kubectl_checked` is called with `output_format="wide"` (not the default `"json"`) and the response is the raw text, untouched by `prune()`/`bound_get_names()`.
**Verified:** confirmed directly in both files; `apply_output_format` no longer mentions `"wide"` at all.

---

### 21. `annotation_selector` + `output=wide` combined silently dropped the selector with no error

**File:** `src/k8s_mcp/tools/get.py`
**Severity:** Low — `wide`'s raw-text output was never filterable to begin with, so no data-correctness issue, but the two structurally similar "incompatible with filtering" combinations were handled inconsistently: `annotation_selector` + `jsonpath_template` was explicitly rejected with an `invalid_selector` error, while `annotation_selector` + `output=wide` silently ignored the selector and returned the unfiltered wide text with no indication filtering didn't happen.
**Fix:** Added an explicit fail-fast rejection for `annotation_selector` + `output=wide`, mirroring the existing `jsonpath_template` check — both now return `invalid_selector` before any kubectl call.
**Test:** Added `test_annotation_selector_rejects_output_wide` to `tests/unit/test_tools_get.py`, asserting the error and that `run_kubectl_checked` is never called.
**Verified:** confirmed directly; found during review of Issue 20's fix, fixed immediately rather than left as a follow-up.

---

### 22. PRD §6's Tool Specification table repeatedly fell behind shipped, model-facing tool params

**File:** `PRD.md` §6 (Tool Specification table)
**Severity:** Documentation-only, but persistent — happened twice in a row (once when `output=jsonpath`/`jsonpath_template` shipped for `k_get`/`k_apply`/`k_patch`, again when `annotation_selector` shipped for `k_get`) before being corrected, meaning the table was inaccurate against the running code for multiple review rounds each time.
**Fix:** §6's `k_get` row now lists `annotation_selector` alongside `jsonpath_template`, and its description column accurately reflects `output=wide`'s real behavior (kubectl's own `-o wide` text passthrough) instead of the stale "byte-identical to default, known gap" note, plus the new `annotation_selector` incompatibility rules (rejects both `jsonpath_template` and `output=wide`).
**Note:** this is a process gap, not a one-off mistake — nothing currently forces §6 to be touched in the same change that ships a new tool param. No code fix applies here; flagging so a future param addition doesn't repeat the pattern a third time.

---

### 23. `k_apply`/`k_patch`'s `output=json`/`yaml` was non-functional

**File:** `src/k8s_mcp/tools/apply.py:114`, `src/k8s_mcp/tools/patch.py:80`
**Severity:** Same class of gap as Issue 20 (`k_get`'s `output=wide`) — `output` was documented (PRD §6) as accepting `json`/`yaml`, but the code only ever checked it against `"jsonpath"`; any other value was silently ignored.
**Fix:** Added an `apply_output_format()` call after `prune()` in both tools' non-jsonpath success paths — `output="yaml"` now returns `{"_yaml": <string>}`, `output="json"`/unset is unchanged. Added an explicit `invalid_output` fail-fast rejection for `output="wide"` on both tools (kubectl's `-o wide` has no meaningful semantics for `apply`/`patch`), chosen over a silent no-op per the SPEC's own recommendation.
**Test:** `TestHandleApplyOutputFormat`/`TestHandlePatchOutputFormat` in `tests/unit/test_tools_apply.py`/`test_tools_patch.py` — `test_output_yaml`, `test_output_json`, `test_output_wide_rejected` in each (6 new tests total).
**Verified:** confirmed directly — both tools call `apply_output_format(pruned, output)`; `output="wide"` fails fast via `invalid_output` before `resolve()`/kubectl in both. **Note:** PRD §6's table described this exact behavior as a "known gap" for three review rounds after it shipped, until corrected alongside this entry — the same drift pattern Issue 22 was written to flag, recurring once more. §6 is now updated (see PRD.md's `k_apply` row).

---

### 24. `events` resource required per-context discovery on every call

**File:** `src/k8s_mcp/data/core_resources.toml`
**Severity:** Low — discovery-cache fallback (R5) already worked, this was a cold-start/TTL latency cost, not a correctness bug. Flagged because `events` is a stable core `v1` kind (not a CRD) and fits the core table's own inclusion criteria exactly, same as `pods`/`services`/etc.
**Fix:** Added a `[[resource]]` entry (`canonical="events"`, `shortnames=["ev"]`, `kind="Event"`, `group=""`, `version="v1"`, `namespaced=true`, `verbs=["get"]`) — purely additive data-file change, no logic touched. PRD R2's rule text (the hardcoded core-table list) updated to include it.
**Test:** `test_core_table.py::test_contains_events`; `test_resolver.py::test_resolve_events_from_core_table`, `test_resolve_events_by_shortname`.
**Verified:** confirmed directly — `resolve(context, "events", discovery_cache=None)` resolves from the core table alone, no discovery cache touched; checked all 16 entries for `canonical`/`shortnames`/`kind` collisions, none found.

---

### 25. Discovery cache never refreshes on a cold or TTL-expired cache — `resolve()` only retries when the cache already has *some* entries

**File:** `src/k8s_mcp/resolution/resolver.py:70-95`
**Severity:** Blocks every resource not in `core_resources.toml` (CRDs, `serviceaccounts`, `componentstatuses`, `customresourcedefinitions`) on the first call for any given context, and again every time the 5-minute discovery-cache TTL lapses.
**Root cause:** the entire "attempt discovery refresh" block was nested inside `if cached is not None:` — `DiscoveryCache.get()` returns `None` on cold cache and TTL expiry, so `refresh()` was never called.
**Fix:** Restructured tier 2 logic: when `cached is None`, call `refresh()` first; collapse duplicated match/ambiguous blocks into one unified block. Added `cast(list[ResourceMeta], refresh_result)` for type narrowing.
**Test:** `test_resolve_with_discovery_cache_cold_refresh` — mocks `refresh()` to return populated list, asserts `resolve()` finds the resource. `test_resolve_with_discovery_cache_cold_resource_not_found` — mocks `refresh()` to return a list without the resource, asserts `unknown_resource`.
**Verified:** confirmed directly — `resolve()` now calls `refresh()` on cold cache; 208 tests pass (2 new tests added).

---

### 26. `test_resolve_with_discovery_cache_miss` asserted Issue 25's broken behavior as correct — the reason 207 passing tests never caught it

**File:** `tests/unit/test_resolver.py:118-124`
**Severity:** Test-quality issue — the one test exercising the cold-cache path asserted the bug was intended behavior.
**Root cause:** constructed a genuinely empty `DiscoveryCache()` and asserted `resolve()` should give up, without mocking `refresh()` — couldn't distinguish "correctly gave up after trying discovery" from "never attempted discovery."
**Fix:** Replaced with two tests: `test_resolve_with_discovery_cache_cold_refresh` (mocks `refresh()`, asserts resource is found) and `test_resolve_with_discovery_cache_cold_resource_not_found` (mocks `refresh()`, asserts `unknown_resource` when resource genuinely not in discovery output).
**Verified:** both new tests pass; old broken test removed.

---

### 27. `k_list_resources` returned an empty resource list against a live cluster — root cause not yet confirmed, and not explained by Issue 25

**File:** `src/k8s_mcp/resolution/discovery.py:68-81`
**Severity:** `k_list_resources(context="<ctx>", search="") → {"resources":[],"count":0}` on a cluster with 200+ real resource types. The `list_resources.py` tool already calls `refresh()` unconditionally on cache miss (no nesting bug), so the issue was that `refresh()` silently passed through an empty parse result as a valid success.
**Root cause:** `_parse_api_resources()` returns `[]` silently when the output doesn't match the expected header/data format (e.g., different kubectl version output shape). `refresh()` treated this as a legitimate (if empty) success and cached it, so subsequent calls returned an empty list.
**Fix:** Added `discovery_failure()` error helper to `errors.py`. Modified `refresh()` to check if `_parse_api_resources()` returns `[]` after a successful kubectl call and return a `discovery_failure` error dict instead of silently passing through the empty list. Every real cluster has core resources, so an empty parse result is evidence of a parsing failure.
**Test:** `TestDiscoveryCacheRefresh::test_refresh_returns_error_on_empty_output` — mocks `run_kubectl` to return empty stdout, asserts `discovery_failure` error is returned. `TestDiscoveryCacheRefresh::test_refresh_succeeds_with_valid_output` — mocks `run_kubectl` to return valid fixture, asserts resources are parsed and cached.
**Verified:** 210 tests pass (2 new tests added); `refresh()` now returns `{"error": "discovery_failure", "detail": "..."}` when kubectl succeeds but parser finds no resources.

---

### 28. `_parse_api_resources()` regex expected `[brackets]` around verbs/categories — `kubectl api-resources -o wide` outputs them as plain comma-separated text, so 0 resources parsed

**File:** `src/k8s_mcp/resolution/discovery.py:132-141` (regex pattern), `src/k8s_mcp/resolution/discovery.py:174-177` (verbs-split)
**Severity:** Even after Issues 25-27 were fixed, the discovery cache parsed **zero** resources because the regex expected bracketed verbs/categories (`[create,delete,...]`) but `kubectl api-resources -o wide` outputs them as plain space-separated text (`create,delete,...`). Every data line failed to match, `_parse_api_resources()` returned `[]`, and `refresh()` returned `discovery_failure`.
**Root cause:** The regex pattern used `\s+\[([^\]]*)\]` for both VERBS and CATEGORIES groups, but the actual kubectl output has no brackets — verbs and categories are just the last space-separated tokens on each line. Additionally, the verbs-split code used `verbs_str.split()` (space-split) instead of `verbs_str.split(",")` (comma-split), since kubectl uses commas within the verb list.
**Fix:** Changed regex from `\s+\[([^\]]*)\]` to `\s+(\S+)` for VERBS and `(?:\s+(\S+))?` for optional CATEGORIES. Changed verbs-split from `verbs_str.split()` to `verbs_str.split(",")`. Updated docstring to reflect actual kubectl output format.
**Verified:** direct test — `_parse_api_resources(kubectl_output)` now returns 254 resources (previously 0); MCP calls to `customresourcedefinitions`, `serviceaccounts`, `horizontalpodautoscalers`, `limitranges` all succeed via discovery cache.

---

### 29. `k_get`'s `jsonpath_template` gives a cryptic, unhelpful error for a specific invalid-syntax mistake (nested `{...}` for multi-field extraction) — not a code defect, but worth fixing anyway

**File:** `src/k8s_mcp/errors.py`, `src/k8s_mcp/resolution/jsonpath_validation.py`, `src/k8s_mcp/tools/get.py`, `src/k8s_mcp/tools/apply.py`, `src/k8s_mcp/tools/patch.py`, `src/k8s_mcp/server.py`
**Severity:** Not a code defect — the MCP server correctly propagated kubectl's rejection via `kubectl_failure`. But the raw kubectl error (`unrecognized character in action: U+007B '{'`) gives the calling model zero actionable guidance, and the nested-brace mistake (`{.items[*].{a,b}}`) is a natural, tempting analogy to other dict/object-literal syntaxes — now proven to occur in practice.
**Root cause:** Nested braces for multi-field extraction is not valid Kubernetes jsonpath syntax. The correct syntax is the bracket-list form (`{.items[*]['field1','field2']}`) or a `{range .items[*]}...{end}` loop. kubectl's own jsonpath engine (built on Go's `text/template` action parser) rejects it.
**Fix:** Added `ERROR_INVALID_JSONPATH_TEMPLATE` constant and `invalid_jsonpath_template()` helper to `errors.py`. Created new `resolution/jsonpath_validation.py` module with `check_nested_braces()` function that scans templates left-to-right tracking brace depth, returning a detail string if depth exceeds 1. Added the check to `handle_get()`, `handle_apply()`, and `handle_patch()` as an R8-style fail-fast before `resolve()`/kubectl. Updated `server.py`'s `jsonpath_template` descriptions on all three tools to proactively mention the correct syntax. Updated PRD.md §6's `k_get`/`k_apply`/`k_patch` rows.
**Test:** `TestCheckNestedBraces` — 10 tests covering valid (simple field, sibling blocks, range loop, complex valid, empty, no braces, unmatched closing, only opening) and invalid (nested braces, deeper nesting) cases. `TestHandleGetWide::test_nested_brace_jsonpath_template_rejected` / `test_sibling_braces_jsonpath_template_allowed`. `TestHandleApplyOutputFormat::test_nested_brace_jsonpath_template_rejected` / `test_sibling_braces_jsonpath_template_allowed`. `TestHandlePatchOutputFormat::test_nested_brace_jsonpath_template_rejected` / `test_sibling_braces_jsonpath_template_allowed`.
**Verified:** 226 tests pass (16 new tests added); nested-brace templates now fail fast with `{"error": "invalid_jsonpath_template", "jsonpath_template": "...", "detail": "Nested braces are not valid Kubernetes jsonpath syntax. For multiple fields per item use the bracket-list form... or a {range}...{end} loop."}` — `resolve()`/`run_kubectl_checked` never called.

---

### 30. `k_logs` was completely broken — `kubectl` rejects the constructed command with `unknown shorthand flag: 'o' in -o`

**File:** `src/k8s_mcp/tools/logs.py:61`
**Severity:** High — every `k_logs` call failed, unconditionally. Reported live via a real MCP client session (a separately-deployed instance of this server), where two consecutive `k_logs` calls against different pods both failed identically. Since `k_logs` is one of the two most-used readonly tools, this was a total functional break of the tool, not an edge case.
**Root cause:** `handle_logs()` called `run_kubectl_checked(context, args)` without overriding `output_format`, so it fell through to the function's default `output_format="json"` — producing `kubectl --context <ctx> -o json logs <pod> ...`. `kubectl logs` has no `-o`/`--output` flag at all (unlike `get`, which does) — `-o` is only valid there as a *shorthand* alias kubectl doesn't recognize on `logs`, hence the specific `unknown shorthand flag: 'o' in -o` error. This is the exact same class of bug Issue 8 fixed for `k_describe`/`k_exec` — `logs.py` was simply missed at the time and never caught since, because no test asserted what `output_format` value reached `run_kubectl_checked` (only the positional `args` were ever checked).
**Fix:** `run_kubectl_checked(context, args, output_format=None)` — same fix shape as Issue 8, applied to the one tool module that fix pass missed.
**Test:** Added `test_logs_output_format_none` to `tests/unit/test_tools_logs.py`, asserting `mock_run.call_args[1]["output_format"] is None` — same assertion style as `test_describe_output_format_none`/`test_exec_output_format_none`.
**Verified:** confirmed directly in `logs.py`; the live report's cluster/pod/namespace details are not reproduced here — the bug is generic to any `k_logs` call, not specific to any cluster.

---

### 31. `k_delete` was completely broken — kubectl rejects `-o json` with `unexpected -o output mode: json. We only support '-o name'`

**File:** `src/k8s_mcp/tools/delete.py:56`
**Severity:** High — every `k_delete` call fails unconditionally. Same class of bug as Issue 8 (`k_describe`/`k_exec`) and Issue 30 (`k_logs`), and apparently the one call site that pass missed: `delete.py` was not among the files touched by either fix.
**Root cause:** `handle_delete()` called `run_kubectl_checked(context, args)` without overriding `output_format`, so it fell through to the function's default `output_format="json"`, producing `kubectl --context <ctx> -o json delete <resource> <name> -n <namespace>`. `kubectl delete` has no `-o json` support at all — it only accepts `-o name` — so the command was rejected before it ran.
**Reported live via a real MCP client session:** a `k_delete` call against a live cluster (context/resource/namespace details not reproduced here — the bug is generic to any `k_delete` call, not specific to any cluster, same as Issue 30) returned `kubectl_failure` with the exact error above. Verified via a follow-up `k_get` that the target resource was untouched — kubectl rejects the invalid flag before performing the delete, so this was a hard failure, not a silent partial success.
**Fix:** `run_kubectl_checked(context, args, output_format=None)` at `delete.py:56` — same fix shape as Issues 8/30. Without `-o`, `kubectl delete` prints a plain-text confirmation (`deployment.apps/my-deploy deleted`), which the existing non-JSON fallback (`{"message": result["stdout"]}`) already handles — no other code change needed.
**Test:** Added `test_delete_output_format_none` to `tests/unit/test_tools_delete.py`, asserting `mock_run.call_args[1]["output_format"] is None` — same assertion style as `test_logs_output_format_none` (Issue 30) and `test_describe_output_format_none`/`test_exec_output_format_none` (Issue 8).
**Verified:** red/green check — the new test fails with `KeyError: 'output_format'` against the pre-fix code (the old call passed no `output_format` kwarg at all) and passes with the fix; 228/228 tests pass.

---
