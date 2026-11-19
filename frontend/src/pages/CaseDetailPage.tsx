import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import type { CaseDetail, ModelVersion } from '../api'
import ImageWorkspace from '../components/ImageWorkspace'
import { dateTime } from '../labels'

export default function CaseDetailPage() {
  const caseId = Number(useParams().caseId)
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [models, setModels] = useState<ModelVersion[]>([])
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api
      .getCase(caseId)
      .then(setDetail)
      .catch((err: Error) => setError(err.message))
    api
      .listModels()
      .then(setModels)
      .catch(() => undefined)
  }, [caseId])

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    const failures: string[] = []
    for (const file of files) {
      try {
        await api.uploadImage(caseId, file)
      } catch (err) {
        failures.push(`${file.name}: ${err instanceof Error ? err.message : 'error'}`)
      }
    }
    if (failures.length > 0) setError(failures.join(' '))
    try {
      setDetail(await api.getCase(caseId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo recargar el caso.')
    }
    setUploading(false)
    if (fileInput.current) fileInput.current.value = ''
  }

  if (detail === null) {
    return (
      <div className="page">
        <Link to="/casos">← Casos</Link>
        {error ? <p className="error">{error}</p> : <p className="muted">Cargando…</p>}
      </div>
    )
  }

  const activeModel = models.find((m) => m.is_active)

  return (
    <div className="page">
      <Link to="/casos">← Casos</Link>
      <h1>
        Caso #{detail.id} · {detail.patient_ref}
      </h1>
      <p className="muted">
        Creado el {dateTime(detail.created_at)}
        {detail.notes && ` · ${detail.notes}`}
      </p>

      {models.length > 0 && !activeModel && (
        <p className="error">No hay un modelo activo; un administrador debe activar uno.</p>
      )}
      {activeModel?.card.demo && (
        <p className="banner">
          El modelo activo es de demostración (sin entrenamiento). Sirve para probar el flujo del
          sistema; sus resultados no tienen ningún significado.
        </p>
      )}

      <div className="card upload">
        <input
          ref={fileInput}
          type="file"
          accept=".png,.jpg,.jpeg,.bmp,.tif,.tiff,.dcm,image/*,application/dicom"
          multiple
          onChange={upload}
          disabled={uploading}
          id="upload"
        />
        <label htmlFor="upload" className="muted small">
          {uploading
            ? 'Subiendo…'
            : 'PNG, JPEG, BMP, TIFF o DICOM sin compresión. Se guardan solo los píxeles: los metadatos se descartan. El texto quemado en la imagen no se elimina.'}
        </label>
      </div>
      {error && <p className="error">{error}</p>}

      {detail.images.length === 0 && <p className="muted">Este caso aún no tiene imágenes.</p>}
      {detail.images.map((image) => (
        <ImageWorkspace key={image.id} image={image} models={models} />
      ))}
    </div>
  )
}
