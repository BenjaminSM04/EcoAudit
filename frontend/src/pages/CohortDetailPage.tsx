import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Activity, Gauge, RefreshCw, Target } from 'lucide-react'
import { Badge, Button, Modal, Skeleton, StatCard, Table } from '../components/ui'
import { ApiError, api, downloadCohortItems, downloadCohortReport } from '../api'
import type { CohortDetail, CohortMetrics, ModelVersion } from '../api'
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
  const [reanalyzing, setReanalyzing] = useState(false)

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
          <Skeleton />
        )}
      </div>
    )
  }

  const { progress } = detail
  return (
    <div className="page">
      <Link to="/auditoria">← Auditoría</Link>
      <div className="page-heading">
        <div><h1>{detail.name}</h1><p>{COHORT_SOURCE[detail.source]} · {detail.model} · {dateTime(detail.created_at)}</p></div>
        <Badge tone={detail.status === 'done' ? 'benign' : detail.status === 'failed' ? 'suspicious' : 'neutral'}>{COHORT_STATUS[detail.status]}</Badge>
      </div>
      {reanalyzing && <ReanalyzeModal id={cohortId} currentModel={detail.model} onClose={() => setReanalyzing(false)} />}
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
          <progress aria-label="Imágenes analizadas" value={progress.done} max={Math.max(progress.total, 1)} />
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
          <Button variant="secondary" onClick={() => setReanalyzing(true)}><RefreshCw size={16} aria-hidden="true" /> Reanalizar con otro modelo</Button>
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
      <div className="cohort-stats">
        <StatCard icon={Activity} label="AUROC" value={decimal(results.auc)} detail={`IC del 95 % · ${results.ci ? `${decimal(results.ci[0])} a ${decimal(results.ci[1])}` : 'Muestra insuficiente'}`} />
        <StatCard icon={Target} label="Brier" value={decimal(results.brier)} />
        <StatCard icon={Gauge} label="Error de calibración (ECE)" value={decimal(results.ece)} />
      </div>
      <p>
        {results.abstentions} de {results.images} imágenes produjeron abstención. La evaluación
        incluye todas las puntuaciones.
      </p>

      <h3>Decisiones</h3>
      <Table label="Decisiones por imagen">
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
      </Table>

      <h3>Calibración observada</h3>
      <CalibrationPlot bins={results.bins} />
      <Table label="Calibración por banda">
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
      </Table>

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

function ReanalyzeModal({ id, currentModel, onClose }: { id: number; currentModel: string; onClose: () => void }) {
  const navigate = useNavigate()
  const [models, setModels] = useState<ModelVersion[] | null>(null)
  const [selected, setSelected] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void api.listModels().then(items => setModels(items.filter(model => `${model.name} ${model.version}` !== currentModel)))
      .catch((err: Error) => setError(err.message))
  }, [currentModel])

  async function reanalyze() {
    setBusy(true)
    setError('')
    try {
      const cohort = await api.reanalyze(id, Number(selected))
      navigate(`/auditoria/${cohort.id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return <Modal title="Reanalizar con otro modelo" onClose={onClose} busy={busy}>
    <form className="page" onSubmit={event => { event.preventDefault(); void reanalyze() }}>
      <p className="muted">Se creará una cohorte con las mismas imágenes, regiones y etiquetas.</p>
      {!models && !error && <Skeleton />}
      {models?.length === 0 && <p>Solo está registrada la versión de esta cohorte.</p>}
      {!!models?.length && <><label>Versión del modelo<select aria-label="Versión del modelo" required value={selected} disabled={busy} onChange={event => setSelected(event.target.value)}>
        <option value="">Seleccione una versión</option>
        {models.map(model => <option value={model.id} key={model.id}>{model.name} {model.version}{model.is_active ? ' · Activo' : ''}</option>)}
      </select></label><Button type="submit" disabled={busy || !selected}>{busy ? 'Enviando…' : 'Crear cohorte y reanalizar'}</Button></>}
      {error && <p className="error" role="alert">{error}</p>}
    </form>
  </Modal>
}

function CalibrationPlot({ bins }: { bins: CohortMetrics['bins'] }) {
  const x = (value: number) => 40 + value * 280
  const y = (value: number) => 155 - value * 130
  const points = bins.filter(bin => bin.n > 0).map(bin => ({ ...bin, x: x(bin.predicted), y: y(bin.observed) }))
  return <figure className="calibration-plot">
    <svg viewBox="0 0 350 190" aria-hidden="true">
      <path d="M40 25v130h280" fill="none" stroke="var(--muted)" />
      <path d="M40 155 320 25" stroke="var(--muted)" strokeDasharray="4 4" />
      <polyline points={points.map(point => `${point.x},${point.y}`).join(' ')} fill="none" stroke="var(--brand)" strokeWidth="2" />
      {points.map(point => <circle key={point.bin} cx={point.x} cy={point.y} r="4" fill="var(--brand)" />)}
      <g fill="var(--muted)" fontSize="10">
        <text x="44" y="18">Proporción observada</text>
        <text x="181" y="182" textAnchor="middle">Probabilidad media</text>
        <text x="20" y="29">1</text><text x="20" y="158">0</text>
        <text x="39" y="169">0</text><text x="315" y="169">1</text>
      </g>
    </svg>
    <figcaption className="small muted">La diagonal punteada indica calibración perfecta. Los puntos corresponden a las bandas con pacientes.</figcaption>
  </figure>
}
