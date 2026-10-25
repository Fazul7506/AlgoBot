"""Create review-only provider draft PRs; generated code is never executed here."""
from __future__ import annotations
import os, re
import requests

API = "https://api.github.com"

class GitHubIntegrationError(RuntimeError):
    pass

def open_provider_draft_pr(*, provider_name: str, provider_slug: str, draft_files: list[dict], summary: str = "") -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "Fazul7506/AlgoBot")
    if not token:
        raise GitHubIntegrationError("GitHub integration is not configured: set GITHUB_TOKEN with repository contents and pull-request permissions.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,80}", provider_slug):
        raise GitHubIntegrationError("Invalid provider slug.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    session = requests.Session()
    def call(method, path, **kwargs):
        response = session.request(method, f"{API}/repos/{repo}/{path.lstrip('/')}", headers=headers, timeout=25, **kwargs)
        if not response.ok:
            raise GitHubIntegrationError(f"GitHub API {method} {path} returned HTTP {response.status_code}; verify repository permissions and branch protection.")
        return response.json() if response.content else {}
    repo_data = call("GET", "")
    base = repo_data.get("default_branch") or "main"
    ref = call("GET", f"git/ref/heads/{base}")
    base_sha = ref["object"]["sha"]
    branch = f"broker-integration/{provider_slug}-{base_sha[:7]}"
    try:
        call("POST", "git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha})
    except GitHubIntegrationError as exc:
        if "HTTP 422" not in str(exc):
            raise
        branch = f"broker-integration/{provider_slug}-{base_sha[:7]}-{os.urandom(2).hex()}"
        call("POST", "git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha})
    for item in draft_files:
        name = item["path"]
        if name not in {"adapter.py", "test_adapter_contract.py", "README.md"}:
            raise GitHubIntegrationError("Generated draft contains a disallowed filename.")
        path = f"apps/brokers/integration_drafts/{provider_slug}/{name}"
        call("PUT", f"contents/{path}", json={"message": f"Draft {provider_name} broker integration: add {name}", "content": __import__("base64").b64encode(item["content"].encode()).decode(), "branch": branch})
    body = (f"## AI-assisted broker integration draft\n\nProvider: **{provider_name}** (`{provider_slug}`)\n\n"
            "This is an untrusted, review-only generated draft. Generated code was not executed, registered, enabled, or merged. "
            "Review API endpoints, auth, order lifecycle, idempotency, reconciliation, risk controls, and sandbox behavior before use.\n\n"
            f"{summary[:4000]}\n\nRequired before merge: provider-specific contract tests, CI green on the latest commit, human review, and documented capabilities/limitations.")
    pr = call("POST", "pulls", json={"title": f"Draft broker integration: {provider_name}", "head": branch, "base": base, "body": body, "draft": True})
    return {"number": pr["number"], "url": pr["html_url"], "head_sha": (pr.get("head") or {}).get("sha", ""), "branch": branch}



def open_project_change_pr(*, task: str, report: dict) -> dict:
    """Open a draft PR for validated general project changes after stale-source checks."""
    from pathlib import Path
    import base64
    import uuid

    from .project_manager_agent import ROOT, _is_allowed_path

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "Fazul7506/AlgoBot")
    if not token:
        raise GitHubIntegrationError(
            "GitHub integration is not configured: set GITHUB_TOKEN with repository contents and pull-request permissions."
        )
    changes = report.get("changes") or []
    if not changes:
        raise GitHubIntegrationError("The project manager produced no safe file changes; no PR was opened.")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    session = requests.Session()

    def call(method, path, *, expected=(200,), **kwargs):
        response = session.request(
            method, f"{API}/repos/{repo}/{path.lstrip('/')}",
            headers=headers, timeout=25, **kwargs,
        )
        if response.status_code not in expected:
            raise GitHubIntegrationError(
                f"GitHub API {method} {path} returned HTTP {response.status_code}; verify permissions and source freshness."
            )
        return response.json() if response.content else {}

    repository = call("GET", "", expected=(200,))
    base = repository.get("default_branch") or "main"
    base_ref = call("GET", f"git/ref/heads/{base}", expected=(200,))
    base_sha = base_ref["object"]["sha"]

    # Preflight every target before creating a branch so stale production code
    # cannot silently overwrite a newer default-branch implementation.
    prepared = []
    for item in changes:
        relative = str(item.get("path") or "")
        content = item.get("content")
        if not _is_allowed_path(relative, allow_new=True) or not isinstance(content, str):
            raise GitHubIntegrationError(f"Project change failed the safe path/content gate: {relative[:160]}")
        local_path = ROOT / relative
        remote = call("GET", f"contents/{relative}?ref={base}", expected=(200, 404))
        if remote:
            try:
                remote_content = base64.b64decode(remote.get("content", "")).decode("utf-8")
            except (ValueError, UnicodeError):
                raise GitHubIntegrationError(f"Could not safely verify the current GitHub version of {relative}.") from None
            if not local_path.is_file():
                raise GitHubIntegrationError(f"Local source for {relative} is missing; refusing a stale overwrite.")
            try:
                local_content = local_path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                raise GitHubIntegrationError(f"Local source for {relative} is unreadable; refusing a stale overwrite.") from None
            if remote_content != local_content:
                raise GitHubIntegrationError(
                    f"GitHub's default-branch version of {relative} differs from this runtime checkout. "
                    "Refresh the deployment source before retrying; no project PR was opened."
                )
            prepared.append({"path": relative, "content": content, "sha": remote.get("sha")})
        else:
            if local_path.exists():
                raise GitHubIntegrationError(
                    f"GitHub does not contain indexed source {relative}; refusing to guess whether it is a new file."
                )
            prepared.append({"path": relative, "content": content, "sha": None})

    branch = f"ai-project-change/{uuid.uuid4().hex[:10]}"
    call("POST", "git/refs", expected=(201,), json={"ref": f"refs/heads/{branch}", "sha": base_sha})
    for item in prepared:
        payload = {
            "message": f"AI project change: {str(report.get('summary') or task)[:100]}",
            "content": base64.b64encode(item["content"].encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if item["sha"]:
            payload["sha"] = item["sha"]
        call("PUT", f"contents/{item['path']}", expected=(201,), json=payload)

    rationale = "\n".join(f"- {str(value)[:500]}" for value in report.get("rationale", [])[:12])
    validation = "\n".join(f"- {str(value)[:500]}" for value in report.get("validation_plan", [])[:12])
    body = (
        "## AI-assisted AlgoBot project change (draft)\n\n"
        f"**Requested task:** {task[:3000]}\n\n"
        f"**Summary:** {str(report.get('summary') or 'No summary supplied')[:3000]}\n\n"
        f"### Rationale\n{rationale or '- Not supplied'}\n\n"
        f"### Validation required\n{validation or '- Run the relevant test suites and review the diff.'}\n\n"
        "### Safety status\n"
        "- Draft PR only; generated code was not executed, deployed, or merged.\n"
        "- Review every file diff and run targeted tests plus production validation.\n"
        "- The integration refuses writes when the runtime checkout differs from the current default branch.\n"
        "- Static preflight is not proof of correctness, security, or production readiness."
    )
    pr = call("POST", "pulls", expected=(201,), json={
        "title": f"AI project change: {str(report.get('summary') or task)[:180]}",
        "head": branch, "base": base, "body": body, "draft": True,
    })
    return {
        "number": pr["number"],
        "url": pr["html_url"],
        "head_sha": (pr.get("head") or {}).get("sha", ""),
        "branch": branch,
    }
