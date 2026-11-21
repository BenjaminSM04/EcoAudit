# Manual de usuario

EcoAudit se utiliza para investigación. Trabaje con archivos ficticios o autorizados y seudónimos. Revise los píxeles antes de la carga y omita nombres, carnets y otros identificadores en notas. Cada operador debe ingresar con su propia cuenta.

## Ingreso y navegación

1. Abra la URL de la instancia e introduzca **Correo** y **Contraseña**.
2. Seleccione **Ingresar**. El médico y el administrador llegan a **Casos**. El investigador llega a **Auditoría**.
3. Use el nombre de la cuenta en la barra superior para abrir **Mi cuenta** o **Salir** para cerrar la sesión.

**Panel**, **Lectura clínica ciega**, exportación FHIR desde **Resultado**, **Comparación de modelos** y **Bitácora** describen recorridos de I4. Los enlaces y controles de esos recorridos se confirman en la interfaz integrada. Mientras tanto, el personal autorizado puede usar las rutas disponibles del backend en una instancia de ensayo. Las etiquetas en negrita de los flujos base corresponden a la SPA inspeccionada.

## Médico

### Panel · I4

1. Abra **Panel** cuando esté habilitado. Revise recuentos, estados y evolución diaria de sus casos.
2. Consulte concordancia cuando haya lecturas evaluables. El indicador disponible coteja la lectura propia con la salida binaria; su denominador puede ser menor que el total de lecturas. El apartado de rendimiento por versión requiere investigador o administrador.

### Casos y detalle de caso

1. En **Casos**, complete **Seudónimo del paciente** y, si procede, **Notas (opcional)**. Pulse **Nuevo caso**.
2. En **Casos registrados**, localice el registro por seudónimo o número y abra su detalle.
3. En el selector de archivos, elija PNG, JPEG, BMP, TIFF o DICOM sin compresión. Si carga varios, revise los errores por archivo y la lista final.
4. Compruebe dimensiones, formato de origen y avisos. Si hay un duplicado, revise si corresponde al caso antes de incluirlo en una cohorte.
5. Arrastre sobre la imagen para dibujar el ROI. Si el localizador está instalado, use **Sugerir ROI experimental** y revise el recuadro. Redibuje si hace falta o pulse **Quitar ROI**.
6. Pulse **Analizar el ROI** o **Analizar la imagen completa**. Espere la consulta de estado. Si falta un modelo activo, contacte con administración.

### Lectura clínica ciega · I4

1. Acceda solo al recorrido de lectura habilitado para el piloto. Antes de abrir el caso, confirme con el coordinador que el flujo asignado oculta lecturas ajenas y la salida algorítmica.
2. Revise la imagen y registre su categoría BI-RADS. La API visible admite `1`, `2`, `3`, `4A`, `4B`, `4C`, `5` y `6`. Añada notas únicamente si el protocolo lo requiere y use datos seudonimizados.
3. Declare el ciego según lo que realmente ocurrió y confirme el registro. Compruebe su lectura guardada. Si vio la salida del modelo o la otra lectura, comunique la incidencia al coordinador.
4. Cada cuenta puede registrar una lectura por análisis. El piloto debe resolver el acceso autorizado de dos lectores al mismo análisis antes de la asignación.

### Resultado

1. Lea la decisión experimental, la probabilidad calibrada, los avisos y la versión. Indeterminado y fuera de dominio indican abstención. Si el análisis falló, registre el número y el error.
2. Use **Mostrar mapa de activación** y **Opacidad del mapa**. El mapa indica regiones que contribuyen al resultado del modelo y carece de valor como contorno tumoral.
3. Pulse **Descargar PDF · Análisis #…**. Si modificó el recuadro después de analizar, el informe sigue asociado al análisis anterior. Para documentar la nueva selección, vuelva a analizar.
4. En I4, obtenga el JSON FHIR del análisis terminado desde la opción de exportación cuando esté habilitada. La ruta disponible es `GET /api/analyses/{analysis_id}/fhir`. Use el archivo únicamente en destinos autorizados.

## Investigador

Puede usar Casos, visor y Resultado sobre sus propios casos, y consultar Panel en I4 dentro de su ámbito.

### Auditoría

1. Abra **Auditoría**. Para usar resultados previos, en **Desde análisis existentes** adjunte un CSV UTF-8 con cabecera `analysis_id,label` y etiquetas 0/1. Use análisis terminados de una misma versión y al menos un paciente por clase. Pulse **Evaluar cohorte**.
2. Para imágenes nuevas, en **Nuevo lote** indique **Nombre de la cohorte**, adjunte **Manifiesto (CSV)** con cabecera `filename,patient_ref,label` y seleccione los archivos correspondientes. Use el mismo seudónimo y etiqueta para todas las imágenes de un paciente. Revise la validación previa y seleccione **Crear lote y analizar**.
3. Abra el registro en **Mis cohortes**. Revise progreso o error. Cuando termine, examine AUROC, intervalo si se puede estimar, Brier, ECE y decisiones. Revise denominadores y huellas.
4. Use **Descargar informe PDF** y **Descargar CSV de ítems**. Mantenga el manifiesto en el entorno autorizado para cotejo posterior.

### Comparación de modelos · I4

1. Seleccione la cohorte base y la versión alternativa. Con la interfaz integrada, solicite el reanálisis de la cohorte; el backend reutiliza imágenes, ROI, etiquetas y seudónimos.
2. Espere que ambas cohortes terminen. Seleccione los identificadores de las dos cohortes para la comparación. La API comprueba coincidencia de imágenes, pacientes y etiquetas.
3. Revise AUROC, Brier, abstenciones y alertas por versión y la diferencia pareada de AUROC con su intervalo cuando resulte estimable. Si alguna ejecución falla, revise sus causas antes de comparar.

## Administrador

Puede consultar todos los casos y cohortes y usar Panel con alcance global en I4.

### Modelos

1. Abra **Modelos** para revisar versión, ficha, huella y estado. Los demás roles autenticados tienen acceso de lectura.
2. Solicite al operador que registre un paquete nuevo mediante la CLI y compruebe la identificación informada.
3. Busque la versión deseada y pulse **Activar**. Verifique su estado. Los análisis ya solicitados mantienen la versión original.

### Usuarios

1. En **Usuarios**, complete **Nombre**, **Correo**, **Contraseña inicial** y **Rol**. Pulse **Crear usuario**.
2. Para una cuenta existente, use el selector de rol o **Desactivar** / **Reactivar** según corresponda.
3. Use **Restablecer contraseña**, indique la nueva contraseña y seleccione **Confirmar**. Las sesiones anteriores se invalidan. Entregue la credencial por el canal institucional autorizado.

### Bitácora · I4

1. Abra **Bitácora** cuando esté disponible. Filtre por usuario, acción o intervalo de fechas y revise los eventos y el total. Una acción de CLI puede carecer de usuario.
2. Confirme entidad, identificador y hora. Considere que la API ordena de más reciente a más antigua.
3. Descargue el CSV cuando el procedimiento de auditoría lo requiera. La API exporta la página solicitada y audita la descarga.

## Mi cuenta · todos los roles

1. Pulse su nombre en la barra superior y compruebe nombre, correo y rol.
2. En **Cambiar contraseña**, complete **Contraseña actual**, **Nueva contraseña** y **Confirmar nueva contraseña**.
3. Seleccione **Cambiar contraseña**. Ingrese de nuevo con la contraseña actualizada.
