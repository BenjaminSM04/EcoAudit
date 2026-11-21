import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import type { Role, User } from '../api'
import { useAuth } from '../session'
import { ROLE } from '../labels'
import { Pencil, UserPlus } from 'lucide-react'
import { Badge, Button, Card, Modal, Skeleton, Table, Toast } from '../components/ui'

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
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<User | null>(null)
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
      setCreating(false)
      setNotice('Usuario creado.')
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
      <div className="page-heading"><div><h1>Usuarios</h1><p>Administre las cuentas, los roles y el acceso a EcoAudit.</p></div>
        <Button onClick={() => { setForm(EMPTY); setError(null); setCreating(true) }}><UserPlus size={18} aria-hidden="true" /> Nuevo usuario</Button></div>
      {creating && <Modal title="Nuevo usuario" busy={busy} onClose={() => { setCreating(false); setError(null) }}>
      <form className="page" onSubmit={create}>
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
            minLength={MIN_PASSWORD}
            maxLength={MAX_PASSWORD}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required
          />
        </label>
        <label>
          Rol
          <select
            aria-label="Rol"
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
        {error && <p className="error" role="alert">{error}</p>}
      </form></Modal>}

      {editing && <Modal title="Editar usuario" busy={busy} onClose={() => { setEditing(null); setError(null) }}>
        <form className="page" onSubmit={event => {
          event.preventDefault()
          void run(async () => {
            await api.updateUser(editing.id, { role: editing.role, is_active: editing.is_active })
            setEditing(null)
            setNotice('Usuario actualizado.')
          })
        }}>
          <p><strong>{editing.full_name}</strong> · {editing.email}</p>
          <label>Rol<select aria-label="Rol" value={editing.role} onChange={event => setEditing({ ...editing, role: event.target.value as Role })}>
            {Object.entries(ROLE).map(([id, label]) => <option value={id} key={id}>{label}</option>)}
          </select></label>
          <label className="check"><input type="checkbox" checked={editing.is_active} onChange={event => setEditing({ ...editing, is_active: event.target.checked })} /> Cuenta activa</label>
          {error && <p className="error" role="alert">{error}</p>}
          <Button type="submit" disabled={busy}>Guardar cambios</Button>
        </form>
      </Modal>}

      {error && !creating && !editing && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && <Toast>{notice}</Toast>}
      {users === null && !error && <Skeleton />}
      {users !== null && (
        <Card className="page"><h2>Cuentas registradas <span className="count">{users.length}</span></h2><Table label="Cuentas de usuario">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Correo</th>
              <th>Rol</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.full_name}</td>
                <td>{user.email}</td>
                <td>{ROLE[user.role]}</td>
                <td><Badge tone={user.is_active ? 'benign' : 'neutral'}>{user.is_active ? 'Activo' : 'Desactivado'}</Badge></td>
                <td>
                  {user.id === me?.id ? (
                    // La propia contraseña se cambia con la actual, en Mi cuenta.
                    <Link to="/cuenta">Cambiar mi contraseña</Link>
                  ) : (
                    <div className="actions">
                      <Button variant="secondary" disabled={busy} onClick={() => {
                        setError(null)
                        setEditing(user)
                      }}><Pencil size={16} aria-hidden="true" /> Editar</Button>
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
        </Table></Card>
      )}
    </div>
  )
}
