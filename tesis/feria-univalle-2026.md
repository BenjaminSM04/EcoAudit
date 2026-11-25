# UNIVALLE INVESTIGA 2026 — Preparación

Jueves 26 de noviembre, 08:30–12:30, terraza de la Torre Innovación.
Material: póster (120 × 90 cm), tríptico (Figma), demo de EcoAudit sin internet.

La rúbrica premia sobre todo **rigor metodológico (20)** y **evidencia y análisis (20)**. Tu
estudio es fuerte justo ahí: un control emparejado, un protocolo fijado antes de evaluar y
estadística corregida. Cada minuto debe mostrar *cómo* lo validaste, no solo *qué* hiciste.

---

## 1. Guion para el jurado (5 minutos)

**0:00–0:45 · Problema (C1).**
"Un modelo de IA que clasifica ecografías mamarias puede funcionar bien en el hospital donde se
entrenó y fallar en otro, porque cambian el equipo y el protocolo. Eso se llama cambio de dominio.
La adaptación de dominio no supervisada promete corregirlo sin etiquetas nuevas. Pero casi todos
los estudios la comparan con un modelo que no siguió entrenando. Así no se sabe si la mejora viene
de adaptar o de entrenar más."

**0:45–1:00 · Objetivo.**
"Mi objetivo fue medir si DANN, CORAL y MMD mejoran la clasificación benigno/maligno al pasar de
Curated BUSI, de Egipto, a BUS-BRA, de Brasil, más allá de simplemente seguir entrenando."

**1:00–2:15 · Metodología (C2), señalando el póster.**
- "Usé dos conjuntos públicos: 358 imágenes depuradas de origen y 1064 pacientes con biopsia de
  destino. Las particiones son por paciente, para que no haya fuga."
- "Entrené ResNet-18 y EfficientNet-B0 con 5 semillas: 160 variantes en total. El protocolo quedó
  fijado antes de mirar la prueba."
- "La clave es el **control emparejado**: cada modelo adaptado se compara con uno que recibe
  exactamente las mismas 225 actualizaciones, la misma semilla y la misma regla de selección. Lo
  único que cambia es la adaptación."
- "Medí AUROC por paciente con intervalos bootstrap de 5000 réplicas, DeLong y corrección de Holm
  por comparaciones múltiples."

**2:15–3:30 · Resultados (C4), señalando las cifras.**
- "El control emparejado llegó a 0.769 de AUROC."
- "Las seis comparaciones adaptación − control quedaron entre −0.018 y +0.009. **Ninguna fue
  significativa.**"
- "De la ganancia aparente de DANN y CORAL, unos 0.03, **0.026 se explican solo por entrenar
  más**."
- "Un dato que sorprende: la forma de la máscara sola, sin mirar la imagen, da 0.917, más que
  cualquier modelo de imagen. Hay que reportar esa referencia."

**3:30–4:30 · Aporte y demo (C3, C5, C6).**
"Convertí este hallazgo en un sistema, EcoAudit. Si no podemos garantizar que el modelo se
adapte, el software tiene que **medir y avisar**." (Demo de 40 s; ver sección 3.)

**4:30–5:00 · Conclusión y limitación.**
"La adaptación no superó al control emparejado. Propongo que estos estudios incluyan siempre ese
control. La limitación principal es que es un reanálisis de una cohorte ya expuesta: hace falta
una cohorte externa nueva antes de cualquier uso clínico."

---

## 2. Versión extendida para el stand (15 minutos)

