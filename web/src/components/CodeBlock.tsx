import { useEffect, useRef, useState } from 'react'
import { copyText } from '../lib/clipboard.ts'

interface Props {
  title: string
  text: string
}

const COPIED_LABEL_MS = 1200

/** Titled <pre> block with a copy button that briefly confirms with "Copied". */
export function CodeBlock({ title, text }: Props) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const copy = async () => {
    if (!(await copyText(text))) return
    setCopied(true)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setCopied(false), COPIED_LABEL_MS)
  }

  return (
    <div className="blk">
      <div className="bh">
        <span>{title}</span>
        <button type="button" onClick={copy}>
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre>{text}</pre>
    </div>
  )
}
