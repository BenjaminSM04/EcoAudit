// Cliente de la API. El token vive en sessionStorage: se pierde al cerrar la pestaña.

const TOKEN_KEY = 'ecoaudit.token'

export type Role = 'medico' | 'investigador' | 'admin'

export interface User {
  id: number
  email: string
  full_name: string
  role: Role
  is_active: boolean
}

export interface Roi {
  x: number
  y: number
  w: number
  h: number
}

export type AnalysisStatus = 'pending' | 'running' | 'done' | 'failed'
export type Decision = 'probably_benign' | 'indeterminate' | 'suspicious' | 'out_of_domain'

export interface Analysis {
  id: number
  image_id: number
  status: AnalysisStatus
  roi: Roi | null
  model_version_id: number
  probability_raw: number | null
  probability: number | null
  member_spread: number | null
  decision: Decision | null
  shift_score: number | null
  shift_flag: boolean | null
  warnings: string[]
  has_cam: boolean
  error: string | null
  // Veces que se intentó correr el análisis; más de 1 si el worker se interrumpió.
  attempts: number
  created_at: string
  finished_at: string | null
}

export interface CaseImage {
  id: number
  case_id: number
  width: number
  height: number
  source_format: string
  qc_flags: string[]
  duplicate_of_id: number | null
  created_at: string
  analyses: Analysis[]
}

export interface CaseSummary {
  id: number
  patient_ref: string
  notes: string
  created_at: string
  image_count: number
}

export interface CaseDetail {
  id: number
  patient_ref: string
  notes: string
  created_at: string
  images: CaseImage[]
}

export interface ModelCard {
  name: string
  version: string
  demo?: boolean
  architecture: string
  training_data: string
  limitations: string[]
  metrics?: Record<string, unknown>
  input: { size: number; expects_roi: boolean }
  members: unknown[]
  calibration: { temperature: number; source?: string }
  decision: { abstain_low: number; abstain_high: number }
  shift: { threshold: number; description?: string } | null
}

export interface ModelVersion {
  id: number
  name: string
  version: string
  bundle_sha256: string
  is_active: boolean
  card: ModelCard
  created_at: string
}

export type CohortStatus = 'processing' | 'done' | 'failed'
export type CohortSource = 'analyses' | 'batch'

export interface CohortProgress {
  total: number
  done: number
  failed: number
}

export interface CohortSummary {
  id: number
  name: string
  source: CohortSource
  status: CohortStatus
  model: string // "nombre versión"
  created_at: string
  progress: CohortProgress
}

export interface CalibrationBin {
  bin: number
  n: number
  predicted: number
  observed: number
}

export interface CohortMetrics {
  patients: number
  positive: number
  images: number
  auc: number
  ci: [number, number] | null
  brier: number
  ece: number
  bins: CalibrationBin[]
  abstentions: number
  decisions: Record<string, number> // conteo por decisión
  demo: boolean
  model_hash: string
  csv_hash: string
}

export interface CohortDetail extends CohortSummary {
  results: CohortMetrics | null // null mientras processing o si failed
  error: string | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // sin almacenamiento disponible la sesión dura lo que dure la página
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      // Errores de validación: objetos con `msg` (FastAPI) o textos sueltos.
      const parts = body.detail
        .map((d: unknown) => (typeof d === 'string' ? d : ((d as { msg?: string }).msg ?? '')))
        .filter((text: string) => text !== '')
      if (parts.length > 0) return parts.join('. ')
    }
  } catch {
    // respuesta sin JSON
  }
  return `Error ${response.status}`
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  let response: Response
  try {
    response = await fetch(path, { ...init, headers })
  } catch {
    throw new ApiError(0, 'No se pudo conectar con el servidor.')
  }
  if (!response.ok) {
    if (response.status === 401 && token) {
      setToken(null)
      window.dispatchEvent(new Event('ecoaudit:logout'))
    }
    throw new ApiError(response.status, await errorMessage(response))
  }
  return response
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await send(path, init)).json() as Promise<T>
}

