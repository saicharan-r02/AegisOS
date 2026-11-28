import type { PrDraft } from '../../lib/draft.ts'
import { CodeBlock } from '../CodeBlock.tsx'

export function PrTextPane({ draft, issueNumber }: { draft: PrDraft; issueNumber: string }) {
  return (
    <div>
      <CodeBlock title="PR title" text={draft.title} />
      <CodeBlock title="PR description" text={draft.body} />
      <CodeBlock title="Commit message" text={`${draft.commit}\n\nFixes #${issueNumber}`} />
      <CodeBlock title="Branch name" text={draft.branch} />
    </div>
  )
}
