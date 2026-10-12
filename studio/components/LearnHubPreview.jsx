'use client'

import { useCallback, useEffect, useRef } from 'react'

const PREVIEW_URL = '/design-preview/learnhub/index.html'

export default function LearnHubPreview({ colors, headingFont, bodyFont, className = '' }) {
  const frame = useRef(null)
  const sendTheme = useCallback(() => {
    frame.current?.contentWindow?.postMessage({
      type: 'agentforge-design-preview', colors, headingFont, bodyFont,
    }, '*')
  }, [colors, headingFont, bodyFont])

  useEffect(() => {
    const ready = event => {
      if (event.source === frame.current?.contentWindow && event.data?.type === 'agentforge-design-preview-ready') {
        sendTheme()
      }
    }
    window.addEventListener('message', ready)
    sendTheme()
    return () => window.removeEventListener('message', ready)
  }, [sendTheme])

  return <iframe ref={frame} src={PREVIEW_URL} title="LearnHub website theme preview"
    onLoad={sendTheme} sandbox="allow-scripts" referrerPolicy="no-referrer"
    className={`block w-full border-0 bg-white ${className}`} />
}
