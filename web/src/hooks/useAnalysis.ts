import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, analyzeIssue } from '../api.ts'
import { parseIssueForm, usernameForApi } from '../lib/format.ts'
import { PROGRESS_STEPS, STEP_INTERVAL_MS } from '../stages.ts'
import type { AnalyzeResponse, IssueContext } from '../types.ts'

export type Phase = 'idle' | 'loading' | 'done' | 'error'

export interface FormValues {
  url: string
  username: string
  issueText: string
}

export interface AnalysisResult {
  response: AnalyzeResponse
  context: IssueContext
  /** Changes on every successful run so the result view starts fresh. */
  runId: number
}

const BAD_URL_MESSAGE = 'Paste a full GitHub issue URL, e.g. https://github.com/owner/repo/issues/123'

/** Owns one analysis run: request, progress chips, error text and the result. */
export function useAnalysis() {
  const [phase, setPhase] = useState<Phase>('idle')
  const [step, setStep] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const runCounter = useRef(0)

  // While the request is in flight, advance the progress chips on a timer.
  useEffect(() => {
    if (phase !== 'loading') return
    const timer = window.setInterval(() => {
      setStep((current) => (current !== null && current < PROGRESS_STEPS.length - 1 ? current + 1 : current))
    }, STEP_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [phase])

  const run = useCallback(async (values: FormValues) => {
    setError('')
    const context = parseIssueForm(values.url, values.username, values.issueText)
    if (!context) {
      setError(BAD_URL_MESSAGE)
      return
    }

    setPhase('loading')
    setStep(0)
    setResult(null)
    try {
      const response = await analyzeIssue({
        issue_url: context.url,
        github_username: usernameForApi(context.username),
        issue_text: context.issueText,
        provider: 'nvidia',
      })
      runCounter.current += 1
      setStep(PROGRESS_STEPS.length)
      setResult({ response, context, runId: runCounter.current })
      setPhase('done')
    } catch (err) {
      setStep(PROGRESS_STEPS.length)
      setError(
        err instanceof ApiError
          ? err.message
          : `Cannot connect to AegisOS API backend (${(err instanceof Error && err.message) || 'error'})`,
      )
      setPhase('error')
    }
  }, [])

  return { phase, step, error, result, run }
}
