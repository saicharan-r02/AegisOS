import { useState } from 'react'
import { executeFix } from '../../api.ts'
import { asText, stringsOnly, usernameForApi } from '../../lib/format.ts'
import type { PrDraft } from '../../lib/draft.ts'
import type { AnalyzeResponse, ExecuteResponse, IssueContext } from '../../types.ts'
import { CodeBlock } from '../CodeBlock.tsx'

interface Props {
  response: AnalyzeResponse
  context: IssueContext
  draft: PrDraft
}

function describeExecution(result: ExecuteResponse): string {
  let message = `Status: ${result.status} | Branch: ${result.branch}`
  if (result.commit_sha) message += ` | Commit: ${result.commit_sha}`
  if (result.changed_files.length) message += `\nFiles: ${result.changed_files.join(', ')}`
  if (result.tests_output) message += `\nCheck: ${result.tests_output}`
  message += result.pr_url ? `\nPR: ${result.pr_url}` : `\nWorkspace: ${result.workspace_path}`
  return message
}

export function SolutionPane({ response, context, draft }: Props) {
  const analysis = response.analysis
  const [running, setRunning] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  // Only a finished run is multi-line text; progress and error notes wrap like plain prose.
  const [preformatted, setPreformatted] = useState(false)

  const execute = async () => {
    setRunning(true)
    setNote('Running deterministic PR Pilot pipeline…')
    try {
      const result = await executeFix({
        issue_url: context.url,
        github_username: usernameForApi(context.username),
        branch: draft.branch,
        commit_message: draft.commit,
        pr_title: draft.title,
        pr_body: draft.body,
        patch: asText(analysis?.patch),
        tests: asText(analysis?.tests),
        summary: asText(analysis?.summary),
        root_cause: asText(analysis?.rootCause),
        affected_files: stringsOnly(analysis?.affected),
      })
      setPreformatted(true)
      setNote(describeExecution(result))
    } catch (err) {
      setNote(`Error: ${(err instanceof Error && err.message) || 'Request failed'}`)
    }
    setRunning(false)
  }

  return (
    <div>
      <h3>Proposed fix</h3>
      <CodeBlock
        title="Patch / code changes"
        text={asText(analysis?.patch) || 'No patch generated. Paste the relevant code and run again.'}
      />
      {Boolean(analysis?.tests) && (
        <>
          <h3>Tests to add</h3>
          <CodeBlock title="Tests" text={asText(analysis?.tests)} />
        </>
      )}
      <button type="button" className="aegis-btn" disabled={running} onClick={execute}>
        {running ? 'Cloning, applying patch & committing…' : 'Execute Autonomous Fix & Open PR via AegisOS →'}
      </button>
      <div className="note" style={{ display: note === null ? 'none' : 'block', whiteSpace: preformatted ? 'pre-wrap' : undefined }}>
        {note}
      </div>
    </div>
  )
}
