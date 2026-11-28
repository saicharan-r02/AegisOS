import type { SceneController } from './scene/createScene.ts'

/** Progress chips shown while the request is running; they advance on a timer. */
export const PROGRESS_STEPS = [
  'Reading the issue',
  'Finding the root cause',
  'Designing the fix',
  'Writing the patch',
  'Building your PR guide',
] as const

export const STEP_INTERVAL_MS = 2500

/** Scene focus switches to the results view once the page is scrolled past the hero. */
export const SCROLL_FOCUS_THRESHOLD = 180

export const focusForScroll = () => (window.scrollY > SCROLL_FOCUS_THRESHOLD ? 'results' : 'hero')

/**
 * Mirror the progress step onto the 3D scene. Step 0 starts a run,
 * steps 1-4 light up the orbit nodes, and PROGRESS_STEPS.length means finished.
 */
export function applyProgress(scene: SceneController, step: number): void {
  if (step === 0) {
    scene.reset()
    scene.setMode('working')
    scene.setFocus('hero')
    scene.setStage('fetch', 'active')
  } else if (step === 1) {
    scene.setStage('fetch', 'done')
    scene.setStage('analyze', 'active')
  } else if (step === 2 || step === 3) {
    scene.setStage('fetch', 'done')
    scene.setStage('analyze', 'done')
    scene.setStage('solve', 'active')
  } else if (step === 4) {
    scene.setStage('fetch', 'done')
    scene.setStage('analyze', 'done')
    scene.setStage('solve', 'done')
    scene.setStage('guide', 'active')
  } else if (step >= PROGRESS_STEPS.length) {
    scene.setStage('fetch', 'done')
    scene.setStage('analyze', 'done')
    scene.setStage('solve', 'done')
    scene.setStage('guide', 'done')
    scene.setMode('done')
    scene.setFocus(focusForScroll())
  }
}
