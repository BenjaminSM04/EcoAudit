import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, getToken, setToken } from './api'
import type { User } from './api'

import { AuthContext } from './session'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(getToken() !== null)

  useEffect(() => {
    if (getToken() === null) return
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('ecoaudit:logout', onLogout)
    return () => window.removeEventListener('ecoaudit:logout', onLogout)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    await api.login(email, password)
    setUser(await api.me())
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
  )
}
