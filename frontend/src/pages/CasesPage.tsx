import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpRight, FileUp, Plus, Search } from 'lucide-react'
import { api, type AnalysisStatus, type CaseSummary, type DicomReceipt } from '../api'
import { ANALYSIS_STATUS, dateTime, warningText } from '../labels'
import { Badge, Button, Card, EmptyState, Modal, Skeleton, Table, Toast } from '../components/ui'
import { useAuth } from '../session'

const PAGE_SIZE = 15
const tones = { pending: 'neutral', running: 'brand', done: 'benign', failed: 'suspicious' }

export default function CasesPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [statuses, setStatuses] = useState<Record<number, AnalysisStatus | 'empty' | 'unknown'>>({})
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [modal, setModal] = useState<'case' | 'dicom' | null>(null)

  function reload() {
    setError('')
    void api.listCases().then(setCases).catch((err: Error) => setError(err.message))
  }

  useEffect(() => {
    void api.listCases().then(setCases).catch((err: Error) => setError(err.message))
  }, [])

  const term = search.trim().toLocaleLowerCase()
  const visible = cases?.filter(item =>
    item.patient_ref.toLocaleLowerCase().includes(term) || String(item.id) === term.replace(/^#/, ''),
  ) ?? []
  const rows = visible.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  // El resumen solo incluye el conteo de imágenes. Se consulta el estado de los casos visibles.
  const caseIds = rows.filter(item => item.image_count > 0).map(item => item.id).join(',')
  useEffect(() => {
    if (!caseIds) return
    let alive = true
    void Promise.all(caseIds.split(',').map(async id => {
      try {
        const detail = await api.getCase(Number(id))
        const latest = detail.images.flatMap(image => image.analyses).reduce(
          (last, item) => !last || last.id < item.id ? item : last, null as (typeof detail.images)[number]['analyses'][number] | null,
        )
        return [id, latest?.status ?? 'empty'] as const
      } catch {
        return [id, 'unknown'] as const
      }
    })).then(items => { if (alive) setStatuses(Object.fromEntries(items)) })
    return () => { alive = false }
  }, [caseIds])

  return <div className="page">
    <div className="page-heading">
      <div><h1>Casos</h1><p>Consulte ecografías y análisis asociados a pacientes seudonimizados.</p></div>
      <div className="actions">
        {user?.role !== 'investigador' && <Button variant="secondary" onClick={() => setModal('dicom')}><FileUp size={18} aria-hidden="true" /> Importar DICOM</Button>}
        <Button onClick={() => setModal('case')}><Plus size={18} aria-hidden="true" /> Nuevo caso</Button>
      </div>
    </div>
    {modal === 'case' && <NewCase onClose={() => setModal(null)} onCreated={id => navigate(`/casos/${id}`)} />}
    {modal === 'dicom' && <DicomImport onClose={() => setModal(null)} onImported={() => { setPage(0); reload() }} />}
    {error && <p className="error" role="alert">{error}</p>}
    {!cases && !error && <Skeleton />}
    {cases && <Card className="page">
      <div className="section-heading case-tools">
        <h2>Casos registrados <span className="count">{cases.length}</span></h2>
        <label>Buscar por seudónimo o número
          <span className="search-field"><Search size={17} aria-hidden="true" /><input type="search" value={search} onChange={event => { setSearch(event.target.value); setPage(0) }} /></span>
        </label>
      </div>
      {rows.length ? <Table label="Casos registrados"><thead><tr>
        <th scope="col">Caso</th><th scope="col">Paciente</th><th scope="col">Imágenes</th><th scope="col">Último análisis</th><th scope="col">Creado</th><th scope="col">Notas</th>
      </tr></thead><tbody>{rows.map(item => {
        const status = item.image_count ? statuses[item.id] : 'empty'
        return <tr key={item.id}>
          <td><Link to={`/casos/${item.id}`} className="row-link">#{item.id}<ArrowUpRight size={14} aria-hidden="true" /></Link></td>
          <td><strong>{item.patient_ref}</strong></td><td>{item.image_count}</td>
          <td>{status && status in tones ? <Badge tone={tones[status as AnalysisStatus]}>{ANALYSIS_STATUS[status as AnalysisStatus]}</Badge>
            : <span className="muted">{status === 'empty' ? 'Sin análisis' : status === 'unknown' ? 'No disponible' : 'Consultando…'}</span>}</td>
          <td>{dateTime(item.created_at)}</td><td className="muted table-notes">{item.notes || '—'}</td>
        </tr>
      })}</tbody></Table> : <EmptyState>{term ? <span role="status">Ningún caso coincide con la búsqueda.</span> : 'Todavía no hay casos.'}</EmptyState>}
      {visible.length > PAGE_SIZE && <div className="section-heading pagination"><span role="status">{page * PAGE_SIZE + 1}–{page * PAGE_SIZE + rows.length} de {visible.length}</span>
        <div className="actions"><Button variant="secondary" disabled={!page} onClick={() => setPage(page - 1)}>Anterior</Button>
          <Button variant="secondary" disabled={(page + 1) * PAGE_SIZE >= visible.length} onClick={() => setPage(page + 1)}>Siguiente</Button></div></div>}
    </Card>}
  </div>
}

