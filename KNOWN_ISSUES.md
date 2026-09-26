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

---

## OPEN (not yet fixed)

### 42. `map_kubectl_error()` conflates "resource type unresolvable" with "named object legitimately doesn't exist" — both surface as `unknown_resource`

**File:** `src/k8s_mcp/kubectl/errors.py:36-41` (`map_kubectl_error()`), `tests/unit/test_kubectl_errors.py:20-40` (asserts the conflation as correct)
**Severity:** Medium — doesn't block reads (`raw_stderr` still carries kubectl's real message), but the `error` code itself is actively misleading. Per this project's own `errors.py` docstring, `unknown_resource` means "No GVK matched the requested resource type name" — a resolver-level, pre-kubectl failure. What's actually happening in the cases below is the opposite: the type resolved correctly, kubectl ran, and the API server returned its standard `NotFound` for a specific object that isn't there. The calling model has no way to tell "your resource string is wrong" from "that object just doesn't exist" apart, even though they call for completely different next actions.

**Reproduced live, three times across three different tools (2026-09-25):**
1. `k_get(context="sinsia-pl", resource="ciliumendpoints", name="kubelet", namespace="kube-system", output="yaml")` → `{"error":"unknown_resource","raw_stderr":"Error from server (NotFound): ciliumendpoints.cilium.io \"kubelet\" not found\n"}`. Note `ciliumendpoints.cilium.io` — the fully-qualified type — appears correctly in kubectl's own error text; only the named object is missing (`kubelet` is a host-level process, not a Pod, so no matching CiliumEndpoint was ever going to exist).
2. `k_describe(context="sinsia-pl", resource="pods", name="kubelet", namespace="kube-system")` → `{"error":"unknown_resource","raw_stderr":"Error from server (NotFound): pods \"kubelet\" not found\n"}`. Same shape: `pods` resolved fine, `kubelet` legitimately isn't a Pod object.
3. Reported the same day via a separate investigation (fork), not independently re-run here but identical in shape: `k_exec` against two different pods both confirmed `Running` by `k_get` moments earlier in the same session nonetheless failed with `{"error":"unknown_resource","raw_stderr":"Error from server (NotFound): pods \"...\" not found\n"}` — third call site, same symptom.

**Root cause:** `map_kubectl_error()` pattern-matches the substring `"not found"`/`"notfound"` in kubectl's stderr and unconditionally returns `unknown_resource`, with no distinction between kubectl rejecting the resource *type* (which in practice never reaches this function — `resolve()` already rejects an unresolvable type before kubectl ever runs, per `resolver.py`) and kubectl successfully resolving the type but returning `NotFound` for the object itself, which is kubectl's normal response to `get`/`describe`/`exec` against something that isn't there. Confirmed this isn't an untested blind spot: `test_kubectl_errors.py:20-40` explicitly feeds this function `'pods "x" not found'` and `'Error from server (NotFound): pods "x" not found'` and asserts `unknown_resource` as the *correct* expected result — the conflation is currently by design, not oversight, the same way Issue 26 found a test asserting a different bug as intended behavior.

**Proposed next step:** either (a) add a distinct error code (e.g. `object_not_found`) reserved for a resolved-type-but-missing-object NotFound, or (b) route this case through the existing `kubectl_failure` path instead, which already carries `command`/`stderr`/`exit_code` without claiming anything about resolver correctness. Either direction needs `map_kubectl_error()` to distinguish the two NotFound shapes — likely by checking whether the stderr's resource-type token matches what was actually requested, since kubectl's own message already contains the fully-qualified type in the case that shouldn't be `unknown_resource`. Needs new tests asserting the two cases produce different `error` values; the two existing tests asserting today's conflation would need to be corrected, not just supplemented, per the Issue 26 precedent.

---

### 43. `cilium_troubleshoot_connectivity` prompt (FR11) is scoped to `(namespace, pod)`, doesn't fit the diffuse/fleet-wide symptoms it was built for, and never emits the mandatory `context=` parameter

**File:** `src/k8s_mcp/prompts.py:38-59` (`cilium_troubleshoot_connectivity`), `src/k8s_mcp/server.py:213-215` (prompt registration)
**Severity:** Medium — the prompt runs and returns text, but following its own literal instructions produces non-functional tool calls, and its parameter shape doesn't match the class of problem it was scoped to help with.
**Reported live (2026-09-25):** invoking the shipped prompt via `/mcp__alfa-k8s__cilium_troubleshoot_connectivity kube-system kubelet` correctly bound `namespace="kube-system"`, `pod="kubelet"` and returned the expected Step 1/2/3 text — the argument binding itself works. But two real problems surfaced running it for real:
1. **Missing `context=`.** None of the three generated calls (`k_get(resource="ciliumendpoints", name=..., namespace=..., output="yaml")`, `k_get(resource="ciliumnetworkpolicies", namespace=..., output="yaml")`, `k_describe(resource="pods", name=..., namespace=...)`) include `context=`, yet every `alfa-k8s` tool requires `context` as a mandatory parameter (`server.py`'s `get()`/`describe()` wrappers both declare `context: str` with no default). A calling model following the prompt's literal text verbatim would get a parameter-validation failure on every step, not real data — confirmed by having to add `context="sinsia-pl"` manually to reproduce the prompt's own instructions.
2. **Wrong scoping for the actual use case.** The prompt assumes the caller already knows a specific offending pod. The class of problem this project's own comparison research (this session, 2026-09-25) actually needed Cilium troubleshooting for — the recurring `:10250`/kubelet-connectivity timeout investigated the prior day — is diffuse and fleet-wide (intermittent, spans many nodes/pods, not attributable to one pod up front). Forcing `(namespace, pod)` as required parameters means the prompt can't be invoked at all for exactly the symptom class it was meant to help diagnose; the user explicitly flagged this design mismatch live.

**Requested correction (from the user, 2026-09-25):** change the signature to `(cluster, issue_description)` — `cluster` becomes the `context=` value threaded into every generated call (fixing problem 1 as a side effect), and `issue_description` is free text describing the symptom rather than a specific pod name. Since a static prompt template can't branch on free-text content, the returned guidance needs restructuring into something that covers both a single-pod complaint and a fleet-wide symptom (e.g. two paths: cluster-wide triage via `ciliumnodes`/`ciliumclusterwidenetworkpolicies`/`ciliumidentities` first, narrowing to a specific pod's `ciliumendpoints`/`ciliumnetworkpolicies` only if one is named in the description) rather than a single fixed 3-step recipe that assumes a pod is already known. Should also explicitly note that Cilium's own eBPF drop-reason counters (`cilium_drop_count_total` by `direction`/`reason`) are Prometheus-exposed, not reachable via any `k_*` tool here — relevant context for the fleet-wide path specifically, since that's exactly what the prior day's real investigation used and this tool can't reach.

**Proposed next step:** rewrite `cilium_troubleshoot_connectivity(cluster: str, issue_description: str)` in `prompts.py` per the above, update the `server.py` prompt registration's parameter names to match, and rewrite `tests/unit/test_prompts.py::TestCiliumTroubleshootConnectivity` for the new signature and content (still asserting exact resource strings and exact field paths per the file's existing test convention, plus a new assertion that every generated call includes `context=`). Not yet implemented — filed as a correction, not started.

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

**Issue 22 note:** unlike the others above, Issue 22 recurred 9 times before being addressed
structurally rather than patched once — see `CHANGELOG.md`'s "Documentation Process" section
for the full recurrence history and the resulting **Definition of Done** checklist (top of this
file), which is the actual fix and remains a live process rule, not closed history.
