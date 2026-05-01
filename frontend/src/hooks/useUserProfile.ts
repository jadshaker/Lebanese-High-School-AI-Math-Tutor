import { useCallback, useState } from 'react'

export interface UserProfile {
  displayName: string
  setupDone: boolean
}

const KEY = 'math-atelier-profile-v1'

function load(): UserProfile {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { displayName: '', setupDone: false }
    return JSON.parse(raw) as UserProfile
  } catch {
    return { displayName: '', setupDone: false }
  }
}

export function useUserProfile() {
  const [profile, setProfileState] = useState<UserProfile>(load)

  const setProfile = useCallback((update: Partial<UserProfile>) => {
    setProfileState((prev) => {
      const next = { ...prev, ...update }
      localStorage.setItem(KEY, JSON.stringify(next))
      return next
    })
  }, [])

  const initials = profile.displayName
    ? profile.displayName
        .split(' ')
        .map((w) => w[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : '?'

  return { profile, setProfile, initials }
}
