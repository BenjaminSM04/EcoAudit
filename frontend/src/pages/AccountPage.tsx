import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import { useAuth } from '../session'
import { ROLE } from '../labels'

const MIN_LENGTH = 10
const MAX_LENGTH = 128

export default function AccountPage() {
  const { user, logout } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (next.length < MIN_LENGTH) {
      setError(`La nueva contraseña debe tener al menos ${MIN_LENGTH} caracteres.`)
      return
    }
    if (next.length > MAX_LENGTH) {
      setError(`La nueva contraseña puede tener como máximo ${MAX_LENGTH} caracteres.`)
      return
    }
    if (next !== confirm) {
      setError('La confirmación no coincide con la nueva contraseña.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.changePassword(current, next)
      // El backend invalida todos los tokens anteriores, incluido el de esta sesión: se cierra
      // y la pantalla de ingreso muestra el aviso.
      logout('Contraseña actualizada. Inicie sesión con la nueva contraseña.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cambiar la contraseña.')
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <h1>Mi cuenta</h1>
      {user && (
        <dl className="card">
          <dt>Nombre</dt>
          <dd>{user.full_name}</dd>
          <dt>Correo</dt>
          <dd>{user.email}</dd>
          <dt>Rol</dt>
          <dd>{ROLE[user.role]}</dd>
        </dl>
      )}

      <form className="card inline-form" onSubmit={submit}>
        <h2 className="full">Cambiar contraseña</h2>
        <p className="muted full">
          La nueva contraseña debe tener entre {MIN_LENGTH} y {MAX_LENGTH} caracteres. Al
          cambiarla se cerrará esta sesión y deberá ingresar de nuevo.
        </p>
        <label>
          Contraseña actual
          <input
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
            disabled={busy}
          />
        </label>
        <label>
          Nueva contraseña
          <input
            type="password"
            autoComplete="new-password"
            maxLength={MAX_LENGTH}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            disabled={busy}
          />
        </label>
        <label>
          Confirmar nueva contraseña
          <input
            type="password"
            autoComplete="new-password"
            maxLength={MAX_LENGTH}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            disabled={busy}
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? 'Cambiando…' : 'Cambiar contraseña'}
        </button>
        {error && (
          <p className="error full" role="alert">
            {error}
          </p>
        )}
      </form>
    </div>
  )
}