| Sección | Tiempo | Qué decir / mostrar |
|---|---|---|
| Introducción | 2 min | Problema del cambio de dominio, por qué importa en hospitales bolivianos (equipos distintos a los de los conjuntos públicos), objetivo. |
| Metodología | 3 min | Datos y particiones por paciente, 160 variantes, control emparejado (dibuja con la mano: "mismo entrenamiento, una sola diferencia"), estadística. Menciona el protocolo bloqueado: los hashes de las imágenes de prueba y el bloqueo de inferencia. |
| Resultados | 7 min | Figura 1 del póster (bosque de diferencias centradas en 0), las 5 cifras clave, recorte con máscara (+0.095, p de Holm = 1.7×10⁻⁵, pero la máscara sola da 0.917), ajuste fino con 20 % de etiquetas (0.822; usa etiquetas, no es comparable). **Demo de 3 min** de EcoAudit. |
| Discusión | 3 min | Qué significa (la mejora venía de entrenar más), respuesta al objetivo (no supera), limitación principal (cohorte ya expuesta), trabajo futuro (cohorte externa, piloto con aval ético). |

---

## 3. Demo de EcoAudit

**Mensaje único:** "El sistema no promete acertar siempre: dice cuándo no confiar."

Recorrido de 40 s (jurado) o de 3 min (visitantes), con la cuenta `medico1@ecoaudit.test`:
1. **Panel**: "Aquí el hospital ve la actividad, la tasa de abstención, las alertas de dominio y
   la latencia."
2. **Casos → caso → cargar** una imagen de `D:\ecoaudit-feria\imagenes-demo` (BUS-BRA, conjunto
   público).
3. **Lectura ciega**: elige un BI-RADS *antes* de ver el resultado. "Así medimos la concordancia
   médico–modelo sin sesgo; el servidor oculta el resultado hasta que el médico registra su
   lectura."
4. **Resultado**: medidor de probabilidad calibrada, zona de abstención y alerta de dominio. "Si la
   imagen se parece poco a los datos de entrenamiento, el sistema lo dice."
5. Cierre (solo en la versión larga): **Exportar FHIR** ("así llega a la historia clínica") y el
   **Panel** con la concordancia entre dos médicos (kappa).

**Cómo levantarla (sin Docker ni internet):** ejecuta
`powershell -ExecutionPolicy Bypass -File D:\ecoaudit-feria\iniciar-demo.ps1`. Abre
`http://localhost:8080`; las cuentas están en `D:\ecoaudit-feria\credenciales.txt`. La demo usa
su propia base de datos (`D:\ecoaudit-feria\datos`) y el **modelo real del estudio**
(ResNet-18, control emparejado, 5 semillas).

**Imágenes de ejemplo** (`D:\ecoaudit-feria\imagenes-demo`, BUS-BRA público). Resultado
verificado el 25/11:

| Archivo | Resultado del sistema | Qué contar |
|---|---|---|
| `1-benigna_…` (BI-RADS 2) | Probablemente benigno · 0.25 | El caso fácil. |
| `2-sospechosa_…` (BI-RADS 5) | Sospechoso · 0.96 | Coincide con la biopsia. |
| `3-alerta-dominio_…` (BI-RADS 2) | **Fuera de dominio** | "Aquí el sistema no da un veredicto: avisa que esta imagen se parece poco a los datos con que se entrenó. Es justo lo que enseña el estudio." |

**Antes del jueves:**
- [x] Modelo real registrado y probado con las imágenes de ejemplo.
- [ ] Ensayar con el portátil **sin Wi-Fi**. La interfaz usa la fuente Inter de Google; sin
      internet cae a la fuente del sistema y sigue funcionando.
- [ ] Grabar un **video de respaldo** de 60 s de la demo (Win + Alt + R en la Xbox Game Bar), por
      si falla el equipo.
- [ ] Dejar la demo abierta en `http://localhost:8080` con la sesión iniciada, el portátil
      enchufado y el modo de suspensión desactivado.

---

## 4. Preguntas probables del jurado

**Metodología**
- *¿Por qué un control emparejado y no el modelo base?* — Porque el modelo adaptado recibe 225
  actualizaciones más. Sin igualarlas, la mejora mezcla dos efectos. Medí que 0.026 de unos 0.03
  de ganancia aparente venía solo de entrenar más.
- *¿Por qué AUROC por paciente y no por imagen?* — Hay pacientes con varias imágenes. Por imagen se
  infla la muestra y se subestima la incertidumbre. El bootstrap remuestrea pacientes.
