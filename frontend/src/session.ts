import { createContext, useContext } from 'react'
import type { User } from './api'

interface AuthState {
  user: User | null
  loading: boolean
  // Aviso que la pantalla de ingreso muestra tras un cierre de sesión (p. ej. cambio de contraseña).
  notice: string | null
  login: (email: string, password: string) => Promise<void>
  logout: (notice?: string) => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (value === null) throw new Error('useAuth fuera de AuthProvider')
  return value
}

