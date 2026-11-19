import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ModelVersion } from '../api'
import { useAuth } from '../session'
import { dateTime, percent } from '../labels'

export default function ModelsPage() {
  const { user } = useAuth()
  const [models, setModels] = useState<ModelVersion[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .listModels()
      .then(setModels)
      .catch((err: Error) => setError(err.message))
  }, [])

  async function activate(id: number) {
    setError(null)
    try {
      await api.activateModel(id)
      setModels(await api.listModels())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo activar el modelo.')
    }
  }

  return (
    <div className="page">
      <h1>Modelos</h1>
      <p className="muted">
        Cada versión es un paquete inmutable identificado por su hash. Todo análisis queda ligado a
        la versión que lo produjo.
      </p>
      {error && <p className="error">{error}</p>}
      {models === null && !error && <p className="muted">Cargando…</p>}
      {models !== null && models.length === 0 && (
        <p className="muted">
          No hay modelos registrados. Se registran desde el servidor con{' '}
          <code>python -m app.cli register-model RUTA --activate</code>.
        </p>
      )}
      {models?.map((model) => (
        <section className="card model" key={model.id}>
          <header>
            <h2>
              {model.name} <span className="muted">{model.version}</span>
            </h2>
            {model.is_active ? (
              <span className="pill">Activo</span>
            ) : (
              user?.role === 'admin' && (
                <button className="secondary" onClick={() => activate(model.id)}>
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
      ))}
    </div>
  )
}
