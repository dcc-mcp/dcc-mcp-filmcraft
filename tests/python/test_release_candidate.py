"""Offline rejection tests for security-sensitive release admission."""

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "check_release_candidate", Path(__file__).resolve().parents[2] / "scripts/check_release_candidate.py"
)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
COMMIT = "a" * 40


def valid_ci():
    run = {
        "repository": {"full_name": release.REPOSITORY},
        "path": ".github/workflows/ci.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": COMMIT,
        "status": "completed",
        "conclusion": "success",
    }
    jobs = {
        "total_count": 14,
        "jobs": [{"name": name, "status": "completed", "conclusion": "success"} for name in release.EXPECTED_JOBS],
    }
    return run, jobs


def test_current_reviewed_ci_matrix_is_admitted():
    release.validate_ci(*valid_ci(), COMMIT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("event", "pull_request"),
        ("head_branch", "other"),
        ("head_sha", "b" * 40),
        ("path", ".github/workflows/unrelated.yml"),
        ("conclusion", "failure"),
        ("status", "in_progress"),
    ],
)
def test_unreviewed_or_incomplete_ci_is_rejected(field, value):
    run, jobs = valid_ci()
    run[field] = value
    with pytest.raises(ValueError):
        release.validate_ci(run, jobs, COMMIT)


@pytest.mark.parametrize("mutation", ["missing", "skipped", "duplicate", "truncated", "empty"])
def test_partial_success_cannot_replace_the_complete_matrix(mutation):
    run, jobs = valid_ci()
    if mutation == "missing":
        jobs["jobs"].pop()
        jobs["total_count"] -= 1
    elif mutation == "skipped":
        jobs["jobs"][0]["conclusion"] = "skipped"
    elif mutation == "duplicate":
        jobs["jobs"][0] = deepcopy(jobs["jobs"][1])
    elif mutation == "truncated":
        jobs["total_count"] += 1
    else:
        jobs = {"total_count": 0, "jobs": []}
    with pytest.raises(ValueError):
        release.validate_ci(run, jobs, COMMIT)


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"name": "pypi", "protection_rules": []},
        {"name": "pypi", "protection_rules": [{"type": "required_reviewers", "reviewers": []}]},
        {"name": "other", "protection_rules": [{"type": "required_reviewers", "reviewers": [1]}]},
    ],
)
def test_absent_or_unprotected_environment_is_rejected(environment):
    with pytest.raises(ValueError):
        release.validate_environment(environment)


def test_existing_required_reviewer_gate_is_admitted():
    release.validate_environment(
        {"name": "pypi", "protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "Team"}]}]}
    )


@pytest.mark.parametrize(
    "tag,commit,run",
    [
        ("v1.2.3; command", COMMIT, "1"),
        ("v1.2.3rc1", COMMIT, "1"),
        ("v1.2.3", "short", "1"),
        ("v1.2.3", COMMIT, "1/../../other"),
    ],
)
def test_inputs_cannot_change_ref_or_api_scope(tag, commit, run):
    with pytest.raises(ValueError):
        release.identifiers(tag, commit, run)


@pytest.mark.parametrize(
    "name",
    [
        "../secret",
        "/absolute",
        "package/.venv-package/pip.py",
        "package/evidence/token.json",
        "package/vendor/tool.exe",
        "package/runtime/host",
    ],
)
def test_local_or_host_payloads_are_rejected(name):
    with pytest.raises(ValueError):
        release.safe_member(name)
