# PRD: Minimal Verb-Based Kubernetes MCP Server

**Version:** 0.2.0
**Status:** Draft
**Author:** Iurii Vlasov
**Date:** 2026-09-13
**Supersedes:** v0.1.0

## Changelog from v0.1.0

- Rules renumbered `R1`–`R10` to avoid collision with section numbers.
- `cluster` parameter renamed to `context` (kubeconfig context = user+cluster+namespace triple); now mandatory on **input and output**.
- Per-call `dry_run` default **replaced** by registration-time access-level filtering (R7).
- **Field pruning added** (R9) — largest single context-reduction lever, absent from both reference implementations.
- Explicit output-reduction defaults specified per tool, with mandatory in-response reporting.
- Error-response contract specified (§7).
- Added: Prior Art (§2), Rejected Alternatives (§11), Success Criteria (§12).
- `k_describe` demoted to open question.
- `k_logs` default `tail` lowered from 200 to 100.

---

## 1. Problem Statement

Existing kubectl-equivalent MCP servers expose one tool per resource-type × verb combination (observed: ~222 tools in current usage). This is an anti-pattern:

- Large tool counts degrade LLM tool-selection accuracy and burn context budget on schema definitions alone.
- The combinatorial explosion is unnecessary: kubectl's surface is a small set of verbs applied generically across resource types, which are data, not distinct behaviors.
- Resource-type enumeration is inherently incomplete and stale — CRDs (Cilium, Istio, cert-manager, ArgoCD, Helm operators) vary per cluster and mutate at runtime; a hardcoded tool-per-resource list cannot track this.

## 2. Prior Art / Validation

Two production implementations independently converged on this design, which is the primary external evidence for the rules below.

| Implementation | Relevant finding |
|---|---|
| **Azure/mcp-kubernetes** | Shipped per-resource specialized tools, then **demoted them to an opt-in `USE_LEGACY_TOOLS` flag**, making a single unified tool the default — explicitly to reduce context consumption. Direct vendor-scale admission that resource-per-tool was the wrong default. |
| **containers/kubernetes-mcp-server** (Red Hat, CNCF Landscape, 2.1k★) | Generic `resources_get/list/create_or_update/delete/scale` parameterized by `apiVersion`+`kind`. Mandatory `context` argument under multi-cluster — same parameter name, same reasoning as R3. Notably ships **no `describe` tool** despite full native client-go access. |

Neither addresses cumulative session-context accumulation (§10, deferred).

## 3. Goal

An MCP server exposing a small, fixed set of verb-based tools, parameterized by resource type and context, providing kubectl-equivalent coverage — including arbitrary CRDs — without per-resource tool proliferation, safe to operate across multiple heterogeneous clusters, and economical with context budget.

## 4. Non-Goals

- Not a GitOps/deployment-pipeline tool.
- Not a Kubernetes dashboard/UI.
- `rollout` and `scale` excluded from v1 (v2 candidates if usage proves deployment-management-heavy rather than debugging-heavy).
- `port-forward`, `cp`, `top` excluded — stream-based or separate-API-group operations unsuited to call/response tooling.
- No MCP Resources (user-driven browse/attach) layer — see §9.
- No Tekton / KubeVirt / NetObserv / Kiali-style domain toolsets.

## 5. Design Rules

**R1. Tools map to verbs, not resource types.** Fixed tool set: `get, logs, apply, patch, delete, exec` (+ `describe`, pending §13). `rollout` and `scale` excluded from v1.

**R2. Resource names resolve through a two-tier lookup.** A hardcoded core table (pod, deployment, statefulset, replicaset, service, pv, pvc, configmap, secret, networkpolicy, ingress, node, namespace, job, cronjob, endpoints, events) takes priority, falling back to per-context dynamic discovery (`kubectl api-resources`) for CRDs and extensions. The core table's job is tie-break priority and cold-start resolution, not correctness.

**R3. `context` is mandatory on every tool call as input, and echoed as a mandatory field in every tool output.** No default, no session-scoped state, no implicit reuse. A context is the kubeconfig user+cluster+namespace triple — the same physical cluster may be reachable under several contexts with different identities. Output echo makes every result self-identifying in interleaved cross-context sessions.

**R4. Every output-reducing default is reported in the response, never silently applied.** Any tool that truncates, tails, prunes, or summarizes must state the bound applied (e.g. `"tail": 100, "truncated": true`) so the model can decide whether to re-request unbounded.

**R5. The discovery cache is keyed and refreshed independently per context.**

**R6. Ambiguous resource-name matches are never auto-resolved.** Core-table entries win by default. Remaining collisions return all candidates and require qualification via `resource.group`. `resource` also accepts the fully-qualified `name.group` form directly as an escape hatch.

**R7. Mutating capability is gated at server startup by access level, with tools filtered at registration time.** Levels: `readonly` (default) → `get`, `logs`, `describe`; `readwrite` → adds `apply`, `patch`, `delete`; `admin` → adds `exec`. The model never sees tools outside its level, so it cannot attempt them, cannot argue past them, and spends no schema tokens on them. `dry_run` remains available as an optional per-call parameter but is **not** the enforcement mechanism.

**R8. Every call is validated against resource metadata (namespaced/cluster-scoped, supported verbs) before execution**, not after a kubectl error.

**R9. All JSON responses are field-pruned by default.** Strip `metadata.managedFields`, `metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"]`, `metadata.uid`, `metadata.generation`, and `metadata.resourceVersion` unconditionally; strip `status` unless the resource kind is one where status carries debugging signal (pods, deployments, statefulsets, jobs, CRDs with conditions) or the caller requests it. Pruning is stateless — no caching, always fresh from the API server.

**R10. Read output is bounded by default**, with full detail only on explicit request (see §6 for per-tool values).

**R11. Operations shell out to the `kubectl` binary** with structured output (`-o json`) rather than reimplementing via a client library.

**R12. MCP Resources (user-driven browse/attach) are out of scope.** Tools only.

> Rules exceed ten as of v0.2.0; the "ten rules" framing from v0.1.0 is dropped in favor of completeness.

## 6. Tool Specification

All tools take `context` (kubeconfig context name) as a required input parameter, and every response includes `context` echoed back as a required output field. Omitted from the table below for brevity.

