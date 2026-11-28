import { PROGRESS_STEPS } from '../stages.ts'

interface Props {
  /** Current progress step, or null before the first run. */
  step: number | null
}

export function StageTracker({ step }: Props) {
  return (
    <div id="stages" style={step === null ? undefined : { display: 'flex' }}>
      {step !== null &&
        PROGRESS_STEPS.map((label, index) => (
          <div key={label} className={'st' + (index < step ? ' done' : index === step ? ' on' : '')}>
            {label}
          </div>
        ))}
    </div>
  )
}
