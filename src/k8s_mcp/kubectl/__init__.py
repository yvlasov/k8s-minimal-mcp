"""Kubectl module — subprocess boundary and error mapping."""

from .runner import KubectlResult, run_kubectl

__all__ = ["run_kubectl", "KubectlResult"]
