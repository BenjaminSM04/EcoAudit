import { randomBytes } from 'node:crypto'
import { expect } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { credentials } from './credentials'
import type { Credential } from './credentials'

// Crea un usuario nuevo con la API (como administrador) y devuelve sus credenciales.
// Sirve para las pruebas que cambian contraseñas o provocan intentos fallidos: cada ejecución
// usa un usuario propio y no depende de que otra prueba lo haya dejado intacto.
export async function createUser(
  request: APIRequestContext,
  role: 'medico' | 'investigador',
  prefix: string,
): Promise<Credential> {
  const admin = credentials('admin')
  const login = await request.post('/api/auth/login', {
    form: { username: admin.email, password: admin.password },
  })
  expect(login.ok()).toBe(true)
  const { access_token } = (await login.json()) as { access_token: string }

  const suffix = `${Date.now()}-${randomBytes(3).toString('hex')}`
  const created: Credential = {
    email: `${prefix}-${suffix}@example.com`,
    password: `Pw-${randomBytes(12).toString('base64url')}`,
    name: `${prefix} ${suffix}`,
    role,
  }
  const response = await request.post('/api/users', {
    headers: { Authorization: `Bearer ${access_token}` },
    data: { email: created.email, full_name: created.name, password: created.password, role },
  })
  expect(response.status()).toBe(201)
  return created
}
