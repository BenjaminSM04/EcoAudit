import { createContext, useContext } from 'react'
import type { User } from './api'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (value === null) throw new Error('useAuth fuera de AuthProvider')
  return value
}

