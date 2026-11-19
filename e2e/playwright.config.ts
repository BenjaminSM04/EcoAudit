import { defineConfig, devices } from '@playwright/test'

// Puertos dedicados a las pruebas: no chocan con el desarrollo normal (8000 y 5173).
const BACKEND_PORT = 8001
const FRONTEND_PORT = 5174
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`

export default defineConfig({
  testDir: './tests',
  outputDir: './test-results',
  // Un solo trabajador: todas las pruebas comparten un backend con SQLite y un mismo modelo.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: FRONTEND_URL,
    locale: 'es-BO',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // Prepara .tmp (borrándolo antes), crea usuarios, registra el modelo de demostración y
      // arranca uvicorn. Ver scripts/backend.mjs.
      command: 'node scripts/backend.mjs',
      url: `${BACKEND_URL}/api/health`,
      env: { E2E_BACKEND_PORT: String(BACKEND_PORT) },
      // Reutilizar un servidor ya levantado dejaría una base con contraseñas de otra ejecución.
      reuseExistingServer: false,
      timeout: 180_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      // Vite con el proxy /api apuntando al backend de pruebas.
      command: `npm run dev -- --host 127.0.0.1 --port ${FRONTEND_PORT} --strictPort`,
      cwd: '../frontend',
      url: FRONTEND_URL,
      env: { ECOAUDIT_API_PROXY: BACKEND_URL },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
})
