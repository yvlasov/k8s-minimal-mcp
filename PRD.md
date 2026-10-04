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

Feature/fix history since v0.2.0 lives in `CHANGELOG.md`, not here.

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

**R1. Tools map to verbs, not resource types.** Fixed tool set: `get, logs, apply, patch, delete, exec` (+ `describe`, pending §13). `rollout` and `scale` excluded from v1. Two deliberate, named exceptions: `k_get_secret_to_file` (§15 FR9) and `k_get_helm_release` (§15 FR12) — each resource-specific by design because the resource type itself demands different handling, not a precedent for further exceptions.

**R2. Resource names resolve through a two-tier lookup.** A hardcoded core table (see `src/k8s_mcp/data/core_resources.toml`) takes priority, falling back to per-context dynamic discovery (`kubectl api-resources`) for CRDs and extensions. The core table's job is tie-break priority and cold-start resolution, not correctness.

**R3. `context` is mandatory on every tool call as input, and echoed as a mandatory field in every tool output.** No default, no session-scoped state, no implicit reuse. A context is the kubeconfig user+cluster+namespace triple — the same physical cluster may be reachable under several contexts with different identities. Output echo makes every result self-identifying in interleaved cross-context sessions.

**R4. Every output-reducing default is reported in the response, never silently applied.** Any tool that truncates, tails, prunes, or summarizes must state the bound applied (e.g. `"tail": 100, "truncated": true`) so the model can decide whether to re-request unbounded.

**R5. The discovery cache is keyed and refreshed independently per context.**

**R6. Ambiguous resource-name matches are never auto-resolved.** Core-table entries win by default. Remaining collisions return all candidates and require qualification via `resource.group`. `resource` also accepts the fully-qualified `name.group` form directly as an escape hatch. **The resolved `group` must reach the actual kubectl invocation, not just internal resolution** — tools build kubectl's resource argument from `resource_meta.fully_qualified_name`, never the bare canonical name, so a qualified `resource` actually disambiguates the kubectl call and not just `resolve()`'s internal return value (see Issue 38 in `CHANGELOG.md`).

**R7. Mutating capability is gated at server startup by access level, with tools filtered at registration time.** Levels: `readonly` (default) → `get`, `logs`, `describe`, `list_resources`, `list_contexts`, `auth_can_i`; `readwrite` → adds `apply`, `patch`, `delete`; `admin` → adds `exec`, `get_secret_to_file`, `get_helm_release`. The model never sees tools outside its level, so it cannot attempt them, cannot argue past them, and spends no schema tokens on them. `dry_run` remains available as an optional per-call parameter but is **not** the enforcement mechanism.

**R8. Every call is validated against resource metadata (namespaced/cluster-scoped, supported verbs) before execution**, not after a kubectl error.

**R9. All JSON responses are field-pruned by default.** Strip `metadata.managedFields`, `metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"]`, `metadata.uid`, `metadata.generation`, and `metadata.resourceVersion` unconditionally; strip `status` unless the resource kind is one where status carries debugging signal (pods, deployments, statefulsets, jobs, CRDs with conditions) or the caller requests it. `Secret` resources additionally have `.data`/`.stringData` replaced with `{"redacted_keys": [...]}` — key names only, never values, hard block with no opt-out. Pruning is stateless — no caching, always fresh from the API server.

**R10. Read output is bounded by default**, with full detail only on explicit request (see §6 for per-tool values).

**R11. Operations shell out to the `kubectl` binary** with structured output (`-o json`) rather than reimplementing via a client library. `kubectl auth can-i` is the one exception to exit-code-as-failure convention (0=allowed, 1=denied, neither a failure) — `k_auth_can_i` calls `run_kubectl` directly rather than `run_kubectl_checked`.

**R12. MCP Resources (user-driven browse/attach) are out of scope.** Tools only.

> Rules exceed ten as of v0.2.0; the "ten rules" framing from v0.1.0 is dropped in favor of completeness.

## 6. Tool Specification

All tools take `context` (kubeconfig context name) as a required input parameter, and every response includes `context` echoed back as a required output field. Omitted from the table below for brevity.

| Tool | Required (beyond `context`) | Optional | Output-reduction default (reported per R4) | Access level |
|---|---|---|---|---|
| `k_get` | `resource` | `name`, `names`, `namespace`, `all_namespaces`, `label_selector`, `field_selector`, `output`, `jsonpath`, `annotation_selector`, `grep`, `grep_ignore_case` | `output=name` (names only) by default; `json`/`yaml` on request. `output=wide` delegates to kubectl's own `-o wide` and returns its plain-text table verbatim as `output`. `jsonpath` triggers jsonpath mode regardless of `output` (bare `output="jsonpath"` with no `jsonpath` parameter, nested braces in the template, or `output="wide"` with no `jsonpath` set are fail-fast errors with `detail`). `annotation_selector` filters results client-side by `metadata.annotations`, reports `{"matched": N, "total": M}` as `_filtered`; incompatible with `jsonpath`/`output=wide`. All non-jsonpath/non-wide JSON field-pruned per R9. | readonly |
| `k_describe` | `resource` | `name`, `names`, `namespace`, `grep`, `grep_ignore_case` | None — delegates verbatim to `kubectl describe`; `grep` filters the returned text to matching lines, reporting `_filtered` per R4. | readonly |
| `k_logs` | `pod` | `namespace`, `container`, `tail`, `previous`, `since`, `since_time`, `limit_bytes`, `grep`, `grep_ignore_case` | `tail=100`, `limit_bytes=8192`. `since`/`since_time` are mutually exclusive per kubectl's own convention (relative duration vs. absolute RFC3339 timestamp). Response states both bounds and whether truncation occurred by either; a byte-limit truncation includes a `message` pointing at `limit_bytes` specifically, since increasing `tail` alone won't help once the byte cap is what's binding. `grep` filters within the already-`tail`/`limit_bytes`-bounded window (applied after bounding), not the full log history — see §15 FR14. | readonly |
| `k_apply` | `manifest` or `src_file` (exactly one) | `namespace`, `dry_run`, `output`, `jsonpath` | N/A — response states `dry_run` status. `src_file` is an absolute path to a server-filesystem manifest file. `jsonpath` returns the raw jsonpath string as `data`. `output="yaml"` returns `{"_yaml": <string>}`; `output="wide"` is rejected unless `jsonpath` is also set (jsonpath unconditionally overrides output). `output="jsonpath"` without `jsonpath` parameter is a fail-fast error with `detail`. Unknown `dry_run` values are rejected fail-fast (`invalid_dry_run`, Issue 63); `k_patch`'s `type` outside `strategic`/`merge`/`json` likewise (`invalid_patch_type`, Issue 59). | readwrite |
| `k_patch` | `resource`, `patch` | `name`, `names`, `namespace`, `type` (strategic/merge/json), `dry_run`, `output`, `jsonpath` | N/A — same as `k_apply` above. | readwrite |
| `k_delete` | `resource` | `name`, `names`, `namespace`, `label_selector`, `dry_run` | N/A — same | readwrite |
| `k_exec` | `pod`, `command` | `namespace`, `container` | N/A | admin |
| `k_get_secret_to_file` | `name`, `namespace`, `dst_secret_file` | `overwrite` | N/A — response contains only key names and the destination path, never values. Named R1 exception (§15 FR9). | admin |
| `k_get_helm_release` | `release`, `namespace` | `revision`, `include_manifest` | N/A — bounded decoded summary by default; full rendered manifest only on explicit `include_manifest=True`. Decoded `values` returned unredacted — the exposure is closed via `admin`-only access level rather than content filtering (see Issue 39). Named R1 exception (§15 FR12). | admin |
| `k_auth_can_i` | none | `verb`, `resource`, `name`, `namespace`, `as_user`, `as_group`, `list_all` | N/A — single-check mode returns `{"allowed": bool}` plus the literal command; `list_all=True` returns `{"permissions": {...}}`. | readonly |

