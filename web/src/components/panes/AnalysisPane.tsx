import { asItems, asText, itemText } from '../../lib/format.ts'
import type { Analysis } from '../../types.ts'

interface Props {
  analysis: Analysis | null
  aiError: string
}

function ItemList({ ordered, items }: { ordered?: boolean; items: unknown[] }) {
  const Tag = ordered ? 'ol' : 'ul'
  return (
    <Tag>
      {items.map((item, index) => (
        <li key={index}>{itemText(item)}</li>
      ))}
    </Tag>
  )
}

/** Heading plus list, rendered only when the model returned at least one item. */
function Section({ title, value, ordered }: { title: string; value: unknown; ordered?: boolean }) {
  const items = asItems(value)
  if (items.length === 0) return null
  return (
    <>
      <h3>{title}</h3>
      <ItemList ordered={ordered} items={items} />
    </>
  )
}

export function AnalysisPane({ analysis, aiError }: Props) {
  return (
    <div>
      {aiError && (
        <div className="note">{`AI analysis wasn’t available (${aiError}). Your PR guide below is still complete.`}</div>
      )}
      {analysis && (
        <>
          <span className="badge">{asText(analysis.kind) || 'issue'}</span>
          <span className="badge">{asText(analysis.difficulty) || '?'}</span>
          <h3>Summary</h3>
          <p>{asText(analysis.summary)}</p>
          <h3>Root cause</h3>
          <p>{asText(analysis.rootCause)}</p>
          <Section title="Likely affected files" value={analysis.affected} />
          <Section title="Fix plan" value={analysis.plan} ordered />
          <Section title="Risks" value={analysis.risks} />
          <Section title="Confirm with maintainers" value={analysis.questions} />
          <div className="note">
            Verify this patch against the real repository code before committing. The model only sees what was
            provided.
          </div>
        </>
      )}
    </div>
  )
}
