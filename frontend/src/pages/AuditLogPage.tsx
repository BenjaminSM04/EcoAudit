import { useEffect, useState, type FormEvent } from 'react'
import { Download } from 'lucide-react'
import { api, type AuditFilters, type AuditLog, type User } from '../api'
import { Button, Card, EmptyState, Skeleton, Table, Toast } from '../components/ui'
import { AUDIT_ACTION, dateTime } from '../labels'

const LIMIT = 50
const initial = { user: '', action: '', from: '', to: '' }
const entities: Record<string, string> = {
  user: 'Usuario', analysis: 'Análisis', case: 'Caso', model_version: 'Modelo',
  image: 'Imagen', cohort: 'Cohorte', audit_log: 'Bitácora',
}

function localDay(value: string, end = false) {
  return value ? new Date(`${value}T${end ? '23:59:59.999' : '00:00:00'}`).toISOString() : undefined
}

export default function AuditLogPage() {
  const [draft, setDraft] = useState(initial)
  const [filters, setFilters] = useState<AuditFilters>({ limit: LIMIT, offset: 0 })
  const [logs, setLogs] = useState<AuditLog | null>(null)
  const [users, setUsers] = useState<User[]>([])
  const [error, setError] = useState('')
  const [filterError, setFilterError] = useState('')
  const [exportError, setExportError] = useState('')
  const [download, setDownload] = useState(false)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    void api.listUsers().then(setUsers).catch((err: Error) => setFilterError(err.message))
  }, [])

  useEffect(() => {
    let alive = true
    void api.auditLog(filters).then(value => { if (alive) setLogs(value) }).catch((err: Error) => { if (alive) setError(err.message) })
    return () => { alive = false }
  }, [filters])

  function change(next: AuditFilters) {
    setError('')
    setNotice('')
    setExportError('')
    setLogs(null)
    setFilters(next)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    change({ user_id: draft.user ? Number(draft.user) : undefined, action: draft.action || undefined,
      desde: localDay(draft.from), hasta: localDay(draft.to, true), limit: LIMIT, offset: 0 })
  }

  async function exportCsv() {
    setDownload(true)
    setNotice('')
    setExportError('')
    try {
      await api.exportAuditLog(filters)
      setNotice('Se descargó el CSV con los filtros aplicados.')
    } catch (err) {
      setExportError((err as Error).message)
    } finally {
      setDownload(false)
    }
  }

  return <div className="page">
    <div className="page-heading"><div><h1>Bitácora</h1><p>El CSV incluye las filas de todas las páginas filtradas, hasta las 50 000 más recientes.</p></div>
      <Button variant="secondary" onClick={() => void exportCsv()} disabled={download || !logs?.total}><Download size={18} aria-hidden="true" /> Exportar CSV</Button>
    </div>
    <form className="card inline-form" onSubmit={submit}>
      <label className="grow">Usuario<select aria-label="Usuario" value={draft.user} onChange={e => setDraft({ ...draft, user: e.target.value })}>
        <option value="">Todos los usuarios</option>{users.map(user => <option value={user.id} key={user.id}>{user.full_name} · #{user.id}</option>)}
      </select></label>
      <label className="grow">Acción<select aria-label="Acción" value={draft.action} onChange={e => setDraft({ ...draft, action: e.target.value })}>
        <option value="">Todas las acciones</option>{Object.entries(AUDIT_ACTION).map(([code, label]) => <option value={code} key={code}>{label}</option>)}
        {logs?.items.filter((entry, index, items) => !Object.hasOwn(AUDIT_ACTION, entry.action) && items.findIndex(item => item.action === entry.action) === index)
          .map(entry => <option key={entry.action} value={entry.action}>{entry.action}</option>)}
        {draft.action && !Object.hasOwn(AUDIT_ACTION, draft.action) && !logs?.items.some(item => item.action === draft.action) && <option value={draft.action}>{draft.action}</option>}
      </select></label>
      <label>Desde<input type="date" value={draft.from} max={draft.to || undefined} onChange={e => setDraft({ ...draft, from: e.target.value })} /></label>
      <label>Hasta<input type="date" value={draft.to} min={draft.from || undefined} onChange={e => setDraft({ ...draft, to: e.target.value })} /></label>
      <Button type="submit">Aplicar filtros</Button>
    </form>
    {[filterError, error, exportError].filter(Boolean).map((message, index) => <p key={index} className="error" role="alert">{message}</p>)}
    {notice && <Toast>{notice}</Toast>}
    {!logs && !error && <Skeleton />}
    {logs && <Card className="page">
      <h2>Eventos registrados <span className="count">{logs.total}</span></h2>
      {logs.items.length ? <Table label="Eventos de la bitácora"><thead><tr>
        <th scope="col">Fecha</th><th scope="col">Usuario</th><th scope="col">Acción</th><th scope="col">Entidad</th><th scope="col">Detalle</th>
      </tr></thead><tbody>{logs.items.map(item => <tr key={item.id}>
        <td>{dateTime(item.created_at)}</td>
        <td>{item.user_id === null ? 'Sistema / sin sesión' : users.find(user => user.id === item.user_id)?.full_name ?? `#${item.user_id}`}</td>
        <td>{AUDIT_ACTION[item.action] ?? item.action}</td>
        <td>{entities[item.entity] ?? item.entity}{item.entity_id !== null && ` #${item.entity_id}`}</td>
        <td>{Object.keys(item.detail).length ? <details><summary>Ver detalle</summary><code className="audit-detail">{JSON.stringify(item.detail)}</code></details> : '—'}</td>
      </tr>)}</tbody></Table> : <EmptyState>No hay eventos para estos filtros.</EmptyState>}
      {logs.total > 0 && <div className="section-heading pagination">
        <span role="status">{logs.offset + 1}–{Math.min(logs.offset + logs.limit, logs.total)} de {logs.total}</span>
        <div className="actions"><Button variant="secondary" disabled={!logs.offset || download} onClick={() => change({ ...filters, offset: logs.offset - logs.limit })}>Anterior</Button>
          <Button variant="secondary" disabled={logs.offset + logs.limit >= logs.total || download} onClick={() => change({ ...filters, offset: logs.offset + logs.limit })}>Siguiente</Button></div>
      </div>}
    </Card>}
  </div>
}
