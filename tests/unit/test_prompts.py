"""Tests for built-in MCP prompts (FR11).

Each test asserts the returned string contains the exact resource= value
and the exact status-field path it claims to reference, so a future rename
doesn't silently drift the prompt text out of sync with reality.
"""

from k8s_mcp.prompts import argocd_app_health, cilium_troubleshoot_connectivity, rbac_effective_permissions


class TestArgocdAppHealth:
    def test_contains_exact_resource_string(self):
        result = argocd_app_health("my-app", "argocd")
        assert "applications.argoproj.io" in result

    def test_contains_status_field_paths(self):
        result = argocd_app_health("my-app", "argocd")
        assert ".status.sync.status" in result
        assert ".status.health.status" in result
        assert ".status.resources[]" in result

    def test_contains_input_params(self):
        result = argocd_app_health("my-app", "argocd")
        assert "my-app" in result
        assert "argocd" in result

    def test_mentions_unreachable_features(self):
        result = argocd_app_health("my-app", "argocd")
        assert "NOT reachable" in result or "not reachable" in result
        assert "ArgoCD API server" in result


class TestCiliumTroubleshootConnectivity:
    def test_contains_exact_resource_strings(self):
        result = cilium_troubleshoot_connectivity("default", "my-pod")
        assert "ciliumendpoints" in result
        assert "ciliumnetworkpolicies" in result
        assert "pods" in result

    def test_contains_step_workflow(self):
        result = cilium_troubleshoot_connectivity("default", "my-pod")
        assert "Step 1" in result
        assert "Step 2" in result
        assert "Step 3" in result

    def test_contains_input_params(self):
        result = cilium_troubleshoot_connectivity("default", "my-pod")
        assert "my-pod" in result
        assert "default" in result

    def test_mentions_hubble_unreachable(self):
        result = cilium_troubleshoot_connectivity("default", "my-pod")
        assert "NOT reachable" in result or "not reachable" in result
        assert "Hubble" in result


class TestRbacEffectivePermissions:
    def test_contains_k_auth_can_i_reference(self):
        result = rbac_effective_permissions("admin-user", "default")
        assert "k_auth_can_i" in result

    def test_contains_input_params(self):
        result = rbac_effective_permissions("admin-user", "default")
        assert "admin-user" in result
        assert "default" in result

    def test_mentions_fr13_dependency(self):
        result = rbac_effective_permissions("admin-user", "default")
        assert "FR13" in result

    def test_mentions_manual_alternative_gap(self):
        result = rbac_effective_permissions("admin-user", "default")
        assert "Roles" in result
        assert "RoleBindings" in result