| Tool | Required (beyond `context`) | Optional | Output-reduction default (reported per R4) | Access level |
|---|---|---|---|---|
| `k_get` | `resource` | `name`, `namespace`, `all_namespaces`, `label_selector`, `field_selector`, `output`, `jsonpath_template`, `annotation_selector` | `output=name` (names only) by default; `json`/`yaml` on request. `output=wide` delegates to kubectl's own `-o wide` and returns its plain-text table verbatim as `output` (bypasses pruning/bounding, same precedent as `k_describe`'s text passthrough). `jsonpath_template` triggers jsonpath mode regardless of `output` (bare `output="jsonpath"` with no template is a fail-fast `invalid_output` error; nested braces like `{.items[*].{a,b}}` is a fail-fast `invalid_jsonpath_template` error explaining the correct bracket-list/`range` syntax) — bypasses pruning/bounding entirely, returns the raw kubectl jsonpath string as `data`, echoes `jsonpath_template` back per R4. `annotation_selector` filters results client-side by `metadata.annotations` (kubectl has no server-side equivalent) — works on both list and single-named-resource fetches, reports `{"matched": N, "total": M}` as `_filtered`; incompatible with `jsonpath_template` and with `output=wide` (both rejected as a fail-fast `invalid_selector` error, since neither leaves structured JSON to filter). All non-jsonpath/non-wide JSON field-pruned per R9. | readonly |
| `k_describe` | `resource`, `name` | `namespace` | None — delegates verbatim to `kubectl describe`. **Pending §13.** | readonly |
| `k_logs` | `pod` | `namespace`, `container`, `tail`, `previous`, `since` | `tail=100`. Response states the bound and whether truncation occurred. | readonly |
| `k_apply` | `manifest` | `namespace`, `dry_run`, `output`, `jsonpath_template` | N/A — response states `dry_run` status. `jsonpath_template` (regardless of `output`) returns the raw jsonpath string as `data` instead of pruned JSON, `dry_run` still echoed; nested braces like `{.items[*].{a,b}}` is a fail-fast `invalid_jsonpath_template` error. `output="yaml"` returns the pruned response as `{"_yaml": <string>}`; `output="json"` (or unset) is the pruned JSON object, unchanged; `output="wide"` is rejected with a fail-fast `invalid_output` error (kubectl's `-o wide` has no meaningful semantics for `apply`) rather than silently accepted. | readwrite |
| `k_patch` | `resource`, `name`, `patch` | `namespace`, `type` (strategic/merge/json), `dry_run`, `output`, `jsonpath_template` | N/A — same as `k_apply` above, including `invalid_jsonpath_template` for nested braces. | readwrite |
| `k_delete` | `resource` | `name`, `namespace`, `label_selector`, `dry_run` | N/A — same | readwrite |
| `k_exec` | `pod`, `command` | `namespace`, `container` | N/A | admin |
| `k_get_secret_to_file` | `name`, `namespace`, `dst_secret_file` | `overwrite` | N/A — response contains only key names and the destination path, never values. Deliberate, named R1 exception (§15 FR9) — resource-specific by design, `Secret`-only. | admin |

Supporting tools:

| Tool | Purpose | Access level |
|---|---|---|
| `k_list_contexts` | Enumerate available kubeconfig contexts (user+cluster+namespace triples) | readonly |
| *(internal)* resource resolver | Not model-facing; backs all tools per R2, R6, R8 | — |

`resource` accepts shortname (`po`), plural (`pods`), kind (`Pod`), or fully-qualified (`ciliumnetworkpolicies.cilium.io`).

## 7. Resource Resolution & Error Contract

```
resolve(context, resource_name):
    1. Normalize (lowercase, strip plural/shortname variance)
    2. Core table lookup — hardcoded GVK + aliases, stable across conformant clusters
       -> match: return (core wins ties)
    3. Per-context discovery cache
       (from `kubectl --context=<ctx> api-resources -o wide`;
        TTL 5–10 min, plus on-miss refresh-once-then-fail)
       -> single match: return
       -> multiple:    return all candidates (R6), do not guess
       -> none:        error + fuzzy-matched suggestions
```

Core table and discovery entries both carry: canonical name, shortnames, kind, group/version, namespaced (bool), supported verbs.

**Error response contract.** Every error returns:

```json
{
  "context": "prod-eu",
  "error": "ambiguous_resource",
  "candidates": ["policies.kyverno.io", "authorizationpolicies.security.istio.io"],
  "hint": "specify resource as <name>.<group>"
}
```

Error codes: `ambiguous_resource`, `unknown_resource` (+ `suggestions`), `verb_unsupported`, `namespace_invalid` (cluster-scoped resource given a namespace, or vice versa), `unknown_context` (+ **full valid context list**, so a wrong guess self-corrects in one round-trip), `access_denied` (verb outside current access level).

**Cache duplication note:** keying strictly per-`context` duplicates identical CRD data when one cluster is reachable via multiple contexts. Accepted for v1 (avoids a separate cluster-identity resolution step); revisit if measurable.

## 8. Safety & Gating

- **Access level set at server startup** (`readonly` default), tools filtered at registration (R7). Not overridable per call.
- **Namespace allowlist** (`--allow-namespaces`, empty = all) as an orthogonal gating axis.
- **Pre-execution validation** per R8 — fail fast with a structured error, never surface a raw kubectl failure.
- **`context` explicit on input, echoed on output, logged on every call** — mutations especially. No inference from conversation history; no ambiguity about which context produced a result.
- **`exec` is admin-only** and the highest-risk surface; consider a separate feature flag independent of access level.

## 9. Multi-Context Handling

- Contexts sourced from kubeconfig via kubectl's own default resolution (`$KUBECONFIG` env var, or `~/.kube/config`) — no server-level `--kubeconfig` flag; see §11's rejected-alternatives entry.
- `k_list_contexts` exposes valid names cheaply; `unknown_context` errors also return the list.
- Core table is static/shared; discovery cache is per-context.
- Heterogeneous extensions (Cilium on one cluster, Istio elsewhere) need no server changes — CRDs surface automatically via per-context discovery and resolve through R2's second tier.

## 10. Deferred: Cumulative Session Context

**Problem.** R4/R9/R10 bound each call. Nothing bounds the session total. A debugging loop making 20–30 calls accumulates monotonically, degrading tool-selection accuracy and eventually truncating — and truncation in an agentic loop discards the early findings that motivated the investigation. Redundant re-fetching of unchanged objects compounds it.

**Decision: field pruning (R9) only for v1. Response caching, dedup, diffing, and `resourceVersion` short-circuiting are deferred.**

Rationale:
- **R9 is stateless** — every response is fetched fresh from the API server; only known-useless fields are stripped. No staleness risk under concurrent multi-agent access on a shared cluster.
- Caching-based schemes introduce session state and a stale-data question. *(Technical note for the record: a `resourceVersion` short-circuit would not actually serve stale data — it still fetches every call and only omits the body when `resourceVersion` is unchanged, so a concurrent mutation by another agent yields a differing version and a full fresh copy. It is deferred for other reasons.)*
- An "unchanged" response is only meaningful if the model still holds the earlier copy — it interacts badly with the very truncation it aims to prevent.
- Neither reference implementation (§2) solves this, so there is no proven pattern to copy and no evidence the need is acute.

**Before building anything here:** instrument. Log call signatures across several real sessions and count exact repeats. If re-fetching is rare, R9 alone is the complete answer.

## 11. Rejected Alternatives

| Alternative | Rejected because |
|---|---|
| **Tool-per-resource-type** (the 222-tool status quo) | Degrades tool selection, burns schema context, cannot cover CRDs without per-cluster maintenance. Azure reversed this default themselves (§2). |
| **GVK-as-parameters** (`apiVersion`+`kind`, Red Hat's shape) | Structurally unambiguous, but taxes *every* call with group/version knowledge to prevent collisions affecting a handful of names (`networkpolicy`, `certificate`, `policy`, `application`). R2+R6 handle those narrowly. Qualified `name.group` remains available as an escape hatch (R6). |
| **Raw `kubectl` command-string tool** (Azure's `call_kubectl`) | Defeats R3, R7, R8 — enforcement requires structured fields before execution. Parsing them back out of a shell string is strictly worse than receiving them typed. Shell-injection surface. *The training-data-prior argument in its favor is real* and is addressed instead by keeping kubectl-identical vocabulary (`resource`, `-o` values, selector syntax) inside typed params. |
| **Stateful `switch_context` / session-scoped context** (Azure's `kubectl_config use-context`; aadarshjain's `switch_context`) | A wrong-context mutation after the model loses track of a switch 15 turns back is a materially worse failure than parameter verbosity. See R3. |
| **Per-call `dry_run` default as safety mechanism** (v0.1.0's R7) | Costs a round-trip per mutation; the model learns to reflexively pass `dry_run=false`, nullifying it. Replaced by registration-time filtering (R7). |
| **MCP Resources layer** | Solves user-driven browse/attach, a different UX pattern from model-driven agentic debugging. Unused surface area here. |
| **Domain toolsets** (Istio/Kiali, Tekton, KubeVirt, NetObserv) | Out of scope. If ever added, they go behind an opt-in `--toolsets` flag (Red Hat's pattern) so the core verb set never regresses to tool bloat. |
| **Dedicated `k_events` tool** | `k_get resource="events"` + `field_selector=involvedObject.name=...,involvedObject.kind=...` already covers the primary use case (scoping events to one object) through the existing verb, no new tool needed. `kubectl events`'s only real edge — the `--for=<kind>/<name>` shorthand and chronological default ordering — wasn't judged worth a whole new model-visible tool (R1's tool-count discipline) for what's a convenience over an already-working `field_selector` query. Follow-up worth doing separately: add `events` to the R2 core table so `resource="events"` resolves instantly instead of falling through to per-context discovery. |
| **Server-level `--kubeconfig` flag** (resolves §13's former "kubeconfig layout" open question) | Considered, implemented, then removed. In practice it was only ever wired into `k_list_contexts` — every other tool (`k_get`/`k_apply`/`k_patch`/`k_delete`/`k_describe`/`k_exec`/`k_logs`) and the discovery cache resolved `context` against kubectl's own default (`$KUBECONFIG`/`~/.kube/config`) regardless of what `--kubeconfig` was set to, since `run_kubectl()` never threaded it through (see `KNOWN_ISSUES.md` Issues 33/34). Fixing that properly meant adding a `kubeconfig` parameter to every tool handler plus the runner — real surface-area cost for a flag whose only legitimate use case (multiple separate kubeconfig files) kubectl's own `$KUBECONFIG` env var already solves without any server involvement. Decision: drop the flag; rely entirely on kubectl's own default kubeconfig resolution, same as every other kubectl-wrapping tool in this project already assumes (R11's "shell out to kubectl" already implies inheriting its config resolution, not reimplementing a parallel one). Simpler, smaller, and removes a whole class of "which file did this actually use" confusion. |

## 12. Success Criteria

- Total model-visible tool count ≤ 10 at `readonly`, ≤ 12 at `admin`.
- Full CRUD coverage of an arbitrary CRD (cert-manager `Certificate`, Cilium `CiliumNetworkPolicy`, ArgoCD `Application`) with **zero** server-side code changes.
- Tokens consumed per resolved debugging task ≤ 40% of the 222-tool baseline being replaced.
- Zero wrong-context mutations across a scripted multi-context test scenario.
- Ambiguous-resource calls (`networkpolicy` on a Cilium cluster) never silently resolve to the wrong API group.

## 13. Open Questions

- [ ] **Ship `k_describe` at all?** Red Hat didn't implement it despite native API access, shipping `get` + `events` instead. Its output is verbose unstructured text — worst context-per-useful-byte of any candidate tool. Dropping it also removes R11's primary justification, reopening native-vs-subprocess on cleaner grounds.
- [ ] `k_exec` in v1, or deferred given risk profile even at `admin`?
- [ ] Which kinds warrant `status` retention by default under R9 (pods/deployments clearly; the general rule for CRDs with `conditions` is less clear).
- [ ] Discovery cache refresh trigger: TTL only, on-miss-retry only, or both.
- [ ] `rollout`/`scale` post-v1 — contingent on observed usage skew. Red Hat's `resources_scale` (get-or-set, always returns current scale) is a cleaner pattern than folding scale into `patch` if added.
- [ ] Cilium/Hubble CLI integration as a v2 `--additional-tools` option (Azure ships `call_cilium`/`call_hubble`); orthogonal to CRD access, but `hubble observe` is more useful for Cilium debugging than reading CRDs.
- [ ] Audit/logging sink for mutating calls.

## 14. Implementation Notes

- Language/runtime: TBD (Python + FastMCP, or Go). No constraint from this PRD; both references are Go.
- `kubectl` binary required in the server's execution environment with kubeconfig access to all target contexts.
- Core resource table should be a version-controlled static data file, not inline code, to ease updates as API conventions shift (cf. historical `extensions/v1beta1` → `apps/v1`).
- Field-pruning (R9) should be a single response-transform applied uniformly at the output boundary, not per-tool logic.

## 15. Feature Requests / Improvements

Not part of v1 scope. Tracked here as candidates, not commitments — promote to a numbered section above only once accepted.

### FR1. `k_get` `output=jsonpath` support

**Motivation.** kubectl's `-o jsonpath=<template>` extracts exactly the fields a caller asks for instead of returning a full (even pruned/bounded) object. For targeted queries — "just this pod's IP", "just the image tags across a deployment's containers" — this is a stronger context-economy lever than `output=json`/`yaml`, and arguably fits R4/R10's "bounded by default, full detail only on explicit request" philosophy better than either: a jsonpath query is a caller-specified bound, more precise than name-only output when the caller already knows which field they want.

**Proposed shape:**
- Add `jsonpath` to `k_get`'s `output` enum (currently `name` (default) / `json` / `yaml` / `wide`; §6).
- Add a new optional param, e.g. `jsonpath_template: string` — required when `output=jsonpath`; its absence in that case should fail R8-style pre-execution validation rather than being forwarded to kubectl as a bare `-o jsonpath=` with no template.
- kubectl invocation becomes `kubectl get <resource> ... -o jsonpath=<jsonpath_template>` in place of `-o json`.

**Interaction with existing rules:**
- **R9 (field pruning) does not apply** to jsonpath output — the template already selects the minimal shape the caller wants; there is no structured JSON left to strip fields from. This should be an explicit skip-pruning branch, not an implicit no-op.
- **R4 (bound self-reporting)** still applies in spirit — echo the `jsonpath_template` used back in the response, the same way `k_logs` echoes `tail`, so the model can see what filter produced this response.
- **Error contract (§7):** a malformed jsonpath expression is a kubectl-side failure (non-zero exit, stderr like `error: error parsing jsonpath ...`) — should map through the existing `kubectl_failure` path rather than a new error code, unless malformed-jsonpath turns out common enough to warrant a dedicated, clearer error.
- **Output shape:** jsonpath output is plain text, not necessarily valid JSON (e.g. `{.items[*].metadata.name}` returns space-separated names) — the response's `data` field becomes a string for this `output` value, the same shape precedent as `k_describe`'s output and the apply/patch/delete non-JSON fallback path.

**Open question (same style as §13):** extend to `k_logs`/`k_describe` too, or keep this `k_get`-only? kubectl's `-o jsonpath` is only meaningful for structured-output commands (`get`) — `describe` is already plain text and `logs` isn't structured at all — so `k_get`-only is the natural boundary unless a concrete use case emerges elsewhere.

### FR2. `annotation_selector` for `k_get`

**Motivation.** kubectl has no server-side annotation selector — `-l`/`--selector` only matches labels, and `--field-selector` is a small per-resource-type allow-list of API-server fields, never annotations. Resources tagged via annotations (common with GitOps tooling — `argocd.argoproj.io/*`, Helm's `meta.helm.sh/*`, custom operator bookkeeping) currently have no narrowing mechanism short of fetching everything with `output=json` and filtering by hand outside the tool.

**Proposed shape:**
- New optional param `annotation_selector: str | None = None` on `k_get` only (not extended to other verbs without a concrete need — same reasoning FR1 applied to its own scope).
- Syntax: a practical subset of label-selector syntax, comma-separated (AND semantics) — `key=value`, `key!=value`, bare `key` (existence). Not the full label-selector grammar (set-based `in`/`notin` deferred unless a need shows up).
- Because this can't be forwarded to kubectl as a flag, `k_get` must always fetch `-o json` internally when `annotation_selector` is set (regardless of the requested `output`), filter the item(s) by walking `metadata.annotations` against the parsed selector, and *then* apply the normal `prune()` → `bound_get_names()`/`apply_output_format()` pipeline on the filtered set — same output-shaping as today, just on a pre-narrowed input.

**Interaction with existing rules:**
- **R11** — this is qualitatively different from `label_selector`/`field_selector`, which are pure kubectl flag passthroughs: this is the first case of the server doing its own query logic rather than delegating the query to kubectl. It stays inside the boundary R9's pruning already established (client-side JSON transforms on a kubectl-fetched response), so it's an extension of existing practice rather than a new category — but worth naming explicitly since it's the first *filtering* (not just *shaping*) logic to live in Python.
- **R4** — report what was filtered: e.g. `_filtered: {"annotation_selector": "...", "matched": N, "total": M}`.
- **R8 / error contract** — a malformed `annotation_selector` string is *our* parse error, not kubectl's (kubectl never sees it) — needs its own error code (e.g. `invalid_selector`) and must fail before any kubectl call, same fail-fast placement as FR1's jsonpath validation.

### FR3. `k_list_resources` tool

**Motivation.** The per-context discovery cache (R5) already fetches and parses `kubectl api-resources -o wide` into structured records — name, shortnames, group/version, `namespaced`, `verbs` — to back `resolve()`/`validate()` internally (R2/R6/R8). None of that is model-facing today. The model currently has no way to discover what resource types (especially CRDs) exist on a cluster except by guessing a name and getting an `unknown_resource` error with fuzzy suggestions. This closes that gap directly against the CRD-coverage goal in §12 — "full CRUD coverage of an arbitrary CRD... with zero server-side code changes" only pays off once the model knows the CRD's name exists in the first place.

**Proposed shape:**
- New tool `k_list_resources`, `readonly` access level (same tier as `k_get`/`k_list_contexts`, R7).
- Required: none beyond `context`. Optional: `search` (substring filter against canonical name/kind/group, for CRD-heavy clusters where the full list can run to 150+ types).
- Response: one entry per resource type — canonical name, shortnames, kind, `api_version` (group/version combined), `namespaced`, `verbs`. Directly serializes the existing `ResourceMeta` shape (`resolution/models.py`) — no pruning concern here (R9 is about stripping noisy *instance* fields like `managedFields`; this is type metadata, not an instance).

**Interaction with existing rules:**
- **R5** — reuses the existing per-context `DiscoveryCache` verbatim (same TTL, same refresh-on-miss trigger `resolve()` already uses) rather than introducing a second discovery mechanism.
- **R9** — does not apply; no instance-level noise fields exist on this data.
- **R10** — the response is compact type metadata (one row per resource type), not deep per-instance JSON, so unbounded-by-default is likely fine; `search` exists for cluster-size management, not as an R4-reported truncation bound. Revisit if a CRD-heavy cluster proves this wrong in practice.
- **R7** — readonly.

**Open question:** should this merge in `core_table.py`'s hardcoded entries, or serve the discovery cache alone? Every core-table resource (pods, deployments, etc.) should also appear in `kubectl api-resources`' own output — the core table exists only for name-resolution tie-breaking (R2), not a separate universe of types — but this hasn't been verified against a live cluster. If discovery-cache-alone turns out incomplete, fall back to unioning `core_table + discovery_cache`, deduped by `(canonical, group)` (note: `resolve()`'s own fuzzy-suggestion fallback already does an un-deduped `table + cached` union today — worth fixing there too if this FR surfaces the duplication).

### FR4. Unit test coverage for `k_delete`, `k_describe`, `k_logs`, `k_exec`, `k_list_contexts`

**Motivation.** Of the seven verb tools plus `k_list_contexts`, only `k_get`/`k_apply`/`k_patch` have unit tests (`test_tools_get.py`, `test_tools_apply.py`, `test_tools_patch.py`, added alongside FR1). `tools/delete.py`, `describe.py`, `logs.py`, `exec_.py`, and `contexts.py` have **zero** unit tests — confirmed by listing `tests/unit/` directly. This is a real risk, not a hygiene nit: `k_exec` and `k_delete` are the two highest-blast-radius tools in the server (arbitrary in-container command execution; resource deletion), and both currently ship with no automated verification of their kubectl-arg construction or error handling at all.

**Two concrete bugs surfaced just from reading these five modules to scope this FR** — the strongest evidence coverage was overdue:
- **`tools/exec_.py`** builds `args = ["exec", pod, "--"]` and *then*, if `container` is set, appends `["-c", container]` — placing `-c <container>` **after** the `--` separator. kubectl's syntax requires `-c` before `--` (`kubectl exec POD -c CONTAINER -- CMD...`); as written, `-c`/the container name are passed as part of the executed command instead of being parsed as kubectl's own flag. **Container selection on `k_exec` does not work today.**
- **`tools/contexts.py`**'s `handle_list_contexts` discards the error from `list_kubeconfig_contexts()` on failure and returns `envelope_list_contexts([], context)` — an empty context list, indistinguishable from "this kubeconfig legitimately has none." A real kubeconfig-read failure is invisible to the model.

Both should be **fixed as part of this FR**, before or alongside writing the corresponding tests — a test that encodes the current (broken) behavior as "correct" would be worse than no test.

**Proposed shape:** five new test files, one per module, following the `test_tools_apply.py`/`test_tools_patch.py` conventions already established (a `ResourceMeta` fixture, `@patch` on `resolve`/`run_kubectl_checked`, one test class per tool).

- `tests/unit/test_tools_delete.py` — `name` vs `label_selector` branch (only one used, `name` takes priority per the `elif`); `dry_run != "none"` adds `--dry-run`; JSON parse+prune success path; non-JSON stdout falls back to `{"message": ...}`; `resolve()`/`validate()`/kubectl error passthrough.
- `tests/unit/test_tools_describe.py` — args built as `describe <resource> <name>` with `output_format=None` (no `-o` flag); optional `namespace` adds `-n`; **note and lock in as a regression test** the existing quirk that `validate()` is called with verb `"get"`, not `"describe"` (`describe.py:34`) — document this as intentional-or-not in the test's own naming/comment so a future reader isn't left guessing; `resolve()`/`validate()`/kubectl error passthrough; success shape `{"output": stdout}`.
- `tests/unit/test_tools_logs.py` — default `tail=100` applied when `tail` is `None`; explicit `tail` overrides the default; `previous`/`since`/`container` each add their respective flag; `bound_logs()` truncation reporting when line count exceeds `tail`; `resolve()`/`validate()`/kubectl error passthrough.
- `tests/unit/test_tools_exec.py` — **written against the fixed arg order** (`-c <container>` before `--`, command after); `command` (a list) is appended verbatim after `--`; `output_format=None` (no `-o` flag, matches `describe`); the `exec_failed` vs. generic `kubectl_failure` error-shape branch (`exec_.py:53-66`) — both paths need a case; success shape `{"stdout", "stderr", "exit_code"}`.
- `tests/unit/test_tools_contexts.py` — **written against the fixed error-surfacing behavior**: a `list_kubeconfig_contexts()` error propagates as a visible error in the response rather than silently becoming an empty list; `kubeconfig_paths=None` defaults to `[]`; happy path returns the enumerated contexts via `envelope_list_contexts`. (Superseded: `kubeconfig_paths` no longer exists — see §11's rejected `--kubeconfig` flag entry and `KNOWN_ISSUES.md` Issues 33/34. This bullet is left as historical record of what FR4 originally built, not a live spec.)

**Interaction with existing rules:** no new rule interactions — this is closing a test-coverage gap on already-specified behavior (§6), not proposing new behavior, aside from the two bug fixes above which restore already-documented behavior (`k_exec`'s `container` param, §6, was always supposed to work; `k_list_contexts` errors should be as visible as every other tool's per the shared error contract, §7).

### FR5. Fix `k_get`'s `output=wide` no-op

**Motivation.** Confirmed while updating §6's table (the update itself had to document this as a known gap rather than silently fix it): `output/bounding.py`'s `apply_output_format()` `"wide"` branch just calls `bound_get_names(data)` — byte-identical to `k_get`'s own default (unrequested) output. A caller explicitly requesting `output=wide` gets nothing beyond the default name-only list; kubectl's actual `-o wide` (resource-kind-specific extra columns — `READY`/`STATUS`/`RESTARTS`/computed `AGE`/`IP`/`NODE` for pods, entirely different columns for a deployment or a node) is not reproduced at all.

**Why this can't be fixed by extending `bound_get_names()`/`apply_output_format()` client-side.** kubectl's real `-o wide` output is resource-kind-specific and includes computed/derived fields (e.g. `AGE` from `creationTimestamp`) that live in kubectl's own per-kind table-printer logic, not in a generic transform over the structured JSON this server already has. Reproducing it faithfully in Python would mean reimplementing that per-kind printer logic — exactly the kind of per-resource-type special-casing R1 exists to avoid, and it would be a direct violation of R11 ("shell out to kubectl... rather than reimplementing") to build a parallel implementation from scratch.

**Proposed fix.** Stop trying to derive `wide` from JSON this server already fetched via the default `-o json` call. Instead, when `output=wide` is requested, invoke kubectl with the *actual* `-o wide` flag and return kubectl's own plain-text table verbatim — the same pattern `k_describe` already uses for its own plain-text passthrough. This reuses kubectl's real column logic (satisfies R11) instead of reinventing it, at the cost of `wide` becoming a plain-text response like `jsonpath`/`k_describe`, not a structured `items` list like `name`/`json`.

**Interaction with existing rules:**
- **R9** — does not apply to `wide` output, same reasoning as FR1's jsonpath: there's no structured JSON left to prune once kubectl's own table-print is used instead of `-o json`.
- **R11** — this fix is what actually satisfies R11 for `wide`; the current code silently doesn't.
- **Response-shape consistency** — the codebase now has two precedents for "raw kubectl text passthrough": `k_describe` uses the key `"output"`, FR1's jsonpath uses the key `"data"`. This FR should pick one deliberately rather than adding a third option by default — leaning `"output"` (matches `k_describe`'s existing plain-text precedent), but this is a call worth making explicitly, not defaulting into.
- **R4** — no bound/truncation metadata needed, matching the existing precedent that `json`/`yaml` (full, on-request output) don't report a bound either — `wide` is a format choice, not a truncation.

**Open question:** confirm `-o wide` composes cleanly with `all_namespaces`/`label_selector`/`field_selector` on a live cluster before calling this done — expected to, since `-o wide` is just `get`'s formatting flag and doesn't restrict which other `get` flags apply, but not yet verified against a live cluster.

### FR6. `k_apply`/`k_patch`'s `output` param silently accepts `json`/`yaml` and does nothing

**Motivation.** `k_apply` and `k_patch` both take an `output` param (added alongside FR1's `jsonpath_template` work) that PRD §6 documents as accepting `json`/`yaml` in addition to triggering jsonpath mode. In the actual implementation, `output` is referenced exactly once in each tool — the `output == "jsonpath" and not jsonpath_template` fail-fast check — and nowhere else. A caller passing `output="yaml"` expecting a YAML string back (the same behavior `k_get`'s own `output=yaml` already provides) silently gets the same pruned JSON object as if `output` had never been set. This is a documented-but-nonfunctional param, the same class of gap FR5 fixed for `k_get`'s `wide`, just lower severity (misleading rather than broken).

**Proposed fix.** `output/bounding.py`'s existing `apply_output_format()` helper already does exactly what's needed — `"json"` is a no-op, `"yaml"` wraps the data as `{"_yaml": <string>}` — and is already used by `k_get` for this exact purpose. Apply it to `k_apply`/`k_patch`'s `pruned` object (after `prune()`, before wrapping into the `{"data": ..., "dry_run": ...}` envelope) in both tools' non-jsonpath success path. Since `apply_output_format(data, None)` returns `data` unchanged, this is a no-op for the default (`output` unset) case — zero behavior change for existing callers who don't pass `output`.

**Scope boundary:** `wide` should **not** become a valid `output` value for `k_apply`/`k_patch` — it's a list-formatting concept (kubectl's own `-o wide` flag doesn't apply meaningfully to `apply`/`patch`'s single-object response the way it does to `get`'s potentially-multi-object one). Only `json`/`yaml` need wiring up; `output="wide"` on these two tools should presumably still be rejected or ignored, not silently accepted as if it did something — worth an explicit decision at implementation time rather than defaulting into either behavior.

**Interaction with existing rules:**
- **R9** — unaffected; pruning still happens before format conversion, same order `k_get` already uses.
- **R4** — no bound/truncation metadata needed, matching `k_get`'s own precedent that `json`/`yaml` (full, on-request output) don't report a bound.

### FR7. Add `events` to the R2 core table

**Motivation.** `events` is not in `data/core_resources.toml`'s hardcoded list (pods, deployments, statefulsets, replicasets, services, pv, pvc, configmaps, secrets, networkpolicies, ingresses, nodes, namespaces, jobs, cronjobs, endpoints) — so `k_get resource="events"` currently falls through to per-context discovery (R2/R5) instead of resolving instantly the way every other stable core `v1` kind does. `events` is exactly the kind of resource the core table exists for: a stable, universally-available built-in type (present on every cluster, unlike a CRD), and — given this project's own "Troubleshooting and Debugging" framing (§1) — arguably more central to the tool's actual purpose than several types already in the table. This was already flagged as a follow-up when a dedicated `k_events` tool was rejected in favor of `k_get resource="events"` + `field_selector` (§11's rejected-alternatives table) — this FR is that follow-up, formalized.

**Proposed entry:**
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
`verbs = ["get"]` only, matching the existing `endpoints` entry's pattern — events aren't a realistic `apply`/`patch`/`delete` target through this tool, only a read target.

**Interaction with existing rules:**
- **R2** — purely additive; core-table entries win ties over discovery-cache entries, so this doesn't change resolution for anything else. No existing behavior regresses.
- **R5** — no change to the discovery cache itself; this just means `events` no longer needs a discovery round-trip (or TTL-cache hit) to resolve.
- **R6** — check `events` doesn't collide with any existing core-table `shortnames`/`canonical`/`kind` before adding (`ev` is not currently used elsewhere in the table) — low risk, but worth the explicit check R6 asks for on any core-table addition.

### FR8. Fail-fast validation for nested-brace `jsonpath_template` syntax (a specific, proven-common invalid-jsonpath mistake)

**Motivation.** A live-cluster occurrence (`KNOWN_ISSUES.md` Issue 29) showed an LLM caller using `{.items[*].{involvedObject.kind,involvedObject.name,namespace,message}}` — nested braces attempting multi-field extraction — as a `jsonpath_template`. This is not valid Kubernetes jsonpath syntax, and kubectl's own jsonpath engine (built on Go's `text/template` action parser) correctly rejected it with `unrecognized character in action: U+007B '{'`. The MCP server correctly propagated this as `kubectl_failure`, exactly the behavior FR1 documented as intended for malformed jsonpath — **this was not a code defect**. But the raw kubectl error gives the calling model zero actionable guidance, and the mistake is a natural, tempting analogy to other dict/object-literal syntaxes (plausible to recur, now proven to occur in practice). FR1 explicitly anticipated this exact tradeoff: *"a malformed jsonpath expression... should map through the existing `kubectl_failure` path rather than a new error code, unless malformed-jsonpath turns out common enough to warrant a dedicated, clearer error."* This FR is that one dedicated case, scoped narrowly to the specific pattern now proven common — not a general jsonpath validator.

**Proposed shape:**
- A new pre-execution (R8-style) fail-fast check, applied consistently across `k_get`/`k_apply`/`k_patch` (the same three tools FR1 touches): detect nested-brace depth greater than one anywhere in `jsonpath_template` — i.e. a second `{` opening before the current action's matching `}` closes. This is a purely syntactic check with no false-positive risk against legitimate templates: sibling top-level blocks (`{.a}{.b}`) and `{range .items[*]}...{end}` loops never have genuinely *nested* braces, only sequential ones.
- New error code + helper: `invalid_jsonpath_template(context, template, *, detail=None)` — distinct from `invalid_output` (FR1, missing template) and `invalid_selector` (FR2, malformed `annotation_selector` query), since this is a third, distinct flavor of malformed caller input.
- The error's `detail` explains the actual working syntax: the bracket-list form `{.items[*]['field1','field2']}`, or a `{range .items[*]}...{end}` loop — not just a bare rejection.
- Additionally (independent of the validation check, addressing the same problem from the other direction): update `jsonpath_template`'s tool-description text on all three wrappers to proactively mention the bracket-list syntax, reducing the odds of hitting this mistake at all.

**Explicit scope boundary:** this does **not** become a general jsonpath grammar validator. Every other way a jsonpath template can be malformed (typos, bad array indices, invalid field paths, etc.) still flows through the existing `kubectl_failure` passthrough exactly as FR1 established — reimplementing kubectl's own jsonpath grammar client-side would violate R11 ("shell out to kubectl... rather than reimplementing") and create an ongoing maintenance burden tracking kubectl's own grammar across versions, for a benefit far smaller than this one proven-common case.

**Interaction with existing rules:**
- **R8** — fail fast before `resolve()`/kubectl, same placement as FR1's own `jsonpath_template`-required check.
- **R11** — this stays on the correct side of the line: a narrow syntactic guard against one specific, proven mistake, not a grammar reimplementation.
- **PRD §6** — remember to update the table's `k_get`/`k_apply`/`k_patch` rows when this ships, describing the new rejection and pointing to the correct syntax. This exact step has been forgotten twice already in this project's history (see `KNOWN_ISSUES.md` Issue 22); flagging explicitly here to try to break that pattern a third time.

### FR9. `k_get_secret_to_file` — write a Secret's decoded content to a local file, never into model context

**Motivation.** Every existing read tool (`k_get`, `k_describe`, `k_logs`) returns its content directly in the tool response, which becomes part of the model's context — logged, sent to the model provider, retained in conversation history. For most resources that's the whole point. For `Secret` resources it's a real exposure: credentials, tokens, and certificates would otherwise flow through the same path as a pod's name or a deployment's replica count. There is currently no way to inspect or export a Secret's decoded values through this server without putting them in front of the model. This FR adds a narrowly-scoped tool that decodes a Secret and writes it straight to a file on disk, returning only metadata (key names, file path) to the model — never values.

**Proposed shape:**
- New tool `k_get_secret_to_file`, **`admin`-only** access level (per explicit requirement) — added to `_VERB_MAP`'s `ADMIN` tier only, same tier `k_exec` occupies, not `readonly`/`readwrite`.
- Required: `context`, `name` (secret name), `namespace` (Secrets are always namespaced — same R8 validation every namespaced resource already gets), `dst_secret_file` (mandatory — destination path on the **server's** local filesystem).
- Implementation: `kubectl get secret <name> -n <namespace> -o json`, then base64-decode each key in `.data` (stdlib `base64`, no new dependency, consistent with R11's "shell out to kubectl, don't reimplement API communication" — decoding a wire-format encoding is not the same thing as reimplementing the API client), then write the decoded key/value map to `dst_secret_file` as JSON.
- Response contains **only metadata** — key *names*, not values: `{"context": ..., "tool": "k_get_secret_to_file", "success": true, "written_to": dst_secret_file, "namespace": ..., "name": ..., "keys": ["username", "password"]}`. No `data` field, no value ever appears in the returned dict under any key.

**Deliberate R1 exception — name this explicitly, don't let it slide by.** R1 says "tools map to verbs, not resource types" — this tool is resource-type-specific (`Secret` only) by design, the first exception to that rule in this project. The exception is justified because Secrets need genuinely different handling (content must never reach model context) that no other resource type requires — this isn't a slippery-slope opener for other resource-specific tools, it's a one-off carve-out for the one resource type where R1's normal generic-verb approach is actively the wrong shape.

**Design decisions that need making before/during implementation, not silently assumed:**
- **Path safety.** `dst_secret_file` is a caller (model)-supplied path written to by the server process — path traversal and "write outside intended directory" are real concerns for a tool whose whole purpose is handling sensitive material carefully. Needs an explicit decision: reject relative paths, restrict to a configured safe directory, or trust the admin-only access gate as sufficient? (`admin` already implies the operator trusts the model with `k_exec`-level capability, so this may be an acceptable-risk decision, but it should be a *decision*, not a default.)
- **File permissions.** The written file should be created with restrictive permissions (e.g. `0600`) given its content — should not silently inherit the process umask.
- **Overwrite behavior.** If `dst_secret_file` already exists: silently overwrite, refuse by default, or require an explicit `overwrite=true`? Given the sensitivity, refusing by default and requiring explicit opt-in to overwrite is the safer posture — but this is a call to make explicitly, not assume.
- **Output file format.** A Secret's `data` map can have multiple keys (e.g. `username`+`password`). Proposed default: one JSON file `{"key1": "decoded_value1", ...}` — matches this project's existing structured-output conventions (vs. `.env`-style `KEY=value` lines, which is also reasonable and worth considering if the file is meant to be consumed by another tool expecting that shape).
- **Scope boundary:** this tool only *gets* (reads Secret → writes file). A companion "apply from file" tool (read a file, patch/create a Secret from it, without the content ever passing through the model either) is a natural follow-up but explicitly out of scope for this FR unless requested separately — the name (`k_get_secret_to_file`) and the motivation above are both about reading, not writing. (This follow-up is now FR10 below, though scoped generically to any manifest, not Secret-specific.)

**Resolved (as implemented — see SPEC.md §8 FR9 / `KNOWN_ISSUES.md` for full detail):**
- **Path safety:** absolute path only (`os.path.isabs()`), fail-fast. No configured directory allowlist — the admin-only access gate was judged sufficient, per the "acceptable-risk decision" framing above.
- **File permissions:** `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)` at creation — no window where the file exists at a wider mode. An explicit extra `os.chmod(path, 0o600)` runs on the overwrite path too, in case an existing file had a different mode before being replaced.
- **Overwrite behavior:** refuses by default (`file_exists` error); explicit `overwrite=true` required to replace an existing file.
- **Output file format:** `{"data": {key: decoded_value, ...}, "base64_keys": [...]}` — not the flat `{key: value}` shape originally proposed above. Values that fail base64 or UTF-8 decoding are written back verbatim (lossless) and their keys listed in `base64_keys`, rather than being corrupted by a `errors="replace"`-style decode.

**Interaction with existing rules:**
- **R1** — deliberate, named exception (see above).
- **R7** — `admin`-only, added to `access.py`'s `_VERB_MAP` for that tier alone.
- **R8** — standard namespaced-resource validation (namespace required) plus the new path-safety/overwrite checks above, all fail-fast before touching kubectl or the filesystem.
- **R9** — does not apply; there's no JSON object returned to prune, the whole point is that structured content never reaches the response.
- **R11** — kubectl still does all cluster communication; only the wire-format base64 decode happens in Python, not a parallel API client.
- **Error contract (§7)** — needs new error cases beyond the existing `kubectl_failure`/`namespace_invalid`: a path-safety rejection, a file-already-exists-without-overwrite rejection, and a file-write failure (permission denied, parent directory missing) each need their own clear error code rather than a generic wrapped exception.

### FR10. `src_file` — apply a manifest from a local file, never through model context

**Motivation.** FR9 lets a caller read a Secret to a file without its content passing through the model. There is currently no symmetric way back in: `k_apply`'s only input is `manifest: str`, always supplied inline, always therefore part of the model's context. The natural round trip this breaks — read a Secret to a file (FR9), edit it out-of-band, apply the edited file back — currently requires the model to see the full content at the apply step even if FR9 kept it out at the read step. `src_file` closes that gap: an alternative way to supply `k_apply`'s manifest, sourced from a file on the server's filesystem instead of an inline string.

**Proposed shape:**
- Add `src_file: str | None = None` to `k_apply`. Exactly one of `manifest` or `src_file` must be set — both or neither is a fail-fast `invalid_manifest` error (reusing the existing error code rather than adding a fourth near-duplicate "malformed apply input" category; this is the same class of problem as today's empty/missing-`kind` checks, just a different specific cause).
- Path safety: `src_file` must be an absolute path — identical rule and identical reasoning to FR9's `dst_secret_file` check (a relative path's target depends on the server process's CWD, invisible to the caller), reusing the same `unsafe_path` error helper FR9 already added rather than inventing a parallel one.
- Read: open `src_file`, read its full text content, and feed that string into the *exact same* `_parse_manifest()` → `resolve()` → `validate()` → kubectl pipeline `manifest` already uses today. No new kubectl invocation shape, no parallel validation path — the only thing that changes is where the string comes from.
- New error: a `file_read_failed` case (file missing, unreadable, permission denied) — mirrors FR9's `file_write_failed`, fail-fast before `_parse_manifest()` is ever called.
- **Scope boundary:** `k_patch` does not get `src_file` in this FR — its `patch` param is typically a small patch document, not a full manifest, and the user's request was specifically about `apply`. A `src_file` on `k_patch` is a plausible future companion but out of scope here unless requested separately, matching FR9's own precedent for naming what's deliberately not included.

**Related finding, surfaced while designing this FR — flagging, not silently bundling into scope.** `output/pruning.py`'s `prune()` has **no special handling for `Secret` resources at all** — confirmed by reading the file. This means `k_get`, `k_apply`, `k_patch`, and `k_delete` already return a Secret's full base64-encoded `.data` map verbatim in their responses today, for *any* Secret fetch or mutation, `src_file` or not. This directly undercuts the motivation behind both this FR and FR9: there's no point routing a Secret's content around the model at the `apply` step if the response from that same `apply` call echoes the resulting object's `.data` field straight back. This is a real, pre-existing gap in already-shipped behavior (not something `src_file` introduces), and it's tracked separately as a proposed R9 extension in `KNOWN_ISSUES.md` rather than folded into this FR, since fixing pruning's Secret-handling is a broader, differently-scoped change (touches every tool that can return a Secret, not just `k_apply`) than adding one new param to one tool.

**Interaction with existing rules:**
- **R8** — fail-fast placement matches every other new check this session: validate `src_file`/`manifest` mutual exclusivity and path safety before `resolve()`/kubectl.
- **R9** — not touched by this FR directly; see the related-finding note above for why it matters anyway.
- **R11** — reading a local file with stdlib `open()` is not a new kubectl-invocation shape; the manifest still reaches kubectl exactly the way it does today, just sourced differently.
