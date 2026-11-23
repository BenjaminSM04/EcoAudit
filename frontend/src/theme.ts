export type Theme = 'claro' | 'oscuro' | 'sistema'

export function savedTheme(): Theme {
  try {
    const value = localStorage.getItem('ecoaudit.theme')
    if (value === 'claro' || value === 'oscuro') return value
  } catch {
    // La preferencia del sistema también funciona sin almacenamiento.
  }
  return 'sistema'
}

export function applyTheme(theme: Theme, systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches) {
  document.documentElement.dataset.theme = theme === 'oscuro' || (theme === 'sistema' && systemDark) ? 'oscuro' : 'claro'
}
