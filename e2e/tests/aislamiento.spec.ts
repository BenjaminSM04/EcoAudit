import { expect, test } from '../support/test'
import { login } from '../support/session'

test('un segundo médico no ve el caso del primero', async ({ page, browser, baseURL }) => {
  // Primer médico: crea su caso.
  await login(page, 'medico')
  const patientRef = `AISLADO-${Date.now()}`
  await page.getByLabel('Seudónimo del paciente').fill(patientRef)
  await page.getByRole('button', { name: 'Nuevo caso' }).click()
  await expect(page).toHaveURL(/\/casos\/\d+$/)
  const caseUrl = page.url()
  await expect(page.getByRole('heading', { level: 1 })).toContainText(patientRef)

  // Segundo médico, en un contexto de navegador aparte (sin compartir la sesión).
  const other = await browser.newContext({ baseURL: baseURL ?? undefined, locale: 'es-BO' })
  try {
    const second = await other.newPage()
    await login(second, 'medico2')
    await expect(second.getByRole('heading', { name: 'Casos', level: 1 })).toBeVisible()
    await expect(second.getByText('Cargando…')).toHaveCount(0)
    await expect(second.getByText(patientRef)).toHaveCount(0)
    await expect(second.getByRole('link', { name: /^#\d+$/ })).toHaveCount(0)

    // Ni siquiera con la dirección exacta: el backend responde 404, no 403.
    await second.goto(caseUrl)
    await expect(second.getByText('Caso no encontrado.')).toBeVisible()
    await expect(second.getByText(patientRef)).toHaveCount(0)
  } finally {
    await other.close()
  }

  // El primero sigue viendo su caso.
  await page.goto('/casos')
  await expect(page.getByRole('row', { name: new RegExp(patientRef) })).toBeVisible()
})
