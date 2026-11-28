import { PLACEHOLDER_USERNAME } from '../../lib/format.ts'
import type { AnalyzeResponse } from '../../types.ts'
import { CodeBlock } from '../CodeBlock.tsx'

export function GuidePane({ response }: { response: AnalyzeResponse }) {
  return (
    <div>
      {response.github_username === PLACEHOLDER_USERNAME && (
        <div className="note">Add your GitHub username above and re-run to fill in every command automatically.</div>
      )}
      {response.guide.map((step) => (
        <div className="step" key={step.step_number}>
          <div className="num">{step.step_number}</div>
          <div>
            <h4>{step.title}</h4>
            <p>{step.description}</p>
            <CodeBlock title="Command / link" text={step.command} />
          </div>
        </div>
      ))}
    </div>
  )
}
