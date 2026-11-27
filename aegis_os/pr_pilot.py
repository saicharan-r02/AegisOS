from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from aegis_os.integrations.github import GitHubIntegration

logger = logging.getLogger("aegis_os.pr_pilot")

_GITHUB_ISSUE_OR_PR_RE = re.compile(
    r"https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/(?:issues|pull)/(?P<number>\d+)",
    re.IGNORECASE,
)

STAGES: tuple[str, ...] = (
    "Reading the issue",
    "Finding the root cause",
    "Designing the fix",
    "Writing the patch",
    "Building your PR guide",
)


@dataclass
class PRPilotGuideStep:
    step_number: int
    title: str
    description: str
    command: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "title": self.title,
            "description": self.description,
            "command": self.command,
        }


@dataclass
class PRPilotResult:
    owner: str
    repo: str
    issue_number: int
    issue_url: str
    github_username: str
    analysis: dict[str, Any] | None
    guide: list[PRPilotGuideStep] = field(default_factory=list)
    branch: str = ""
    commit: str = ""
    pr_title: str = ""
    pr_body: str = ""
    ai_error: str = ""
    fetched_from_github: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "repo": self.repo,
            "issue_number": self.issue_number,
            "issue_url": self.issue_url,
            "github_username": self.github_username,
            "analysis": self.analysis,
            "guide": [step.to_dict() for step in self.guide],
            "branch": self.branch,
            "commit": self.commit,
            "pr_title": self.pr_title,
            "pr_body": self.pr_body,
            "ai_error": self.ai_error,
            "fetched_from_github": self.fetched_from_github,
        }


def parse_github_issue_url(url: str) -> tuple[str, str, int] | None:
    """Extract (owner, repo, number) from a GitHub issue or PR URL."""
    match = _GITHUB_ISSUE_OR_PR_RE.search((url or "").strip())
    if not match:
        return None
    return match.group("owner"), match.group("repo"), int(match.group("number"))


def sanitize_username(username: str | None) -> str:
    cleaned = re.sub(r"[^\w-]", "", (username or "").strip())
    return cleaned or "YOUR-USERNAME"


def slugify_branch(text: str | None, issue_number: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:40].strip("-")
    return slug or f"fix-issue-{issue_number}"


def build_pr_guide(
    owner: str,
    repo: str,
    issue_number: int,
    github_username: str,
    branch: str,
    commit: str,
) -> list[PRPilotGuideStep]:
    """Build the 10-step deterministic PR workflow guide matching PR Pilot."""
    base = f"https://github.com/{owner}/{repo}"
    me = sanitize_username(github_username)
    raw_steps = [
        (
            "Read the rules and claim the issue",
            "Open CONTRIBUTING.md and check the issue is open and unassigned. "
            "Comment “I’d like to work on this” on the issue so maintainers know.",
            f"{base}/issues/{issue_number}\n{base}/blob/HEAD/CONTRIBUTING.md",
        ),
        (
            "Fork the repository",
            f"Click Fork on the repo page. This creates your own copy under {me}.",
            base,
        ),
        (
            "Clone your fork and link the original",
            "Add the original repo as “upstream” so you can stay in sync.",
            f"git clone https://github.com/{me}/{repo}.git\ncd {repo}\ngit remote add upstream {base}.git\ngit fetch upstream",
        ),
        (
            "Create a branch for this issue",
            "Never work on main. Use the branch name below. If the repo’s default branch is master or develop, swap it in.",
            f"git checkout -b {branch} upstream/main",
        ),
        (
            "Apply the fix",
            "Open the Solution tab, apply the changes to your files (or save the diff as fix.patch and apply it). "
            "Always compare against the real code first.",
            "git apply --check fix.patch && git apply fix.patch",
        ),
        (
            "Run tests, linters and the app",
            "Use the commands in the README or CONTRIBUTING file. Add the tests from the Solution tab. "
            "Don’t open a PR with failing checks.",
            "git status\ngit diff",
        ),
        (
            "Commit with a clear message",
            "Reference the issue so GitHub links them. Add -s if the project requires a DCO sign-off.",
            f'git add -A\ngit commit -s -m "{commit}" -m "Fixes #{issue_number}"',
        ),
        (
            "Push your branch",
            "This uploads the branch to your fork.",
            f"git push -u origin {branch}",
        ),
        (
            "Open the pull request",
            "Open the link below (or use the “Compare & pull request” banner). "
            "Paste the title and body from the PR Text tab. Keep “Fixes #"
            f"{issue_number}” so the issue closes on merge.",
            f"{base}/compare/main...{me}:{branch}?expand=1",
        ),
        (
            "Handle review feedback",
            "Maintainers may request changes. Commit to the same branch and push; the PR updates itself. "
            "If the base moved, rebase first.",
            "git fetch upstream\ngit rebase upstream/main\ngit push --force-with-lease",
        ),
    ]
    return [
        PRPilotGuideStep(step_number=idx, title=title, description=desc, command=cmd)
        for idx, (title, desc, cmd) in enumerate(raw_steps, start=1)
    ]


