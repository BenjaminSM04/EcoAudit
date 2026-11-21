import { useEffect, useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, CheckCircle2, CirclePause, Clock3, FolderOpen, Image, Layers3, TriangleAlert } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type Concordance, type Overview, type Performance } from '../api'
import { Card, EmptyState, Skeleton, StatCard, Table } from '../components/ui'
import { DECISION, DECISION_ORDER, decimal, percent } from '../labels'
import { useAuth } from '../session'

const colors = ['#77ba99', '#c6a978', '#ba3a50', '#7963a1']
const seconds = (value: number | null) => value === null ? '—' : `${decimal(value)} s`
const shortDay = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`

export default function DashboardPage() {
  const { user } = useAuth()
  const gradient = useId()
  const canAudit = user?.role !== 'medico'
  const [data, setData] = useState<Overview | null>(null)
  const [agreement, setAgreement] = useState<Concordance | null>(null)
  const [performance, setPerformance] = useState<Performance | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    let alive = true
    const failed = (section: string) => (error: Error) => {
      if (alive) setErrors(current => ({ ...current, [section]: error.message }))
    }
    void api.overview().then(value => { if (alive) setData(value) }).catch(failed('Resumen'))
    void api.concordance().then(value => { if (alive) setAgreement(value) }).catch(failed('Concordancia'))
    if (canAudit) void api.performance().then(value => { if (alive) setPerformance(value) }).catch(failed('Latencia por modelo'))
    return () => { alive = false }
  }, [canAudit])

  const decisions = DECISION_ORDER.map((key, index) => ({ name: DECISION[key].title, fill: colors[index], value: data?.decisions[key] ?? 0 }))
  const total = decisions.reduce((sum, item) => sum + item.value, 0)
  const done = data?.analyses_by_status.done ?? 0
  return <div className="page">
    <div className="page-heading"><div><h1>Panel</h1><p>Actividad, decisiones del modelo y lecturas clínicas dentro de su alcance.</p></div>
      <Link className="button secondary" to="/casos"><FolderOpen size={18} aria-hidden="true" /> Ver casos</Link>
    </div>
    {Object.entries(errors).map(([section, error]) => <p className="error" role="alert" key={section}><strong>{section}.</strong> {error}</p>)}
    {!data && !errors.Resumen && <Skeleton label="Cargando indicadores" />}
    {data && <>
      <section className="stat-grid" aria-label="Indicadores">
        <StatCard icon={FolderOpen} label="Casos" value={data.cases} detail="Casos registrados" />
        <StatCard icon={Image} label="Imágenes" value={data.images} detail="Ecografías cargadas" />
        <StatCard icon={CheckCircle2} label="Análisis terminados" value={done} detail={`${data.analyses_by_status.pending + data.analyses_by_status.running} en proceso`} tone="benign" />
        <StatCard icon={CirclePause} label="Tasa de abstención" value={percent(data.abstention_rate, 1)} detail="Decisiones indeterminadas" tone="neutral" />
        <StatCard icon={TriangleAlert} label="Alertas de dominio" value={percent(data.shift_alert_rate, 1)} detail={`${data.shift_monitored} análisis monitoreados`} tone="warning" />
        <StatCard icon={Clock3} label="Latencia p95" value={seconds(data.latency_seconds.total.p95)} detail={`De solicitud a fin · n = ${data.latency_seconds.total.n}`} />
      </section>
      <div className="dashboard-grid">
        <Card>
          <h2>Análisis por día</h2><p className="muted small">Solicitudes de los últimos 30 días · UTC</p>
          <div className="chart" aria-label="Solicitudes de análisis por día">
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <AreaChart data={data.analyses_by_day} margin={{ top: 12, right: 12, bottom: 4, left: 0 }}>
                <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#BF658F" stopOpacity={.38} /><stop offset="100%" stopColor="#BF658F" stopOpacity={.04} /></linearGradient></defs>
                <CartesianGrid vertical={false} stroke="#ecdee4" strokeDasharray="4 4" />
                <XAxis dataKey="date" tickFormatter={shortDay} tick={{ fill: '#66545f', fontSize: 11 }} minTickGap={22} axisLine={false} tickLine={false} />
                <YAxis width={34} allowDecimals={false} tick={{ fill: '#66545f', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip labelFormatter={value => shortDay(String(value))} />
                <Area isAnimationActive={false} type="monotone" dataKey="count" name="Solicitudes" stroke="#934565" strokeWidth={2.5} fill={`url(#${gradient})`} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <details className="chart-details"><summary>Ver datos por día</summary><Table label="Solicitudes por día"><thead><tr><th scope="col">Fecha (UTC)</th><th scope="col">Solicitudes</th></tr></thead><tbody>{data.analyses_by_day.map(day => <tr key={day.date}><td>{day.date}</td><td>{day.count}</td></tr>)}</tbody></Table></details>
        </Card>
        <Card>
          <h2>Distribución de decisiones</h2><p className="muted small">Análisis terminados con decisión</p>
          {total > 0 ? <div className="donut">
            <ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <PieChart><Pie isAnimationActive={false} data={decisions.filter(item => item.value > 0)} dataKey="value" nameKey="name" innerRadius="65%" outerRadius="92%" paddingAngle={2} stroke="none" /><Tooltip /></PieChart>
            </ResponsiveContainer>
            <div className="donut-total" aria-hidden="true"><strong>{total}</strong><small>Decisiones</small></div>
          </div> : <EmptyState>Aún no hay decisiones registradas.</EmptyState>}
          <ul className="legend">{decisions.map(item => <li key={item.name}><span style={{ background: item.fill }} aria-hidden="true" />{item.name}<strong>{item.value}</strong></li>)}</ul>
        </Card>
      </div>
    </>}
    <div className="dashboard-grid">
      {agreement ? <Card className="page">
        <h2>Concordancia médico–modelo</h2>
        <div className="metrics">
          <div><span>Kappa</span><strong>{decimal(agreement.kappa)}</strong></div>
          <div><span>Acuerdo</span><strong>{agreement.agreement_percent === null ? '—' : percent(agreement.agreement_percent / 100, 1)}</strong></div>
        </div>
        <Table label="Matriz de concordancia"><thead><tr><th scope="col">Lectura clínica</th><th scope="col">Modelo no sospechoso</th><th scope="col">Modelo sospechoso</th></tr></thead><tbody>
          <tr><th scope="row">No sospechosa</th><td>{agreement.matrix[0][0]}</td><td>{agreement.matrix[0][1]}</td></tr>
          <tr><th scope="row">Sospechosa</th><td>{agreement.matrix[1][0]}</td><td>{agreement.matrix[1][1]}</td></tr>
        </tbody></Table>
        <p className="muted small">{agreement.n} {agreement.n === 1 ? 'par elegible' : 'pares elegibles'} · {agreement.n_indeterminate} {agreement.n_indeterminate === 1 ? 'indeterminado' : 'indeterminados'} fuera de la matriz · {agreement.n_blinded} {agreement.n_blinded === 1 ? 'lectura ciega' : 'lecturas ciegas'}.</p>
      </Card> : !errors.Concordancia && <Skeleton label="Cargando concordancia" />}
      {data && <Card className="page">
        <div className="stat-icon tone-brand"><Layers3 size={20} aria-hidden="true" /></div><h2>Modelo activo</h2>
        {data.active_model ? <><strong className="active-model">{data.active_model.name}</strong><p className="muted">Versión {data.active_model.version}</p></> : <p className="muted">No hay un modelo activo.</p>}
        <p><Activity size={16} aria-hidden="true" /> {data.clinical_readings} {data.clinical_readings === 1 ? 'lectura clínica registrada' : 'lecturas clínicas registradas'}</p>
        <Link to="/modelos">Ver registro de modelos</Link>
      </Card>}
    </div>
    {canAudit && (performance ? <Card className="page"><h2>Latencia por versión de modelo</h2>
      {performance.models.length ? <Table label="Latencia por versión en segundos"><thead><tr><th scope="col">Versión</th><th scope="col">Medición</th><th scope="col">n</th><th scope="col">Media</th><th scope="col">p50</th><th scope="col">p95</th><th scope="col">Máxima</th></tr></thead><tbody>
        {performance.models.flatMap(model => (['processing', 'total'] as const).map(kind => {
          const latency = model.latency_seconds[kind]
          return <tr key={`${model.model_version_id}-${kind}`}><th scope="row">{model.name} {model.version}</th><td>{kind === 'processing' ? 'Procesamiento' : 'Total'}</td><td>{latency.n}</td><td>{seconds(latency.mean)}</td><td>{seconds(latency.p50)}</td><td>{seconds(latency.p95)}</td><td>{seconds(latency.max)}</td></tr>
        }))}
      </tbody></Table> : <EmptyState>Aún no hay mediciones por versión.</EmptyState>}
    </Card> : !errors['Latencia por modelo'] && <Skeleton label="Cargando desempeño" />)}
  </div>
}
