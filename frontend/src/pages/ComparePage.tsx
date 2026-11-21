import { useEffect, useState, type FormEvent } from 'react'
import { Scale } from 'lucide-react'
import { api, type CohortSummary, type Comparison, type ConfidenceInterval } from '../api'
import { Badge, Button, Card, EmptyState, Skeleton, StatCard, Table } from '../components/ui'
import { decimal, percent } from '../labels'

function interval(ci: ConfidenceInterval) {
  return ci ? `${decimal(ci[0])} a ${decimal(ci[1])}` : 'Muestra insuficiente'
}

export default function ComparePage() {
  const [cohorts, setCohorts] = useState<CohortSummary[] | null>(null)
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [result, setResult] = useState<Comparison | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void api.listCohorts().then(items => setCohorts(items.filter(item => item.status === 'done'))).catch((err: Error) => setError(err.message))
  }, [])

  async function compare(event: FormEvent) {
    event.preventDefault()
    setError('')
    setResult(null)
    setBusy(true)
    try {
      setResult(await api.compare(Number(a), Number(b)))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const difference = result?.paired_auc_difference
  const ci = difference?.ci
  const models = [a, b].map(id => cohorts?.find(item => String(item.id) === id)?.model)
  const position = (value: number) => 20 + (value + 1) * 180
  return <div className="page">
    <div className="page-heading"><div><h1>Comparar modelos</h1><p>Evaluación pareada sobre las mismas imágenes, pacientes y etiquetas.</p></div></div>
    {error && <p className="error" role="alert">{error}</p>}
    {!cohorts && !error && <Skeleton />}
    {cohorts && cohorts.length < 2 && <Card><EmptyState>Se necesitan dos cohortes terminadas. Puede crear una segunda versión desde el detalle de una cohorte.</EmptyState></Card>}
    {cohorts && cohorts.length >= 2 && <form className="card inline-form" onSubmit={compare}>
      {([['Cohorte A', a, b, setA], ['Cohorte B', b, a, setB]] as const).map(([label, selected, other, set]) =>
        <label key={label} className="grow">{label}<select aria-label={label} required disabled={busy} value={selected} onChange={event => {
          set(event.target.value)
          setResult(null)
          setError('')
        }}>
          <option value="">Seleccione una cohorte</option>
          {cohorts.map(item => <option key={item.id} value={item.id} disabled={String(item.id) === other}>{item.name} · {item.model}</option>)}
        </select></label>)}
      <Button type="submit" disabled={busy || !a || !b || a === b}>{busy ? 'Comparando…' : 'Comparar cohortes'}</Button>
    </form>}
    {result && difference && <>
      <div className="comparison-grid">{([result.a, result.b] as const).map((item, index) => <Card className="page" key={item.cohort_id}>
        <div className="section-heading"><h2>{models[index]}</h2><Badge tone="brand">Cohorte {index === 0 ? 'A' : 'B'}</Badge></div>
        <StatCard icon={Scale} label="AUROC" value={decimal(item.auc)} detail={`IC del 95 % · ${interval(item.ci)}`} />
        <Table label={`Métricas de la cohorte ${index === 0 ? 'A' : 'B'}`}><tbody>
          <tr><th scope="row">Brier</th><td>{decimal(item.brier)}</td></tr>
          <tr><th scope="row">Abstención por imagen</th><td>{percent(item.abstention_rate, 1)}</td></tr>
          <tr><th scope="row">Alertas de dominio por imagen</th><td>{percent(item.shift_alert_rate, 1)}</td></tr>
          <tr><th scope="row">Imágenes monitoreadas</th><td>{item.shift_monitored}</td></tr>
        </tbody></Table>
      </Card>)}</div>
      <Card className="page">
        <h2>Diferencia pareada de AUROC (B − A)</h2>
        <p><strong>{decimal(difference.value)}</strong> · IC del 95 %: {interval(difference.ci)}</p>
        <svg className="forest" viewBox="0 0 400 88" aria-hidden="true">
          <path d="M20 50h360" stroke="var(--line)" strokeWidth="2" />
          <path d="M200 12v43" stroke="var(--muted)" strokeDasharray="3 4" />
          {ci && <path d={`M${position(ci[0])} 20v20m0-10H${position(ci[1])}m0-10v20`} fill="none" stroke="var(--brand)" strokeWidth="2" />}
          <circle cx={position(difference.value)} cy="30" r="5" fill="var(--brand)" />
          {[-1, 0, 1].map(value => <text key={value} x={position(value)} y="70" textAnchor="middle" fill="var(--muted)" fontSize="12">{value}</text>)}
        </svg>
        <p className="muted">{!ci ? 'La muestra es insuficiente para estimar el intervalo de la diferencia.'
          : ci[0] <= 0 && ci[1] >= 0 ? 'El intervalo incluye 0. Los datos son compatibles con una diferencia nula de AUROC en esta cohorte.'
          : 'El intervalo excluye 0 en esta cohorte. La diferencia observada corresponde a esta muestra de evaluación.'}</p>
      </Card>
    </>}
  </div>
}
