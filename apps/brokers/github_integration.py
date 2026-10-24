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
