import { useEffect, useState } from 'react'
import { api } from '../api'

// Las imágenes exigen el token, así que no sirven en un <img src> directo:
// se descargan con fetch y se muestran desde una URL de objeto.
export function useBlobUrl(path: string | null): string | null {
  const [loaded, setLoaded] = useState<{ path: string; url: string } | null>(null)

  useEffect(() => {
    if (path === null) return
    let cancelled = false
    let created: string | null = null
    api
      .blob(path)
      .then((blob) => {
        if (cancelled) return
        created = URL.createObjectURL(blob)
        setLoaded({ path, url: created })
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
      if (created) URL.revokeObjectURL(created)
    }
  }, [path])

  return loaded !== null && loaded.path === path ? loaded.url : null
}
