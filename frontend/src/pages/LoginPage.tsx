import { useState } from 'react'
import type { FormEvent } from 'react'
import { Activity, ArrowRight, Fingerprint, ScanLine, ShieldAlert } from 'lucide-react'
import { Brand, Disclaimer } from '../components/Brand'
import { Button, Toast } from '../components/ui'
import { useAuth } from '../session'

export default function LoginPage() {
  const { login, notice } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo iniciar sesión.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <section className="login-intro">
        <Brand />
        <div className="login-intro-content">
          <h1>Ecografía mamaria e investigación clínica</h1>
          <p>Apoyo a la clasificación de lesiones y a la auditoría de modelos en ecografía.</p>
          <ul className="login-features">
            <li><ScanLine aria-hidden="true" /><span><strong>Calibración con abstención</strong><small>Identifica la zona en que el modelo se abstiene.</small></span></li>
            <li><ShieldAlert aria-hidden="true" /><span><strong>Alerta de cambio de dominio</strong><small>Señala imágenes que difieren de la referencia del modelo.</small></span></li>
            <li><Fingerprint aria-hidden="true" /><span><strong>Trazabilidad del modelo</strong><small>Vincula cada análisis a la versión que lo produjo.</small></span></li>
          </ul>
        </div>
        <Activity className="login-wave" aria-hidden="true" />
      </section>
      <main className="login-access">
        <form className="card" onSubmit={submit}>
          <h2>Iniciar sesión</h2>
          <p className="muted">Ingrese con su cuenta de EcoAudit.</p>
        <label>
          Correo
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
        </label>
        <label>
          Contraseña
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {notice && (
          <Toast>{notice}</Toast>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <Button type="submit" disabled={busy}>
          {busy ? 'Ingresando…' : 'Ingresar'} <ArrowRight size={18} aria-hidden="true" />
        </Button>
        </form>
        <Disclaimer />
      </main>
    </div>
  )
}
