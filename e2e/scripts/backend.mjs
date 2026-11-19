// Prepara un entorno aislado y arranca el backend para las pruebas e2e.
//
// Playwright lo lanza como `webServer` (ver playwright.config.ts). Se ejecuta una sola vez, antes
// de que arranque ningún navegador:
//   1. borra e2e/.tmp y lo recrea (base SQLite y almacenamiento propios, nunca backend/data/);
//   2. con la CLI del backend crea los usuarios de prueba, genera un bundle de demostración y lo
//      registra como activo;
//   3. guarda las contraseñas (aleatorias) en e2e/.tmp/credentials.json;
//   4. arranca uvicorn en el puerto 8001 con worker en línea.
// Las contraseñas no están en el código: cada ejecución genera otras.

import { spawn, spawnSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const E2E_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const BACKEND_DIR = resolve(E2E_DIR, '..', 'backend')
const TMP_DIR = join(E2E_DIR, '.tmp')
const PORT = process.env.E2E_BACKEND_PORT ?? '8001'

// Usuarios de prueba. `medico2` sirve para la prueba de aislamiento. Las pruebas que cambian
// contraseñas o provocan intentos fallidos crean su propio usuario por la API (support/api.ts):
// así el bloqueo por intentos fallidos y los cambios de contraseña no afectan a las demás.
const USERS = [
  { key: 'admin', name: 'Admin E2E', role: 'admin' },
  { key: 'medico', name: 'Medico E2E', role: 'medico' },
  { key: 'medico2', name: 'Medico Dos E2E', role: 'medico' },
  { key: 'investigador', name: 'Investigador E2E', role: 'investigador' },
]

// Intérprete de Python: variable explícita, luego el venv del repositorio y, si no existe (CI),
// el que haya en el PATH.
function findPython() {
  if (process.env.ECOAUDIT_E2E_PYTHON) return process.env.ECOAUDIT_E2E_PYTHON
  for (const candidate of ['.venv/Scripts/python.exe', '.venv/bin/python']) {
    const path = join(BACKEND_DIR, candidate)
    if (existsSync(path)) return path
  }
  return process.platform === 'win32' ? 'python' : 'python3'
}

function sqliteUrl(file) {
  // sqlite:///D:/ruta en Windows; sqlite:////ruta en POSIX (la ruta absoluta ya empieza con «/»).
  return `sqlite:///${file.replaceAll('\\', '/')}`
}

rmSync(TMP_DIR, { recursive: true, force: true })
mkdirSync(TMP_DIR, { recursive: true })

const python = findPython()
const env = {
  ...process.env,
  ECOAUDIT_DATABASE_URL: sqliteUrl(join(TMP_DIR, 'ecoaudit.db')),
  ECOAUDIT_STORAGE_DIR: join(TMP_DIR, 'storage'),
  ECOAUDIT_INLINE_WORKER: 'true',
  PYTHONUTF8: '1',
}

function cli(...args) {
  const result = spawnSync(python, ['-m', 'app.cli', ...args], {
    cwd: BACKEND_DIR,
    env,
    stdio: 'inherit',
  })
  if (result.error || result.status !== 0) {
    console.error(`La CLI del backend falló: python -m app.cli ${args[0]} (código ${result.status}).`)
    if (result.error) console.error(result.error.message)
    process.exit(1)
  }
}

const credentials = {}
for (const { key, name, role } of USERS) {
  const email = `${key}@example.com`
  const password = `Pw-${randomBytes(12).toString('base64url')}`
  credentials[key] = { email, password, name, role }
  cli('create-user', '--email', email, '--name', name, '--role', role, '--password', password)
}
writeFileSync(join(TMP_DIR, 'credentials.json'), JSON.stringify(credentials, null, 2))

const bundle = join(TMP_DIR, 'bundle')
cli('make-demo-bundle', bundle)
cli('register-model', bundle, '--activate')

const server = spawn(
  python,
  ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', PORT, '--no-access-log'],
  { cwd: BACKEND_DIR, env, stdio: 'inherit' },
)
server.on('exit', (code) => process.exit(code ?? 0))
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.kill(signal))
