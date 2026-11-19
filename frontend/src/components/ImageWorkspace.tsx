import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { api, downloadFile } from '../api'
import type { Analysis, CaseImage, ModelVersion, Roi } from '../api'
import { warningText } from '../labels'
import ResultPanel from './ResultPanel'
import { useBlobUrl } from './useBlobUrl'

interface Props {
  image: CaseImage
  models: ModelVersion[]
}

const MIN_ROI = 8 // píxeles de imagen; el backend rechaza recortes menores

export default function ImageWorkspace({ image, models }: Props) {
  const imageUrl = useBlobUrl(`/api/images/${image.id}/file`)
  const [analysis, setAnalysis] = useState<Analysis | null>(image.analyses.at(-1) ?? null)
  const [roi, setRoi] = useState<Roi | null>(analysis?.roi ?? null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showCam, setShowCam] = useState(true)
  const [camOpacity, setCamOpacity] = useState(0.7)
  const frameRef = useRef<HTMLDivElement>(null)
  const dragStart = useRef<{ x: number; y: number } | null>(null)

  const camUrl = useBlobUrl(analysis?.has_cam ? `/api/analyses/${analysis.id}/cam` : null)
  const waiting = analysis?.status === 'pending' || analysis?.status === 'running'

  // Mientras el análisis está en cola o corriendo, se consulta cada segundo.
  useEffect(() => {
    if (!analysis || !waiting) return
    const timer = setTimeout(() => {
      api
        .getAnalysis(analysis.id)
        .then(setAnalysis)
        .catch((err: Error) => setError(err.message))
    }, 1000)
    return () => clearTimeout(timer)
  }, [analysis, waiting])

  function toImagePoint(event: ReactPointerEvent): { x: number; y: number } {
    const rect = frameRef.current!.getBoundingClientRect()
    const x = ((event.clientX - rect.left) / rect.width) * image.width
    const y = ((event.clientY - rect.top) / rect.height) * image.height
    return {
      x: Math.min(Math.max(x, 0), image.width),
      y: Math.min(Math.max(y, 0), image.height),
    }
  }

  function onPointerDown(event: ReactPointerEvent) {
    if (busy || waiting || event.button !== 0) return
    event.currentTarget.setPointerCapture(event.pointerId)
    dragStart.current = toImagePoint(event)
    setRoi(null)
  }

  function onPointerMove(event: ReactPointerEvent) {
    if (dragStart.current === null) return
    const start = dragStart.current
    const end = toImagePoint(event)
    setRoi({
      x: Math.min(start.x, end.x),
      y: Math.min(start.y, end.y),
      w: Math.abs(end.x - start.x),
      h: Math.abs(end.y - start.y),
    })
  }

  function onPointerUp() {
    dragStart.current = null
    setRoi((current) =>
      current !== null && (current.w < MIN_ROI || current.h < MIN_ROI) ? null : current,
    )
  }

  async function analyze() {
    setBusy(true)
    setError(null)
    try {
      setAnalysis(await api.requestAnalysis(image.id, roi))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo solicitar el análisis.')
    } finally {
      setBusy(false)
    }
  }

  const savedRoi = analysis?.roi ?? null
  const changed = roi === null || savedRoi === null
    ? roi !== savedRoi
    : roi.x !== savedRoi.x || roi.y !== savedRoi.y || roi.w !== savedRoi.w || roi.h !== savedRoi.h
  const roiStyle =
    roi === null
      ? undefined
      : {
          left: `${(roi.x / image.width) * 100}%`,
          top: `${(roi.y / image.height) * 100}%`,
          width: `${(roi.w / image.width) * 100}%`,
          height: `${(roi.h / image.height) * 100}%`,
        }
  const model = analysis ? models.find((m) => m.id === analysis.model_version_id) : undefined

  return (
    <section className="card workspace">
      <div className="viewer">
        <div
          className="frame"
          ref={frameRef}
          style={{ aspectRatio: `${image.width} / ${image.height}` }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          {imageUrl ? (
            <img src={imageUrl} alt={`Ecografía ${image.id}`} draggable={false} />
          ) : (
            <span className="frame-note">Cargando imagen…</span>
          )}
          {camUrl && !changed && showCam && analysis?.status === 'done' && (
            <img
              className="cam"
              src={camUrl}
              alt=""
              style={{ opacity: camOpacity }}
              draggable={false}
            />
          )}
          {roiStyle && <div className="roi" style={roiStyle} />}
        </div>
        <p className="muted small">
          Imagen #{image.id} · {image.width}×{image.height} px · origen {image.source_format}.
          Arrastre sobre la imagen para marcar la lesión (ROI).
        </p>
        {image.qc_flags.length > 0 && (
          <ul className="flags">
            {image.qc_flags.map((flag) => (
              <li key={flag}>{warningText(flag)}</li>
            ))}
          </ul>
        )}
      </div>

      <div className="side">
        <div className="actions">
          <button onClick={analyze} disabled={busy || waiting}>
            {waiting ? 'Analizando…' : roi ? 'Analizar el ROI' : 'Analizar la imagen completa'}
          </button>
          <button className="secondary" disabled={busy || waiting} onClick={async () => {
            setBusy(true)
            setError(null)
            try {
              const suggestion = await api.suggest(image.id)
              if (suggestion.roi) setRoi(suggestion.roi)
              else setError('Sin propuesta utilizable. Trace el ROI manualmente.')
            } catch (err) { setError((err as Error).message) }
            finally { setBusy(false) }
          }}>Sugerir ROI experimental</button>
          {roi && (
            <button className="secondary" onClick={() => setRoi(null)} disabled={busy || waiting}>
              Quitar ROI
            </button>
          )}
        </div>
        {roi && <p className="muted small">Revise el recuadro antes de analizar. Puede volver a trazarlo.</p>}
        {analysis?.status === 'done' && <button className="secondary" onClick={() =>
          downloadFile(`/api/analyses/${analysis.id}/report`, `analisis-${analysis.id}.pdf`).catch(err => setError(err.message))
        }>Descargar PDF · Análisis #{analysis.id}</button>}
        {error && <p className="error">{error}</p>}

        {analysis === null && <p className="muted">Esta imagen todavía no fue analizada.</p>}
        {changed && analysis?.status === 'done' && <p className="banner">La región seleccionada cambió. El informe anterior corresponde al análisis #{analysis.id}. Vuelva a analizar para obtener el resultado de esta selección.</p>}
        {analysis !== null && !changed && <ResultPanel analysis={analysis} model={model} />}

        {analysis?.status === 'done' && analysis.has_cam && !changed && (
          <div className="cam-controls">
            <label className="check">
              <input
                type="checkbox"
                checked={showCam}
                onChange={(e) => setShowCam(e.target.checked)}
              />
              Mostrar mapa de activación
            </label>
            <input
              type="range"
              min={0.1}
              max={1}
              step={0.05}
              value={camOpacity}
              onChange={(e) => setCamOpacity(Number(e.target.value))}
              disabled={!showCam}
              aria-label="Opacidad del mapa"
            />
            <p className="muted small">
              El mapa señala las regiones que empujaron la predicción hacia «maligno». Sirve para
              verificar que el modelo mira la lesión y no un artefacto; no delimita el tumor.
            </p>
          </div>
        )}
      </div>
    </section>
  )
}
