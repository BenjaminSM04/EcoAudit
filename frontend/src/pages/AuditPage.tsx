import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { CohortSummary } from '../api'
import { COHORT_SOURCE, COHORT_STATUS, dateTime, progressText } from '../labels'
import { MANIFEST_EXAMPLE, MANIFEST_HEADER, MAX_BATCH_IMAGES, checkManifest } from '../manifest'
import type { ManifestCheck } from '../manifest'

const IMAGE_ACCEPT = '.png,.jpg,.jpeg,.bmp,.tif,.tiff,.dcm,image/*,application/dicom'
const LIST_PREVIEW = 15

export default function AuditPage() {
  const [cohorts, setCohorts] = useState<CohortSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .listCohorts()
      .then(setCohorts)
      .catch((err: Error) => setError(err.message))
  }, [])

  return (
    <div className="page">
      <h1>Auditoría de cohortes</h1>
      <p className="muted">
        Una cohorte reúne imágenes con su etiqueta de referencia (0 benigna, 1 maligna) y mide qué
        tan bien discrimina y calibra el modelo, agrupando por paciente.
      </p>

      <section className="card page">
        <h2>Mis cohortes</h2>
        {error && <p className="error">{error}</p>}
        {cohorts === null && !error && <p className="muted">Cargando…</p>}
        {cohorts !== null && cohorts.length === 0 && (
          <p className="muted">Todavía no hay cohortes. Cree la primera con uno de los formularios.</p>
        )}
        {cohorts !== null && cohorts.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Origen</th>
                <th>Estado</th>
                <th>Progreso</th>
                <th>Creada</th>
              </tr>
            </thead>
            <tbody>
              {cohorts.map((cohort) => (
                <tr key={cohort.id}>
                  <td>
                    <Link to={`/auditoria/${cohort.id}`}>{cohort.name}</Link>
                  </td>
                  <td>{COHORT_SOURCE[cohort.source]}</td>
                  <td>{COHORT_STATUS[cohort.status]}</td>
                  <td>{progressText(cohort.progress)}</td>
                  <td>{dateTime(cohort.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <BatchForm />
      <AnalysesForm />
    </div>
  )
}

// ---------- Nuevo lote: manifiesto + imágenes ----------

function BatchForm() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [manifest, setManifest] = useState<File | null>(null)
  const [manifestText, setManifestText] = useState<string | null>(null)
  const [images, setImages] = useState<File[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Evita que la lectura de un manifiesto anterior pise la del actual.
  const reading = useRef(0)

  const check = useMemo(
    () =>
      manifestText === null
        ? null
        : checkManifest(manifestText, images.length > 0 ? images.map((file) => file.name) : null),
    [manifestText, images],
  )
  const tooMany = images.length > MAX_BATCH_IMAGES
  const ready = name.trim() !== '' && manifest !== null && check?.ok === true && !tooMany

  async function chooseManifest(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    const ticket = ++reading.current
    setManifest(file)
    setManifestText(null)
    setError(null)
    if (file === null) return
    try {
      const text = await file.text()
      if (ticket === reading.current) setManifestText(text)
    } catch {
      if (ticket === reading.current) setError('No se pudo leer el archivo del manifiesto.')
    }
  }

  function chooseImages(event: ChangeEvent<HTMLInputElement>) {
    setImages(Array.from(event.target.files ?? []))
    setError(null)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!ready || manifest === null || busy) return
    setBusy(true)
    setError(null)
    try {
      const created = await api.createCohortBatch(name.trim(), manifest, images)
      navigate(`/auditoria/${created.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear el lote.')
      setBusy(false)
    }
  }

  return (
    <form className="card page" onSubmit={submit}>
      <h2>Nuevo lote</h2>
      <p>
        Suba imágenes nuevas junto con un manifiesto CSV UTF-8 con cabecera{' '}
        <code>{MANIFEST_HEADER}</code>: el nombre del archivo, el seudónimo del paciente (las
        imágenes con el mismo seudónimo forman un caso) y la etiqueta, 0 para benigna y 1 para
        maligna. Cada imagen elegida debe figurar en el manifiesto y cada fila del manifiesto debe
        tener su imagen. Máximo {MAX_BATCH_IMAGES} imágenes.
      </p>
      <pre className="example">{MANIFEST_EXAMPLE}</pre>
      <p className="muted small">
        Las imágenes se procesan igual que en un caso (se descartan los metadatos y se aplica el
        control de calidad) y se analizan con el modelo activo, imagen completa. No use nombres ni
        datos que identifiquen al paciente.
      </p>

      <div className="inline-form">
        <label className="grow">
          Nombre de la cohorte
          <input value={name} onChange={(e) => setName(e.target.value)} required disabled={busy} />
        </label>
        <label>
          Manifiesto (CSV)
          <input
            type="file"
            accept=".csv,text/csv"
            required
            disabled={busy}
            onChange={(e) => void chooseManifest(e)}
          />
        </label>
        <label>
          Imágenes
          <input
            type="file"
            accept={IMAGE_ACCEPT}
            multiple
            required
            disabled={busy}
            onChange={chooseImages}
          />
        </label>
      </div>

      {images.length > 0 && <p className="muted small">{images.length} imágenes elegidas.</p>}
      {tooMany && (
        <p className="error" role="alert">
          Eligió {images.length} imágenes; el máximo es {MAX_BATCH_IMAGES} por lote.
        </p>
      )}
      {check && <ManifestReport check={check} />}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div className="actions">
        <button type="submit" disabled={!ready || busy}>
          {busy ? `Enviando ${images.length} imágenes…` : 'Crear lote y analizar'}
        </button>
      </div>
      {busy && (
        <p className="muted small" role="status">
          Subiendo y validando en el servidor; con muchas imágenes puede tardar. No cierre la página.
        </p>
      )}
    </form>
  )
}

function NameList({ names }: { names: string[] }) {
  const shown = names.slice(0, LIST_PREVIEW)
  return (
    <ul>
      {shown.map((item) => (
        <li key={item}>
          <code>{item}</code>
        </li>
      ))}
      {names.length > shown.length && <li>… y {names.length - shown.length} más</li>}
    </ul>
  )
}

function ManifestReport({ check }: { check: ManifestCheck }) {
  const shownProblems = check.problems.slice(0, LIST_PREVIEW)
  return (
    <div className="page" aria-live="polite">
      {check.problems.length > 0 && (
        <div className="error" role="alert">
          <strong>El manifiesto tiene errores ({check.problems.length}):</strong>
          <ul>
            {shownProblems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
            {check.problems.length > shownProblems.length && (
              <li>… y {check.problems.length - shownProblems.length} más</li>
            )}
          </ul>
        </div>
      )}
      {check.missing.length > 0 && (
        <div className="error" role="alert">
          <strong>
            Figuran en el manifiesto pero no se eligió su imagen ({check.missing.length}):
          </strong>
          <NameList names={check.missing} />
        </div>
      )}
      {check.extra.length > 0 && (
        <div className="error" role="alert">
          <strong>
            Se eligieron pero no figuran en el manifiesto ({check.extra.length}):
          </strong>
          <NameList names={check.extra} />
        </div>
      )}
      {!check.compared && check.problems.length === 0 && (
        <p className="muted small">
          El manifiesto declara {check.images} imágenes de {check.patients} pacientes. Elija las
          imágenes para comprobar que coinciden.
        </p>
      )}
      {check.ok && (
        <p className="pill" role="status">
          Manifiesto consistente: {check.images} imágenes de {check.patients} pacientes.
        </p>
      )}
    </div>
  )
}

// ---------- Desde análisis existentes ----------

function AnalysesForm() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (file === null || busy) return
    setBusy(true)
    setError(null)
    try {
      const created = await api.createCohortFromAnalyses(file, name)
      navigate(`/auditoria/${created.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear la cohorte.')
      setBusy(false)
    }
  }

  return (
    <form className="card page" onSubmit={submit}>
      <h2>Desde análisis existentes</h2>
      <p>
        Use análisis ya terminados. Suba un CSV UTF-8 con cabecera <code>analysis_id,label</code>;
        indique 0 para benigna y 1 para maligna. Incluya un análisis por imagen, todos de una misma
        versión del modelo y de casos suyos. El sistema agrupa las imágenes con el mismo seudónimo.
      </p>
      <pre className="example">{'analysis_id,label\n12,0\n13,1\n14,1'}</pre>
      <div className="inline-form">
        <label className="grow">
          Nombre (opcional)
          <input value={name} onChange={(e) => setName(e.target.value)} disabled={busy} />
        </label>
        <label>
          Archivo de etiquetas (CSV)
          <input
            type="file"
            accept=".csv,text/csv"
            required
            disabled={busy}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              setError(null)
            }}
          />
        </label>
        <button type="submit" disabled={file === null || busy}>
          {busy ? 'Calculando…' : 'Evaluar cohorte'}
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  )
}