Supporting tools:

| Tool | Purpose | Access level |
|---|---|---|
| `k_list_contexts` | Enumerate available kubeconfig contexts (user+cluster+namespace triples) | readonly |
| `k_list_resources` | List/search resource types known to the resolver (core table + discovery cache) | readonly |
| *(internal)* resource resolver | Not model-facing; backs all tools per R2, R6, R8 | — |

**Prompts** (a distinct MCP primitive from tools — no schema/tool-count cost, not counted against §12's tool-count success criteria; §15 FR11): `argocd_app_health(name, namespace)`, `cilium_troubleshoot_connectivity(cluster, issue_description)`, `rbac_effective_permissions(as_user, namespace)`. Registered unconditionally, not gated by access level (R7) — a prompt returns only guidance text pointing at the tool calls above, it performs no cluster access itself. `cilium_troubleshoot_connectivity`'s `(cluster, issue_description)` signature is Issue 43's correction — see `CHANGELOG.md`.

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

Error codes: `ambiguous_resource`, `unknown_resource` (+ `suggestions` — resolver-level, before kubectl ever runs), `object_not_found` (resolved type, but kubectl returned `NotFound` for the named object — see `CHANGELOG.md` Issue 42), `verb_unsupported`, `namespace_invalid` (cluster-scoped resource given a namespace, or vice versa), `unknown_context` (+ **full valid context list**, so a wrong guess self-corrects in one round-trip), `access_denied` (verb outside current access level), `authentication_failed` (credentials expired/invalid — 401, distinct from RBAC denial), `kubectl_failure` (unclassified kubectl non-zero exit), `kubectl_timeout` (subprocess exceeded timeout), `kubectl_not_installed` (binary not in PATH), `kubectl_exec_error` (OSError executing kubectl), `kubectl_unreachable` (cluster/network unreachable — DNS, connection refused), `kubectl_invalid_argument` (kubectl CLI rejected the invocation), `object_invalid` (API server rejected the object on apply/patch), `unexpected_output` (kubectl exited 0 but its stdout was not parseable JSON — raw text returned under `raw`; see `CHANGELOG.md` Issue 58), `invalid_patch_type` (`type` outside the documented `strategic`/`merge`/`json` enum, rejected before kubectl runs; see `CHANGELOG.md` Issue 59), `invalid_dry_run` (`dry_run` outside the documented `none`/`client`/`server` values, rejected before kubectl runs; see `CHANGELOG.md` Issue 63).

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
| **Dedicated `k_events` tool** | `k_get resource="events"` + `field_selector=involvedObject.name=...,involvedObject.kind=...` already covers the primary use case through the existing verb, no new tool needed. Follow-up done separately: `events` added to the R2 core table (§15 FR7). |
| **Server-level `--kubeconfig` flag** | Considered, implemented, then removed. It was only ever wired into `k_list_contexts` — every other tool and the discovery cache resolved `context` against kubectl's own default regardless. Fixing that properly meant real surface-area cost across every handler for a flag whose only legitimate use case (multiple kubeconfig files) `$KUBECONFIG` already solves without server involvement. Decision: drop the flag; rely entirely on kubectl's own default resolution. See `CHANGELOG.md` Issues 33/34. |

## 12. Success Criteria

- Total model-visible tool count ≤ 10 at `readonly`, ≤ 12 at `admin`.
- Full CRUD coverage of an arbitrary CRD (cert-manager `Certificate`, Cilium `CiliumNetworkPolicy`, ArgoCD `Application`) with **zero** server-side code changes.
- Tokens consumed per resolved debugging task ≤ 40% of the 222-tool baseline being replaced.
- Zero wrong-context mutations across a scripted multi-context test scenario.
- Ambiguous-resource calls (`networkpolicy` on a Cilium cluster) never silently resolve to the wrong API group.

**Current status against `main` (as of 2026-10-04 @ `4fac0f5`; counts re-verified against
`access.py` + the per-level registration assertions in `tests/unit/test_server.py` — dating
itself was item 9 of Issue 60):**
- **Tool count:** met — 6 tools at `readonly`, 9 at `readwrite`, 12 at `admin` (limit 12).
- **Ambiguous-resource / wrong-API-group criterion:** met (see Issue 38 in `CHANGELOG.md` for the period it was violated and how it was fixed).
- **CRUD coverage of an arbitrary CRD with zero server-side changes:** **met** — read and write paths both hold. Discovery verb translation (FR23) maps raw Kubernetes API verbs (`create`, `update`, `patch`, etc.) to MCP tool-verbs (`apply`, `patch`, etc.), and `daemonsets` is now in the static core table. See CHANGELOG.md FR23.
- **Token budget ≤40%:** unmeasured — §10's own instrumentation step was never built.
- **Zero wrong-context mutations:** structurally enforced by R3 (no default `context`, no session state) across every tool; no dedicated named multi-context test scenario exists as its own artifact, but every handler test exercises distinct `context` values and asserts correct echo.

## 13. Open Questions

- [x] **Ship `k_describe` at all?** — **resolved: shipped** (readonly+, counted in §12's 12-tool total; `_SHIP_DESCRIBE` kept as the reversibility seam SPEC §7 asked for). Original reasoning: Red Hat didn't implement it despite native API access, shipping `get` + `events` instead. Its output is verbose unstructured text — worst context-per-useful-byte of any candidate tool. Dropping it also removes R11's primary justification, reopening native-vs-subprocess on cleaner grounds.
- [x] `k_exec` in v1, or deferred given risk profile even at `admin`? — **resolved: shipped at `admin`** (`_SHIP_EXEC`).
- [x] ~~Which kinds warrant `status` retention by default under R9~~ — resolved as implemented: `output/pruning.py`'s `_STATUS_KINDS`/`_CONDITION_KINDS` are hardcoded allowlists (the latter currently `CustomResourceDefinition`, `Certificate`, `CiliumNetworkPolicy`), not a general "CRDs with conditions" rule. **Residual gap:** an arbitrary CRD with `status.conditions` outside that allowlist (e.g. ArgoCD `Application`) still has `status` stripped by default unless the caller passes `keep_status=True` — no dynamic "has `status.conditions`" detection exists. Extending `_CONDITION_KINDS`, or introducing generic conditions-shape detection, is open for a future FR if this proves to matter in practice.
- [ ] Discovery cache refresh trigger: TTL only, on-miss-retry only, or both.
- [ ] `rollout`/`scale` post-v1 — contingent on observed usage skew. Red Hat's `resources_scale` (get-or-set, always returns current scale) is a cleaner pattern than folding scale into `patch` if added.
- [ ] Cilium/Hubble CLI integration as a v2 `--additional-tools` option (Azure ships `call_cilium`/`call_hubble`); orthogonal to CRD access, but `hubble observe` is more useful for Cilium debugging than reading CRDs.
- [ ] Audit/logging sink for mutating calls.

## 14. Implementation Notes

- Language/runtime: Python + FastMCP (see SPEC.md).
- `kubectl` binary required in the server's execution environment with kubeconfig access to all target contexts.
- Core resource table should be a version-controlled static data file, not inline code, to ease updates as API conventions shift (cf. historical `extensions/v1beta1` → `apps/v1`).
- Field-pruning (R9) should be a single response-transform applied uniformly at the output boundary, not per-tool logic.

## 15. Feature Requests / Improvements

Not part of v1 scope. Tracked here as candidates, not commitments — promote to a numbered section above only once accepted. Shipped-status and verification history for each FR lives in `CHANGELOG.md`; `KNOWN_ISSUES.md` tracks current status.

### FR1. `k_get` `output=jsonpath` support — **Done**

**Motivation.** kubectl's `-o jsonpath=<template>` extracts exactly the fields a caller asks for instead of returning a full (even pruned/bounded) object. For targeted queries — "just this pod's IP", "just the image tags across a deployment's containers" — this is a stronger context-economy lever than `output=json`/`yaml`.

**Shape:** `jsonpath_template: string` param on `k_get`/`k_apply`/`k_patch`; presence of the template (not `output=="jsonpath"`) triggers jsonpath mode. Bypasses R9 pruning (nothing left to strip). Echoes `jsonpath_template` back per R4. Malformed jsonpath maps through `kubectl_failure`, except the proven-common nested-brace mistake, which gets its own `invalid_jsonpath_template` error (FR8).

**Scope boundary:** `k_get`-only for the template-required enum value; `describe`/`logs` excluded (not structured output).

**Superseded by FR20 (done):** the param was renamed `jsonpath_template`→`jsonpath` and `output="jsonpath"` was dropped as a documented value entirely — the presence of `jsonpath` alone is now the sole, unconditional trigger, overriding `output` regardless of its value. This section is left as the historical record of what originally shipped; see FR20 for the current design.

### FR2. `annotation_selector` for `k_get` — **Done**

**Motivation.** kubectl has no server-side annotation selector — `-l`/`--selector` only matches labels. Resources tagged via annotations (GitOps tooling, Helm's `meta.helm.sh/*`, custom operator bookkeeping) had no narrowing mechanism short of fetching everything and filtering by hand outside the tool.

**Shape:** `annotation_selector: str | None` on `k_get` only. Syntax: comma-separated (AND) `key=value`/`key!=value`/bare `key`. Forces a full `-o json` fetch internally when set, filters client-side, then continues through the normal `prune()` → bounding pipeline. Reports `_filtered: {"matched": N, "total": M}`.

### FR3. `k_list_resources` tool — **Done**

**Motivation.** The per-context discovery cache (R5) already parses `kubectl api-resources -o wide` into structured records to back `resolve()`/`validate()` internally — none of that was model-facing. The model had no way to discover what resource types (especially CRDs) exist except by guessing and getting an `unknown_resource` error.

**Shape:** `readonly` tool, optional `search` substring filter (canonical/kind/group). Reuses the existing per-context `DiscoveryCache` verbatim.

### FR4. Unit test coverage for `k_delete`, `k_describe`, `k_logs`, `k_exec`, `k_list_contexts` — **Done**

**Motivation.** Only `k_get`/`k_apply`/`k_patch` had unit tests; `k_exec` and `k_delete` (the two highest-blast-radius tools) shipped with zero automated verification. Two real bugs surfaced while scoping this FR and were fixed as part of it — see Issues 17/18 in `CHANGELOG.md`.

### FR5. Fix `k_get`'s `output=wide` no-op — **Done**

**Motivation.** `output/bounding.py`'s `apply_output_format()` `"wide"` branch was byte-identical to the default (unrequested) output — kubectl's real `-o wide` (resource-kind-specific computed columns) was never reproduced. **Why not derive it from JSON:** kubectl's per-kind table-printer logic isn't a generic transform over structured JSON; reimplementing it in Python would violate both R1 (no per-resource special-casing) and R11 (shell out, don't reimplement).

**Shape:** invoke kubectl with the actual `-o wide` flag, return its plain-text table verbatim as `{"output": ...}` — same precedent as `k_describe`.

### FR6. Fix `k_apply`/`k_patch`'s non-functional `output` param — **Done**

**Motivation.** `output="yaml"` on `k_apply`/`k_patch` silently returned the same pruned JSON as if unset — `apply_output_format()` was never actually called for either tool.

**Shape:** call the existing `apply_output_format()` helper (already used by `k_get`) after `prune()`. `output="wide"` explicitly rejected (`invalid_output`) rather than silently ignored — `-o wide` has no meaning for a single-object apply/patch response.

### FR7. Add `events` to the R2 core table — **Done**

**Motivation.** `events` was absent from `data/core_resources.toml` despite being a stable, universally-available built-in type — every other call fell through to per-context discovery. Flagged as a follow-up when a dedicated `k_events` tool was rejected (§11) in favor of `k_get resource="events"` + `field_selector`.

**Shape:** `canonical="events"`, `shortnames=["ev"]`, `kind="Event"`, `verbs=["get"]` — read-only, matching the `endpoints` entry's pattern.

### FR8. Fail-fast validation for nested-brace `jsonpath_template` syntax — **Done**

**Motivation.** A live occurrence (Issue 29) showed nested-brace multi-field syntax (`{.items[*].{a,b,c}}`) — not valid Kubernetes jsonpath — correctly rejected by kubectl but with zero actionable guidance in the raw error. FR1 explicitly anticipated this exact tradeoff and scoped this fix narrowly to the one proven-common mistake.

**Shape:** `check_nested_braces()` — pure syntactic brace-depth scan, applied to `k_get`/`k_apply`/`k_patch` before `resolve()`/kubectl. New `invalid_jsonpath_template` error explaining the bracket-list/`range` syntax. **Explicit scope boundary:** not a general jsonpath grammar validator — every other malformed-jsonpath case still flows through `kubectl_failure`.

**Unaffected by FR20:** this check operates on the template string's syntax regardless of which parameter name carries it — FR20's rename doesn't change `check_nested_braces()` itself, only which param supplies its input.

### FR9. `k_get_secret_to_file` — write a Secret's decoded content to a local file, never into model context — **Done**

**Motivation.** Every existing read tool returns content directly in the response, which becomes part of the model's context. For `Secret` resources that's a real exposure — credentials/tokens/certificates flowing through the same path as a pod name. This tool decodes a Secret and writes it to a file on disk, returning only key names and the file path — never values.

**Deliberate R1 exception** — named explicitly, not a slippery-slope opener: `Secret` is the one resource type where R1's generic-verb shape is actively the wrong shape, because content must never reach model context.

**Shape (resolved decisions):** `admin`-only. Absolute-path-only (`os.path.isabs()`), no directory allowlist — the admin gate is judged sufficient. Refuses to overwrite by default (`file_exists`); `overwrite=true` required to replace. Written via `os.open(..., O_WRONLY|O_CREAT|O_TRUNC, 0o600)` — no wider-permission window. Output format `{"data": {key: decoded_value, ...}, "base64_keys": [...]}` — non-UTF-8/non-base64 values are written back verbatim (lossless) and their keys listed in `base64_keys`, rather than corrupted.

### FR10. `src_file` — apply a manifest from a local file, never through model context — **Done**

**Motivation.** FR9 lets a caller read a Secret to a file without its content passing through the model. There was no symmetric way back in — `k_apply`'s only input was `manifest: str`, always inline. `src_file` closes the round trip: read a Secret to a file (FR9), edit it out-of-band, apply the edited file back, all without the content ever reaching the model.

**Shape:** `src_file: str | None` alternative to `manifest` on `k_apply` only (not `k_patch` — its `patch` param is a small patch document, not a full manifest). Exactly one of the two required. Same absolute-path rule as FR9's `dst_secret_file`, reusing `unsafe_path`. New `file_read_failed` error mirrors FR9's `file_write_failed`.

**Related finding, resolved via Issue 35:** `k_apply`'s response already echoed a Secret's `.data` verbatim regardless of `src_file`, undercutting this FR's whole motivation — closed by Issue 35's hard-block Secret redaction in `prune()`.

### FR11. Built-in MCP prompts for resources whose computed status is already a plain API object (ArgoCD `Application`, Cilium CRDs) — **Done**

**Motivation.** Live testing confirmed `k_get` already reaches ArgoCD's and Cilium's CRDs generically through the Tier-2 discovery cache — reach was never the gap. The model just has no way to know where the useful status fields live (e.g. ArgoCD's sync/health status) or which resource answers a given troubleshooting question. MCP prompts close that gap without adding resource-specific tools.

**Shape:** three prompts (`argocd-app-health`, `cilium-troubleshoot-connectivity`, `rbac-effective-permissions`), registered unconditionally — no access-level gate, since a prompt performs no cluster access itself. Each returns a literal, exact tool-call shape, not a paraphrase, and states what it does **not** cover.

**Resolved:** prompts do not validate `namespace` against `--allow-namespaces` — the prompt never touches the cluster, so validating a namespace never used for access would be theater.

**Open correction:** `cilium-troubleshoot-connectivity`'s `(namespace, pod)` signature doesn't fit fleet-wide symptoms and omits `context=` — see `KNOWN_ISSUES.md` Issue 43.

### FR12. `k_get_helm_release` — decode a Helm release's storage Secret into usable metadata — **Done**

**Motivation.** Helm v3 stores each release revision as a `Secret` (labels `owner=helm`, `name=<release>`, `version=<revision>`) whose `.data.release` value is `base64(gzip(json))` — technically kubectl-reachable but not usable as-is, and now hard-redacted by Issue 35's Secret handling in `prune()`.

**Shape:** read-only tool `k_get_helm_release(context, release, namespace, revision=None, include_manifest=False)`. Omitted `revision` resolves to the highest `version` label. Response is a bounded, decoded summary; full rendered manifest only on `include_manifest=True`. Fetches the Secret directly (bypassing `prune()`'s redaction), the same pattern FR9 established.

**Resolved via Issue 39 (Option B):** `values` is returned unredacted in full — the exposure was closed by moving the tool to `admin`-only access, not by content filtering.

### FR13. `k_auth_can_i` — thin wrapper over `kubectl auth can-i` for RBAC effective-permission checks — **Done**

**Motivation.** `Role`/`RoleBinding`/`ClusterRole`/`ClusterRoleBinding` are already reachable via generic `k_get`, but answering "can subject X perform verb Y on resource Z" requires walking every binding and resolving aggregated (Cluster)Roles — logic the API server already computes authoritatively via `SubjectAccessReview`.

**Shape:** read-only tool `k_auth_can_i(context, verb=None, resource=None, name=None, namespace=None, as_user=None, as_group=None, list_all=False)`. Single-check mode returns `{"allowed": bool}` plus the literal command; `list_all=True` returns `{"permissions": {...}}`.

**A genuine exception to the exit-code convention, not a rule violation:** `kubectl auth can-i` uses exit code as its answer channel (0=allowed, 1=denied — neither a failure) — must call `run_kubectl` directly, not `run_kubectl_checked`.

**Decision already resolved, not re-litigated:** an unprivileged caller cannot use `--as` to probe beyond their own reach — kubectl itself requires the `impersonate` verb before honoring `--as`/`--as-group`, enforced server-side. No new privilege-escalation surface.

Shipping this tool took two more rounds beyond the core logic to make it actually callable — see `KNOWN_ISSUES.md` Issue 40 / `CHANGELOG.md` for the full history.

### FR14. `grep` — server-side text-filtering for unstructured-text tool output — **Done**

**Motivation.** `k_logs`, `k_describe`, and `k_get`'s `output=wide` all return plain kubectl
text output verbatim, with no server-side narrowing mechanism — unlike JSON-shaped output,
which already has `annotation_selector` (FR2) and `jsonpath_template` (FR1). A caller wanting
only the lines matching a pattern (an error string in a log stream, one field in a `describe`
block, rows matching a name pattern in a `wide` table) must fetch the whole blob and filter in
the model's own context — exactly the R4/R10 context-economy problem this project exists to
avoid, just for the one response shape (raw text) those two mechanisms don't cover.

**Proposed shape:**
- New optional param `grep: str | None = None` (interpreted as a regex, `re.search` per line)
  and `grep_ignore_case: bool = False`, added to `k_logs`, `k_describe`, and `k_get` (relevant
  there only when `output="wide"` — other `k_get` output modes already have `jsonpath_template`/
  `annotation_selector`).
- Filter kubectl's returned text to matching lines, join back with newlines. Report
  `_filtered: {"matched": N, "total": M}` (line counts) via R4 — same shape convention as
  FR2's `_filtered`.
- Malformed regex → new fail-fast error `invalid_grep_pattern` (mirrors `invalid_selector`/
  `invalid_jsonpath_template`), before the kubectl call.
- **Scope boundary:** not extended to `k_exec`'s stdout/stderr in this FR — interactive command
  output, typically short-lived; out of scope unless requested separately.
- **Ordering constraint, binding on the implementation:** `grep` filters only the text field
  (`logs`/`output`), applied *before* `_bound`/`_filtered` metadata is assembled, never the
  other way around. `k_logs`'s truncation hint (added when `limit_bytes` or `tail` bind — see
  its Tool Specification row above) lives in `_bound.message`, a structured field alongside the
  text, not concatenated into the log string itself — this is deliberate so a `grep` pass over
  the text can never filter the hint message out along with non-matching log lines. Any future
  hint/warning text added to a tool that also gets a `grep` param must follow the same rule:
  metadata field, never inline in the greppable content.

**Interaction with existing rules:**
- **R11** — same acknowledgment FR2 already made: this is the server doing its own query logic
  rather than delegating to kubectl, since kubectl has no output-filtering flag for `logs`/
  `describe`. Consistent with existing practice (FR2), not a new category.
- **R4** — `_filtered` reporting, same convention as FR2.
- **R9/R10** — not applicable; no structured JSON involved for any of the three target shapes.

**Resolved design questions (were open, now shipped as built):** for `k_logs` specifically,
`grep` filters only *within* the already-`tail`/`limit_bytes`-bounded window, not the full log
history — kubectl's own `--tail`/`--limit-bytes` flags bound what reaches this tool before
`grep` ever sees it. The `k_logs` tool description states this explicitly (see §6's Tool
Specification table). Matching is regex (`re.search` per line, not plain-substring), with
`grep_ignore_case` mirroring `grep -i`.

**Status:** Done — implemented per the plan at SPEC.md §8 FR14; shipped on `k_logs`, `k_describe`,
and `k_get` (the last only meaningful with `output="wide"`). See `CHANGELOG.md` for the
verification record.

### FR15. Typing/naming consistency cleanup

**Motivation.** Two small, previously-flagged-but-never-applied deviations from this project's
own stated conventions (Rule 9's "strong typing, avoid loose types" and "single source of
truth for defaults"), found while reviewing the codebase for a code-quality pass.

**Proposed shape:**
- `src/k8s_mcp/tools/auth_can_i.py:84` — `discovery_cache: object | None = None` should be
  `discovery_cache: DiscoveryCache | None = None`, matching every other handler's signature
  (`get_helm_release.py:87`'s precedent, among others). This was flagged as a "minor unfixed
  typing deviation" during FR13's original review and never applied — `object` type-checks
  nothing; a caller could pass any value and no static or runtime check would catch it.
- `src/k8s_mcp/tools/logs.py` — `tail`'s default (`100`) is an inline literal at
  `effective_tail = tail if tail is not None else 100`, while `limit_bytes`'s default is a
  named module-level constant (`DEFAULT_LOG_LIMIT_BYTES = 8192`). Extract
  `DEFAULT_LOG_TAIL = 100` for consistency — both defaults are equally part of this tool's
  documented contract (PRD §6) and should be equally easy to find/grep for for the next
  reader.

**Interaction with existing rules:** none — pure consistency cleanup, zero behavior change.
Low effort, low risk; good first task for whoever picks up this list.

### FR16. Add automated lint/type-checking (`mypy` + `ruff`)

**Motivation.** This project's own coding guidelines (strong typing, avoid loose types,
consistent naming, function/class size limits) are currently enforced only by manual review —
nothing in `pyproject.toml` or CI actually checks them. FR15's `object`-typed parameter is a
concrete example of exactly the kind of deviation a type checker would have caught
automatically instead of requiring a human to notice it during a later review pass.

**Proposed shape:**
- Add `mypy>=1.10` and `ruff>=0.6` to `pyproject.toml`'s `dev` optional-dependencies group.
- Baseline `mypy` config (a `[tool.mypy]` section, or a separate `mypy.ini`) — start with
  `disallow_untyped_defs = true` and `warn_return_any = true` at minimum; a full `strict = true`
  pass may surface pre-existing gaps beyond FR15's one finding and should be scoped as its own
  follow-up if so, not silently absorbed into this FR.
- Baseline `ruff` config (`[tool.ruff]` in `pyproject.toml`) covering at least the default
  lint rule set plus import-sorting; `ruff format` as the formatter (already effectively
  followed by hand across this codebase, per its consistent style — codifying it prevents
  drift as more contributors touch it).
- Document both as a `README.md` Testing-section step (`uv run mypy src`, `uv run ruff check`),
  alongside the existing `pytest` instructions.

**Interaction with existing rules:** none direct — this is tooling that enforces rules already
stated in this project's own `CLAUDE.md`-equivalent guidelines, not new design surface.

### FR17. Pin `fastmcp` to a tested version range

**Motivation.** `pyproject.toml`'s `dependencies` still lists `fastmcp>=0.2` — unbounded, and
provably wrong: Issue 13's full history (see `CHANGELOG.md`) is a two-round crash caused
specifically by `fastmcp` API differences between versions (`add_tool()` vs. `.tool()`;
`**kwargs`-shaped tool schemas rejected starting at some version at/before `4.0.4`, which this
project's code now assumes throughout `server.py`). A fresh `pip install`/`uv sync` today could
still resolve to a `fastmcp` version old enough to reproduce Issue 13's exact crash, because
nothing in the dependency constraint reflects what was actually fixed against.

**Proposed shape:** change `"fastmcp>=0.2"` to a range covering the version this project is
actually built and tested against (`fastmcp>=4.0,<5`, adjusted to whatever the currently
installed/tested version genuinely is — confirm via `uv pip show fastmcp` at implementation
time rather than assuming `4.0.4` is still current).

**Interaction with existing rules:** none — a packaging-manifest fix, same class of change as
Issue 37's `pyyaml` fix, not a code change.

### FR18. Add CI (GitHub Actions) running the test suite on push/PR

**Motivation.** This is a public GitHub repository with 337 passing tests and zero automated
verification that they still pass on any given push or PR — every verification in this
project's history (`CHANGELOG.md`) was a manual `pytest` run during a review session. A
contributor (or a future automated change) could break the suite and nothing would flag it
before merge.

**Proposed shape:** a minimal `.github/workflows/test.yml` — checkout, set up Python 3.11+,
`uv sync --extra dev`, `PYTHONPATH=. uv run pytest -q`, triggered on `push` and `pull_request`
against `main`. Once FR16 lands, add `uv run ruff check` and `uv run mypy src` as additional
steps in the same workflow rather than a second one.

**Interaction with existing rules:** none — infrastructure, not application code.

### FR19. Split `errors.py` into a small package by error domain (low priority)

**Motivation.** `src/k8s_mcp/errors.py` is 306 lines — over this project's own stated
300-line-per-module guideline (Rule 9). It's a flat catalog of ~20 small, independent helper
functions (each following the identical `_base()` + specific-fields shape) spanning several
unrelated domains: core resolution errors (`ambiguous_resource`, `unknown_resource`, ...),
file-I/O errors (`unsafe_path`, `file_exists`, `file_write_failed`, `file_read_failed`), and
Helm-specific errors (`helm_release_not_found`, `helm_release_decode_failed`). Not a
correctness problem — no shared mutable state, no complex logic — but it's a single file doing
several unrelated jobs.

**Proposed shape:** convert `errors.py` into a package `errors/` — `errors/core.py` (the
original R2/R6/R7/R8 contract helpers), `errors/files.py` (FR9/FR10's path/file helpers),
`errors/helm.py` (FR12's helpers) — with `errors/__init__.py` re-exporting every public name so
every existing `from ..errors import X` call site across the codebase needs zero changes.
Purely organizational; low priority relative to FR15–FR18, worth doing only once those land
(splitting a file that's about to grow again from FR14's new `invalid_grep_pattern` helper is
premature).

**Interaction with existing rules:** none — module reorganization, zero behavior change.

### FR20. Rename `jsonpath_template`→`jsonpath`; drop `output="jsonpath"`; `jsonpath` unconditionally overrides `output` — **Done**

**Motivation.** A real agent-facing failure mode, reported live: an agent called `k_get(...,
output="jsonpath")` without also setting `jsonpath_template`, hit `invalid_output`, and the
response carried **no `detail` field at all** — just `{"error": "invalid_output", "output":
"jsonpath"}` — giving the agent zero information about what was actually wrong or how to fix
it. Root cause traced to `errors.py`'s `invalid_output()` helper already supporting an optional
`detail` parameter that **none of its five call sites** (`get.py`, `apply.py` ×2, `patch.py`
×2) ever pass. Separately, the underlying design itself invites the mistake: `"jsonpath"` is
advertised as a valid `output` enum value, but setting it alone accomplishes nothing — the
actual trigger, since FR1, has always been `jsonpath_template`'s presence, `output`'s value
being otherwise irrelevant. Two params that can independently claim to select "jsonpath mode,"
one of which is a no-op by itself, is the actual source of confusion — a better error message
alone treats the symptom, not the design that produces it.

**Proposed shape:**
- Rename `jsonpath_template: str | None` → `jsonpath: str | None` on `k_get`/`k_apply`/
  `k_patch` — matches kubectl's own `-o jsonpath=<template>` vocabulary directly (this
  project's own stated principle, R6/§11, is keeping kubectl-identical vocabulary in typed
  params rather than inventing parallel names).
- **Drop `"jsonpath"` from `output`'s documented/valid enum entirely.** `jsonpath`'s presence
  (truthy) becomes the sole trigger for jsonpath mode — full stop, not "presence of the
  template, unless overridden by a specific `output` value."
- **`jsonpath` unconditionally overrides `output` whenever both are set — regardless of what
  `output` is set to.** `k_get(resource=..., jsonpath="{.metadata.name}", output="wide")`,
  `k_apply(..., jsonpath="{.metadata.name}", output="wide")`, and every other
  `output` value in combination with `jsonpath` all succeed identically to `jsonpath` set
  alone. This is a genuine behavior change for `k_apply`/`k_patch`: today, `output="wide"` is
  rejected unconditionally *before* the code ever checks whether `jsonpath_template` would have
  made the value moot (`apply.py`'s `if output == "wide": return invalid_output(...)` fires
  regardless of `jsonpath_template`) — under the new precedence rule, that check must only
  fire when `jsonpath` is *not* set.
- **Legacy/back-compat safety net, not a silent no-op:** a caller that still passes
  `output="jsonpath"` with no `jsonpath` value gets a clear, corrective `invalid_output` error
  — `detail` explicitly states `jsonpath` is no longer a valid `output` value and that setting
  the `jsonpath` parameter alone (no `output` needed) is the correct usage, with a one-line
  example. This directly fixes the original reported failure mode even for a caller still
  reaching for the old convention out of kubectl-CLI habit.
- **While touching every `invalid_output` call site anyway, populate `detail` on all of
  them** — including `apply.py`/`patch.py`'s pre-existing `output=="wide"` rejection, which
  today also passes no `detail` (same root gap, same fix, same commit).
- Success-response key renamed to match: `{"data": ..., "jsonpath": jsonpath}` (was
  `"jsonpath_template"`).

**Interaction with existing rules:**
- **R4** — self-reporting requirement unchanged; only the echoed key name changes.
- **R6/§11** — this rename is a direct application of "keep kubectl-identical vocabulary,"
  the same reasoning already applied to `resource`, `-o` values, and selector syntax elsewhere.
- **FR1/FR8** — both superseded for the param name specifically; their original implementation
  record is left as historical detail (see the "Superseded by FR20" notes on each), not
  rewritten in place.

**Success criteria (this FR is not "implemented" until every one of these has a passing test —
see SPEC.md §8 FR20 for the exact test list):**
1. `jsonpath` set, `output` unset → succeeds, unchanged from today's `jsonpath_template` behavior.
2. `jsonpath` set + `output="json"` → succeeds identically to (1); `output` fully ignored.
3. `jsonpath` set + `output="wide"` on `k_get` → succeeds identically to (1).
4. `jsonpath` set + `output="wide"` on `k_apply`/`k_patch` → **succeeds** (this is the fixed
   ordering bug — today this combination is rejected before `jsonpath_template` is ever
   checked; must have an explicit regression test guarding the new order).
5. `output="jsonpath"` with no `jsonpath` set → `invalid_output`, with a non-empty `detail`
   naming the `jsonpath` parameter as the correct replacement.
6. `output="wide"` on `k_apply`/`k_patch` with **no** `jsonpath` set → still rejected as before
   (regression guard: confirms the reordering didn't accidentally let `wide` through when
   `jsonpath` is genuinely absent).
7. Nested-brace validation (FR8) still fires correctly reading from the renamed `jsonpath` param.
8. `annotation_selector` + `jsonpath` still mutually exclusive on `k_get` (rename-only
   regression case).
9. Every `invalid_output` call site touched by this FR carries a non-empty `detail` in its
   test assertion, not just a bare error code.
10. `tests/unit/test_server.py`'s dispatch-path fixtures for `get`/`apply`/`patch` updated to
    the renamed `jsonpath` kwarg — must match the real wrapper's call shape exactly, per the
    Issue 40/41 lesson this project has already paid for once.
11. Full suite passes with zero regressions elsewhere; every existing
    `jsonpath_template=` call in `test_tools_get.py`/`test_tools_apply.py`/`test_tools_patch.py`
    updated to `jsonpath=`.

**Status:** Done — verified: rename, reordering, and both `detail` messages confirmed present
in `get.py`/`apply.py`/`patch.py`/`server.py` by direct read; PRD §6's table already reflects
the new param. See `CHANGELOG.md` FR20.

### FR21. Distinguishable error codes for timeout/connectivity, authentication vs. authorization, and kubectl-level argument failures

**Motivation.** §7's error contract requires every error response to carry `{"context": ...,
"error": <code>, ...}`. Three real failure classes currently either bypass this contract
entirely or collapse into an undifferentiated code, verified by direct read of
`kubectl/runner.py`, `kubectl/errors.py`, and their tests (2026-09-28):

1. **Timeout / connectivity.** `kubectl/runner.py`'s `run_kubectl()` catches
   `subprocess.TimeoutExpired`, `FileNotFoundError`, and `OSError` and returns ad hoc dicts —
   e.g. `{"error": f"kubectl timed out after {timeout}s", "command": base_args}` — that never
   go through `errors.py`'s `_base()` helper. Confirmed: none of the three branches include a
   `context` key at all (violating R3's "echoed on every output" requirement), and `error`
   holds a free-text sentence rather than a stable code, so a caller can't reliably switch on
   it — `tests/unit/test_runner.py`'s own assertions (`test_timeout_expired_error`,
   `test_file_not_found_error`, `test_oserror_error`) only substring-match the free text,
   confirming no code contract exists to test against. Separately, a genuinely unreachable
   cluster (DNS failure, connection refused) doesn't always hit this path — kubectl itself can
   fail fast with a non-zero exit and a stderr message like `"Unable to connect to the
   server..."`, which today falls through `map_kubectl_error()`'s pattern list into the generic
   `kubectl_failure` catch-all, indistinguishable from any other kubectl error.
2. **Authentication vs. authorization.** `kubectl/errors.py`'s `map_kubectl_error()` maps both
   `"forbidden"` and `"unauthorized"` substrings to the single code `access_denied`. Confirmed:
   `tests/unit/test_kubectl_errors.py`'s `test_unauthorized` asserts a literal `stderr='Unauthorized'`
   (kubectl's real wording for expired/invalid credentials — a 401, distinct from a 403 RBAC
   denial) maps to `access_denied` — identical to `test_forbidden`'s `'error: forbidden: user
   "admin" is forbidden'` (a genuine RBAC/403 denial). These are actionably different failures:
   authentication failure means refresh/fix credentials (expired token, bad cert, wrong
   kubeconfig user); authorization failure means the identity is valid but lacks the RBAC grant
   (actionable via `k_auth_can_i`, §15 FR13). Collapsing them into one code loses that signal.
3. **kubectl/API-server-level argument or object-validation failures.** Most argument mistakes
   are already caught by this project's own pre-execution `validate()` (R8) before kubectl ever
   runs. But failures kubectl/the API server itself rejects — a malformed `--type` value, an
   unknown flag, or an API-server object-validation rejection on `apply`/`patch` (kubectl's own
   `"... is invalid: ..."` wording) — have no dedicated code today and land in the same
   `kubectl_failure` catch-all as truly unclassified failures, indistinguishable from case 1's
   connectivity fallthrough or a genuinely novel kubectl error.

**Proposed shape:**
- **New error codes** in `errors/core.py`, each a thin `_base()`-shaped helper like every
  existing one (never a raw ad hoc dict):
  - `ERROR_KUBECTL_TIMEOUT = "kubectl_timeout"` — the `subprocess.TimeoutExpired` case;
    `detail` states the timeout value and command (mirrors the current free-text content, now
    structured).
  - `ERROR_KUBECTL_NOT_INSTALLED = "kubectl_not_installed"` — the `FileNotFoundError` case
    (missing binary in `PATH`), kept distinct from timeout since it's an environment/setup
    problem, not a network one.
  - `ERROR_KUBECTL_EXEC_ERROR = "kubectl_exec_error"` — the generic `OSError` catch-all
    (permission denied on the binary, etc.).
  - `ERROR_KUBECTL_UNREACHABLE = "kubectl_unreachable"` — new pattern in
    `map_kubectl_error()`: stderr containing `"unable to connect to the server"` / `"connection
    refused"` / `"no such host"` / `"dial tcp"` (case-insensitive) → cluster/network
    unreachable, distinct from a timeout (kubectl failed fast) and from a generic failure.
  - `ERROR_AUTHENTICATION_FAILED = "authentication_failed"` — new pattern in
    `map_kubectl_error()`, checked *before* the existing forbidden/unauthorized branch:
    stderr matching `"unauthorized"` (without `"forbidden"` also present), `"must be logged
    in"`, or `"x509:"` (expired/invalid client certificate) → authentication failure. The
    existing `"forbidden"` branch keeps `access_denied` unchanged — that's the RBAC/authorization
    case and is already correctly named and tested.
  - `ERROR_KUBECTL_INVALID_ARGUMENT = "kubectl_invalid_argument"` — new pattern: stderr
    starting with `"error: unknown flag"` / `"error: unknown shorthand flag"` / `"error:
    unknown command"` (kubectl CLI usage errors) → argument-level rejection, distinct from an
    object/data validation rejection.
  - `ERROR_OBJECT_INVALID = "object_invalid"` — new pattern: stderr containing `" is
    invalid: "` (the API server's own object-validation wording on `apply`/`patch`) →
    server-side validation rejection, distinct from a client-side argument mistake.
  - Everything not matched by any pattern still falls through to the existing `kubectl_failure`
    catch-all — unchanged behavior for truly novel failures.
- **`kubectl/runner.py`:** all three exception branches (`TimeoutExpired`, `FileNotFoundError`,
  `OSError`) construct their return value via the new `errors.py` helpers instead of ad hoc
  dicts — closes the R3/§7 contract gap identified above; every branch now includes `context`.
- **Pattern-match ordering in `map_kubectl_error()`:** authentication/x509 checks must run
  before the existing forbidden check (since "forbidden" is the more specific, higher-confidence
  signal and must not be shadowed), and the new `kubectl_unreachable`/`kubectl_invalid_argument`/
  `object_invalid` checks run before the final `kubectl_failure` fallback. Exact ordering and
  stderr substrings to be finalized against real kubectl output samples during implementation —
  the patterns above are a reasoned starting set, not verified against a live cluster this
  session (no cluster was available for reproduction in the corporate-isolation-respecting scope
  of this review — see `KNOWN_ISSUES.md` process note on `sinsia-pl`).

**Interaction with existing rules:**
- **R3** — every new/fixed branch now echoes `context`, closing the gap `runner.py`'s exception
  handlers currently have.
- **R4** — no output-reduction default involved; not applicable.
- **§7** — this FR is squarely about honoring the existing error contract, not inventing a new
  one; no change to the contract's shape, only to which code a given failure maps to.
- **R8** — case 3's `object_invalid` is deliberately *not* folded into R8's pre-execution
  validation; R8 validates against locally-known resource metadata (namespaced/verb-supported),
  it cannot anticipate API-server-side object schema rejections, which only kubectl/the server
  can surface.

**Success Criteria (test coverage):**
1. `run_kubectl()`'s `TimeoutExpired`/`FileNotFoundError`/`OSError` branches each assert a
   fixed `error` code (`kubectl_timeout`/`kubectl_not_installed`/`kubectl_exec_error`) and a
   present, correct `context` key — replacing the current free-text substring assertions.
2. `map_kubectl_error()`: a `test_unreachable` case (stderr containing "Unable to connect to
   the server") asserts `kubectl_unreachable`, distinct from `kubectl_failure`.
3. `map_kubectl_error()`: `test_unauthorized` (stderr `'Unauthorized'` alone) asserts
   `authentication_failed`; `test_forbidden` continues to assert `access_denied` unchanged —
   both cases co-exist in the same test file, proving the split.
4. A case with both "forbidden" and incidental "unauthorized"-adjacent wording still resolves
   to `access_denied` (forbidden takes precedence) — guards the ordering requirement above.
5. `map_kubectl_error()`: `test_invalid_argument` (stderr `"error: unknown flag: --bogus"`)
   asserts `kubectl_invalid_argument`; a separate `test_object_invalid` (stderr containing
   `"Deployment.apps \"x\" is invalid: ..."`) asserts `object_invalid`.
6. Existing `test_default_kubectl_failure` still passes unchanged for stderr matching none of
   the new patterns — proves the catch-all is preserved, not narrowed incorrectly.
7. Full suite passes with zero regressions; no existing test's expected error code changes
   except `test_unauthorized` (intentionally, per item 3).

**Status:** Done — see CHANGELOG.md FR21.

### FR22. Emit multiline tool output as a JSON array of lines instead of an escaped string

**Motivation.** `k_get`'s `output="wide"`, `k_describe`, and `k_logs` all return their raw
kubectl/API-server text under a string field (`output` for the first two, `logs` for the
third — confirmed by direct read of `tools/get.py:151`, `tools/describe.py:64-66`, and
`output/bounding.py:90`). Once JSON-encoded in the MCP response, embedded newlines become
literal `\n` escapes — a client that spills a large tool response to a file for `grep`/
line-addressable reading gets a single unbroken JSON line instead of one line per log/describe/
wide-table line, defeating that workflow entirely. Emitting the same content as a JSON array of
lines (`list[str]`) instead of one joined string preserves line-addressability with no
`grep -o`/`sed` decoding step needed first.

**Scope note:** the FEATURE REQUESTS table entry names only `data.output`, but the same
escaping problem applies identically to `k_logs`'s `logs` field — FR14 above already treats
`k_get output=wide`, `k_describe`, and `k_logs` as one group solving the analogous
"unstructured text" problem, so this plan extends to all three for consistency rather than
fixing two of three.

**Status:** Done — see CHANGELOG.md FR22.

### FR23. Translate discovery's raw Kubernetes API verbs into this project's MCP-tool verb vocabulary — `apply` is structurally unavailable on every CRD today

**Motivation.** `resolution/models.py`'s `ResourceMeta.verbs` field is explicitly documented:
`verbs: list[str]  # subset of {get, logs, apply, patch, delete, exec}` — this project's own
tool-verb vocabulary, not Kubernetes API verbs. The static core table (`data/core_resources.toml`)
honors this correctly (e.g. `verbs = ["get", "apply", "patch", "delete"]` for `deployments`). But
`resolution/discovery.py`'s live-cluster fallback (`kubectl api-resources -o wide`, used for
every resource type *not* in the static table — i.e. every CRD) parses kubectl's VERBS column
**verbatim** into this same field: real Kubernetes API verbs like `create, delete,
deletecollection, get, list, patch, update, watch`. This is a type-contract violation the model's
own docstring already rules out, and it has a concrete functional consequence, confirmed by
direct trace of `resolver.py:116`'s `if verb not in resource_meta.verbs` check: **`"apply"` is
not a literal Kubernetes API verb** (kubectl apply is a client-side composite of create-or-patch,
not a single REST verb the API server reports), so it can never appear in kubectl's raw VERBS
output — meaning `k_apply` on *any* resource type resolved via discovery (every CRD: ArgoCD
`Application`, Cilium policies, cert-manager `Certificate`, and any core-eligible type like
`daemonsets` not yet hand-added to the static table) fails with `verb_unsupported` **regardless
of the caller's actual RBAC permissions.** `get`/`patch`/`delete` happen to work today only
because those three words coincidentally also exist as literal Kubernetes API verb names — an
accident of overlap, not a designed translation. This directly undermines §12's Success Criteria
("Full CRUD coverage of an arbitrary CRD... with zero server-side code changes") — that line is
already self-qualified as "not independently re-verified against a live cluster," but is now
confirmed false for the write path by direct code trace, not just unverified.

Originally filed narrowly as "add `daemonsets` to the core table" (a real, valid gap — DaemonSets
are a common built-in apps/v1 type with no principled reason to require discovery at all). But
that fix alone would leave every actual CRD's `apply` path broken, which is the larger and more
consequential defect the same root-cause trace surfaced. This FR fixes both: the general
translation (so *every* discovery-resolved resource gets a correct verb set derived from its real
RBAC-reported capabilities) and the specific `daemonsets` table row (so a common built-in type
doesn't pay the discovery round-trip cost at all, consistent with its apps/v1 siblings already in
the table).

**Proposed shape:**
- **General fix — `resolution/discovery.py`:** replace the verbatim `verbs = [v.strip() for v in
  verbs_str.split(",") if v.strip()]` passthrough with a translation table mapping each real
  Kubernetes API verb to the MCP tool-verb(s) it enables:
  - `get` → `get`; `list` → `get` (a listing capability is exercised through `k_get`, not a
    distinct MCP verb).
  - `create` → `apply`; `update` → `apply`; `patch` → `apply`, `patch` (kubectl apply can create
    a new object *or* strategic-merge-patch an existing one — either underlying capability
    should enable it; `patch` also separately enables the direct `k_patch` tool).
  - `delete` → `delete`.
  - `watch`, `deletecollection` → no MCP verb (not exposed by any tool).
  - Any verb kubectl reports that isn't in this table contributes nothing (safe default, not an
    error — accommodates future/unknown API verbs without crashing).
  - The resulting `resource_meta.verbs` is the **union** of the mapped sets for whatever verbs
    kubectl actually reports for that identity in that context — meaning it still correctly
    reflects real RBAC (if `patch`/`create`/`update` are genuinely denied, `apply` correctly
    stays unavailable; this is a translation of reported capability, not an unconditional grant).
  - `logs`/`exec` are deliberately excluded from the mapping — no CRD resolves to those verbs,
    since R2's core-table-wins-ties rule means `pods` (the only type `k_logs`/`k_exec` ever
    target) is always resolved from the static table, never discovery.
- **Specific fix — `data/core_resources.toml`:** add a `[[resource]]` block for `daemonsets`
  (canonical `"daemonsets"`, shortname `"ds"`, kind `"DaemonSet"`, group `"apps"`, version
  `"v1"`, namespaced `true`, `verbs = ["get", "apply", "patch", "delete"]` — identical shape to
  the adjacent `deployments`/`statefulsets`/`replicasets` entries).

**Interaction with existing rules:**
- **R2** — no change to the two-tier priority; this only fixes what discovery produces once it's
  reached, and adds one more type that no longer needs to reach it.
- **R6** — unaffected; ambiguous-match handling is orthogonal to per-entry verb population.
- **R8** — this *is* R8's pre-execution validation; the fix makes that validation correctly
  reflect reality for discovery-sourced entries instead of systematically under-reporting
  `apply` capability.
- **§12 Success Criteria** — once shipped, the "CRUD coverage of an arbitrary CRD" line should be
  updated from "architecturally holds... not independently re-verified" to a claim actually
  backed by this fix, and the update should say so explicitly rather than carry the old hedge
  forward unchanged.

**Success Criteria (test coverage):**
1. Discovery-parsing unit test: a synthetic `kubectl api-resources -o wide` line with raw verbs
   `create,delete,get,list,patch,update,watch` for a CRD-shaped entry produces
   `resource_meta.verbs == {"get", "apply", "patch", "delete"}` (order-independent) — proving the
   translation, not passthrough.
2. A synthetic line with only `get,list,watch` (a read-only CRD, e.g. RBAC denies write)
   produces `resource_meta.verbs == {"get"}` — proving `apply` is correctly *absent* when the
   underlying create/patch/update capability is absent, not unconditionally granted.
3. `resolver.py`/`validate()` integration test: a discovery-resolved (non-core-table) resource
   with `create`/`patch`/`update` in its raw verbs successfully passes `validate(resource_meta,
   "apply", namespace)` — the exact call `k_apply`'s handler makes — where today it fails with
   `verb_unsupported`.
4. `daemonsets` resolves via the static core table (not discovery) and `k_apply`/`k_patch`/
   `k_delete` against a `daemonsets` manifest pass `validate()` without a live cluster (same
   fixture pattern as the existing `deployments`/`statefulsets` core-table tests).
5. Full suite passes with zero regressions; no existing discovery-resolved-resource test's
   expected verb set narrows as a side effect of the translation (only `apply` should newly
   appear where `create`/`patch`/`update` was already present in the raw fixture).

**Status:** Done — see CHANGELOG.md FR23.

### FR24. Multi-resource operations: add `names: list[str]` param to `k_get`/`k_delete`/`k_patch`/`k_describe`

**Motivation.** Users need to operate on multiple resource instances at once without calling the tool repeatedly. The existing tools only accepted a single `name` parameter, requiring the model to issue multiple tool calls for batch operations.

**Proposed shape:**
- Add `names: list[str] | None` parameter to `k_get`, `k_delete`, `k_patch`, `k_describe`.
- For `k_get`/`k_delete`, `name` remains optional but `names` is an alternative; for `k_patch`/`k_describe`, `name` is changed to optional and `names` is the alternative.
- Validation ensures exactly one of `name`/`names` is set. `names` is incompatible with `all_namespaces` (for `k_get`) and `label_selector` (for `k_delete`).
- For `k_get`, when `names` is provided, returns a pruned list of individual resource objects.

**Interaction with existing rules:**
- **R2** — no change to resource resolution; only the parameter shape changes.
- **R8** — pre-execution validation ensures exactly one of `name`/`names` is provided.
- **R9** — `k_get` with `names` returns a pruned list of individual resources.

**Status:** Done — see CHANGELOG.md FR24.

### FR25. Add RBAC and common built-in resources to the core table

**Motivation.** The core resources table (`src/k8s_mcp/data/core_resources.toml`) was missing Kubernetes built-in resources that are stable and commonly used: RBAC resources (`serviceaccounts`, `roles`, `clusterroles`, `rolebindings`, `clusterrolebindings`), scheduling/resource management (`priorityclasses`, `poddisruptionbudgets`, `limitranges`, `resourcequotas`), autoscaling (`horizontalpodautoscalers`), and admission controllers (`validatingwebhookconfigurations`, `mutatingwebhookconfigurations`). Without these in the core table, they fall through to per-context `kubectl api-resources` discovery, which is unnecessary for these built-in, stable resource types.

**Proposed shape:**
- Add the 12 new resource blocks to `src/k8s_mcp/data/core_resources.toml` with correct GVK, shortnames, namespaced status, and `verbs = ["get", "apply", "patch", "delete"]`.

**Interaction with existing rules:**
- **R2** — these resources now bypass per-context discovery and resolve from the static core table.
- **R8** — pre-execution validation correctly reflects the supported verbs for these resources.

**Status:** Done — see CHANGELOG.md FR25.