def build_analysis_prompt(
    owner: str,
    repo: str,
    issue_number: int,
    issue_url: str,
    issue_text: str,
) -> str:
    """Build the senior-maintainer analysis prompt matching PR Pilot."""
    return (
        "You are a senior open-source maintainer helping a contributor fix a GitHub issue.\n"
        f"Repository: {owner}/{repo}  Issue: #{issue_number} ({issue_url})\n\n"
        "ISSUE TEXT AND CODE PROVIDED BY THE CONTRIBUTOR:\n"
        '"""\n'
        f"{issue_text[:24000]}\n"
        '"""\n\n'
        "Analyze the issue completely: classify it, find the root cause, plan the fix, and write the patch.\n"
        "If the code isn’t provided, write the most likely correct fix, state your assumptions in rootCause, "
        'mark guessed file paths with "(guess)", and never invent facts about the repository.\n'
        "Return ONLY a valid JSON object (properly escape newlines as \\n inside strings) with exactly these keys:\n"
        "kind (bug|feature|docs|test|refactor), difficulty (easy|medium|hard), "
        "summary (2-3 sentences), rootCause (string), affected (array of file paths), "
        "plan (array of short steps), patch (string: unified diff or full code per file, with file paths), "
        "tests (string: runnable test code), branch (kebab-case, max 40 chars), "
        "commit (conventional commit message, max 72 chars), prTitle (string), "
        f'prBody (markdown with What, Why, How, Testing, Checklist sections and the line "Fixes #{issue_number}"), '
        "risks (array), questions (array of things to confirm with maintainers)."
    )


