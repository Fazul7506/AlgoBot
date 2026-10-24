"""Synchronize persisted broker integration runs with GitHub PR and CI state."""
from __future__ import annotations
import os
import requests

class GitHubSyncError(RuntimeError):
    pass

def sync_integration_run(run) -> dict:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "Fazul7506/AlgoBot")
    if not token:
        raise GitHubSyncError("GITHUB_TOKEN is not configured.")
    if not run.pull_request_number:
        raise GitHubSyncError("This integration run has no GitHub pull request number.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    base = f"https://api.github.com/repos/{repo}"
    def get(url):
        response = requests.get(url, headers=headers, timeout=20)
        if not response.ok:
            raise GitHubSyncError(f"GitHub returned HTTP {response.status_code} while synchronizing PR #{run.pull_request_number}.")
        return response.json()
    pr = get(f"{base}/pulls/{run.pull_request_number}")
    sha = (pr.get("head") or {}).get("sha", "")
    checks = get(f"{base}/commits/{sha}/check-runs?per_page=100") if sha else {"check_runs": []}
    combined = get(f"{base}/commits/{sha}/status") if sha else {"state": "pending", "statuses": []}
    check_runs = checks.get("check_runs", [])
    conclusions = [c.get("conclusion") or c.get("status") for c in check_runs]
    legacy_statuses = combined.get("statuses", [])
    checks_complete = bool(check_runs) and all(c.get("status") == "completed" and c.get("conclusion") == "success" for c in check_runs)
    legacy_complete = bool(legacy_statuses) and all(c.get("state") == "success" for c in legacy_statuses)
    all_passed = (checks_complete or (not check_runs and legacy_complete)) and combined.get("state") != "failure"
    failed = any(c in {"failure", "cancelled", "timed_out", "action_required"} for c in conclusions) or any(c.get("state") == "failure" or c.get("state") == "error" for c in legacy_statuses) or combined.get("state") == "failure"
    ready = bool(all_passed and not pr.get("draft") and pr.get("mergeable") is True and pr.get("state") == "open")
    data = {
        "synced": True, "pr_state": pr.get("state"), "draft": bool(pr.get("draft")),
        "mergeable": pr.get("mergeable"), "merge_state": pr.get("mergeable_state"),
        "head_sha": sha, "check_runs": [{"name": c.get("name"), "status": c.get("status"), "conclusion": c.get("conclusion"), "url": c.get("html_url")} for c in check_runs],
        "combined_status": combined.get("state"), "checks_passed": all_passed, "checks_failed": failed,
        "merge_ready": ready, "checked_at": __import__("django.utils.timezone", fromlist=["now"]).now().isoformat(),
    }
    run.head_sha = sha
    run.validation_results = {**(run.validation_results or {}), "github": data}
    if pr.get("merged"):
        run.status = "merged"
    elif failed:
        run.status = "failed"
        run.failure_detail = "One or more GitHub checks failed. See validation_results.github.check_runs."
    elif pr.get("state") == "open":
        run.status = "validating" if not all_passed else "pr_open"
    run.save(update_fields=["head_sha", "validation_results", "status", "failure_detail", "updated_at"])
    return data
