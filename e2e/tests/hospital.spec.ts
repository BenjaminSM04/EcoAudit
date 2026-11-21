import { expect, test } from '../support/test'
import { noisePng } from '../support/images'
import { login, readDownload } from '../support/session'

test('Panel, lectura clínica ciega y exportación FHIR', async ({ page }) => {
  await login(page, 'medico')
  await expect(page).toHaveURL(/\/panel$/)
  await expect(page.getByRole('heading', { name: 'Panel', level: 1 })).toBeVisible()
  const indicators = page.getByRole('region', { name: 'Indicadores' })
  for (const label of ['Casos', 'Imágenes', 'Análisis terminados', 'Tasa de abstención', 'Alertas de dominio', 'Latencia p95']) {
    await expect(indicators.getByText(label, { exact: true })).toBeVisible()
  }
  await expect(page.getByRole('heading', { name: 'Concordancia médico–modelo' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Modelo activo' })).toBeVisible()

  await page.getByRole('navigation').getByRole('link', { name: 'Casos', exact: true }).click()
  await page.getByRole('button', { name: 'Nuevo caso' }).click()
  await page.getByLabel('Seudónimo del paciente').fill(`HOSP-E2E-${Date.now()}`)
  await page.getByRole('button', { name: 'Crear caso' }).click()
  await page.getByLabel('Imágenes', { exact: true }).setInputFiles({
    name: 'hospital.png', mimeType: 'image/png', buffer: noisePng(72),
  })
  await page.getByRole('button', { name: 'Analizar la imagen completa' }).click()
  await expect(page.getByRole('heading', { name: 'Registre su lectura antes de ver el resultado' })).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('probabilidad calibrada de malignidad')).toHaveCount(0)
  await expect(page.getByLabel('Mostrar mapa de activación')).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Descargar PDF|Exportar FHIR/ })).toHaveCount(0)

  await page.getByLabel('BI-RADS').selectOption('4A')
  await page.getByLabel('Notas (opcional)').fill('Lectura de prueba')
  const submitted = page.waitForResponse(response =>
    /\/api\/analyses\/\d+\/reading$/.test(response.url()) && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Registrar lectura y ver resultado' }).click()
  const saved = await submitted
  expect(saved.status()).toBe(201)
  const reading = await saved.json()
  expect(reading).toMatchObject({ birads: '4A', blinded: true, notes: 'Lectura de prueba' })
  await expect(page.getByText('probabilidad calibrada de malignidad')).toBeVisible()
  await expect(page.getByText('BI-RADS 4A', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('BI-RADS 4A', { exact: true })).toBeVisible()

  const [download, response] = await Promise.all([
    page.waitForEvent('download'),
    page.waitForResponse(response => response.url().endsWith(`/analyses/${reading.analysis_id}/fhir`)),
    page.getByRole('button', { name: 'Exportar FHIR' }).click(),
  ])
  expect(response.headers()['content-type']).toContain('application/fhir+json')
  expect(download.suggestedFilename()).toBe(`analisis-${reading.analysis_id}.fhir.json`)
  const contents = (await readDownload(download)).toString('utf8')
  const bundle = JSON.parse(contents)
  expect(bundle).toMatchObject({ resourceType: 'Bundle', type: 'collection' })
  expect(bundle.entry.map((entry: { resource: { resourceType: string } }) => entry.resource.resourceType))
    .toEqual(expect.arrayContaining(['Patient', 'Observation', 'DiagnosticReport']))
  expect(contents).toContain('4A')
  expect(contents).not.toContain('Lectura de prueba')
})
