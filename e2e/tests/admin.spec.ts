import { randomBytes } from 'node:crypto'
import { expect, test } from '../support/test'
import { login, loginWith, logout } from '../support/session'

test.describe('Administrador', () => {
  test('crea un usuario, restablece su contraseña y el usuario entra con la nueva', async ({
    page,
    browser,
    baseURL,
  }) => {
    await login(page, 'admin')
    await page.getByRole('navigation').getByRole('link', { name: 'Usuarios' }).click()
    await expect(page).toHaveURL(/\/usuarios$/)
    await expect(page.getByRole('heading', { name: 'Usuarios', level: 1 })).toBeVisible()

    // --- Crear un usuario ---
    const stamp = Date.now()
    const email = `creado-${stamp}@example.com`
    const fullName = `Creado ${stamp}`
    const initialPassword = `Inicial-${randomBytes(9).toString('base64url')}`
    const resetPassword = `Reinicio-${randomBytes(9).toString('base64url')}`

    await page.getByLabel('Nombre', { exact: true }).fill(fullName)
    await page.getByLabel('Correo').fill(email)
    await page.getByLabel('Contraseña inicial').fill(initialPassword)
    await page.getByLabel('Rol').selectOption({ label: 'Investigador' })
    await page.getByRole('button', { name: 'Crear usuario' }).click()

    const row = page.getByRole('row', { name: new RegExp(email) })
    await expect(row).toBeVisible()
    await expect(row).toContainText('Investigador')
    await expect(row).toContainText('Activo')

    // El usuario recién creado abre sesión con su contraseña inicial (en otro navegador).
    const other = await browser.newContext({ baseURL: baseURL ?? undefined, locale: 'es-BO' })
    const otherPage = await other.newPage()
    await loginWith(otherPage, email, initialPassword, fullName)

    // --- Restablecer su contraseña ---
    await row.getByRole('button', { name: 'Restablecer contraseña' }).click()
    await page.getByLabel(`Nueva contraseña para ${fullName}`).fill(resetPassword)
    await page.getByRole('button', { name: 'Confirmar' }).click()
    await expect(page.getByRole('status')).toContainText(
      `Contraseña de ${fullName} restablecida.`,
    )

    // Su sesión abierta se cerró: la siguiente petición lo devuelve al ingreso.
    await otherPage.getByRole('navigation').getByRole('link', { name: 'Modelos' }).click()
    await expect(otherPage.getByRole('button', { name: 'Ingresar' })).toBeVisible()
    await other.close()

    // --- El usuario creado: la contraseña inicial ya no vale, la nueva sí ---
    await logout(page)
    await page.getByLabel('Correo').fill(email)
    await page.getByLabel('Contraseña', { exact: true }).fill(initialPassword)
    await page.getByRole('button', { name: 'Ingresar' }).click()
    await expect(page.getByRole('alert')).toHaveText('Correo o contraseña incorrectos.')

    await page.getByLabel('Contraseña', { exact: true }).fill(resetPassword)
    await page.getByRole('button', { name: 'Ingresar' }).click()
    await expect(page.locator('.session')).toContainText(`${fullName} · Investigador`)
    // Un investigador entra a la auditoría, no a la administración de usuarios.
    await expect(page).toHaveURL(/\/auditoria$/)
    await expect(page.getByRole('navigation').getByRole('link', { name: 'Usuarios' })).toHaveCount(0)
  })

  test('la página de modelos muestra el modelo activo', async ({ page }) => {
    await login(page, 'admin')
    await page.getByRole('navigation').getByRole('link', { name: 'Modelos' }).click()
    await expect(page).toHaveURL(/\/modelos$/)
    await expect(page.getByRole('heading', { name: 'Modelos', level: 1 })).toBeVisible()

    const model = page.locator('section.model', { hasText: 'demo-brillo' })
    await expect(model).toHaveCount(1)
    await expect(model.getByRole('heading', { level: 2 })).toContainText('demo-brillo')
    await expect(model.getByRole('heading', { level: 2 })).toContainText('0.0.0')
    await expect(model.locator('.pill')).toHaveText('Activo')
    await expect(model.getByText('Modelo de demostración: sin entrenamiento ni validez.')).toBeVisible()
    await expect(model).toContainText('conv-demo · ensamble de 3')
    await expect(model).toContainText('35 % a 65 %')
    // El modelo activo no ofrece el botón de activar.
    await expect(model.getByRole('button', { name: 'Activar' })).toHaveCount(0)
  })

  test('el médico no ve los enlaces Auditoría ni Usuarios', async ({ page }) => {
    await login(page, 'medico')
    const nav = page.getByRole('navigation')
    await expect(nav.getByRole('link', { name: 'Casos' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Modelos' })).toBeVisible()
    await expect(nav.getByRole('link', { name: 'Auditoría' })).toHaveCount(0)
    await expect(nav.getByRole('link', { name: 'Usuarios' })).toHaveCount(0)

    // Tampoco entra escribiendo la dirección: la ruta no existe para su rol.
    for (const path of ['/auditoria', '/usuarios']) {
      await page.goto(path)
      await expect(page).toHaveURL(/\/casos$/)
    }
  })

  test('el administrador sí ve todos los enlaces', async ({ page }) => {
    await login(page, 'admin')
    const nav = page.getByRole('navigation')
    for (const link of ['Casos', 'Auditoría', 'Modelos', 'Usuarios']) {
      await expect(nav.getByRole('link', { name: link })).toBeVisible()
    }
  })
})
