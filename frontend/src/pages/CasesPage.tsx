import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { CaseSummary } from '../api'
import { dateTime } from '../labels'

export default function CasesPage() {
  const navigate = useNavigate()
  const [cases, setCases] = useState<CaseSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [patientRef, setPatientRef] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .listCases()
      .then(setCases)
      .catch((err: Error) => setError(err.message))
  }, [])

  async function create(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const created = await api.createCase(patientRef, notes)
      navigate(`/casos/${created.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo crear el caso.')
      setBusy(false)
    }
  }

  const term = search.trim().toLocaleLowerCase()
  const visible = cases?.filter(item =>
    item.patient_ref.toLocaleLowerCase().includes(term) || String(item.id) === term.replace(/^#/, '')
  ) ?? []

  return (
    <div className="page">
      <h1>Casos</h1>

      <form className="card inline-form" onSubmit={create}>
        <label>
          Seudónimo del paciente
          <input
            value={patientRef}
            onChange={(e) => setPatientRef(e.target.value)}
            placeholder="p. ej. P-0042"
            maxLength={64}
            required
          />
        </label>
        <label className="grow">
          Notas (opcional)
          <input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={4000} />
        </label>
        <button type="submit" disabled={busy}>
          Nuevo caso
        </button>
        <p className="muted full">
          No escriba el nombre, el carnet ni otros datos que identifiquen al paciente.
        </p>
      </form>

      {error && <p className="error">{error}</p>}
      {cases === null && !error && <p className="muted">Cargando…</p>}
      {cases !== null && cases.length === 0 && (
        <p className="muted">Todavía no hay casos. Cree el primero con el formulario de arriba.</p>
      )}
      {cases !== null && cases.length > 0 && <div className="case-tools">
        <h2>Casos registrados <span className="count">{cases.length}</span></h2>
        <label>Buscar por seudónimo o número<input type="search" value={search} onChange={e => setSearch(e.target.value)} /></label>
      </div>}
      {term && !visible.length && <p role="status">Ningún caso coincide con la búsqueda.</p>}
      {visible.length > 0 && (
        <table className="card">
          <thead>
            <tr>
              <th>Caso</th>
              <th>Paciente</th>
              <th>Imágenes</th>
              <th>Creado</th>
              <th>Notas</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.id}>
                <td>
                  <Link to={`/casos/${item.id}`}>#{item.id}</Link>
                </td>
                <td>{item.patient_ref}</td>
                <td>{item.image_count}</td>
                <td>{dateTime(item.created_at)}</td>
                <td className="muted">{item.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
