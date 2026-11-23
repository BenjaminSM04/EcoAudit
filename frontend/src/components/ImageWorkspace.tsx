import { useEffect, useRef, useState } from 'react'
import type { FormEvent, PointerEvent as ReactPointerEvent } from 'react'
import { api, downloadFile } from '../api'
import type { Analysis, CaseImage, ModelVersion, Roi } from '../api'
import { Download, FileJson } from 'lucide-react'
import { warningText } from '../labels'
import { useAuth } from '../session'
import { ReadingForm, ReadingSummary } from './Reading'
import { Button, Toast } from './ui'
import ResultPanel from './ResultPanel'
import { useBlobUrl } from './useBlobUrl'

interface Props {
  image: CaseImage
  models: ModelVersion[]
  canManage: boolean
  target: number
}

const MIN_ROI = 8 // píxeles de imagen; el backend rechaza recortes menores

export default function ImageWorkspace({ image, models, canManage, target }: Props) {
  const { user } = useAuth()
  const imageUrl = useBlobUrl(`/api/images/${image.id}/file`)
  const [analysis, setAnalysis] = useState<Analysis | null>(() => image.analyses.find(a => a.id === target) ?? image.analyses.at(-1) ?? null)
  const [history, setHistory] = useState(image.analyses)
  const [roi, setRoi] = useState<Roi | null>(analysis?.roi ?? null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showCam, setShowCam] = useState(true)
  const [camOpacity, setCamOpacity] = useState(0.7)
  const frameRef = useRef<HTMLDivElement>(null)
  const dragStart = useRef<{ x: number; y: number } | null>(null)

  const [revealed, setRevealed] = useState<number | null>(null)
  const [exporting, setExporting] = useState(false)
  const [notice, setNotice] = useState('')
  const revealKey = `ecoaudit.revealed.${user?.id}.${analysis?.id}`
  let previouslyRevealed = false
  try {
    previouslyRevealed = sessionStorage.getItem(revealKey) === '1'
  } catch {
    // La revelación sigue disponible durante esta visita.
  }
  const complete = analysis?.status === 'done'
  const serverBlinded = analysis?.blinded_for_reader === true
  const hidden = serverBlinded || (complete && user?.role === 'medico' && !analysis.reading && revealed !== analysis.id && !previouslyRevealed)
  const camUrl = useBlobUrl(analysis?.has_cam && !hidden ? `/api/analyses/${analysis.id}/cam` : null)

  function reveal() {
    if (!analysis) return
    setRevealed(analysis.id)
    try {
      sessionStorage.setItem(revealKey, '1')
    } catch {
      // El estado del visor conserva la elección.
    }
  }

  async function exportResult(id: number, format: 'pdf' | 'fhir') {
    setExporting(true)
    setError(null)
    setNotice('')
    try {
      if (format === 'fhir') await api.exportFhir(id)
      else await downloadFile(`/api/analyses/${id}/report`, `analisis-${id}.pdf`)
      setNotice(format === 'fhir' ? 'Exportación FHIR descargada.' : 'Informe PDF descargado.')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setExporting(false)
    }
  }
  const waiting = analysis?.status === 'pending' || analysis?.status === 'running'

  // Mientras el análisis está en cola o corriendo, se consulta cada segundo.
  useEffect(() => {
    if (!analysis || !waiting) return
    let alive = true
    let timer: ReturnType<typeof setTimeout>
    function poll(id: number) {
      timer = setTimeout(() => {
        void api.getAnalysis(id).then(next => {
          if (alive) { setAnalysis(next); setError(null) }
        }).catch((err: Error) => {
          if (alive) { setError(err.message); poll(id) }
        })
      }, 1000)
    }
    poll(analysis.id)
    return () => { alive = false; clearTimeout(timer) }
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
    if (!canManage || busy || waiting || event.button !== 0) return
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

  function applyCoordinates(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const candidate = { x: Number(data.get('x')), y: Number(data.get('y')), w: Number(data.get('w')), h: Number(data.get('h')) }
    if (candidate.x + candidate.w > image.width || candidate.y + candidate.h > image.height) {
      setError('La región debe quedar dentro de los límites de la imagen.')
      return
    }
    setError(null)
    setRoi(candidate)
  }

  async function analyze() {
    setBusy(true)
    setError(null)
    setNotice('')
    try {
      const requested = await api.requestAnalysis(image.id, roi)
      setAnalysis(requested)
      setHistory(current => [...current, requested])
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

  async function selectAnalysis(id: number) {
    setError(null)
    setNotice('')
    setBusy(true)
    try {
      const next = await api.getAnalysis(id)
      setAnalysis(next)
      setRoi(next.roi)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function refreshResult(id: number) {
    setError(null)
    try {
      const next = await api.getAnalysis(id)
      setAnalysis(current => current?.id === id ? next : current)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <section className="card workspace">
      <div className="viewer">
        <div
          className={canManage ? 'frame' : 'frame is-readonly'}
          ref={frameRef}
          style={{ aspectRatio: `${image.width} / ${image.height}`, maxWidth: `${65 * image.width / image.height}dvh` }}
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
          {camUrl && !hidden && !changed && showCam && complete && (
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
          {canManage && ' Arrastre sobre la imagen para marcar la lesión (ROI).'}
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
        {history.length > 1 && <label>Análisis de la imagen<select value={analysis?.id ?? ''} disabled={busy || waiting}
          onChange={event => void selectAnalysis(Number(event.target.value))}>
          {history.map(item => <option key={item.id} value={item.id}>Análisis #{item.id}</option>)}
        </select></label>}
        {canManage && <><div className="actions">
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
        <details className="small">
          <summary>Definir ROI por coordenadas</summary>
          <form className="page" onSubmit={applyCoordinates} key={roi ? [roi.x, roi.y, roi.w, roi.h].join(',') : 'full'}>
            <div className="roi-fields">
              {([['x', 'Posición X', 0, image.width - MIN_ROI], ['y', 'Posición Y', 0, image.height - MIN_ROI],
                ['w', 'Ancho', MIN_ROI, image.width], ['h', 'Alto', MIN_ROI, image.height]] as const).map(([key, label, min, max]) =>
                <label key={key}>{label} (px)<input name={key} type="number" min={min} max={max} required disabled={busy || waiting}
                  defaultValue={roi ? Math.round(roi[key]) : undefined} /></label>)}
            </div>
            <Button type="submit" variant="secondary" disabled={busy || waiting}>Aplicar coordenadas</Button>
          </form>
        </details>
        {roi && <p className="muted small">Revise el recuadro antes de analizar. Puede volver a trazarlo.</p>}</>}
        {error && <p className="error" role="alert">{error}</p>}

        {analysis === null && <p className="muted">Esta imagen todavía no fue analizada.</p>}
        {changed && analysis?.status === 'done' && <p className="banner">La región seleccionada cambió. El informe anterior corresponde al análisis #{analysis.id}. Vuelva a analizar para obtener el resultado de esta selección.</p>}
        {analysis && !changed && !hidden && <ResultPanel analysis={analysis} model={model} />}
        {analysis && complete && !changed && (
          analysis.reading ? !serverBlinded && <ReadingSummary analysis={analysis} reading={analysis.reading} />
            : user?.role !== 'investigador' && <ReadingForm key={analysis.id} id={analysis.id} blinded={hidden}
              onReveal={hidden && !serverBlinded ? reveal : undefined} onSaved={reading => {
                setAnalysis(current => current?.id === reading.analysis_id ? { ...current, reading } : current)
                window.dispatchEvent(new Event('ecoaudit:reading-saved'))
                if (serverBlinded) void refreshResult(reading.analysis_id)
              }} />
        )}
        {analysis?.reading && serverBlinded && error && <Button variant="secondary" onClick={() => void refreshResult(analysis.id)}>Reintentar consulta del resultado</Button>}
        {analysis && complete && !hidden && !changed && <div className="actions">
          <Button variant="secondary" disabled={exporting} onClick={() => void exportResult(analysis.id, 'pdf')}>
            <Download size={16} aria-hidden="true" /> Descargar PDF · Análisis #{analysis.id}
          </Button>
          <Button variant="secondary" disabled={exporting} onClick={() => void exportResult(analysis.id, 'fhir')}>
            <FileJson size={16} aria-hidden="true" /> Exportar FHIR
          </Button>
        </div>}
        {notice && !changed && <Toast>{notice}</Toast>}

        {complete && !hidden && analysis.has_cam && !changed && (
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
