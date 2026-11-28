import { useState } from 'react'
import type { PointerEvent } from 'react'
import type { FormValues } from '../hooks/useAnalysis.ts'
import { StageTracker } from './StageTracker.tsx'

interface Props {
  loading: boolean
  error: string
  step: number | null
  onSubmit: (values: FormValues) => void
}

/** Subtle 3D tilt that follows the pointer over the card. */
function tiltOnMove(event: PointerEvent<HTMLDivElement>) {
  const card = event.currentTarget
  const rect = card.getBoundingClientRect()
  const rotateX = ((event.clientY - rect.top) / rect.height - 0.5) * -3
  const rotateY = ((event.clientX - rect.left) / rect.width - 0.5) * 4
  card.style.transform = `perspective(900px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`
}

function resetTilt(event: PointerEvent<HTMLDivElement>) {
  event.currentTarget.style.transform = ''
}

export function IssueForm({ loading, error, step, onSubmit }: Props) {
  const [url, setUrl] = useState('')
  const [username, setUsername] = useState('')
  const [issueText, setIssueText] = useState('')

  return (
    <div className="card" id="form" onPointerMove={tiltOnMove} onPointerLeave={resetTilt}>
      <div className="row">
        <div>
          <label htmlFor="url">GitHub issue URL</label>
          <input
            id="url"
            placeholder="https://github.com/owner/repo/issues/123"
            autoComplete="off"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="me">Your GitHub username</label>
          <input
            id="me"
            placeholder="optional"
            autoComplete="off"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>
      </div>
      <label htmlFor="txt">Issue text and relevant code</label>
      <textarea
        id="txt"
        placeholder="Paste the issue title, description, error logs, and the file(s) where the bug lives — or leave blank to auto-fetch from GitHub."
        value={issueText}
        onChange={(event) => setIssueText(event.target.value)}
      />
      <div className="hint">
        Leave blank to auto-fetch the issue from GitHub, or paste extra code and logs for a sharper patch. The link
        supplies the repo, issue number and every command in your PR guide.
      </div>
      <button className="go" id="go" type="button" disabled={loading} onClick={() => onSubmit({ url, username, issueText })}>
        {loading ? 'Analyzing…' : 'Analyze & solve issue'}
      </button>
      <StageTracker step={step} />
      <div id="err" style={error ? { display: 'block' } : undefined}>
        {error}
      </div>
    </div>
  )
}