function NewCase({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setError('')
    try {
      onCreated((await api.createCase(String(form.get('patient')).trim(), String(form.get('notes')))).id)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }
  return <Modal title="Nuevo caso" busy={busy} onClose={onClose}>
    <form className="page" onSubmit={create}>
      <p className="muted">No escriba el nombre, el carnet ni otros datos que identifiquen al paciente.</p>
      <label>Seudónimo del paciente<input name="patient" placeholder="p. ej. P-0042" maxLength={64} required /></label>
      <label>Notas (opcional)<textarea name="notes" rows={3} maxLength={4000} /></label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions"><Button type="submit" disabled={busy}>Crear caso</Button><Button variant="secondary" onClick={onClose} disabled={busy}>Cancelar</Button></div>
    </form>
  </Modal>
}

function DicomImport({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [busy, setBusy] = useState(false)
  const [receipt, setReceipt] = useState<DicomReceipt | null>(null)
  const [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const files = new FormData(form).getAll('files').filter((file): file is File => file instanceof File && file.size > 0)
    setReceipt(null)
    setError('')
    if (!files.length || files.length > 100) {
      setError('Seleccione entre 1 y 100 archivos DICOM.')
      return
    }
    setBusy(true)
    try {
      const result = await api.importDicom(files)
      setReceipt(result)
      if (result.instancias.length) {
        onImported()
        form.reset()
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return <Modal title="Importar DICOM" onClose={onClose} busy={busy}>
    <form className="page" onSubmit={submit}>
      <p className="muted">Cada archivo requiere PatientID. EcoAudit agrupa las instancias en casos por seudónimo. Revise que los píxeles no contengan información identificable.</p>
      <label>Archivos DICOM<input name="files" type="file" accept=".dcm,.dicom,application/dicom" multiple required disabled={busy} /></label>
      <Button type="submit" disabled={busy}>{busy ? 'Importando…' : 'Importar instancias'}</Button>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {!!receipt?.instancias.length && <div className="page"><Toast>{receipt.instancias.length === 1 ? '1 instancia importada.' : `${receipt.instancias.length} instancias importadas.`}</Toast>
      <ul>{receipt.instancias.map(item => <li key={item.image_id}>
        <Link to={`/casos/${item.case_id}`}>{item.patient_ref}</Link> · Imagen #{item.image_id}
        {item.qc_flags.length > 0 && <span> · {item.qc_flags.map(warningText).join(' ')}</span>}
      </li>)}</ul></div>}
    {!!receipt?.fallos.length && <div role="alert" className="error"><strong>Instancias rechazadas</strong>
      <ul>{receipt.fallos.map(item => <li key={item.indice}>Archivo {item.indice} · {item.motivo}</li>)}</ul></div>}
  </Modal>
}
