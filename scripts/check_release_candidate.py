"""Fail-closed release admission and distribution inspection; never publishes."""

from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

REPOSITORY = "dcc-mcp/dcc-mcp-filmcraft"
PROJECT = "dcc-mcp-filmcraft"
EXPECTED_JOBS = (
    {
        f"SDK / Node {node} / {platform}"
        for node in ("22", "24")
        for platform in ("ubuntu-latest", "windows-latest", "macos-latest")
    }
    | {
        f"Core MCP / Python {version} / {platform}"
        for version in ("3.10", "3.12")
        for platform in ("ubuntu-latest", "windows-latest", "macos-latest")
    }
    | {"Official browser WASM acceptance", "Official native CLI Core MCP acceptance"}
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identifiers(tag, commit, run_id=None):
    require(bool(re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag)), "expected a stable vMAJOR.MINOR.PATCH tag")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "expected a full lowercase commit SHA")
    if run_id is not None:
        require(bool(re.fullmatch(r"[1-9][0-9]*", str(run_id))), "expected a positive CI run id")
    return tag[1:]


def validate_ci(run, job_data, commit):
    require(run.get("repository", {}).get("full_name") == REPOSITORY, "CI belongs to another repository")
    require(run.get("path") == ".github/workflows/ci.yml", "CI workflow path differs")
    require(run.get("event") == "push" and run.get("head_branch") == "main", "CI must be a main push")
    require(run.get("head_sha") == commit, "CI tested another commit")
    require(run.get("status") == "completed" and run.get("conclusion") == "success", "CI is not successful")
    jobs = job_data.get("jobs", [])
    require(job_data.get("total_count") == len(jobs), "CI job list is incomplete")
    require(len(jobs) == len(EXPECTED_JOBS), "CI job count differs from the reviewed matrix")
    require({job.get("name") for job in jobs} == EXPECTED_JOBS, "CI job names differ from the reviewed matrix")
    require(
        all(job.get("status") == "completed" and job.get("conclusion") == "success" for job in jobs),
        "every reviewed CI job must complete successfully",
    )


def validate_environment(environment):
    require(environment.get("name") == "pypi", "existing pypi environment was not returned")
    rules = environment.get("protection_rules", [])
    require(
        any(rule.get("type") == "required_reviewers" and rule.get("reviewers") for rule in rules),
        "pypi must already have a required reviewer; no environment is created here",
    )


def gh_json(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def preflight(args):
    version = identifiers(args.tag, args.commit, args.ci_run_id)
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "run only in the canonical repository")
    if args.publish:
        require(os.environ.get("GITHUB_REF") == "refs/heads/main", "publishing must be dispatched from main")
        require(os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "manual dispatch is required")
    tag_commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"refs/tags/{args.tag}^{{commit}}"], text=True
    ).strip()
    require(tag_commit == args.commit, "tag differs from the approved commit")
    subprocess.run(["git", "merge-base", "--is-ancestor", args.commit, "refs/remotes/origin/main"], check=True)
    import tomllib  # Release automation is explicitly run on Python 3.12.

    project = tomllib.loads(subprocess.check_output(["git", "show", f"{args.commit}:pyproject.toml"], text=True))[
        "project"
    ]
    require(project.get("name") == PROJECT and project.get("version") == version, "project/tag metadata differs")
    run = gh_json(f"repos/{REPOSITORY}/actions/runs/{args.ci_run_id}")
    attempt = run.get("run_attempt")
    require(type(attempt) is int and attempt > 0, "CI attempt is missing")
    jobs = gh_json(f"repos/{REPOSITORY}/actions/runs/{args.ci_run_id}/attempts/{attempt}/jobs?per_page=100")
    validate_ci(run, jobs, args.commit)
    if args.publish:
        validate_environment(gh_json(f"repos/{REPOSITORY}/environments/pypi"))
    result = {"commit": args.commit, "tag": args.tag, "version": version, "publish": args.publish}
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            for key in ("commit", "tag", "version"):
                stream.write(f"{key}={result[key]}\n")
            stream.write(f"publish={'true' if args.publish else 'false'}\n")
    return result


def safe_member(name):
    require("\\" not in name and "\x00" not in name, "distribution uses a nonportable path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts, "distribution path escapes its root")
    require(
        not any(
            part.startswith(".venv") or part in {"evidence", "runtime", "vendor", "node_modules"} for part in path.parts
        ),
        "distribution contains a local environment, evidence or vendor payload",
    )
    require(path.suffix.lower() not in {".exe", ".dll", ".so", ".dylib", ".wasm"}, "host binary in distribution")


def validate_metadata(raw, version):
    metadata = email.message_from_bytes(raw)
    require(metadata["Name"] == PROJECT and metadata["Version"] == version, "distribution name/version differs")
    require((metadata["License-Expression"] or metadata["License"]) == "MIT", "adapter license differs")


def inspect_dist(directory, tag, commit):
    version = identifiers(tag, commit)
    files = sorted(directory.iterdir())
    wheel_name = f"dcc_mcp_filmcraft-{version}-py3-none-any.whl"
    sdist_name = f"dcc_mcp_filmcraft-{version}.tar.gz"
    require({p.name for p in files} == {wheel_name, sdist_name}, "expected exactly one universal wheel and one sdist")
    require(all(p.is_file() and not p.is_symlink() for p in files), "distributions must be regular files")
    with zipfile.ZipFile(directory / wheel_name) as wheel:
        for entry in wheel.infolist():
            safe_member(entry.filename)
            require(not stat.S_ISLNK(entry.external_attr >> 16), "wheel symlink")
        metadata_names = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")]
        require(len(metadata_names) == 1, "wheel metadata is ambiguous")
        validate_metadata(wheel.read(metadata_names[0]), version)
        for name in (
            "skills/filmcraft-native/SKILL.md",
            "skills/filmcraft-native/tools.yaml",
            "skills/filmcraft-browser/SKILL.md",
            "skills/filmcraft-browser/tools.yaml",
            "assets/index.js",
            "assets/mcp-bridge.js",
        ):
            require(bool(wheel.read("dcc_mcp_filmcraft/" + name)), "bundled Skill/JS asset missing")
        require(any(name.endswith("/licenses/LICENSE") for name in wheel.namelist()), "wheel license is missing")
    with tarfile.open(directory / sdist_name, "r:gz") as sdist:
        for entry in sdist.getmembers():
            safe_member(entry.name)
            require(entry.isdir() or entry.isfile(), "sdist contains a link or special file")
        metadata = sdist.extractfile(f"dcc_mcp_filmcraft-{version}/PKG-INFO")
        require(metadata is not None, "sdist metadata missing")
        validate_metadata(metadata.read(), version)
        require(sdist.getmember(f"dcc_mcp_filmcraft-{version}/LICENSE").isfile(), "sdist license missing")
    return {
        "project": PROJECT,
        "version": version,
        "tag": tag,
        "commit": commit,
        "artifacts": [
            {"name": p.name, "size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in files
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--ci-run-id")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--inspect-dist", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.inspect_dist:
        require(not args.publish, "inspection cannot authorize publishing")
        result = inspect_dist(args.inspect_dist, args.tag, args.commit)
    else:
        require(args.ci_run_id is not None, "CI run id is required")
        result = preflight(args)
    if args.manifest:
        args.manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
