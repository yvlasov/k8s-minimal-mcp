"""Kubectl module — subprocess boundary and error mapping."""

from .runner import run_kubectl, KubectlResult

__all__ = ["run_kubectl", "KubectlResult"]