def extract_json_object(raw: str) -> dict[str, Any]:
    """Extract a JSON object from raw LLM output (handling think tags, code fences, or Python dicts)."""
    import ast
    import json

    text = (raw or "").strip()
    if not text:
        raise ValueError("empty response")

    # Strip <think>...</think> blocks emitted by reasoning models
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

    # Strip ```json ... ``` or ``` ... ``` fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    last_err: Exception | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate, strict=False)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            last_err = exc
            try:
                parsed = ast.literal_eval(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

    if last_err is not None:
        raise ValueError(f"{last_err} (preview: {text[:160]!r})") from last_err
    raise ValueError("Model response did not contain a valid JSON object")


def _invoke_llm_for_analysis(
    prompt: str,
    provider: str = "nvidia",
    model: str | None = None,
) -> dict[str, Any]:
    """Invoke AegisOS's configured LLM router/model and return parsed analysis JSON."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from aegis_os.kernel.llm import get_llm

    try:
        llm = get_llm(provider=provider, model=model, role="CTO", max_tokens=8192)
    except Exception:
        llm = get_llm(provider=provider, model=model, max_tokens=8192)

    messages = [
        SystemMessage(
            content=(
                "You are PR Pilot, AegisOS's senior open-source maintainer assistant. "
                "Respond with ONLY valid JSON matching the requested schema."
            )
        ),
        HumanMessage(content=prompt),
    ]

    if hasattr(llm, "complete"):
        result = llm.complete(messages)
        msg = getattr(result, "message", result)
        content = getattr(msg, "content", None) or str(msg)
    elif hasattr(llm, "invoke_chat"):
        result = llm.invoke_chat(messages)
        content = getattr(result, "content", None) or str(result)
    else:
        response = llm.invoke(messages)
        content = getattr(response, "content", None) or str(response)

    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return extract_json_object(str(content))


def analyze_pr_issue(
    issue_url: str,
    github_username: str | None = None,
    issue_text: str | None = None,
    provider: str = "nvidia",
    model: str | None = None,
    github_client: GitHubIntegration | None = None,
    llm_caller: Any | None = None,
) -> PRPilotResult:
    """
    Analyze a GitHub issue end-to-end using AegisOS's GitHub integration and LLM engine,
    returning structured Analysis, Solution, deterministic 10-step PR Guide, and PR Text.
    """
    parsed = parse_github_issue_url(issue_url)
    if not parsed:
        raise ValueError(
            "Paste a full GitHub issue URL, e.g. https://github.com/owner/repo/issues/123"
        )
    owner, repo, issue_number = parsed
    me = sanitize_username(github_username)
    text = (issue_text or "").strip()
    fetched_from_github = False

    if not text:
        gh = github_client or GitHubIntegration()
        try:
            issue = gh.fetch_issue(issue_url)
            parts = [f"# {issue.title}", "", issue.body]
            if issue.comments:
                parts.extend(["", "## Comments", *issue.comments])
            candidate_text = "\n".join(parts).strip()
            # Only treat as fetched if GitHub API actually returned real content (not fallback)
            if not candidate_text.startswith(f"# Resolve issue #{issue_number} in {owner}/{repo}"):
                text = candidate_text
                fetched_from_github = True
        except Exception as exc:
            logger.debug("GitHub auto-fetch failed for %s: %s", issue_url, exc)

    ai_data: dict[str, Any] | None = None
    ai_error = ""

    if not text:
        ai_error = "paste the issue text to get an analysis and patch"
    else:
        prompt = build_analysis_prompt(owner, repo, issue_number, issue_url.strip(), text)
        caller = llm_caller or _invoke_llm_for_analysis
        try:
            ai_data = caller(prompt, provider=provider, model=model)
            if not isinstance(ai_data, dict):
                ai_data = None
                ai_error = "empty response"
        except Exception as exc:
            ai_error = str(exc) or type(exc).__name__
            logger.warning("PR Pilot LLM analysis failed for %s: %s", issue_url, ai_error)

    a = ai_data or {}
    branch = slugify_branch(a.get("branch"), issue_number)
    commit = str(a.get("commit") or f"fix: resolve issue #{issue_number}").strip()
    pr_title = str(a.get("prTitle") or f"Fix: resolve issue #{issue_number}").strip()
    pr_body = str(
        a.get("prBody")
        or (
            f"## What\nAddresses #{issue_number}.\n\n"
            "## Why\n\n## How\n\n## Testing\n\n"
            f"## Checklist\n- [ ] Tests added/updated\n- [ ] Docs updated\n\nFixes #{issue_number}"
        )
    )

    guide = build_pr_guide(owner, repo, issue_number, me, branch, commit)

    return PRPilotResult(
        owner=owner,
        repo=repo,
        issue_number=issue_number,
        issue_url=issue_url.strip(),
        github_username=me,
        analysis=ai_data,
        guide=guide,
        branch=branch,
        commit=commit,
        pr_title=pr_title,
        pr_body=pr_body,
        ai_error=ai_error,
        fetched_from_github=fetched_from_github,
    )


def execute_pr_pilot(
    issue_url: str,
    github_username: str = "",
    branch: str = "",
    commit_message: str = "",
    pr_title: str = "",
    pr_body: str = "",
    patch: str = "",
    tests: str = "",
    summary: str = "",
    root_cause: str = "",
    affected_files: list[str] | None = None) -> dict[str, Any]:

    import os
    import subprocess
    from pathlib import Path

    from langchain_core.messages import HumanMessage, SystemMessage

    from aegis_os.kernel.llm import get_llm
    from aegis_os.kernel.providers import ProviderRouter
    from aegis_os.workspace.repo_manager import _reset_dir
    parsed_issue = parse_github_issue_url(issue_url)

    if parsed_issue is None:
        raise ValueError("A valid GitHub issue or pull request URL is required.")

    owner, repo, issue_num = parsed_issue
    branch_name = branch.strip() or slugify_branch(pr_title or f"fix-issue-{issue_num}", issue_num)
    ws = Path("workspaces") / f"pr-pilot-{owner}-{repo}-{issue_num}"
    ws.parent.mkdir(parents=True, exist_ok=True)
    _reset_dir(ws)

    clone_url = f"https://github.com/{owner}/{repo}.git"
    subprocess.run(
        ["git", "-c", "core.longpaths=true", "clone", "--depth", "1", clone_url, str(ws)],
        check=True, capture_output=True, text=True, timeout=180,
    )
    subprocess.run(["git", "checkout", "-B", branch_name], cwd=ws, check=True, capture_output=True, text=True)

    applied = False
    clean_patch = (patch or "").strip()
    if clean_patch and ("diff --git" in clean_patch or "--- " in clean_patch):
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "--reject"],
            cwd=ws, input=clean_patch + "\n", text=True, capture_output=True,
        )
        if proc.returncode == 0:
            applied = True

    if not applied:
        candidates = [f for f in (affected_files or []) if (ws / f).is_file()]
        if candidates:
            llm = get_llm(role="DEV", max_tokens=8192)
            for rel in candidates[:3]:
                fp = ws / rel
                content = fp.read_text(encoding="utf-8", errors="replace")
                if len(content) > 40000:
                    continue
                prompt = (
                    f"Update ONLY `{rel}` to fix GitHub issue #{issue_num}.\n"
                    f"Summary: {summary}\nRoot cause: {root_cause}\n"
                    f"Proposed patch reference:\n{clean_patch[:4000]}\n\n"
                    f"Return ONLY the complete updated file content inside a single ``` block, or NO_CHANGES if unchanged.\n\n"
                    f"Current `{rel}`:\n```\n{content}\n```"
                )
                messages = [
                            SystemMessage(content="You are a precise code editor. Output only the updated file inside ``` fences."),
                            HumanMessage(content=prompt)
                            ]

                if isinstance(llm, ProviderRouter):
                    response = llm.complete(messages).message
                else:
                    response = llm.invoke(messages)

                raw = str(getattr(response, "content", "") or "")
                if "NO_CHANGES" not in raw and "```" in raw:
                    parts = raw.split("```")
                    if len(parts) >= 3:
                        body = parts[1]
                        if "\n" in body and not body.startswith("\n"):
                            body = body.split("\n", 1)[1]
                        else:
                            body = body.lstrip("\n")
                        if body.strip():
                            fp.write_text(body, encoding="utf-8")
                            applied = True

    status_proc = subprocess.run(["git", "status", "--porcelain"], cwd=ws, capture_output=True, text=True)
    changed = [line[3:].strip() for line in status_proc.stdout.splitlines() if line.strip()]

    tests_output = ""
    py_files = [f for f in changed if f.endswith(".py") and (ws / f).is_file()]
    if py_files:
        chk = subprocess.run(["python", "-m", "py_compile", *py_files], cwd=ws, capture_output=True, text=True)
        tests_output += f"py_compile exit={chk.returncode}\n{chk.stdout}{chk.stderr}".strip() + "\n"

    if not changed:
        return {
            "status": "NO_CHANGES",
            "workspace_path": str(ws.resolve()),
            "branch": branch_name,
            "commit_sha": "",
            "changed_files": [],
            "tests_output": tests_output.strip(),
            "pr_url": None,
            "message": "Patch could not be auto-applied to the repository; workspace cloned for manual review.",
        }

    subprocess.run(["git", "config", "user.name", github_username or "AegisOS PR Pilot"], cwd=ws, capture_output=True)
    subprocess.run(["git", "config", "user.email", f"{github_username or 'aegis-bot'}@users.noreply.github.com"], cwd=ws, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True, capture_output=True)
    msg = (commit_message or pr_title or f"Fix #{issue_num}").strip()
    if f"#{issue_num}" not in msg:
        msg = f"{msg}\n\nFixes #{issue_num}"
    subprocess.run(["git", "commit", "-m", msg], cwd=ws, check=True, capture_output=True, text=True)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ws, capture_output=True, text=True).stdout.strip()

    pr_url = None
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token and github_username:
        fork_remote = f"https://{token}@github.com/{github_username}/{repo}.git"
        push = subprocess.run(["git", "push", "-u", fork_remote, branch_name, "--force-with-lease"], cwd=ws, capture_output=True, text=True)
        if push.returncode == 0:
            try:
                from aegis_os.integrations.github import GitHubIntegration
                gh = GitHubIntegration(token=token)
                pr_url = gh.create_or_update_pr(
                    owner=owner,
                    repo=repo,
                    head_branch=f"{github_username}:{branch_name}",
                    base_branch="main",
                    title=pr_title or f"Fix #{issue_num}",
                    body=pr_body or f"Fixes #{issue_num}",
                )
            except Exception:
                pass

    return {
        "status": "PR_OPENED" if pr_url else "COMMITTED_LOCAL",
        "workspace_path": str(ws.resolve()),
        "branch": branch_name,
        "commit_sha": sha,
        "changed_files": changed,
        "tests_output": tests_output.strip(),
        "pr_url": pr_url,
        "message": f"Committed {len(changed)} file(s) on branch {branch_name} ({sha}).",
    }
