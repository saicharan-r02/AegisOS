import { useState } from 'react'
import { buildDraft } from '../lib/draft.ts'
import type { AnalyzeResponse, IssueContext } from '../types.ts'
import { AnalysisPane } from './panes/AnalysisPane.tsx'
import { GuidePane } from './panes/GuidePane.tsx'
import { PrTextPane } from './panes/PrTextPane.tsx'
import { SolutionPane } from './panes/SolutionPane.tsx'

const TABS = ['Analysis', 'Solution', 'PR Guide', 'PR Text'] as const

interface Props {
  response: AnalyzeResponse
  context: IssueContext
}

/**
 * Tabbed result view. All panes stay mounted (hidden by CSS) so state such as
 * the "Execute" output survives switching tabs.
 */
export function Results({ response, context }: Props) {
  const [active, setActive] = useState<(typeof TABS)[number]>('Analysis')
  const draft = buildDraft(response, context)
  const paneClass = (tab: (typeof TABS)[number]) => 'pane' + (tab === active ? ' on' : '')

  return (
    <>
      <div className="tabs" id="tabs">
        {TABS.map((tab) => (
          <button key={tab} type="button" className={tab === active ? 'on' : undefined} onClick={() => setActive(tab)}>
            {tab}
          </button>
        ))}
      </div>
      <div id="panes">
        <div className={paneClass('Analysis')}>
          <AnalysisPane analysis={response.analysis} aiError={response.ai_error} />
        </div>
        <div className={paneClass('Solution')}>
          <SolutionPane response={response} context={context} draft={draft} />
        </div>
        <div className={paneClass('PR Guide')}>
          <GuidePane response={response} />
        </div>
        <div className={paneClass('PR Text')}>
          <PrTextPane draft={draft} issueNumber={context.number} />
        </div>
      </div>
    </>
  )
}
