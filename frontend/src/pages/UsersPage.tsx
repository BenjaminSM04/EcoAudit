import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { Role, User } from '../api'
import { useAuth } from '../session'
import { ROLE } from '../labels'

const EMPTY = { email: '', full_name: '', password: '', role: 'medico' as Role }
const MIN_PASSWORD = 10
const MAX_PASSWORD = 128

export default function UsersPage() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState<User[] | null>(null)
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Usuario cuyo restablecimiento de contraseña está desplegado (una fila a la vez).
  const [resetting, setResetting] = useState<number | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  useEffect(() => {
    api
      .listUsers()
      .then(setUsers)
      .catch((err: Error) => setError(err.message))
  }, [])

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await action()
      setUsers(await api.listUsers())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'La operación falló.')
    } finally {
      setBusy(false)
    }
  }

  function create(event: FormEvent) {
    event.preventDefault()
    void run(async () => {
      await api.createUser(form)
      setForm(EMPTY)
    })
  }

  function openReset(id: number) {
    setResetting(id)
    setNewPassword('')
    setShowPassword(false)
    setError(null)
    setNotice(null)
  }

  function closeReset() {
    setResetting(null)
    setNewPassword('')
  }

  function confirmReset(event: FormEvent, target: User) {
    event.preventDefault()
    if (newPassword.length < MIN_PASSWORD || newPassword.length > MAX_PASSWORD) {
      setNotice(null)
      setError(`La contraseña debe tener entre ${MIN_PASSWORD} y ${MAX_PASSWORD} caracteres.`)
      return
    }
    void run(async () => {
      await api.resetUserPassword(target.id, newPassword)
      closeReset()
      setNotice(
        `Contraseña de ${target.full_name} restablecida. Sus sesiones abiertas se cerraron; ` +
          'comuníquele la nueva contraseña por un canal seguro.',
      )
    })
  }

  return (
    <div className="page">
      <h1>Usuarios</h1>

      <form className="card inline-form" onSubmit={create}>
        <label>
          Nombre
          <input
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            required
          />
        </label>
        <label>
          Correo
          <input
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
          />
        </label>
        <label>
          Contraseña inicial
          <input
            type="password"
            autoComplete="new-password"
            minLength={10}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required
          />
        </label>
        <label>
          Rol
          <select
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
          >
            {Object.entries(ROLE).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={busy}>
          Crear usuario
        </button>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="banner" role="status">
          {notice}
        </p>
      )}
      {users === null && !error && <p className="muted">Cargando…</p>}
      {users !== null && (
        <table className="card">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Correo</th>
              <th>Rol</th>
              <th>Estado</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.full_name}</td>
                <td>{user.email}</td>
                <td>{ROLE[user.role]}</td>
                <td>{user.is_active ? 'Activo' : 'Desactivado'}</td>
                <td>
                  {user.id === me?.id ? (
                    // La propia contraseña se cambia con la actual, en Mi cuenta.
                    <Link to="/cuenta">Cambiar mi contraseña</Link>
                  ) : (
                    <div className="actions">
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() =>
                          void run(() => api.updateUser(user.id, { is_active: !user.is_active }))
                        }
                      >
                        {user.is_active ? 'Desactivar' : 'Reactivar'}
                      </button>
                      <button
                        className="secondary"
                        disabled={busy}
                        aria-expanded={resetting === user.id}
                        onClick={() => (resetting === user.id ? closeReset() : openReset(user.id))}
                      >
                        Restablecer contraseña
                      </button>
                    </div>
                  )}
                  {resetting === user.id && (
                    <form className="inline-form reset" onSubmit={(e) => confirmReset(e, user)}>
                      <label>
                        Nueva contraseña para {user.full_name}
                        <input
                          type={showPassword ? 'text' : 'password'}
                          autoComplete="new-password"
                          minLength={MIN_PASSWORD}
                          maxLength={MAX_PASSWORD}
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          required
                          autoFocus
                        />
                      </label>
                      <label className="check">
                        <input
                          type="checkbox"
                          checked={showPassword}
                          onChange={(e) => setShowPassword(e.target.checked)}
                        />
                        Mostrar
                      </label>
                      <button type="submit" disabled={busy}>
                        Confirmar
                      </button>
                      <button type="button" className="secondary" onClick={closeReset}>
                        Cancelar
                      </button>
                    </form>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
