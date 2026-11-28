import type { AnalyzeResponse, IssueContext } from '../types.ts'

/** PR text shown to the user, with fallbacks for fields the server left empty. */
export interface PrDraft {
  branch: string
  commit: string
  title: string
  body: string
}

export function buildDraft(response: AnalyzeResponse, context: IssueContext): PrDraft {
  const n = context.number
  return {
    branch: response.branch || `fix-issue-${n}`,
    commit: response.commit || `fix: resolve issue #${n}`,
    title: response.pr_title || `Fix: resolve issue #${n}`,
    body:
      response.pr_body ||
      `## What\nAddresses #${n}.\n\n## Why\n\n## How\n\n## Testing\n\n## Checklist\n- [ ] Tests added/updated\n- [ ] Docs updated\n\nFixes #${n}`,
  }
}
