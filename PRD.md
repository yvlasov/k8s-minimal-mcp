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

**R2. Resource names resolve through a two-tier lookup.** A hardcoded core table (pod, deployment, statefulset, replicaset, service, pv, pvc, configmap, secret, networkpolicy, ingress, node, namespace, job, cronjob, endpoints, events) takes priority, falling back to per-context dynamic discovery (`kubectl api-resources`) for CRDs and extensions. The core table's job is tie-break priority and cold-start resolution, not correctness.

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
| `k_get` | `resource` | `name`, `namespace`, `all_namespaces`, `label_selector`, `field_selector`, `output`, `jsonpath_template`, `annotation_selector` | `output=name` (names only) by default; `json`/`yaml` on request. `output=wide` delegates to kubectl's own `-o wide` and returns its plain-text table verbatim as `output`. `jsonpath_template` triggers jsonpath mode regardless of `output` (bare `output="jsonpath"` with no template, or nested braces in the template, are fail-fast errors). `annotation_selector` filters results client-side by `metadata.annotations`, reports `{"matched": N, "total": M}` as `_filtered`; incompatible with `jsonpath_template`/`output=wide`. All non-jsonpath/non-wide JSON field-pruned per R9. | readonly |
| `k_describe` | `resource`, `name` | `namespace` | None — delegates verbatim to `kubectl describe`. | readonly |
| `k_logs` | `pod` | `namespace`, `container`, `tail`, `previous`, `since` | `tail=100`. Response states the bound and whether truncation occurred. | readonly |
| `k_apply` | `manifest` or `src_file` (exactly one) | `namespace`, `dry_run`, `output`, `jsonpath_template` | N/A — response states `dry_run` status. `src_file` is an absolute path to a server-filesystem manifest file. `jsonpath_template` returns the raw jsonpath string as `data`. `output="yaml"` returns `{"_yaml": <string>}`; `output="wide"` is rejected. | readwrite |
| `k_patch` | `resource`, `name`, `patch` | `namespace`, `type` (strategic/merge/json), `dry_run`, `output`, `jsonpath_template` | N/A — same as `k_apply` above. | readwrite |
| `k_delete` | `resource` | `name`, `namespace`, `label_selector`, `dry_run` | N/A — same | readwrite |
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

**Prompts** (a distinct MCP primitive from tools — no schema/tool-count cost, not counted against §12's tool-count success criteria; §15 FR11): `argocd_app_health(name, namespace)`, `cilium_troubleshoot_connectivity(namespace, pod)`, `rbac_effective_permissions(as_user, namespace)`. Registered unconditionally, not gated by access level (R7) — a prompt returns only guidance text pointing at the tool calls above, it performs no cluster access itself. `cilium_troubleshoot_connectivity`'s signature has an open correction pending — see `KNOWN_ISSUES.md` Issue 43.

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

Error codes: `ambiguous_resource`, `unknown_resource` (+ `suggestions`), `verb_unsupported`, `namespace_invalid` (cluster-scoped resource given a namespace, or vice versa), `unknown_context` (+ **full valid context list**, so a wrong guess self-corrects in one round-trip), `access_denied` (verb outside current access level). Known gap: `unknown_resource` also currently fires for a resolved-type-but-missing-object `NotFound` — see `KNOWN_ISSUES.md` Issue 42.

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

**Current status against `main`:**
- **Tool count:** met — 6 tools at `readonly`, 9 at `readwrite`, 12 at `admin` (limit 12).
- **Ambiguous-resource / wrong-API-group criterion:** met (see Issue 38 in `CHANGELOG.md` for the period it was violated and how it was fixed).
- **CRUD coverage of an arbitrary CRD with zero server-side changes:** architecturally holds — FR9/FR11/FR12/FR13 added tools/prompts without special-casing any CRD type. Not independently re-verified against a live cluster.
- **Token budget ≤40%:** unmeasured — §10's own instrumentation step was never built.
- **Zero wrong-context mutations:** structurally enforced by R3 (no default `context`, no session state) across every tool; no dedicated named multi-context test scenario exists as its own artifact, but every handler test exercises distinct `context` values and asserts correct echo.

## 13. Open Questions

- [ ] **Ship `k_describe` at all?** Red Hat didn't implement it despite native API access, shipping `get` + `events` instead. Its output is verbose unstructured text — worst context-per-useful-byte of any candidate tool. Dropping it also removes R11's primary justification, reopening native-vs-subprocess on cleaner grounds.
- [ ] `k_exec` in v1, or deferred given risk profile even at `admin`?
- [ ] Which kinds warrant `status` retention by default under R9 (pods/deployments clearly; the general rule for CRDs with `conditions` is less clear).
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
