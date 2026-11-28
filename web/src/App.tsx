import { useEffect, useRef, useState } from 'react'
import { IssueForm } from './components/IssueForm.tsx'
import { OrbitScene } from './components/OrbitScene.tsx'
import { Results } from './components/Results.tsx'
import { useAnalysis } from './hooks/useAnalysis.ts'
import type { SceneController } from './scene/createScene.ts'
import { applyProgress, focusForScroll } from './stages.ts'

export default function App() {
  const [scene, setScene] = useState<SceneController | null>(null)
  const { phase, step, error, result, run } = useAnalysis()
  const resultsRef = useRef<HTMLDivElement>(null)

  // Mirror progress onto the 3D scene (also catches up if the scene loads mid-run).
  useEffect(() => {
    if (!scene || step === null) return
    applyProgress(scene, step)
    if (phase === 'error') scene.setMode('error')
  }, [scene, step, phase])

  // Shrink the scene to the corner once the user scrolls down to the results.
  useEffect(() => {
    if (!scene || !result) return
    const onScroll = () => scene.setFocus(focusForScroll())
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [scene, result])

  useEffect(() => {
    if (result) resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [result])

  return (
    <>
      <OrbitScene onReady={setScene} />
      <div className="wrap">
        <header>
          <div className="logo">
            <i></i>PR Pilot
          </div>
          <h1>
            From GitHub issue to <span>merged-ready PR</span>
          </h1>
          <p>
            Paste an issue link. PR Pilot finds the root cause, drafts the fix, and walks you through raising the pull
            request step by step.
          </p>
        </header>

        <IssueForm loading={phase === 'loading'} error={error} step={step} onSubmit={run} />

        <div id="out" className="card" ref={resultsRef} style={result ? { display: 'block' } : undefined}>
          {result && <Results key={result.runId} response={result.response} context={result.context} />}
        </div>
      </div>
    </>
  )
}
