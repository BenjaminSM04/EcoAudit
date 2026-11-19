import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import type { Role, User } from '../api'
import { useAuth } from '../session'
import { ROLE } from '../labels'

const EMPTY = { email: '', full_name: '', password: '', role: 'medico' as Role }

export default function UsersPage() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState<User[] | null>(null)
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .listUsers()
      .then(setUsers)
      .catch((err: Error) => setError(err.message))
  }, [])

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
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

      {error && <p className="error">{error}</p>}
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
                  {user.id !== me?.id && (
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        void run(() => api.updateUser(user.id, { is_active: !user.is_active }))
                      }
                    >
                      {user.is_active ? 'Desactivar' : 'Reactivar'}
                    </button>
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
