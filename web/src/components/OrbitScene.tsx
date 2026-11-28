import { useEffect, useRef } from 'react'
import type { SceneController } from '../scene/createScene.ts'

interface Props {
  /** Called with the controller once the scene is ready, and with null when it is torn down. */
  onReady: (controller: SceneController | null) => void
}

/** Full-screen WebGL background. three.js is loaded lazily so the form paints first. */
export function OrbitScene({ onReady }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    let cancelled = false
    let controller: SceneController | null = null

    import('../scene/createScene.ts')
      .then(({ createScene }) => {
        if (cancelled) return
        controller = createScene(canvas)
        onReady(controller)
      })
      .catch(() => {
        // The background is decorative; the page works without it.
        canvas.hidden = true
      })

    return () => {
      cancelled = true
      controller?.dispose()
      onReady(null)
    }
  }, [onReady])

  return <canvas id="bg" ref={canvasRef} aria-hidden="true" />
}
