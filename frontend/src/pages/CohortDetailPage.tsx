import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, api, downloadCohortItems, downloadCohortReport } from '../api'
import type { CohortDetail, CohortMetrics } from '../api'
import {
  COHORT_SOURCE,
  COHORT_STATUS,
  DECISION_ORDER,
  dateTime,
  decimal,
  decisionTitle,
  progressText,
} from '../labels'

// Intervalo de consulta mientras la cohorte se procesa.
const POLL_MS = 2000

type Download = 'pdf' | 'csv'

export default function CohortDetailPage() {
  const cohortId = Number(useParams().cohortId)
  const [loaded, setLoaded] = useState<CohortDetail | null>(null)
  // Cuenta ciclos de consulta: cada respuesta (o fallo de red) programa la siguiente.
  const [tick, setTick] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<Download | null>(null)

  // Si la ruta cambia de cohorte, el detalle anterior no vale.
  const detail = loaded !== null && loaded.id === cohortId ? loaded : null
  const status = detail?.status

  useEffect(() => {
    let cancelled = false
    api
      .getCohort(cohortId)
      .then((next) => {
        if (!cancelled) setLoaded(next)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [cohortId])

  // Sondeo: solo mientras está en `processing`. El efecto se limpia al desmontar o cuando
  // cambia el estado, y se encadena con setTimeout para que nunca haya dos consultas a la vez.
  useEffect(() => {
    if (status !== 'processing') return
    let cancelled = false
    const timer = setTimeout(() => {
      api
        .getCohort(cohortId)
        .then((next) => {
          if (cancelled) return
          setLoaded(next)
          setError(null)
          setTick((n) => n + 1)
        })
        .catch((err: unknown) => {
          if (cancelled) return
          setError(err instanceof Error ? err.message : 'No se pudo consultar la cohorte.')
          // Un corte de red es pasajero: se reintenta. Cualquier otro error detiene el sondeo.
          if (err instanceof ApiError && err.status === 0) setTick((n) => n + 1)
        })
    }, POLL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [cohortId, status, tick])

  async function download(kind: Download) {
    setDownloading(kind)
    setError(null)
    try {
      await (kind === 'pdf' ? downloadCohortReport(cohortId) : downloadCohortItems(cohortId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo descargar el archivo.')
    } finally {
      setDownloading(null)
    }
  }

  if (detail === null) {
    return (
      <div className="page">
        <Link to="/auditoria">← Auditoría</Link>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : (
          <p className="muted">Cargando…</p>
        )}
      </div>
    )
  }

  const { progress } = detail
  return (
    <div className="page">
      <Link to="/auditoria">← Auditoría</Link>
      <h1>{detail.name}</h1>
      <p className="muted">
        {COHORT_SOURCE[detail.source]} · {detail.model} · creada el {dateTime(detail.created_at)} ·{' '}
        {COHORT_STATUS[detail.status]}
      </p>
      {error && (
        <div className="error" role="alert">
          <p>{error}</p>
          {detail.status === 'processing' && (
            <button
              className="secondary"
              onClick={() => {
                setError(null)
                setTick((n) => n + 1)
              }}
            >
              Reintentar
            </button>
          )}
        </div>
      )}

      {detail.status === 'processing' && (
        <section className="card page">
          <h2>Procesando</h2>
          <progress value={progress.done} max={Math.max(progress.total, 1)} />
          <p role="status">
            Analizadas {progress.done} de {progress.total} imágenes
            {progress.failed > 0 && ` (${progress.failed} con fallo)`}.
          </p>
          <p className="muted small">
            La página se actualiza sola cada {POLL_MS / 1000} s. Puede salir y volver: el
            procesamiento sigue en el servidor.
          </p>
        </section>
      )}

      {detail.status === 'failed' && (
        <section className="card page">
          <h2>La cohorte falló</h2>
          <p className="error" role="alert">
            {detail.error ?? 'El servidor no dio más detalle.'}
          </p>
          <p className="muted">Análisis terminados: {progressText(progress)}.</p>
        </section>
      )}

      {detail.status === 'done' && detail.results === null && (
        <p className="banner">La cohorte terminó pero no tiene resultados que mostrar.</p>
      )}
      {detail.status === 'done' && detail.results !== null && (
        <MetricsView results={detail.results} />
      )}

      {detail.status !== 'processing' && (
        <div className="actions">
          {detail.status === 'done' && (
            <button disabled={downloading !== null} onClick={() => void download('pdf')}>
              {downloading === 'pdf' ? 'Descargando…' : 'Descargar informe PDF'}
            </button>
          )}
          <button
            className="secondary"
            disabled={downloading !== null}
            onClick={() => void download('csv')}
          >
            {downloading === 'csv' ? 'Descargando…' : 'Descargar CSV de ítems'}
          </button>
        </div>
      )}
    </div>
  )
}

function MetricsView({ results }: { results: CohortMetrics }) {
  const tiles: [string, number][] = [
    ['AUROC', results.auc],
    ['Brier', results.brier],
    ['ECE', results.ece],
  ]
  // Primero las decisiones conocidas, en orden; después cualquier código inesperado.
  const decisionCodes = [
    ...DECISION_ORDER,
    ...Object.keys(results.decisions).filter((code) => !DECISION_ORDER.some((c) => c === code)),
  ]

  return (
    <section className="card page">
      <h2>Resultados por paciente</h2>
      {results.demo && (
        <p className="banner">Modelo de demostración: sin entrenamiento, estas cifras no significan nada.</p>
      )}
      <p>
        {results.images} imágenes · {results.patients} pacientes · {results.positive} positivos
      </p>
      <div className="metrics">
        {tiles.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{decimal(value)}</strong>
          </div>
        ))}
      </div>
      <p>
        IC del 95 % para AUROC ·{' '}
        {results.ci ? `${decimal(results.ci[0])} – ${decimal(results.ci[1])}` : 'Muestra insuficiente'}
      </p>
      <p>
        {results.abstentions} de {results.images} imágenes produjeron abstención. La evaluación
        incluye todas las puntuaciones.
      </p>

      <h3>Decisiones</h3>
      <table>
        <thead>
          <tr>
            <th>Decisión</th>
            <th>Imágenes</th>
          </tr>
        </thead>
        <tbody>
          {decisionCodes.map((code) => (
            <tr key={code}>
              <td>{decisionTitle(code)}</td>
              <td>{results.decisions[code] ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Calibración observada</h3>
      <table>
        <thead>
          <tr>
            <th>Banda</th>
            <th>n</th>
            <th>Media</th>
            <th>Observada</th>
          </tr>
        </thead>
        <tbody>
          {results.bins.map((b) => (
            <tr key={b.bin}>
              <td>
                {b.bin * 10}–{(b.bin + 1) * 10} %
              </td>
              <td>{b.n}</td>
              <td>{decimal(b.predicted)}</td>
              <td>{decimal(b.observed)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <dl className="small">
        <dt>Modelo (sha256)</dt>
        <dd>
          <code>{results.model_hash.slice(0, 16)}…</code>
        </dd>
        <dt>Etiquetas (sha256)</dt>
        <dd>
          <code>{results.csv_hash.slice(0, 16)}…</code>
        </dd>
      </dl>
    </section>
  )
}