// Para respuestas 204: no hay cuerpo que leer.
async function noContent(path: string, init?: RequestInit): Promise<void> {
  await send(path, init)
}

function body(method: string, data: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }
}

// Descarga un archivo autenticado (PDF, CSV…): el token no viaja en un <a href> directo.
export async function downloadFile(path: string, fileName: string): Promise<void> {
  const url = URL.createObjectURL(await api.blob(path))
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30000)
}

export const downloadCohortReport = (id: number) =>
  downloadFile(`/api/cohorts/${id}/report`, `auditoria-${id}.pdf`)

export const downloadCohortItems = (id: number) =>
  downloadFile(`/api/cohorts/${id}/items.csv`, `auditoria-${id}-items.csv`)

export const api = {
  suggest: (id: number) => json<{roi: Roi | null}>(`/api/images/${id}/roi`, { method: 'POST' }),
  async login(email: string, password: string): Promise<void> {
    const form = new URLSearchParams({ username: email, password })
    const result = await json<{ access_token: string }>('/api/auth/login', {
      method: 'POST',
      body: form,
    })
    setToken(result.access_token)
  },
  me: () => json<User>('/api/auth/me'),
  // 204. Los tokens anteriores dejan de valer: quien llama debe cerrar la sesión.
  changePassword: (current_password: string, new_password: string) =>
    noContent('/api/auth/password', body('POST', { current_password, new_password })),

  listCases: () => json<CaseSummary[]>('/api/cases'),
  createCase: (patient_ref: string, notes: string) =>
    json<CaseDetail>('/api/cases', body('POST', { patient_ref, notes })),
  getCase: (id: number) => json<CaseDetail>(`/api/cases/${id}`),
  uploadImage: (caseId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return json<CaseImage>(`/api/cases/${caseId}/images`, { method: 'POST', body: form })
  },
  requestAnalysis: (imageId: number, roi: Roi | null) =>
    json<Analysis>(`/api/images/${imageId}/analyses`, body('POST', { roi })),
  getAnalysis: (id: number) => json<Analysis>(`/api/analyses/${id}`),
  blob: async (path: string) => (await send(path)).blob(),

  listModels: () => json<ModelVersion[]>('/api/models'),
  activateModel: (id: number) =>
    json<ModelVersion>(`/api/models/${id}/activate`, { method: 'POST' }),

  listUsers: () => json<User[]>('/api/users'),
  createUser: (data: { email: string; full_name: string; password: string; role: Role }) =>
    json<User>('/api/users', body('POST', data)),
  updateUser: (id: number, data: { role?: Role; is_active?: boolean }) =>
    json<User>(`/api/users/${id}`, body('PATCH', data)),
  // Solo admin. 204; invalida los tokens de ese usuario.
  resetUserPassword: (id: number, new_password: string) =>
    noContent(`/api/users/${id}/password`, body('POST', { new_password })),

  listCohorts: () => json<CohortSummary[]>('/api/cohorts'),
  getCohort: (id: number) => json<CohortDetail>(`/api/cohorts/${id}`),
  // CSV `analysis_id,label`; el nombre es opcional. Responde 201 con la cohorte ya terminada.
  createCohortFromAnalyses: (file: File, name: string) => {
    const form = new FormData()
    form.append('file', file)
    if (name.trim() !== '') form.append('name', name.trim())
    return json<CohortDetail>('/api/cohorts', { method: 'POST', body: form })
  },
  // Lote nuevo: manifiesto `filename,patient_ref,label` + imágenes. Responde 201 en `processing`.
  createCohortBatch: (name: string, manifest: File, images: File[]) => {
    const form = new FormData()
    form.append('name', name)
    form.append('manifest', manifest)
    for (const image of images) form.append('images', image)
    return json<CohortDetail>('/api/cohorts/batch', { method: 'POST', body: form })
  },
}
