import { Link } from 'react-router-dom'
import type { WorklistItem } from '../api'
import { Card, EmptyState, Skeleton, Table } from '../components/ui'
import { dateTime } from '../labels'

export default function WorklistPage({ items, error }: { items: WorklistItem[] | null; error: string }) {
  return <div className="page">
    <div className="page-heading"><div><h1>Pendientes</h1><p>Análisis terminados que aún requieren su lectura, del más antiguo al más reciente.</p></div></div>
    {error && <p className="error" role="alert">{error}</p>}
    {!items && !error && <Skeleton label="Cargando lecturas pendientes" />}
    {items && <Card>
      {items.length ? <Table label="Lecturas pendientes"><thead><tr>
        <th scope="col">Caso</th><th scope="col">Imagen</th><th scope="col">Análisis</th><th scope="col">Finalización</th><th scope="col">Lectura</th>
      </tr></thead><tbody>{items.map(item => <tr key={item.analysis_id}>
        <th scope="row">{item.patient_ref} · #{item.case_id}</th><td>#{item.image_id}</td><td>#{item.analysis_id}</td>
        <td>{item.finished_at ? dateTime(item.finished_at) : '—'}</td>
        <td><Link className="button secondary" to={`/casos/${item.case_id}?analisis=${item.analysis_id}`}>Leer<span className="sr-only"> análisis #{item.analysis_id}</span></Link></td>
      </tr>)}</tbody></Table> : <EmptyState>No tiene lecturas pendientes.</EmptyState>}
    </Card>}
  </div>
}
