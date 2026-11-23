// Textos que ve el usuario para los códigos que devuelve el backend.

import type { AnalysisStatus, Birads, CohortProgress, CohortSource, CohortStatus, Decision, Role } from './api'

export const DECISION: Record<Decision, { title: string; detail: string; tone: string }> = {
  probably_benign: {
    title: 'Probablemente benigna',
    detail: 'La probabilidad calibrada está por debajo de la zona de abstención.',
    tone: 'benign',
  },
  suspicious: {
    title: 'Sospechosa de malignidad',
    detail: 'La probabilidad calibrada está por encima de la zona de abstención.',
    tone: 'suspicious',
  },
  indeterminate: {
    title: 'Indeterminada',
    detail: 'La probabilidad cae en la zona de abstención: el modelo no se pronuncia.',
    tone: 'neutral',
  },
  out_of_domain: {
    title: 'Fuera de dominio',
    detail:
      'La imagen difiere de los datos con los que se entrenó el modelo. La probabilidad no es confiable.',
    tone: 'warning',
  },
}

// Orden en que se listan los conteos por decisión (de menor a mayor sospecha).
export const DECISION_ORDER: Decision[] = [
  'probably_benign',
  'indeterminate',
  'suspicious',
  'out_of_domain',
]

// El backend devuelve las decisiones como texto libre: un código desconocido se muestra tal cual.
export function decisionTitle(code: string): string {
  return Object.hasOwn(DECISION, code) ? DECISION[code as Decision].title : code
}

export const COHORT_STATUS: Record<CohortStatus, string> = {
  processing: 'Procesando',
  done: 'Terminada',
  failed: 'Fallida',
}

export const COHORT_SOURCE: Record<CohortSource, string> = {
  analyses: 'Análisis existentes',
  batch: 'Lote nuevo',
}

export const ANALYSIS_STATUS: Record<AnalysisStatus, string> = {
  pending: 'En cola', running: 'Procesando', done: 'Terminado', failed: 'Fallido',
}

export const BIRADS: Record<Birads, string> = {
  '1': 'Negativo', '2': 'Hallazgo benigno', '3': 'Probablemente benigno',
  '4A': 'Sospecha baja', '4B': 'Sospecha moderada', '4C': 'Sospecha alta',
  '5': 'Altamente sugestivo de malignidad', '6': 'Malignidad confirmada por biopsia',
}

// Orden clínico explícito: Object.entries pondría primero las claves numéricas (1, 2, 3, 5, 6, 4A…).
export const BIRADS_ORDER: Birads[] = ['1', '2', '3', '4A', '4B', '4C', '5', '6']

export const AUDIT_ACTION: Record<string, string> = {
  case_reader_assigned: 'Lectura asignada',
  demo_seeded: 'Datos de demostración preparados',
  login: 'Inicio de sesión', login_failed: 'Ingreso fallido', login_blocked: 'Ingreso bloqueado',
  password_changed: 'Contraseña cambiada', password_reset: 'Contraseña restablecida',
  user_created: 'Usuario creado', user_updated: 'Usuario actualizado',
  case_created: 'Caso creado', image_uploaded: 'Imagen cargada',
  analysis_requested: 'Análisis solicitado', clinical_reading_created: 'Lectura clínica registrada',
  analysis_fhir_exported: 'Resultado exportado a FHIR', audit_log_exported: 'Bitácora exportada',
  model_registered: 'Modelo registrado', model_activated: 'Modelo activado',
  cohort_created: 'Cohorte creada', cohort_reanalyzed: 'Reanálisis de cohorte solicitado',
  roi_suggested: 'ROI sugerido',
}

export const WARNING: Record<string, string> = {
  demo_model: 'Modelo de demostración sin entrenamiento: este resultado no significa nada.',
  out_of_domain: 'Imagen fuera del dominio de entrenamiento.',
  shift_not_monitored: 'Este modelo no incluye referencia para detectar cambio de dominio.',
  members_disagree: 'Los modelos del ensamble discrepan entre sí.',
  roi_expected: 'El modelo se entrenó con recortes de la lesión: marque el ROI y repita.',
  roi_not_expected: 'El modelo se entrenó con la imagen completa; se analizó solo el recorte.',
  low_resolution: 'Imagen de baja resolución.',
  low_contrast: 'Imagen con muy poco contraste.',
  color_content: 'La imagen tiene color (Doppler o anotaciones): fuera del uso previsto.',
  exact_duplicate: 'Imagen idéntica a otra del mismo caso.',
  near_duplicate: 'Imagen casi idéntica a otra del mismo caso.',
  exact_duplicate_other_case: 'Imagen idéntica a otra de otro caso suyo.',
  near_duplicate_other_case: 'Imagen casi idéntica a otra de otro caso suyo.',
}

export const ROLE: Record<Role, string> = {
  medico: 'Médico',
  investigador: 'Investigador',
  admin: 'Administrador',
}

export function warningText(code: string): string {
  return WARNING[code] ?? code
}

export function percent(value: number | null, digits = 0): string {
  return value === null ? '—' : `${(value * 100).toLocaleString('es-BO', { minimumFractionDigits: digits, maximumFractionDigits: digits })} %`
}

// Número con tres decimales (AUROC, Brier, ECE…); '—' si no es finito.
export function decimal(value: number | null): string {
  return value !== null && Number.isFinite(value)
    ? value.toLocaleString('es-BO', { minimumFractionDigits: 3, maximumFractionDigits: 3 })
    : '—'
}

// «done/total» y, si los hay, los fallidos. `done` cuenta análisis terminados con éxito.
export function progressText(progress: CohortProgress): string {
  const base = `${progress.done}/${progress.total}`
  if (progress.failed === 0) return base
  return `${base} · ${progress.failed} ${progress.failed === 1 ? 'fallido' : 'fallidos'}`
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString('es-BO', { dateStyle: 'medium', timeStyle: 'short' })
}
