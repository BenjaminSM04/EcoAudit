import { useState, type FormEvent } from 'react'
import { Eye, ScanLine } from 'lucide-react'
import { ApiError, api, type Analysis, type Birads, type ClinicalReading } from '../api'
import { BIRADS, BIRADS_ORDER, dateTime } from '../labels'
import { Badge, Button, Card } from './ui'

export function ReadingForm({ id, blinded, onSaved, onReveal }: {
  id: number; blinded: boolean; onSaved: (reading: ClinicalReading) => void; onReveal?: () => void
}) {
  const [birads, setBirads] = useState<Birads | ''>('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!birads) return
    setBusy(true)
    setError('')
    try {
      onSaved(await api.createReading(id, { birads, blinded, notes: notes.trim() || null }))
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        try {
          onSaved(await api.getReading(id))
          return
        } catch (readError) {
          setError((readError as Error).message)
        }
      } else {
        setError((err as Error).message)
      }
    } finally {
      setBusy(false)
    }
  }

  return <Card className="reading-card page">
    <div className="stat-icon tone-brand"><ScanLine size={20} aria-hidden="true" /></div>
    <h3>{blinded ? 'Registre su lectura antes de ver el resultado' : 'Registrar lectura clínica'}</h3>
    <p className="muted small">{blinded ? 'Seleccione la categoría BI-RADS según su evaluación de la imagen.' : 'La lectura quedará registrada como posterior a la consulta del resultado.'}</p>
    <form className="page" onSubmit={submit}>
      <label>BI-RADS<select aria-label="BI-RADS" value={birads} onChange={e => setBirads(e.target.value as Birads | '')} required disabled={busy}>
        <option value="">Seleccione una categoría</option>{BIRADS_ORDER.map(code => <option key={code} value={code}>{code} · {BIRADS[code]}</option>)}
      </select></label>
      <label>Notas (opcional)<textarea rows={3} value={notes} onChange={e => setNotes(e.target.value)} maxLength={2000} disabled={busy} /></label>
      {error && <p className="error" role="alert">{error}</p>}
      <Button type="submit" disabled={busy}>{busy ? 'Registrando…' : blinded ? 'Registrar lectura y ver resultado' : 'Registrar lectura'}</Button>
    </form>
    {onReveal && <Button className="reveal-link" variant="ghost" disabled={busy} onClick={onReveal}><Eye size={17} aria-hidden="true" /> Ver resultado sin registrar lectura</Button>}
  </Card>
}

export function ReadingSummary({ analysis, reading }: { analysis: Analysis; reading: ClinicalReading }) {
  const comparable = analysis.decision === 'probably_benign' || analysis.decision === 'suspicious'
  const agrees = comparable && (analysis.decision === 'suspicious') === !['1', '2', '3'].includes(reading.birads)
  return <Card className="page reading-card">
    <div className="section-heading"><h3>Lectura clínica</h3><Badge tone={agrees ? 'benign' : 'neutral'}>{comparable ? (agrees ? 'Concuerda' : 'No concuerda') : 'Sin comparación'}</Badge></div>
    <p><strong>BI-RADS {reading.birads}</strong> · {BIRADS[reading.birads]}</p>
    <p className="small muted">{reading.blinded ? 'Lectura ciega' : 'Lectura posterior a ver el resultado'} · {dateTime(reading.created_at)}</p>
    {reading.notes && <p className="reading-notes">{reading.notes}</p>}
  </Card>
}
