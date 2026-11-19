import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api, getToken, setToken } from './api'
import type { User } from './api'

import { AuthContext } from './session'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(getToken() !== null)
  const [notice, setNotice] = useState<string | null>(null)

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
    setNotice(null)
  }, [])

  const logout = useCallback((message?: string) => {
    setToken(null)
    setUser(null)
    setNotice(message ?? null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, notice, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
