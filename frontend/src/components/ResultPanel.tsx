import type { Analysis, ModelVersion } from '../api'
import { DECISION, dateTime, percent, warningText } from '../labels'

interface Props {
  analysis: Analysis
  model: ModelVersion | undefined
}

export default function ResultPanel({ analysis, model }: Props) {
  if (analysis.status === 'pending' || analysis.status === 'running') {
    return (
      <p className="muted">
        {analysis.status === 'pending' ? 'En cola…' : 'Procesando…'} (análisis #{analysis.id})
      </p>
    )
  }
  if (analysis.status === 'failed') {
    return (
      <div className="result tone-warning">
        <h3>El análisis falló</h3>
        <p className="small">{analysis.error}</p>
        {analysis.attempts > 1 && <p className="small">Intentos: {analysis.attempts}.</p>}
      </div>
    )
  }

  const decision = analysis.decision ? DECISION[analysis.decision] : null
  const band = model?.card.decision
  const probability = analysis.probability ?? 0

  return (
    <div className={`result tone-${decision?.tone ?? 'neutral'}`}>
      <h3>{decision?.title ?? 'Sin decisión'}</h3>
      <p className="small">{decision?.detail}</p>

      <div className={analysis.decision === 'out_of_domain' ? 'prob unreliable' : 'prob'}>
        <span className="prob-value">{percent(analysis.probability)}</span>
        <span className="muted small">probabilidad calibrada de malignidad</span>
      </div>
      <div className="bar" aria-hidden="true">
        {band && (
          <div
            className="band"
            style={{
              left: `${band.abstain_low * 100}%`,
              width: `${(band.abstain_high - band.abstain_low) * 100}%`,
            }}
            title="Zona de abstención"
          />
        )}
        <div className="marker" style={{ left: `${probability * 100}%` }} />
      </div>
      {band && (
        <p className="muted small">
          Zona de abstención experimental: {percent(band.abstain_low)} a {percent(band.abstain_high)}.
        </p>
      )}

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
