import { expect, test } from '../support/test'
import { credentials } from '../support/credentials'
import { noisePng } from '../support/images'
import { login, logout } from '../support/session'

test('el administrador asigna una segunda lectura y consulta la concordancia', async ({ page }) => {
  const reference = `PAC-DOBLE-${Date.now()}`
  await login(page, 'medico')
  await page.getByRole('navigation').getByRole('link', { name: 'Casos', exact: true }).click()
  await page.getByRole('button', { name: 'Nuevo caso' }).click()
  await page.getByLabel('Seudónimo del paciente').fill(reference)
  await page.getByRole('button', { name: 'Crear caso' }).click()
  await expect(page).toHaveURL(/\/casos\/\d+$/)
  const casePath = new URL(page.url()).pathname
  const caseId = casePath.split('/').at(-1)
  await page.getByLabel('Imágenes', { exact: true }).setInputFiles({
    name: 'lectura.png', mimeType: 'image/png', buffer: noisePng(34),
  })
  const analyze = page.getByRole('button', { name: 'Analizar la imagen completa' })
  const read = page.getByRole('button', { name: 'Registrar lectura y ver resultado' })
  await analyze.click()
  await page.getByLabel('BI-RADS').selectOption('4A')
  const firstReading = page.waitForResponse(response =>
    /\/analyses\/\d+\/reading$/.test(response.url()) && response.request().method() === 'POST',
  )
  await read.click()
  const firstResponse = await firstReading
  expect(firstResponse.status()).toBe(201)
  const analysisId = (await firstResponse.json()).analysis_id
  await expect(page.getByText('BI-RADS 4A', { exact: true })).toBeVisible()

  await analyze.click()
  await expect(read).toBeVisible()
  await logout(page)

  await login(page, 'admin')
  await page.goto(casePath)
  const secondDoctor = credentials('medico2').name
  const option = page.getByLabel('Segundo médico').getByRole('option', { name: new RegExp(secondDoctor) })
  await expect(option).toBeAttached()
  await page.getByLabel('Segundo médico').selectOption(await option.getAttribute('value') ?? '')
  const assignment = page.waitForResponse(response =>
    response.url().endsWith(`/api/cases/${caseId}/readers`) && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Asignar lectura' }).click()
  expect((await assignment).status()).toBe(201)
  await expect(page.getByText('Médico asignado al caso.')).toBeVisible()
  await logout(page)

  await login(page, 'medico2')
  const pendingLink = page.getByRole('navigation').getByRole('link', { name: /Pendientes/ })
  await expect(pendingLink.locator('.count')).toHaveText('2')
  await pendingLink.click()
  const pendingRow = page.getByRole('row').filter({ has: page.getByRole('link', { name: `Leer análisis #${analysisId}`, exact: true }) })
  await expect(pendingRow).toContainText(reference)
  await pendingRow.getByRole('link').click()
  await expect(page).toHaveURL(new RegExp(`${casePath}\\?analisis=${analysisId}$`))
  await expect(page.getByLabel('Análisis de la imagen')).toHaveValue(String(analysisId))
  await expect(page.getByText('Lectura asignada. Puede consultar las imágenes')).toBeVisible()
  await expect(page.getByLabel('Imágenes', { exact: true })).toHaveCount(0)
  await expect(analyze).toHaveCount(0)
  await expect(page.getByText('probabilidad calibrada de malignidad')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Ver resultado sin registrar lectura' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Exportar FHIR' })).toHaveCount(0)
  await page.getByLabel('BI-RADS').selectOption('4A')
  const secondReading = page.waitForResponse(response =>
    response.url().endsWith(`/analyses/${analysisId}/reading`) && response.request().method() === 'POST',
  )
  await read.click()
  const saved = await secondReading
  expect(saved.status()).toBe(201)
  expect(await saved.json()).toMatchObject({ analysis_id: analysisId, birads: '4A', blinded: true })
  await expect(page.getByText('probabilidad calibrada de malignidad')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Exportar FHIR' })).toBeVisible()
  await expect(pendingLink.locator('.count')).toHaveText('1')
  await pendingLink.click()
  await expect(pendingRow).toHaveCount(0)
  await logout(page)

  await login(page, 'admin')
  await expect(page.getByRole('heading', { name: 'Concordancia entre lectores' })).toBeVisible()
  const table = page.getByRole('region', { name: 'Concordancia por par de médicos' }).getByRole('table')
  const pair = table.getByRole('row').filter({ hasText: secondDoctor })
  await expect(pair).toContainText(credentials('medico').name)
  await expect(pair.getByRole('cell').first()).toHaveText('1')
  await expect(pair).toContainText(/100,0\s?%/)
})

test('la apariencia persiste y sigue la preferencia del sistema', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await login(page, 'admin')
  const theme = page.getByLabel('Apariencia')
  const root = page.locator('html')
  await expect(theme).toHaveValue('sistema')
  await expect(root).toHaveAttribute('data-theme', 'claro')
  await theme.selectOption('oscuro')
  await expect(root).toHaveAttribute('data-theme', 'oscuro')
  await page.reload()
  await expect(theme).toHaveValue('oscuro')
  await expect(root).toHaveAttribute('data-theme', 'oscuro')
  await expect(page.locator('.stat-card .stat-label').first()).toBeVisible()
  const contrast = await page.evaluate(() => {
    const pairs = [['.topbar select', '.topbar select'], ['h1', 'html'], ['.stat-card .stat-label', '.stat-card'], ['.disclaimer', '.disclaimer']]
    const luminance = (color: string) => {
      const components = color.match(/\d+/g)!.slice(0, 3).map(channel => {
        const value = Number(channel) / 255
        return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4
      })
      return .2126 * components[0] + .7152 * components[1] + .0722 * components[2]
    }
    return pairs.map(([text, surface]) => {
      const values = [
        luminance(getComputedStyle(document.querySelector(text)!).color),
        luminance(getComputedStyle(document.querySelector(surface)!).backgroundColor),
      ].sort((a, b) => b - a)
      return (values[0] + .05) / (values[1] + .05)
    })
  })
  expect(Math.min(...contrast)).toBeGreaterThanOrEqual(4.5)
  await theme.selectOption('claro')
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(root).toHaveAttribute('data-theme', 'claro')
  await theme.selectOption('sistema')
  await expect(root).toHaveAttribute('data-theme', 'oscuro')
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(root).toHaveAttribute('data-theme', 'claro')
})