- *¿Por qué Holm?* — Hice 6 comparaciones primarias. Sin corrección, alguna saldría
  "significativa" por azar.
- *¿Por qué 5 semillas?* — Las redes varían según la inicialización. Reporto el ensamble y cada
  semilla para mostrar esa variación.
- *¿Por qué esos dos conjuntos?* — Son públicos, de dos países y equipos distintos. BUS-BRA tiene
  confirmación por biopsia y permite partir por paciente. De BUSI usé la versión depurada, porque
  la original tiene duplicados que inflan las métricas.
- *¿Cómo evitaste sobreajustar a la prueba?* — El protocolo quedó fijado antes de evaluar, con los
  hashes de las imágenes de prueba registrados y bloqueo de inferencia.

**Resultados y limitaciones**
- *¿Entonces la adaptación no sirve?* — En este par de conjuntos y con estos métodos no superó al
  control emparejado. No digo que nunca sirva: digo que hay que medirla contra el control
  correcto.
- *¿Qué significa que la máscara sola dé 0.917?* — Que la forma de la lesión anotada ya separa muy
  bien benigno de maligno. Si un modelo usa la máscara, parte de su acierto viene de la anotación,
  no de la imagen. Por eso la propongo como referencia obligatoria.
- *¿Cuál es la principal limitación?* — La cohorte de prueba ya se había usado: es un reanálisis y
  los resultados son descriptivos. Falta una cohorte externa nueva, evaluada una sola vez.
- *¿Por qué 0.769 es "bueno" o "malo"?* — Es moderado. El punto no es el valor absoluto, sino que
  la adaptación no lo mejoró frente al control justo.

**Sistema y aplicación social**
- *¿Esto ya se puede usar en un hospital?* — No. Es un prototipo de investigación y no es un
  dispositivo médico. Antes hacen falta una validación externa, un piloto con aval ético y
  revisión regulatoria (AGEMED).
- *¿Cómo protege los datos?* — Las imágenes se re-codifican y se descartan los metadatos.
  El paciente se identifica con un seudónimo, el acceso es por roles y hay una bitácora de
  acciones. En la investigación solo usé datos públicos anonimizados.
- *¿Cómo se integra con el hospital?* — Recibe estudios del PACS o del ecógrafo por DICOMweb y
  exporta resultados en HL7 FHIR para la historia clínica.
- *¿Por qué marca "fuera de dominio" una imagen benigna de BUS-BRA?* — Porque BUS-BRA es un
  dominio distinto al de entrenamiento: el aviso no dice que la lesión sea maligna, dice que el
  modelo no vio imágenes parecidas. El umbral actual marca cerca del 70 % de BUS-BRA; calibrarlo
  con una cohorte local es parte del trabajo futuro.
- *¿Cómo sabe el sistema que no debe confiar?* — Mide la distancia de la imagen a los datos de
  entrenamiento (cambio de dominio) y tiene una zona de abstención en la probabilidad calibrada.
- *¿Cómo lo validaste como software?* — Con 123 pruebas automáticas, 92 % de cobertura, 16 flujos
  de extremo a extremo en navegador y una prueba de carga con 10 usuarios sin errores. La
  documentación sigue ISO/IEC 25010.

---

## 5. Lista para el stand

- [ ] Póster ploteado de 120 × 90 cm, con su soporte o panel.
- [ ] Trípticos impresos (Figma → exportar PDF → imprimir a doble cara, volteo por el borde corto,
      unos 30 ejemplares). Escanea los QR impresos para verificarlos.
- [ ] Alargador de corriente y cargador del portátil.
- [ ] Portátil con la demo probada sin internet y video de respaldo.
- [ ] Tela lisa de fondo (granate o blanca), mantel y un letrero con el nombre del proyecto y el
      tuyo.
- [ ] Globos o cintas en granate y blanco (colores del póster), sin tapar el póster.
- [ ] Opcional: dulces para los visitantes.
- [ ] Ensaya dos veces con cronómetro: 5 min para el jurado y 15 min completos.
