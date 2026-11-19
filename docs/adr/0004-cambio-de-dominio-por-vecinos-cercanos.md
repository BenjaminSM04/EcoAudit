# ADR 0004: el cambio de dominio se mide con vecinos más cercanos

**Estado:** aceptada. Reemplaza la distancia de Mahalanobis de la primera implementación.

## Contexto

El sistema debe avisar cuando una imagen se aleja de los datos con los que se entrenó el modelo.
La primera versión usaba la distancia de Mahalanobis sobre el embedding (512 dimensiones en
ResNet-18). Al verificarla con el ensamble del estudio no detectaba nada.

## Evidencia

Medido con el ensamble ResNet-18 `source_only_matched`, usando solo la validación de origen
(57 imágenes) y 200 imágenes del split de adaptación de BUS-BRA. La cohorte de prueba histórica
no se usó.

| Detector | AUROC origen vs. BUS-BRA | BUS-BRA marcadas | Imágenes sintéticas marcadas (de 5) |
|---|---|---|---|
| Mahalanobis con PCA (8 a 64 componentes) | 0,34 a 0,38 | 0 % | 0 a 1 |
| Distancia coseno al 5.º vecino | 0,98 | 72 % | 5 |

Las sintéticas eran ruido, degradado, negro, blanco y tablero. El umbral fue en todos los casos
el percentil 99 de la validación de origen. La causa del fallo de Mahalanobis: hay 229 imágenes
de entrenamiento para 512 dimensiones, así que la covarianza no se puede estimar.

## Decisión

El puntaje es la distancia coseno del embedding a su k-ésimo vecino más cercano (k = 5) entre los
embeddings de las imágenes de entrenamiento, promediada entre los miembros del ensamble. El
bundle guarda esos embeddings en `shift_reference.npz`.

## Consecuencias

- Sin supuestos de distribución ni matrices que invertir; funciona con pocos datos.
- El bundle crece con el conjunto de entrenamiento (229 × 512 × 5 miembros: unos 2 MB). Con
  decenas de miles de imágenes habría que submuestrear o indexar.
- **Problema abierto:** con el umbral actual, alrededor del 70 % de las imágenes de BUS-BRA
  quedan como «fuera de dominio». Es coherente con el estudio (ahí el AUROC cae de ~0,95 a
  0,77), pero un sistema que se abstiene casi siempre en un hospital nuevo no es útil. Hay que
  decidir con datos si el umbral se relaja, si el aviso se gradúa en niveles o si el modelo se
  entrena con más de un origen. Es parte de la validación externa.
- El puntaje mide distancia en el espacio del clasificador, no calidad de imagen ni error
  esperado; falta comprobar si un puntaje alto predice realmente más errores.
