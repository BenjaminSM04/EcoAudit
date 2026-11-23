import { percent } from '../../labels'

const point = (value: number) => {
  const angle = Math.PI * (1 - value)
  return [108 + 84 * Math.cos(angle), 101 - 84 * Math.sin(angle)]
}

function arc(from: number, to: number) {
  const [sx, sy] = point(from)
  const [ex, ey] = point(to)
  return `M${sx} ${sy} A84 84 0 0 1 ${ex} ${ey}`
}

export function Gauge({ value, band, unreliable }: {
  value: number | null; band?: { abstain_low: number; abstain_high: number }; unreliable: boolean
}) {
  const marker = value === null ? null : point(Math.min(1, Math.max(0, value)))
  return <div className={unreliable ? 'gauge unreliable' : 'gauge'}>
    <div className="gauge-face">
      <svg viewBox="0 0 216 119" aria-hidden="true">
        <path d={arc(0, 1)} fill="none" stroke="#f2cedb" strokeWidth="12" strokeLinecap="round" />
        {band && <path d={arc(band.abstain_low, band.abstain_high)} fill="none" stroke="#D9C8A9" strokeWidth="12" />}
        {marker && <circle cx={marker[0]} cy={marker[1]} r="8" fill="#7A3D50" stroke="white" strokeWidth="3" />}
        <text x="16" y="117" fill="var(--muted)" fontSize="9">0 %</text><text x="180" y="117" fill="var(--muted)" fontSize="9">100 %</text>
      </svg>
      <strong>{percent(value)}</strong>
    </div>
    <p>probabilidad calibrada de malignidad</p>
    {band && <small><span className="sand-dot" aria-hidden="true" /> Zona de abstención experimental · {percent(band.abstain_low)} a {percent(band.abstain_high)}</small>}
  </div>
}
