import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import type { CaseDetail, ModelVersion } from '../api'
import ImageWorkspace from '../components/ImageWorkspace'
import { ImagePlus } from 'lucide-react'
import { dateTime } from '../labels'
import { useBlobUrl } from '../components/useBlobUrl'
import { EmptyState, Skeleton } from '../components/ui'
import CaseReaders from '../components/CaseReaders'

export default function CaseDetailPage() {
  const caseId = Number(useParams().caseId)
  const [params] = useSearchParams()
  const target = Number(params.get('analisis'))
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [models, setModels] = useState<ModelVersion[]>([])
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
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
        const image = await api.uploadImage(caseId, file)
        setSelected(image.id)
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
        {error ? <p className="error" role="alert">{error}</p> : <Skeleton />}
      </div>
    )
  }

  const activeModel = models.find((m) => m.is_active)
  const activeImage = selected ?? detail.images.find(image => image.analyses.some(a => a.id === target))?.id ?? detail.images[0]?.id

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

      {detail.can_manage && models.length > 0 && !activeModel && (
        <p className="error" role="alert">No hay un modelo activo; un administrador debe activar uno.</p>
      )}
      {detail.can_manage && activeModel?.card.demo && (
        <p className="banner">
          El modelo activo es de demostración (sin entrenamiento). Sirve para probar el flujo del
          sistema; sus resultados no tienen ningún significado.
        </p>
      )}

      {detail.can_manage ? <><CaseReaders caseId={caseId} /><div className="card upload">
        <label htmlFor="upload"><ImagePlus size={20} aria-hidden="true" /> Imágenes</label>
        <input
          ref={fileInput}
          type="file"
          accept=".png,.jpg,.jpeg,.bmp,.tif,.tiff,.dcm,image/*,application/dicom"
          multiple
          onChange={upload}
          disabled={uploading}
          id="upload"
          aria-describedby="upload-help"
        />
        <p id="upload-help" className="muted small" role={uploading ? 'status' : undefined}>
          {uploading
            ? 'Subiendo…'
            : 'PNG, JPEG, BMP, TIFF o DICOM sin compresión. Se guardan solo los píxeles: los metadatos se descartan. El texto quemado en la imagen no se elimina.'}
        </p>
      </div></> : <p className="banner">Lectura asignada. Puede consultar las imágenes y registrar su lectura clínica.</p>}
      {error && <p className="error" role="alert">{error}</p>}

      {detail.images.length === 0 && <EmptyState>Este caso aún no tiene imágenes.</EmptyState>}
      {detail.images.length > 0 && <section aria-label="Galería de ecografías" className="card page">
        <h2>Ecografías <span className="count">{detail.images.length}</span></h2>
        <div className="thumbnails">{detail.images.map(image => <Thumbnail key={image.id}
          id={image.id} active={image.id === activeImage} onSelect={() => setSelected(image.id)} />)}</div>
      </section>}
      {detail.images.map(image => <div key={image.id} hidden={image.id !== activeImage}>
        <ImageWorkspace image={image} models={models} target={target} canManage={detail.can_manage} />
      </div>)}
    </div>
  )
}

function Thumbnail({ id, active, onSelect }: { id: number; active: boolean; onSelect: () => void }) {
  const url = useBlobUrl(`/api/images/${id}/file`)
  return <button type="button" className="thumbnail" aria-pressed={active} onClick={onSelect}>
    {url ? <img src={url} alt="" /> : <span className="thumbnail-placeholder" aria-hidden="true" />}
    <span>Imagen #{id}</span>
  </button>
}
