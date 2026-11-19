import type { Page } from '@playwright/test'
import { expect, test } from '../support/test'
import { noisePng } from '../support/images'
import { login, readDownload } from '../support/session'

const DECISIONS = /^(Probablemente benigna|Sospechosa de malignidad|Indeterminada|Fuera de dominio)$/
const DEMO_WARNING = 'Modelo de demostración sin entrenamiento: este resultado no significa nada.'

// Crea un caso por la interfaz y deja la página dentro de su detalle.
async function createCase(page: Page, patientRef: string): Promise<number> {
  await page.getByLabel('Seudónimo del paciente').fill(patientRef)
  await page.getByLabel('Notas (opcional)').fill('Caso creado por la prueba e2e')
  await page.getByRole('button', { name: 'Nuevo caso' }).click()
  await expect(page).toHaveURL(/\/casos\/\d+$/)
  const caseId = Number(page.url().split('/').pop())
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(`Caso #${caseId} · ${patientRef}`)
  return caseId
}

test('médico: caso, imagen, ROI, análisis, mapa de activación y PDF', async ({ page }) => {
  await login(page, 'medico')

  // --- Crear el caso ---
  const patientRef = `E2E-${Date.now()}`
  await createCase(page, patientRef)
  await expect(page.getByText('El modelo activo es de demostración')).toBeVisible()
  await expect(page.getByText('Este caso aún no tiene imágenes.')).toBeVisible()

  // --- Subir una imagen PNG generada en la prueba ---
  await page.locator('input#upload').setInputFiles({
    name: 'ecografia.png',
    mimeType: 'image/png',
    buffer: noisePng(1),
  })
  const picture = page.getByRole('img', { name: /^Ecografía \d+$/ })
  await expect(picture).toBeVisible()
  await expect(page.getByText(/192×192 px · origen PNG/i)).toBeVisible()
  // La imagen se descargó con el token y se decodificó de verdad (no es un ícono roto).
  await expect
    .poll(() => picture.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBe(192)

  // --- Dibujar un ROI arrastrando sobre el visor ---
  const frame = page.locator('.frame')
  const box = await frame.boundingBox()
  expect(box).not.toBeNull()
  const { x, y, width, height } = box!
  await page.mouse.move(x + width * 0.25, y + height * 0.25)
  await page.mouse.down()
  await page.mouse.move(x + width * 0.5, y + height * 0.5, { steps: 6 })
  await page.mouse.move(x + width * 0.7, y + height * 0.7, { steps: 6 })
  await page.mouse.up()

  const roi = page.locator('.roi')
  await expect(roi).toBeVisible()
  const roiBox = await roi.boundingBox()
  // El recuadro cubre aproximadamente el 45 % del ancho y del alto del visor.
  expect(roiBox!.width).toBeGreaterThan(width * 0.4)
  expect(roiBox!.width).toBeLessThan(width * 0.5)
  expect(roiBox!.height).toBeGreaterThan(height * 0.4)
  expect(roiBox!.height).toBeLessThan(height * 0.5)
  await expect(page.getByText('Revise el recuadro antes de analizar.')).toBeVisible()

  // --- Pedir el análisis y esperar el resultado ---
  // El ROI viaja al backend en píxeles de la imagen (192 px), no del visor.
  const analysisRequest = page.waitForRequest(
    (request) => /\/api\/images\/\d+\/analyses$/.test(request.url()) && request.method() === 'POST',
  )
  await page.getByRole('button', { name: 'Analizar el ROI' }).click()
  const sent = (await analysisRequest).postDataJSON() as { roi: { x: number; y: number; w: number; h: number } }
  expect(sent.roi.x).toBeCloseTo(192 * 0.25, -1)
  expect(sent.roi.y).toBeCloseTo(192 * 0.25, -1)
  expect(sent.roi.w).toBeCloseTo(192 * 0.45, -1)
  expect(sent.roi.h).toBeCloseTo(192 * 0.45, -1)

  const result = page.locator('.result')
  await expect(result).toBeVisible({ timeout: 60_000 })
  await expect(result.getByRole('heading', { level: 3 })).toHaveText(DECISIONS)
  await expect(result).toContainText('probabilidad calibrada de malignidad')
  await expect(result).toContainText('ROI marcado')
  await expect(result).toContainText('demo-brillo 0.0.0')
  // Aviso de modelo de demostración dentro del resultado.
  await expect(result.getByText(DEMO_WARNING)).toBeVisible()

  // --- Mapa de activación ---
  const cam = page.locator('img.cam')
  await expect(cam).toBeVisible()
  await expect
    .poll(() => cam.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0)
  // El mapa se superpone exactamente sobre la imagen.
  const camBox = (await cam.boundingBox())!
  const frameBox = (await frame.boundingBox())!
  expect(Math.abs(camBox.x - frameBox.x)).toBeLessThan(2)
  expect(Math.abs(camBox.y - frameBox.y)).toBeLessThan(2)
  expect(Math.abs(camBox.width - frameBox.width)).toBeLessThan(2)
  expect(Math.abs(camBox.height - frameBox.height)).toBeLessThan(2)

  const toggle = page.getByLabel('Mostrar mapa de activación')
  await expect(toggle).toBeChecked()
  await toggle.uncheck()
  await expect(cam).toHaveCount(0)
  await toggle.check()
  await expect(cam).toBeVisible()

  // --- Descargar el PDF del análisis ---
  const pdfButton = page.getByRole('button', { name: /^Descargar PDF · Análisis #\d+$/ })
  const analysisId = (await pdfButton.textContent())!.match(/#(\d+)/)![1]
  const [download] = await Promise.all([page.waitForEvent('download'), pdfButton.click()])
  expect(download.suggestedFilename()).toBe(`analisis-${analysisId}.pdf`)
  const pdf = await readDownload(download)
  expect(pdf.subarray(0, 5).toString('latin1')).toBe('%PDF-')
  expect(pdf.length).toBeGreaterThan(1000)

  // --- Al recargar, el resultado y el ROI vuelven desde el backend ---
  await page.reload()
  await expect(page.locator('.result').getByRole('heading', { level: 3 })).toHaveText(DECISIONS)
  await expect(page.locator('.result')).toContainText('ROI marcado')
  await expect(page.locator('.roi')).toBeVisible()
  await expect(page.locator('img.cam')).toBeVisible()

  // --- Cambiar la región invalida el resultado hasta repetir el análisis ---
  await page.getByRole('button', { name: 'Quitar ROI' }).click()
  await expect(page.getByText('La región seleccionada cambió.')).toBeVisible()
  await expect(page.locator('.result')).toHaveCount(0)
  await expect(page.locator('img.cam')).toHaveCount(0)
  await page.getByRole('button', { name: 'Analizar la imagen completa' }).click()
  await expect(page.locator('.result')).toContainText('imagen completa', { timeout: 60_000 })
  await expect(page.locator('.result').getByRole('heading', { level: 3 })).toHaveText(DECISIONS)
  await expect(page.getByText('La región seleccionada cambió.')).toHaveCount(0)
  // Es otro análisis: el botón del PDF apunta a un número mayor.
  const secondId = (await pdfButton.textContent())!.match(/#(\d+)/)![1]
  expect(Number(secondId)).toBeGreaterThan(Number(analysisId))

  // --- El caso aparece en el listado con su imagen ---
  await page.getByRole('link', { name: '← Casos' }).click()
  const row = page.getByRole('row', { name: new RegExp(patientRef) })
  await expect(row).toBeVisible()
  await expect(row.getByRole('cell').nth(2)).toHaveText('1')

  // La búsqueda por seudónimo filtra la tabla.
  await page.getByLabel('Buscar por seudónimo o número').fill(patientRef.toLowerCase())
  await expect(row).toBeVisible()
  await page.getByLabel('Buscar por seudónimo o número').fill('no-existe-este-seudonimo')
  await expect(page.getByText('Ningún caso coincide con la búsqueda.')).toBeVisible()
})

test('médico: el control de calidad marca duplicados y baja resolución', async ({ page }) => {
  await login(page, 'medico')
  await createCase(page, `QC-${Date.now()}`)

  const uploads = page.locator('input#upload')
  await uploads.setInputFiles({ name: 'original.png', mimeType: 'image/png', buffer: noisePng(7) })
  await expect(page.getByRole('img', { name: /^Ecografía \d+$/ })).toHaveCount(1)
  // La misma imagen otra vez, y una de 64 px (por debajo del mínimo de 128 px).
  await uploads.setInputFiles({ name: 'copia.png', mimeType: 'image/png', buffer: noisePng(7) })
  await expect(page.getByRole('img', { name: /^Ecografía \d+$/ })).toHaveCount(2)
  await uploads.setInputFiles({ name: 'chica.png', mimeType: 'image/png', buffer: noisePng(8, 64) })
  await expect(page.getByRole('img', { name: /^Ecografía \d+$/ })).toHaveCount(3)

  await expect(page.getByText('Imagen idéntica a otra del mismo caso.')).toHaveCount(1)
  await expect(page.getByText('Imagen de baja resolución.')).toHaveCount(1)
})
