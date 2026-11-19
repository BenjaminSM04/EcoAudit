// Textos que ve el usuario para los códigos que devuelve el backend.

import type { Decision, Role } from './api'

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
  return value === null ? '—' : `${(value * 100).toFixed(digits)} %`
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString('es-BO', { dateStyle: 'medium', timeStyle: 'short' })
}
