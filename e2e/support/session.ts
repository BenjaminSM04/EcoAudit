import { expect } from '@playwright/test'
import type { Download, Page } from '@playwright/test'
import { credentials } from './credentials'
import type { UserKey } from './credentials'

// Inicia sesión por la interfaz, como lo haría una persona, con un correo y una contraseña dados.
export async function loginWith(
  page: Page,
  email: string,
  password: string,
  name: string,
): Promise<void> {
  await page.goto('/')
  await page.getByLabel('Correo').fill(email)
  await page.getByLabel('Contraseña', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Ingresar' }).click()
  await expect(page.getByRole('button', { name: 'Salir' })).toBeVisible()
  await expect(page.getByRole('link', { name, exact: true })).toBeVisible()
}

// Igual, con uno de los usuarios que prepara scripts/backend.mjs.
export async function login(page: Page, key: UserKey): Promise<void> {
  const { email, password, name } = credentials(key)
  await loginWith(page, email, password, name)
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Salir' }).click()
  await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible()
}

// Lee el PDF/CSV de una descarga de Playwright y lo devuelve como Buffer.
export async function readDownload(download: Download): Promise<Buffer> {
  const stream = await download.createReadStream()
  const chunks: Buffer[] = []
  for await (const chunk of stream) chunks.push(chunk as Buffer)
  return Buffer.concat(chunks)
}
