import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Drift } from '../api'
import { percent } from '../labels'
import { Card, EmptyState, Table } from './ui'

const shortWeek = (date: string) => `${date.slice(8, 10)}/${date.slice(5, 7)}`
const tick = { fill: 'var(--muted)', fontSize: 11 }
const score = new Intl.NumberFormat('es-BO', { maximumSignificantDigits: 4 })

export default function DriftCard({ drift }: { drift: Drift }) {
  return <Card className="page">
    <h2>Deriva del modelo</h2>
    <p className="muted small">Últimas 12 semanas ISO · UTC. Umbral de alerta de dominio {percent(drift.alert_threshold, 0)} a partir de 10 análisis en la semana actual.</p>
    {drift.models.length === 0 && <EmptyState>Aún no hay análisis en este período.</EmptyState>}
    {drift.models.map(model => {
      const name = `${model.name} ${model.version}`
      const latest = model.weeks.at(-1)
      return <section className="page" key={model.model_version_id} aria-label={name}>
        <h3>{name}</h3>
        {latest?.alert && <p className="banner" role="alert">Alerta de deriva en {name}. La tasa semanal de alertas de dominio fue del {percent(latest.shift_alert_rate, 1)} en {latest.n} análisis.</p>}
        <div className="chart" aria-label={`Tasas semanales de ${name}`}>
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <LineChart data={model.weeks} margin={{ top: 10, right: 20, bottom: 4, left: 2 }}>
              <CartesianGrid vertical={false} stroke="var(--line)" strokeDasharray="4 4" />
              <XAxis dataKey="week" tickFormatter={shortWeek} tick={tick} minTickGap={12} />
              <YAxis domain={[0, 1]} width={53} tickFormatter={value => percent(value, 0)} tick={tick} />
              <ReferenceArea y1={drift.alert_threshold} y2={1} fill="var(--orchid-500)" fillOpacity={.12} />
              <ReferenceLine y={drift.alert_threshold} stroke="var(--muted)" strokeDasharray="5 4" />
              <Tooltip labelFormatter={value => `Semana del ${value}`} formatter={value => percent(Number(value), 1)}
                contentStyle={{ background: 'var(--surface)', borderColor: 'var(--control-line)', color: 'var(--text)' }}
                itemStyle={{ color: 'var(--text)' }} />
              <Line dataKey="shift_alert_rate" name="Alertas de dominio" stroke="var(--brand)" strokeWidth={2.5} isAnimationActive={false} />
              <Line dataKey="abstention_rate" name="Abstención" stroke="var(--chart-mint)" strokeWidth={2} strokeDasharray="5 3" isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-legend small"><span>━ Alertas de dominio</span><span>┄ Abstención</span></div>
        <details className="chart-details"><summary>Ver datos semanales</summary>
          <Table label={`Datos semanales de ${name}`}><thead><tr><th scope="col">Semana del</th><th scope="col">Análisis</th><th scope="col">Alertas de dominio</th><th scope="col">Puntaje medio de deriva</th><th scope="col">Abstención</th></tr></thead>
            <tbody>{model.weeks.map(week => <tr key={week.week}><th scope="row">{week.week}</th><td>{week.n}</td><td>{percent(week.shift_alert_rate, 1)}</td><td>{week.mean_shift_score === null ? '—' : score.format(week.mean_shift_score)}</td><td>{percent(week.abstention_rate, 1)}</td></tr>)}</tbody>
          </Table>
        </details>
      </section>
    })}
  </Card>
}
