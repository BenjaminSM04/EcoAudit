# ADR 0003: de-identificación por reconstrucción de la imagen

**Estado:** aceptada.

## Contexto

Un DICOM lleva decenas de etiquetas con datos del paciente y un JPEG puede llevar EXIF. Borrar
etiquetas una por una depende de una lista que siempre puede quedar incompleta.

## Decisión

Del archivo subido solo se leen los píxeles, y con ellos se escribe un PNG nuevo. El archivo
original nunca se guarda. El caso se identifica con un seudónimo que escribe el usuario.

## Consecuencias

- Ningún metadato sobrevive, sin depender de listas de etiquetas.
- Se pierden metadatos útiles (fabricante del equipo, espaciado de píxel). Si el módulo de
  auditoría los necesita, se conservará una lista explícita de campos no identificables.
- **No resuelve el texto quemado en la imagen** (nombre o fecha impresos por el ecógrafo). La
  interfaz lo advierte; detectarlo automáticamente está en la hoja de ruta.
- No se admite DICOM comprimido (JPEG 2000, JPEG-LS) hasta añadir los decodificadores.
