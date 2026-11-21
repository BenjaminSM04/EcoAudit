import type { Analysis, ModelVersion } from '../api'
import { DECISION, dateTime, percent, warningText } from '../labels'
import { Badge } from './ui'
import { Gauge } from './ui/Gauge'

interface Props {
  analysis: Analysis
  model: ModelVersion | undefined
}

export default function ResultPanel({ analysis, model }: Props) {
  if (analysis.status === 'pending' || analysis.status === 'running') {
    return (
      <p className="muted" role="status">
        {analysis.status === 'pending' ? 'En cola…' : 'Procesando…'} (análisis #{analysis.id})
      </p>
    )
  }
  if (analysis.status === 'failed') {
    return (
      <div className="result tone-warning" role="alert">
        <h3>El análisis falló</h3>
        <p className="small">{analysis.error}</p>
        {analysis.attempts > 1 && <p className="small">Intentos: {analysis.attempts}.</p>}
      </div>
    )
  }

  const decision = analysis.decision ? DECISION[analysis.decision] : null
  const band = model?.card.decision


  return (
    <div className={`result tone-${decision?.tone ?? 'neutral'}`}>
      <h3><Badge tone={decision?.tone}>{decision?.title ?? 'Sin decisión'}</Badge></h3>
      <p className="small">{decision?.detail}</p>
      <Gauge value={analysis.probability} band={band} unreliable={analysis.decision === 'out_of_domain'} />

      <dl>
        <dt>Sin calibrar</dt>
        <dd>{percent(analysis.probability_raw)}</dd>
        <dt>Dispersión del ensamble</dt>
        <dd>{analysis.member_spread === null ? '—' : `± ${percent(analysis.member_spread, 1)}`}</dd>
        <dt>Cambio de dominio</dt>
        <dd>
          {analysis.shift_score === null
            ? 'no monitoreado'
            : `${analysis.shift_score.toFixed(2)}${
                model?.card.shift ? ` (umbral ${model.card.shift.threshold.toFixed(2)})` : ''
              }`}
        </dd>
        <dt>Región analizada</dt>
        <dd>{analysis.roi ? 'ROI marcado' : 'imagen completa'}</dd>
        <dt>Modelo</dt>
        <dd>{model ? `${model.name} ${model.version}` : `#${analysis.model_version_id}`}</dd>
        {model && <><dt>Paquete del modelo</dt><dd><code title={model.bundle_sha256}>{model.bundle_sha256.slice(0, 16)}…</code></dd></>}
        <dt>Fecha</dt>
        <dd>{analysis.finished_at ? dateTime(analysis.finished_at) : '—'}</dd>
        {analysis.attempts > 1 && (
          <>
            <dt>Intentos</dt>
            <dd>{analysis.attempts} (el análisis se interrumpió y se repitió)</dd>
          </>
        )}
      </dl>

      {analysis.warnings.length > 0 && (
        <ul className="flags">
          {analysis.warnings.map((code) => (
            <li key={code}>{warningText(code)}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
