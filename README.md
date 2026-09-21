# k8s-minimal-mcp

Minimal verb-based Kubernetes MCP server. Replaces 200+ per-resource tools with a fixed set of 6 verbs (`get`, `logs`, `apply`, `patch`, `delete`, `exec`) parameterized by resource type and kubeconfig context.

## Features

- **Verb-based tools** — `k_get`, `k_logs`, `k_apply`, `k_patch`, `k_delete`, `k_exec` (+ `k_describe`, `k_list_contexts`)
- **Two-tier resource resolution** — hardcoded core table + per-context `kubectl api-resources` discovery for CRDs
- **Access-level gating** — `readonly` (default), `readwrite`, `admin` (filters tools at registration)
- **Field pruning** — strips `uid`, `generation`, `resourceVersion`, `managedFields`, `last-applied-configuration` by default
- **Output bounding** — `k_get` returns names only by default; full JSON/YAML on request
- **Multi-context** — `context` required on every call, echoed in every response

## Installation

```bash
pip install -e .
```

Requires `kubectl` in `$PATH` with valid kubeconfig access.

## Usage

### Start the server

```bash
# Default: readonly access, ~/.kube/config
k8s-mcp

# Read-write access
k8s-mcp --access-level readwrite

# Admin access (includes k_exec)
k8s-mcp --access-level admin

# Restrict to specific namespaces
k8s-mcp --allow-namespaces default,kube-system

# Custom kubeconfig path(s), colon-separated
k8s-mcp --kubeconfig ~/.kube/config:~/.kube/other-config
```

### CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--access-level` | `readonly` | `{readonly, readwrite, admin}` — gates mutating tools |
| `--allow-namespaces` | *(empty)* | Comma-separated namespace allowlist; empty = all |
| `--kubeconfig` | `~/.kube/config` | Path(s) to kubeconfig, colon-separated |

### MCP Client Configuration

```json
{
  "mcpServers": {
    "k8s-minimal-mcp": {
      "command": "k8s-mcp",
      "args": [
        "--access-level", "readonly",
        "--allow-namespaces", "default,kube-system",
        "--kubeconfig", "/path/to/kubeconfig"
      ]
    }
  }
}
```

## Available Tools

| Tool | Description | Access Level |
|------|-------------|--------------|
| `k_get` | Get resources by type/name | readonly |
| `k_logs` | Stream pod logs | readonly |
| `k_describe` | Describe a resource | readonly |
| `k_list_contexts` | List kubeconfig contexts | readonly |
| `k_apply` | Apply a manifest | readwrite |
| `k_patch` | Patch a resource | readwrite |
| `k_delete` | Delete resources | readwrite |
| `k_exec` | Execute commands in a pod | admin |

All tools accept `context` (kubeconfig context name) as a required parameter.

## Resource Resolution

The `resource` parameter accepts:
- Shortname: `po`, `deploy`, `svc`
- Plural: `pods`, `deployments`, `services`
- Kind: `Pod`, `Deployment`, `Service`
- Fully-qualified: `ciliumnetworkpolicies.cilium.io`

Core resources (pods, deployments, services, etc.) resolve from a static table. CRDs and extensions resolve from per-context `kubectl api-resources` discovery with TTL caching.

## Testing

```bash
PYTHONPATH=. pytest tests/ -v
```

## Architecture

```
PRD → SPEC → CLI args → AccessLevel → Tool registration → FastMCP
                                      │
                                      ├─ Resource resolver (core table + discovery cache)
                                      ├─ Field pruner (R9)
                                      ├─ Output bouncer (R10)
                                      └─ Envelope (context echo + metadata)
```

## License

MIT
