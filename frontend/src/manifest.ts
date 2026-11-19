// Validación barata, en el navegador, del manifiesto de un lote de imágenes.
// El backend vuelve a validar todo: esto solo evita subir cientos de archivos para descubrir
// una errata evidente.

export const MANIFEST_HEADER = 'filename,patient_ref,label'
export const MAX_BATCH_IMAGES = 1000

export const MANIFEST_EXAMPLE = `${MANIFEST_HEADER}
img001.png,P-0001,0
img002.png,P-0001,0
img003.png,P-0002,1`

// CSV según RFC 4180: campos entre comillas, comillas dobles escapadas y saltos de línea \n o \r\n.
// Se descartan las líneas totalmente vacías y la marca BOM inicial.
export function parseCsv(text: string): string[][] {
  const source = text.replace(/^﻿/, '')
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false

  for (let i = 0; i < source.length; i++) {
    const char = source[i]
    if (quoted) {
      if (char !== '"') field += char
      else if (source[i + 1] === '"') {
        field += '"'
        i++
      } else quoted = false
    } else if (char === '"' && field === '') {
      quoted = true
    } else if (char === ',') {
      row.push(field)
      field = ''
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && source[i + 1] === '\n') i++
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else {
      field += char
    }
  }
  if (field !== '' || row.length > 0) {
    row.push(field)
    rows.push(row)
  }
  return rows.filter((r) => !(r.length === 1 && r[0].trim() === ''))
}

export interface ManifestCheck {
  // Errores de formato (cabecera, columnas, etiquetas, nombres repetidos).
  problems: string[]
  // Nombres que figuran en el manifiesto pero no entre los archivos elegidos.
  missing: string[]
  // Archivos elegidos que no figuran en el manifiesto.
  extra: string[]
  // Filas de datos y seudónimos distintos que declara el manifiesto.
  images: number
  patients: number
  // true si se comparó contra archivos elegidos.
  compared: boolean
  // true solo si no hay nada que corregir y se pudo comparar.
  ok: boolean
}

// `fileNames` es null mientras todavía no se eligieron imágenes: entonces solo se revisa el formato.
export function checkManifest(text: string, fileNames: string[] | null): ManifestCheck {
  const result: ManifestCheck = {
    problems: [],
    missing: [],
    extra: [],
    images: 0,
    patients: 0,
    compared: false,
    ok: false,
  }

  const rows = parseCsv(text)
  if (rows.length === 0) {
    result.problems.push('El manifiesto está vacío.')
    return result
  }

  const header = rows[0].map((cell) => cell.trim()).join(',')
  if (header !== MANIFEST_HEADER) {
    result.problems.push(
      `La cabecera debe ser «${MANIFEST_HEADER}»; el archivo empieza con «${header}».`,
    )
    return result
  }

  const names: string[] = []
  const firstRow = new Map<string, number>()
  const patients = new Set<string>()

  rows.slice(1).forEach((cells, index) => {
    const n = index + 1 // fila de datos, sin contar la cabecera
    if (cells.length !== 3) {
      result.problems.push(`Fila ${n}: se esperaban 3 columnas y hay ${cells.length}.`)
      return
    }
    const [filename, patientRef, label] = cells.map((cell) => cell.trim())
    if (filename === '') result.problems.push(`Fila ${n}: falta el nombre del archivo.`)
    if (patientRef === '') result.problems.push(`Fila ${n}: falta el seudónimo del paciente.`)
    if (label !== '0' && label !== '1') {
      result.problems.push(`Fila ${n}: la etiqueta debe ser 0 (benigna) o 1 (maligna); se leyó «${label}».`)
    }
    if (filename !== '') {
      const previous = firstRow.get(filename)
      if (previous !== undefined) {
        result.problems.push(`Fila ${n}: «${filename}» ya figura en la fila ${previous}.`)
      } else {
        firstRow.set(filename, n)
        names.push(filename)
      }
    }
    if (patientRef !== '') patients.add(patientRef)
  })

  if (rows.length === 1) result.problems.push('El manifiesto no tiene filas de datos.')
  result.images = rows.length - 1
  result.patients = patients.size

  if (fileNames !== null) {
    const chosen = new Set(fileNames)
    result.compared = true
    result.missing = names.filter((name) => !chosen.has(name))
    result.extra = fileNames.filter((name) => !firstRow.has(name))
  }

  result.ok =
    result.compared &&
    result.problems.length === 0 &&
    result.missing.length === 0 &&
    result.extra.length === 0
  return result
}
