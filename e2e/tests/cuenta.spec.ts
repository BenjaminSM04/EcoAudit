import { randomBytes } from 'node:crypto'
import { expect, test } from '../support/test'
import { createUser } from '../support/api'
import { loginWith, logout } from '../support/session'

test('cambiar la contraseña cierra la sesión y la nueva contraseña funciona', async ({
  page,
  browser,
  baseURL,
  request,
}) => {
  // Usuario creado para esta prueba: cambiarle la contraseña no afecta a las demás.
  const { email, password, name } = await createUser(request, 'medico', 'cuenta')
  const nextPassword = `Nueva-${randomBytes(12).toString('base64url')}`
  await loginWith(page, email, password, name)

  // Una segunda sesión del mismo usuario (otro navegador), abierta antes del cambio.
  const other = await browser.newContext({ baseURL: baseURL ?? undefined, locale: 'es-BO' })
  try {
    const otherPage = await other.newPage()
    await loginWith(otherPage, email, password, name)

    await page.locator('.session').getByRole('link', { name, exact: true }).click()
    await expect(page).toHaveURL(/\/cuenta$/)
    await expect(page.getByRole('heading', { name: 'Mi cuenta', level: 1 })).toBeVisible()
    await expect(page.getByRole('definition').filter({ hasText: email })).toBeVisible()

    const current = page.getByLabel('Contraseña actual')
    const next = page.getByLabel('Nueva contraseña', { exact: true })
    const confirm = page.getByLabel('Confirmar nueva contraseña')
    const submit = page.getByRole('button', { name: 'Cambiar contraseña' })

    // Validaciones de la interfaz: contraseña corta y confirmación distinta.
    await current.fill(password)
    await next.fill('corta')
    await confirm.fill('corta')
    await submit.click()
    await expect(page.getByRole('alert')).toContainText('al menos 10 caracteres')

    await next.fill(nextPassword)
    await confirm.fill(`${nextPassword}-distinta`)
    await submit.click()
    await expect(page.getByRole('alert')).toContainText('La confirmación no coincide')

    // El backend rechaza una contraseña actual equivocada y la sesión sigue abierta.
    await current.fill('contraseña-actual-equivocada')
    await confirm.fill(nextPassword)
    await submit.click()
    await expect(page.getByRole('alert')).toHaveText('La contraseña actual es incorrecta.')
    await expect(page.getByRole('button', { name: 'Salir' })).toBeVisible()

    // Cambio correcto: se cierra la sesión y la pantalla de ingreso avisa.
    await current.fill(password)
    await submit.click()
    await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible()
    await expect(page.getByRole('status')).toHaveText(
      'Contraseña actualizada. Inicie sesión con la nueva contraseña.',
    )
    const token = await page.evaluate(() => sessionStorage.getItem('ecoaudit.token'))
    expect(token).toBeNull()

    // La otra sesión, abierta antes del cambio, deja de valer: su siguiente petición la expulsa.
    await otherPage.getByRole('navigation').getByRole('link', { name: 'Modelos' }).click()
    await expect(otherPage.getByRole('button', { name: 'Ingresar' })).toBeVisible()

    // La nueva contraseña funciona de inmediato (el token nuevo no queda invalidado por el cambio).
    await page.getByLabel('Correo').fill(email)
    await page.getByLabel('Contraseña', { exact: true }).fill(nextPassword)
    await page.getByRole('button', { name: 'Ingresar' }).click()
    await expect(page.getByRole('button', { name: 'Salir' })).toBeVisible()
    // La ruta no cambió al cerrar la sesión: la persona vuelve a «Mi cuenta».
    await expect(page.locator('.session')).toContainText(`${name} · Médico`)
    await expect(page.getByRole('heading', { name: 'Mi cuenta', level: 1 })).toBeVisible()

    // La contraseña anterior ya no sirve.
    await logout(page)
    await page.getByLabel('Correo').fill(email)
    await page.getByLabel('Contraseña', { exact: true }).fill(password)
    await page.getByRole('button', { name: 'Ingresar' }).click()
    await expect(page.getByRole('alert')).toHaveText('Correo o contraseña incorrectos.')
  } finally {
    await other.close()
  }
})
