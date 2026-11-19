import { expect, test } from '../support/test'
import type { Page } from '@playwright/test'
import { noisePng } from '../support/images'
import { login, readDownload } from '../support/session'

// Cuatro pacientes, una imagen cada uno: dos benignos (0) y dos malignos (1).
const ROWS = [
  { filename: 'eco-001.png', patient: 'P-E2E-A', label: 0 },
  { filename: 'eco-002.png', patient: 'P-E2E-B', label: 0 },
  { filename: 'eco-003.png', patient: 'P-E2E-C', label: 1 },
  { filename: 'eco-004.png', patient: 'P-E2E-D', label: 1 },
]

function manifestOf(rows: typeof ROWS): string {
  const lines = rows.map((r) => `${r.filename},${r.patient},${r.label}`)
  return ['filename,patient_ref,label', ...lines].join('\n') + '\n'
}

function images(names: string[]) {
  return names.map((name, index) => ({
    name,
    mimeType: 'image/png',
    buffer: noisePng(100 + index),
  }))
}

async function chooseManifest(page: Page, text: string) {
  await page.getByLabel('Manifiesto (CSV)').setInputFiles({
    name: 'manifiesto.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(text, 'utf-8'),
  })
}

test.describe('Auditoría por lote (investigador)', () => {
  test('sube un lote, espera la cohorte y descarga PDF y CSV', async ({ page }) => {
    await login(page, 'investigador')
    // El investigador aterriza en la auditoría.
    await expect(page).toHaveURL(/\/auditoria$/)
    await expect(page.getByRole('heading', { name: 'Auditoría de cohortes', level: 1 })).toBeVisible()

    const name = `Cohorte e2e ${Date.now()}`
    await page.getByLabel('Nombre de la cohorte').fill(name)
    await chooseManifest(page, manifestOf(ROWS))
    await page.getByLabel('Imágenes', { exact: true }).setInputFiles(images(ROWS.map((r) => r.filename)))

    await expect(page.getByText('4 imágenes elegidas.')).toBeVisible()
    await expect(
      page.getByText('Manifiesto consistente: 4 imágenes de 4 pacientes.'),
    ).toBeVisible()
    await page.getByRole('button', { name: 'Crear lote y analizar' }).click()

    // La cohorte nace en proceso y la página consulta hasta que queda terminada.
    await expect(page).toHaveURL(/\/auditoria\/\d+$/)
    const cohortId = page.url().split('/').pop()!
    await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible()
    await expect(page.getByText(/· Terminada$/)).toBeVisible({ timeout: 90_000 })

    // Resultados: AUROC, Brier y ECE con tres decimales.
    await expect(page.getByText('4 imágenes · 4 pacientes · 2 positivos')).toBeVisible()
    for (const metric of ['AUROC', 'Brier', 'ECE']) {
      const tile = page.locator('.metrics > div').filter({ hasText: metric })
      await expect(tile).toBeVisible()
      await expect(tile.locator('strong')).toHaveText(/^\d+[.,]\d{3}$/)
    }
    // Con dos pacientes por clase hay intervalo de confianza para el AUROC.
    await expect(page.getByText(/^IC del 95 % para AUROC · \d+[.,]\d{3} – \d+[.,]\d{3}$/)).toBeVisible()
    await expect(
      page.getByText('Modelo de demostración: sin entrenamiento, estas cifras no significan nada.'),
    ).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Calibración observada' })).toBeVisible()

    // La tabla de decisiones reparte las 4 imágenes entre las categorías.
    await expect(page.getByRole('heading', { name: 'Decisiones' })).toBeVisible()
    const decisionCounts = await page
      .locator('table', { hasText: 'Decisión' })
      .locator('tbody tr td:nth-child(2)')
      .allTextContents()
    expect(decisionCounts.map(Number).reduce((a, b) => a + b, 0)).toBe(ROWS.length)

    // Informe PDF.
    const [pdfDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Descargar informe PDF' }).click(),
    ])
    expect(pdfDownload.suggestedFilename()).toBe(`auditoria-${cohortId}.pdf`)
    const pdf = await readDownload(pdfDownload)
    expect(pdf.subarray(0, 5).toString('latin1')).toBe('%PDF-')
    expect(pdf.length).toBeGreaterThan(1000)

    // CSV de ítems: cabecera del contrato y una fila por imagen, todas terminadas.
    const [csvDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Descargar CSV de ítems' }).click(),
    ])
    expect(csvDownload.suggestedFilename()).toBe(`auditoria-${cohortId}-items.csv`)
    const lines = (await readDownload(csvDownload)).toString('utf-8').trim().split(/\r?\n/)
    expect(lines[0]).toBe('analysis_id,patient_ref,label,probability,decision,status')
    expect(lines).toHaveLength(1 + ROWS.length)
    for (const row of ROWS) {
      expect(lines.some((l) => l.includes(`,${row.patient},${row.label},`))).toBe(true)
    }
    expect(lines.slice(1).every((l) => l.endsWith(',done'))).toBe(true)

    // La cohorte figura en el listado como terminada, con todo analizado.
    await page.getByRole('link', { name: '← Auditoría' }).click()
    const row = page.getByRole('row', { name: new RegExp(name) })
    await expect(row).toContainText('Lote nuevo')
    await expect(row).toContainText('Terminada')
    await expect(row).toContainText('4/4')
  })

  test('el navegador rechaza un manifiesto con un archivo faltante', async ({ page }) => {
    await login(page, 'investigador')

    // Se enviaron peticiones al backend? No debe haber ninguna: la validación es local.
    const batchRequests: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/cohorts/batch')) batchRequests.push(request.url())
    })

    await page.getByLabel('Nombre de la cohorte').fill(`Lote incompleto ${Date.now()}`)
    await chooseManifest(page, manifestOf(ROWS))
    // Solo tres de las cuatro imágenes del manifiesto.
    await page
      .getByLabel('Imágenes', { exact: true })
      .setInputFiles(images(ROWS.slice(0, 3).map((r) => r.filename)))

    const missing = page.getByText('Figuran en el manifiesto pero no se eligió su imagen (1):')
    await expect(missing).toBeVisible()
    await expect(page.getByRole('alert').getByText('eco-004.png')).toBeVisible()
    await expect(page.getByText('Manifiesto consistente')).toHaveCount(0)
    const submit = page.getByRole('button', { name: 'Crear lote y analizar' })
    await expect(submit).toBeDisabled()

    // Una imagen de más (que el manifiesto no menciona) también se detecta.
    await page
      .getByLabel('Imágenes', { exact: true })
      .setInputFiles(images([...ROWS.map((r) => r.filename), 'sobrante.png']))
    await expect(
      page.getByText('Se eligieron pero no figuran en el manifiesto (1):'),
    ).toBeVisible()
    await expect(page.getByRole('alert').getByText('sobrante.png')).toBeVisible()
    await expect(submit).toBeDisabled()

    // Una etiqueta inválida se detecta aunque los archivos coincidan.
    await chooseManifest(page, manifestOf(ROWS).replace('P-E2E-D,1', 'P-E2E-D,2'))
    await page
      .getByLabel('Imágenes', { exact: true })
      .setInputFiles(images(ROWS.map((r) => r.filename)))
    await expect(page.getByText('la etiqueta debe ser 0 (benigna) o 1 (maligna)')).toBeVisible()
    await expect(submit).toBeDisabled()

    expect(batchRequests).toEqual([])
  })
})
