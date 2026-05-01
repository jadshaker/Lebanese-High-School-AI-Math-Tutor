import { useEffect, useState } from 'react'
import { fetchHealth } from '../api/client'
import type { HealthResponse } from '../api/types'

export function useHealth(intervalMs = 30_000) {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let mounted = true

    const check = async () => {
      try {
        const h = await fetchHealth()
        if (mounted) {
          setHealth(h)
          setError(false)
        }
      } catch {
        if (mounted) setError(true)
      }
    }

    check()
    const id = setInterval(check, intervalMs)
    return () => {
      mounted = false
      clearInterval(id)
    }
  }, [intervalMs])

  return { health, offline: error }
}
