import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, downloadPdf } from '../api'
import type { Cohort } from '../api'

const number = (v: number) => v.toLocaleString('es-BO', { minimumFractionDigits: 3, maximumFractionDigits: 3 })

export default function AuditPage() {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<Cohort | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    setBusy(true)
    setResult(null)
    setError('')
    try { setResult(await api.audit(file)) }
    catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }

  return <div className="page">
    <h1>Auditoría de cohortes</h1>
    <form className="card" onSubmit={submit}>
      <h2>Importar etiquetas de referencia</h2>
      <p>Incluya un análisis terminado por imagen y una única versión del modelo. El sistema agrupa las imágenes con el mismo seudónimo.</p>
      <p>Use un CSV UTF-8 con cabecera <code>analysis_id,label</code>. Indique 0 para benigna y 1 para maligna.</p>
      <div className="inline-form"><label>Archivo de etiquetas<input type="file" accept=".csv,text/csv" required disabled={busy}
        onChange={event => { setFile(event.target.files?.[0] ?? null); setResult(null); setError('') }} /></label>
        <button disabled={!file || busy}>{busy ? 'Calculando…' : 'Evaluar cohorte'}</button></div>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {result && <section className="card" aria-live="polite">
      <h2>Resultados por paciente</h2>
      <p>{result.model}{result.demo && ' · Modelo de demostración'} · {result.images} imágenes · {result.patients} pacientes · {result.positive} positivos</p>
      <div className="metrics">{[['AUROC',result.auc],['Brier',result.brier],['ECE',result.ece]].map(([label,value]) =>
        <div key={label}><span>{label}</span><strong>{number(Number(value))}</strong></div>)}</div>
      <p>IC del 95 % para AUROC · {result.ci ? result.ci.map(number).join(' – ') : 'Muestra insuficiente'}</p>
      <p>{result.abstentions} de {result.images} imágenes produjeron abstención. La evaluación incluye todas las puntuaciones.</p>
      <h3>Calibración observada</h3>
      <table><thead><tr><th>Banda</th><th>n</th><th>Media</th><th>Observada</th></tr></thead>
      <tbody>{result.bins.map(b => <tr key={b.bin}><td>{b.bin*10}–{(b.bin+1)*10} %</td><td>{b.n}</td><td>{number(b.predicted)}</td><td>{number(b.observed)}</td></tr>)}</tbody></table>
      <button onClick={() => downloadPdf('/api/cohorts/'+result.id+'/report', 'auditoria-'+result.id).catch(err => setError(err.message))}>Descargar informe PDF</button>
    </section>}
  </div>
}

