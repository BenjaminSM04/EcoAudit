import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ModelVersion } from '../api'
import { useAuth } from '../session'
import { dateTime, percent } from '../labels'
import { Badge, EmptyState, Skeleton, Toast } from '../components/ui'

export default function ModelsPage() {
  const { user } = useAuth()
  const [models, setModels] = useState<ModelVersion[] | null>(null)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .listModels()
      .then(setModels)
      .catch((err: Error) => setError(err.message))
  }, [])

  async function activate(id: number) {
    setError(null)
    setNotice('')
    setBusy(true)
    try {
      await api.activateModel(id)
      setModels(await api.listModels())
      setNotice('Modelo activo actualizado.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo activar el modelo.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <div className="page-heading"><div><h1>Modelos</h1><p>Cada análisis queda ligado a la versión del modelo que lo produjo.</p></div></div>
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <Toast>{notice}</Toast>}
      {models === null && !error && <Skeleton />}
      {models !== null && models.length === 0 && (
        <EmptyState>No hay modelos registrados.</EmptyState>
      )}
      <div className="comparison-grid">{models?.map((model) => (
        <section className="card model" key={model.id}>
          <header>
            <h2>
              {model.name} <span className="muted">{model.version}</span>
            </h2>
            {model.is_active ? (
              <Badge tone="benign">Activo</Badge>
            ) : (
              user?.role === 'admin' && (
                <button className="secondary" disabled={busy} onClick={() => activate(model.id)}>
                  Activar
                </button>
              )
            )}
          </header>
          {model.card.demo && (
            <p className="banner">Modelo de demostración: sin entrenamiento ni validez.</p>
          )}
          <dl>
            <dt>Arquitectura</dt>
            <dd>
              {model.card.architecture} · ensamble de {model.card.members.length} · entrada{' '}
              {model.card.input.size} px ·{' '}
              {model.card.input.expects_roi ? 'recorte de lesión (ROI)' : 'imagen completa'}
            </dd>
            <dt>Datos de entrenamiento</dt>
            <dd>{model.card.training_data}</dd>
            <dt>Calibración</dt>
            <dd>
              temperatura {model.card.calibration.temperature.toFixed(3)}
              {model.card.calibration.source && ` · ${model.card.calibration.source}`}
            </dd>
            <dt>Zona de abstención</dt>
            <dd>
              {percent(model.card.decision.abstain_low)} a {percent(model.card.decision.abstain_high)}
            </dd>
            <dt>Cambio de dominio</dt>
            <dd>
              {model.card.shift
                ? (model.card.shift.description ?? `umbral ${model.card.shift.threshold}`)
                : 'sin referencia'}
            </dd>
            <dt>Limitaciones</dt>
            <dd>
              <ul>
                {model.card.limitations.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            </dd>
            <dt>Registro</dt>
            <dd className="small">
              {dateTime(model.created_at)} · sha256 <code>{model.bundle_sha256.slice(0, 16)}…</code>
            </dd>
          </dl>
        </section>
      ))}</div>
    </div>
  )
}
