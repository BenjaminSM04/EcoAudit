import { expect, test } from '../support/test'
import { createUser } from '../support/api'
import { credentials } from '../support/credentials'
import { login, logout } from '../support/session'

test.describe('Inicio y cierre de sesión', () => {
  test('credenciales erróneas muestran un error y no dan acceso', async ({ page, request }) => {
    // Usuario propio: los intentos fallidos cuentan para el bloqueo por correo (5 en 15 minutos)
    // y no deben acumularse sobre las cuentas que usan las demás pruebas.
    const { email } = await createUser(request, 'medico', 'erroneo')
    await page.goto('/')
    await page.getByLabel('Correo').fill(email)
    await page.getByLabel('Contraseña', { exact: true }).fill('una-contraseña-equivocada')
    await page.getByRole('button', { name: 'Ingresar' }).click()

    await expect(page.getByRole('alert')).toHaveText('Correo o contraseña incorrectos.')
    await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Salir' })).toHaveCount(0)
  })

  test('credenciales correctas entran y Salir cierra la sesión', async ({ page }) => {
    const { name } = credentials('medico')
    await login(page, 'medico')

    // El médico aterriza en Casos y la barra muestra su nombre y su rol.
    await expect(page).toHaveURL(/\/casos$/)
    await expect(page.getByRole('heading', { name: 'Casos', level: 1 })).toBeVisible()
    await expect(page.locator('.session')).toContainText(`${name} · Médico`)

    await logout(page)
    // El token desaparece y recargar no devuelve la sesión.
    const token = await page.evaluate(() => sessionStorage.getItem('ecoaudit.token'))
    expect(token).toBeNull()
    await page.reload()
    await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible()
  })

  test('sin sesión, una ruta interna muestra el ingreso', async ({ page }) => {
    await page.goto('/casos')
    await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible()
  })
})
