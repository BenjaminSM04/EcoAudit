import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Las contraseñas las genera scripts/backend.mjs en cada ejecución y las deja en
// e2e/.tmp/credentials.json (ignorado por git). Aquí solo se leen.
export type UserKey = 'admin' | 'medico' | 'medico2' | 'investigador'

export interface Credential {
  email: string
  password: string
  name: string
  role: 'admin' | 'medico' | 'investigador'
}

const FILE = join(dirname(fileURLToPath(import.meta.url)), '..', '.tmp', 'credentials.json')

export function credentials(key: UserKey): Credential {
  const all = JSON.parse(readFileSync(FILE, 'utf8')) as Record<UserKey, Credential>
  return all[key]
}
