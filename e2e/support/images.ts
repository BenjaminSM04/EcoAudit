import { PNG } from 'pngjs'

// Generador pseudoaleatorio determinista (mulberry32): las imágenes de prueba son reproducibles
// y distintas entre sí según la semilla, de modo que el control de calidad no las marca como
// duplicadas.
function mulberry32(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// PNG en escala de grises con ruido gaussiano (media 110, desviación 45) y una mancha oscura
// elíptica que hace las veces de lesión. 192 px: por encima del mínimo de resolución del control
// de calidad (128) y con contraste suficiente (desviación típica >> 8).
export function noisePng(seed: number, size = 192): Buffer {
  const random = mulberry32(seed)
  const gauss = () => Math.sqrt(-2 * Math.log(1 - random())) * Math.cos(2 * Math.PI * random())
  const png = new PNG({ width: size, height: size })
  const cx = size * (0.35 + 0.3 * random())
  const cy = size * (0.35 + 0.3 * random())
  const rx = size * (0.12 + 0.08 * random())
  const ry = size * (0.08 + 0.08 * random())

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const inside = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 < 1
      const value = Math.round(Math.min(255, Math.max(0, (inside ? 50 : 110) + 45 * gauss())))
      const offset = (y * size + x) * 4
      png.data[offset] = value
      png.data[offset + 1] = value
      png.data[offset + 2] = value
      png.data[offset + 3] = 255
    }
  }
  // colorType 0: escala de grises real (sin canales de color).
  return PNG.sync.write(png, { colorType: 0, inputColorType: 6, inputHasAlpha: true })
}
