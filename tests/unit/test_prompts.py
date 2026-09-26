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
    def test_contains_cluster_wide_resource_strings(self):
        result = cilium_troubleshoot_connectivity("sinsia-pl", "pod-to-service connectivity failing")
        assert "ciliumnodes" in result
        assert "ciliumclusterwidenetworkpolicies" in result
        assert "ciliumidentities" in result

    def test_contains_pod_specific_resources_when_pod_named(self):
        result = cilium_troubleshoot_connectivity("sinsia-pl", "pod my-app-pod cannot reach service")
        assert "ciliumendpoints" in result
        assert "ciliumnetworkpolicies" in result
        assert "my-app-pod" in result

    def test_contains_no_pod_specific_resources_when_no_pod_named(self):
        result = cilium_troubleshoot_connectivity("sinsia-pl", "fleet-wide connectivity timeouts on :10250")
        assert "ciliumendpoints" not in result
        assert "ciliumnetworkpolicies" not in result

    def test_every_generated_call_includes_context(self):
        result = cilium_troubleshoot_connectivity("sinsia-pl", "pod my-app-pod cannot reach service")
        # Count occurrences of context= in k_get/k_describe calls
        import re
        context_calls = re.findall(r'context="sinsia-pl"', result)
        assert len(context_calls) >= 3  # At least ciliumnodes, ciliumclusterwidenetworkpolicies, ciliumidentities

    def test_contains_cluster_wide_step_workflow(self):
        result = cilium_troubleshoot_connectivity("sinsia-pl", "pod-to-service connectivity failing")
        assert "Step 1" in result
        assert "Step 2" in result
        assert "Step 3" in result

    def test_contains_pod_specific_steps_when_pod_named(self):
        result = cilium_troubleshoot_connectivity("sinsia-pl", "pod my-app-pod cannot reach service")
        assert "Step 4" in result
        assert "Step 5" in result

    def test_contains_input_params(self):
        result = cilium_troubleshoot_connectivity("sinsia-pl", "pod my-app-pod cannot reach service")
        assert "sinsia-pl" in result
        assert "my-app-pod" in result

    def test_mentions_prometheus_drop_counters(self):
        result = cilium_troubleshoot_connectivity("sinsia-pl", "pod-to-service connectivity failing")
        assert "Prometheus" in result
        assert "cilium_drop_count_total" in result
        assert "not reachable" in result.lower()

    def test_promql_label_values_quoted(self):
        result = cilium_troubleshoot_connectivity("sinsia-pl", "pod-to-service connectivity failing")
        assert 'direction="INGRESS"' in result
        assert 'direction="EGRESS"' in result

    def test_extract_pod_name_from_description(self):
        from k8s_mcp.utils import extract_named_entity
        assert extract_named_entity("pod my-app-pod cannot reach service", "pod") == "my-app-pod"
        assert extract_named_entity("pods/my-app-pod is failing", "pod") == "my-app-pod"
        assert extract_named_entity("named my-app-pod", "pod") == "my-app-pod"
        assert extract_named_entity("fleet-wide connectivity timeouts", "pod") is None


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
