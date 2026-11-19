import { expect, test as base } from '@playwright/test'

// `test` de Playwright con una vigilancia automática: cualquier excepción no capturada en la
// página, cualquier `console.error` que no sea un simple fallo HTTP esperado y cualquier
// respuesta 5xx del backend hacen fallar la prueba aunque la interfaz «parezca» bien.
// Los 4xx no se vigilan aquí porque varias pruebas los provocan a propósito (contraseña
// errónea, caso ajeno); cada prueba comprueba el mensaje que corresponde.
export const test = base.extend<{ vigilancia: void }>({
  vigilancia: [
    async ({ page }, use) => {
      const problemas: string[] = []
      page.on('pageerror', (error) => problemas.push(`Excepción en la página: ${error.message}`))
      page.on('console', (message) => {
        if (message.type() !== 'error') return
        // Chrome registra así cada respuesta 4xx/5xx; los 5xx se vigilan abajo.
        if (message.text().startsWith('Failed to load resource')) return
        problemas.push(`console.error: ${message.text()}`)
      })
      page.on('response', (response) => {
        if (response.status() >= 500) {
          problemas.push(`HTTP ${response.status()} en ${response.request().method()} ${response.url()}`)
        }
      })
      await use()
      expect(problemas, 'Errores de la página o del backend durante la prueba').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
