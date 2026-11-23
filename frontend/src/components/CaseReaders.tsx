import { useEffect, useState, type FormEvent } from 'react'
import { api, type CaseReaders as Readers } from '../api'
import { Button, Card, Toast } from './ui'

export default function CaseReaders({ caseId }: { caseId: number }) {
  const [readers, setReaders] = useState<Readers | null>(null)
  const [selected, setSelected] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => {
    let alive = true
    void api.caseReaders(caseId).then(value => { if (alive) setReaders(value) })
      .catch((err: Error) => { if (alive) setError(err.message) })
    return () => { alive = false }
  }, [caseId])

  async function assign(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api.assignReader(caseId, Number(selected))
      setSelected('')
      setNotice('Médico asignado al caso.')
      setReaders(await api.caseReaders(caseId))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return <Card className="page">
    <h2>Lectura asignada</h2>
    {error && <p className="error" role="alert">{error}</p>}
    {notice && <Toast>{notice}</Toast>}
    {readers && <>
      {readers.assigned.length > 0 && <ul className="reader-list">{readers.assigned.map(reader =>
        <li key={reader.id}>{reader.full_name} · #{reader.id}</li>
      )}</ul>}
      {readers.eligible.length ? <form className="inline-form" onSubmit={assign}>
        <label className="grow">Segundo médico<select required value={selected} onChange={event => setSelected(event.target.value)}>
          <option value="">Seleccione un médico</option>
          {readers.eligible.map(reader => <option key={reader.id} value={reader.id}>{reader.full_name} · #{reader.id}</option>)}
        </select></label>
        <Button type="submit" variant="secondary" disabled={!selected || busy}>Asignar lectura</Button>
      </form> : <p className="muted">No hay más médicos disponibles para asignar.</p>}
    </>}
  </Card>
}
