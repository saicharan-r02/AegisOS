// Request/response shapes of the PR Pilot API (see aegis_os/api_models.py).

/**
 * Analysis object produced by the LLM (keys follow build_analysis_prompt).
 * The backend passes it through as `dict[str, Any]`, so every value is `unknown`
 * and must go through the helpers in lib/format.ts before it is rendered.
 */
export interface Analysis {
  kind?: unknown
  difficulty?: unknown
  summary?: unknown
  rootCause?: unknown
  affected?: unknown
  plan?: unknown
  patch?: unknown
  tests?: unknown
  risks?: unknown
  questions?: unknown
}

export interface GuideStep {
  step_number: number
  title: string
  description: string
  command: string
}

export interface AnalyzeRequest {
  issue_url: string
  github_username: string
  issue_text: string
  provider: 'nvidia'
}

export interface AnalyzeResponse {
  owner: string
  repo: string
  issue_number: number
  issue_url: string
  github_username: string
  analysis: Analysis | null
  guide: GuideStep[]
  branch: string
  commit: string
  pr_title: string
  pr_body: string
  ai_error: string
  fetched_from_github: boolean
}

export interface ExecuteRequest {
  issue_url: string
  github_username: string
  branch: string
  commit_message: string
  pr_title: string
  pr_body: string
  patch: string
  tests: string
  summary: string
  root_cause: string
  affected_files: string[]
}

export interface ExecuteResponse {
  status: string
  workspace_path: string
  branch: string
  commit_sha: string
  changed_files: string[]
  tests_output: string
  pr_url: string | null
  message: string
}

/** What the user typed, after validation of the issue URL. */
export interface IssueContext {
  owner: string
  repo: string
  number: string
  /** Sanitised username, or YOUR-USERNAME when left blank. */
  username: string
  url: string
  issueText: string
}
