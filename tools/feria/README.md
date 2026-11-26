# Demo de EcoAudit para la feria en Windows 11

La Samsung Galaxy Book3 Pro 360 con Intel x64 puede ejecutar la demo en CPU. El camino
recomendado por el autor usa Docker Desktop y funciona con una sola unidad `C:`. Los scripts
sin Docker quedan disponibles como respaldo.

## 1. Docker Desktop (recomendado)

### Preparar una laptop nueva con internet

1. En PowerShell, instala Git y Docker Desktop para Windows x64. Si WSL aún no está instalado,
   ejecuta `wsl --install` en PowerShell como administrador. Si ya está instalado, ejecuta
   `wsl --update`. Reinicia Windows después de la instalación.

   ```powershell
   winget install --id Git.Git -e
   winget install --id Docker.DockerDesktop -e
   ```

2. Abre Docker Desktop, acepta sus términos y espera a que arranque el motor de contenedores
   Linux con WSL 2. Compruébalo con `docker info`. Si falla, revisa [la instalación de Docker
   Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
3. En una terminal nueva, clona EcoAudit en una carpeta de tu usuario en `C:`. Si el clon aún no
   trae los scripts `docker-*`, copia a `tools\feria` los archivos de esta entrega junto con
   `comun.ps1`.

   ```powershell
   $repo = Join-Path $env:USERPROFILE 'EcoAudit'
   git clone https://github.com/BenjaminSM04/EcoAudit.git $repo
   Set-Location -LiteralPath $repo
   ```

4. Haz doble clic en `tools\feria\docker-demo.cmd` o ejecuta lo siguiente desde la raíz del
   clon. La primera ejecución crea `.env` con claves aleatorias, compila las imágenes Docker,
   descarga y verifica los dos ZIP del release, activa el modelo del estudio y prepara las cuentas.

   ```powershell
   .\tools\feria\docker-demo.cmd
   ```

5. Abre <http://localhost:8080> e inicia sesión como `medico1@ecoaudit.test` con la clave de
   `%LOCALAPPDATA%\EcoAuditFeria\credenciales-docker.txt`. Ese archivo contiene las cuatro
   cuentas y su clave compartida. Crea un caso de prueba, carga
   `imagenes-demo\2-sospechosa_bus_0059-l.png` desde la misma carpeta de datos y solicita el análisis.

### Ensayar y abrir sin internet

1. Completa la primera ejecución con internet. Conserva el clon con su `.env`, los volúmenes y
   las imágenes de Docker Desktop, y `%LOCALAPPDATA%\EcoAuditFeria` con sus credenciales, ZIP e
   imágenes de ejemplo. Los ZIP verificados quedan en el subdirectorio `descargas`.
2. Haz doble clic en `tools\feria\docker-detener.cmd` al terminar el ensayo. Ejecuta
   `docker compose stop`, que conserva PostgreSQL y el almacenamiento. Evita borrar los
   volúmenes o limpiar las imágenes Docker antes de la feria.
3. Desconecta el Wi-Fi y repite la prueba de inicio y análisis. Desde la raíz del clon, usa el
   siguiente comando para iniciar con las imágenes Docker instaladas. La interfaz y la
   inferencia funcionan localmente. El navegador usa una tipografía del sistema si no puede
   descargar la fuente Inter.

   ```powershell
   .\tools\feria\docker-demo.cmd -SinCompilar
   ```

   Equivale a hacer doble clic en `tools\feria\docker-feria.cmd`, pensado para el día del evento.

4. Si ya preparaste la demo con el puerto predeterminado, `docker compose up -d` desde la raíz
   también reanuda los servicios. Puedes volver a ejecutar `docker-demo.cmd` para preparar o
   comprobar la instalación. Usa `-SinCompilar` para el día del evento sin internet.

### Rutas y puerto alternativos

- `-Datos` permite elegir otra carpeta. `-SinNavegador` omite abrir el navegador.
- Puedes copiar ambos ZIP de [la publicación `modelo-v1.0.0`](https://github.com/BenjaminSM04/EcoAudit/releases/tag/modelo-v1.0.0)
  a `<Datos>\descargas`, con sus nombres originales, o indicar `-ZipModelo` y `-ZipImagenes` con
  sus rutas locales. El script verifica el SHA-256 y borra el ZIP si la suma es incorrecta.
  Si pasas rutas externas, vuelve a indicarlas en el siguiente arranque o guarda copias con
  sus nombres originales en `descargas`.
- Para usar otra instalación de EcoAudit a la vez, configura un nombre de proyecto Compose y
  una carpeta de datos propios, y elige un puerto libre. `-PuertoWeb` requiere Compose 2.24.4 o
  posterior. Mantén el mismo nombre de proyecto para detener y reanudar la demo, y repite el
  puerto y la carpeta de datos al reanudar con `docker-demo.cmd`.

  ```powershell
  $env:COMPOSE_PROJECT_NAME = 'ecoauditferia'
  $datos = Join-Path $env:LOCALAPPDATA 'EcoAuditFeriaAlterna'
  .\tools\feria\docker-demo.cmd -Datos $datos -PuertoWeb 8099 -SinNavegador
  .\tools\feria\docker-detener.cmd
  ```

## 2. Sin Docker (respaldo)

Usa una copia local completa de EcoAudit. Instala **Python 3.11 o posterior (x64)** y **Node.js
24 LTS (x64, con npm)** y asegúrate de que estén en el PATH. La rama Node 20 es compatible
desde la versión 20.19. Copia del USB la carpeta completa del modelo ONNX del estudio y,
si las vas a usar, las imágenes de ejemplo. La inferencia se ejecuta en CPU.

### Preparar con internet

Desde `tools\feria`, ejecuta lo siguiente en una terminal. Ajusta las rutas a las de tu equipo.

```powershell
.\preparar.cmd -Modelo "C:\Feria\paper-resnet18-control" -Imagenes "C:\Feria\imagenes-demo"
```

`-Imagenes` es opcional. `-Datos` permite elegir otra carpeta. El valor por defecto es
`%LOCALAPPDATA%\EcoAuditFeria`. Allí quedan SQLite, el modelo registrado, las imágenes
copiadas y `credenciales.txt`, con las cuatro cuentas y su clave compartida. Repetir la
preparación conserva la clave de sesiones, las credenciales y los casos existentes. Puedes
omitir `-Modelo` si ya hay un modelo activo en esa base. Detén la demo antes de actualizar
Node.js o las dependencias del proyecto.

### Abrir y cerrar en la feria

Haz doble clic en `iniciar.cmd`. Cuando respondan los servicios, se abrirá
<http://127.0.0.1:8080>. Entra como `medico1@ecoaudit.test` con la clave de
`credenciales.txt`. Crea un caso, carga un PNG de `imagenes-demo` y solicita el análisis.
Haz doble clic en `detener.cmd` al terminar. Mantén en su sitio la copia preparada del
proyecto y su carpeta de datos. Después de la preparación, el inicio y la inferencia
funcionan sin conexión. Si el navegador no puede descargar la fuente Inter, usa la
tipografía del sistema.

Si hay un puerto ocupado, elige puertos libres. Usa los mismos valores de `-Datos`,
`-PuertoApi` y `-PuertoWeb` al iniciar y al detener. `-SinNavegador` omite abrir el navegador.

```powershell
.\iniciar.cmd -PuertoApi 8110 -PuertoWeb 8190 -SinNavegador
.\detener.cmd -PuertoApi 8110 -PuertoWeb 8190
```
