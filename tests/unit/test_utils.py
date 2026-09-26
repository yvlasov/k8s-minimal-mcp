"""Tests for utils.py — general-purpose text extraction utilities."""

from k8s_mcp.utils import extract_named_entity


class TestExtractNamedEntity:
    def test_pod_with_prefix(self):
        assert extract_named_entity("pod my-app-pod cannot reach service", "pod") == "my-app-pod"

    def test_pod_with_slash(self):
        assert extract_named_entity("pods/my-app-pod is failing", "pod") == "my-app-pod"

    def test_pod_named_pattern(self):
        assert extract_named_entity("named my-app-pod", "pod") == "my-app-pod"

    def test_service_with_prefix(self):
        assert extract_named_entity("service my-svc cannot reach backend", "service") == "my-svc"

    def test_deployment_with_prefix(self):
        assert extract_named_entity("deployment my-deploy has high latency", "deployment") == "my-deploy"

    def test_no_match_returns_none(self):
        assert extract_named_entity("fleet-wide connectivity timeouts", "pod") is None

    def test_single_char_name(self):
        assert extract_named_entity("pod a", "pod") == "a"

    def test_name_with_dots(self):
        assert extract_named_entity("pod my.app.pod", "pod") == "my.app.pod"

    def test_name_with_hyphens(self):
        assert extract_named_entity("pod my-app-pod-123", "pod") == "my-app-pod-123"

    def test_case_insensitive_prefix(self):
        assert extract_named_entity("POD my-app-pod", "pod") == "my-app-pod"
        assert extract_named_entity("Pod my-app-pod", "pod") == "my-app-pod"

    def test_quoted_name(self):
        assert extract_named_entity('pod "my-app-pod"', "pod") == "my-app-pod"
        assert extract_named_entity("pod 'my-app-pod'", "pod") == "my-app-pod"

    def test_plural_pods_prefix(self):
        assert extract_named_entity("pods my-app-pod and other-pod", "pod") == "my-app-pod"

    def test_no_match_for_empty_text(self):
        assert extract_named_entity("", "pod") is None

    def test_name_length_boundary_63_chars(self):
        long_name = "a" * 63
        result = extract_named_entity(f"pod {long_name}", "pod")
        assert result == long_name

    def test_name_too_long_filtered_by_regex(self):
        # Names with uppercase or special chars won't match the k8s naming regex
        assert extract_named_entity("pod My-Invalid-Name", "pod") is None
