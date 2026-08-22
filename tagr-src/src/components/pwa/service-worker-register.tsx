'use client'

import { useEffect } from 'react'

export function ServiceWorkerRegister() {
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/tags/sw.js', { scope: '/tags/' }).catch((err) => {
        console.warn('SW registration failed:', err)
      })
    }
  }, [])

  return null
}
