import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En desarrollo, /api se reenvía al backend (uvicorn en el puerto 8000 por defecto).
// ECOAUDIT_API_PROXY permite apuntar a otro destino; las pruebas e2e lo usan para el 8001.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': process.env.ECOAUDIT_API_PROXY ?? 'http://127.0.0.1:8000' },
  },
})
