# FilmCraft package publishing preparation

This repository now contains a manual-only `.github/workflows/release.yml`.
Adding this source file does not register a PyPI project, configure a publisher,
create a GitHub environment, or publish a package. No push, tag or release event
triggers it. `publish` defaults to `false`.

## Exact prospective publisher identity

| Field | Value |
|---|---|
| Target | PyPI; no TestPyPI override |
| Project | `dcc-mcp-filmcraft` |
| GitHub owner | `dcc-mcp` |
| Repository | `dcc-mcp-filmcraft` |
| Workflow filename | `release.yml` |
| GitHub environment | `pypi` |

These are reviewable source fields, not proof that a publisher or project exists.
Check the authenticated project and pending-publisher lists first. A missing
public project page does not prove name availability or absence of a pending
publisher. Any new continuing publisher authorization requires the user's
specific action-time approval. Existing account authentication, sensitive
challenges and ownership verification remain separate from this workflow.

The current declared package candidate is `0.1.0`, still unreleased. This
document allocates no tag or new version. A future reviewed tag must match the
package metadata and exact approved source commit. Do not substitute artifacts
from a development branch for an existing version's tagged artifacts.

## Source, CI and artifact gates

Dispatch from `main` with an existing stable `vMAJOR.MINOR.PATCH` tag, its full
lowercase commit SHA and the successful **main push** CI run id for that same
commit. The validator rejects another repository/workflow/branch, another head,
an incomplete attempt, missing or skipped jobs, and any change to the reviewed
14-job matrix. The tag must resolve to the approved SHA, be an ancestor of
`origin/main`, and match `pyproject.toml` name/version.

The build job has read-only permissions and no OIDC access. Only its admission
step receives the existing ephemeral GitHub token for read-only metadata calls;
the package build backend does not receive that environment variable. It builds
wheel and sdist, checks metadata/license/Skills/JS assets, rejects local runtime
or evidence contamination, resolves the base wheel in a new environment and
runs installed CLI/entry-point smoke without starting a DCC or browser.

Both distributions and their SHA-256 manifest are stored as one current-run
artifact. The publish job checks that manifest again, executes no source checkout
or build backend, and uses the pinned official PyPA action. Only this job obtains
`id-token: write`; no PyPI password/API token is created or used. It does not
silently skip existing files or overwrite a release.

## Remaining operator configuration and approval

Before any `publish=true` dispatch, the `pypi` GitHub environment must already
exist with a nonempty required-reviewer rule. The read-only admission check
rejects a missing or unprotected environment before the publish job is scheduled;
it does not create or alter one. Configure that protection and the exact PyPI
publisher only after their separately reviewed approval. An administrator can
change repository/environment policy later; these checks are not an atomic lock
against trusted administrators.

`publish=false` produces reviewable artifacts only. After source, tag, CI,
publisher and environment are all verified and the particular upload is
authorized, `publish=true` additionally waits at the environment approval gate
and uploads those same artifacts to PyPI. This workflow never creates tags,
GitHub releases or release PRs. A passing build is not authorization to publish.

The adapter is MIT licensed. It does not ship the vendor runtime. Vendor assets,
fonts, marks and codec redistribution obligations retain their separate terms.

References: [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
and the [official packaging workflow guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/).

## 中文说明

本次只准备发布源码；未创建项目、publisher、环境、凭据或 tag，也未上传。
工作流仅允许手动调度，默认 `publish=false`。未来准确字段为正式 PyPI 项目
`dcc-mcp-filmcraft`、仓库 `dcc-mcp/dcc-mcp-filmcraft`、文件名 `release.yml`、
环境 `pypi`；这些字段须先核对既有配置并取得持续授权的动作时确认。
真实上传还要求精确 tag/提交、同提交的主干完整 CI、已存在且有 reviewer 的环境，
以及针对该次上传的批准；本工作流不会自动创建这些前置条件。
