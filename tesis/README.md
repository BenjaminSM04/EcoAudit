# Manuscrito y reproducción

[Descargar el documento académico editable](EcoAudit.docx). Edición de noviembre de 2026 sin plantilla institucional.

## Repetir el experimento

Desde la raíz del proyecto, en PowerShell y con Python 3.11, instale las dependencias de ML en un entorno propio con `pip install -r ml/requirements.txt`. Los siguientes comandos presuponen la corrida local del estudio precursor. La opción de salida determina el archivo que se usará. Guarde una nueva corrida en otro directorio para conservar los pesos de la tesis.

```powershell
$origen = 'D:/busgen-ojemb-code'
$corrida = "$origen/results/publication_v3_5seed"
$env:PYTHONPATH = "$PWD/ml;$PWD/backend"
python -m ecoaudit_ml.train_roi --root $origen --splits "$corrida/splits" --out ./reproduccion/segmenter.onnx
python -m ecoaudit_ml.compare_roi --root $origen --run $corrida --localizer ./reproduccion/segmenter.onnx
```

El segmentador instalado en esta estación está en `backend/data/storage/roi/segmenter.onnx`. SHA-256 de los pesos evaluados: `a00c8a99417ae7cd75346ced8e57e5d6be44ad1ee3efa893dc0832084f01996c`. En otra instalación copie esos pesos a `roi/segmenter.onnx` dentro de ECOAUDIT_STORAGE_DIR. En Docker, con los servicios en ejecución, use `docker compose exec api mkdir -p /data/storage/roi` y `docker compose cp backend/data/storage/roi/segmenter.onnx api:/data/storage/roi/segmenter.onnx`. El clasificador tiene su propio registro y activación. Los pesos y los datos están excluidos de Git.

Se leyeron 229 imágenes source_train y 946 target_adapt para la segmentación, con las 57 de source_val reservadas para evaluación. En una RTX 2060 SUPER, PyTorch 2.5.1 y semilla 42, el Dice medio fue 0,669803. AUROC por imagen: completa 0,946292, máscara 0,973146, automática 0,822251 y automática con cabeza reajustada 0,822251. El intervalo de la diferencia automática menos máscara fue [−0,258376; −0,052398]. Un reentrenamiento en GPU puede producir pesos diferentes. La comparación reutiliza los checkpoints v3 de las familias main y roi. El reajuste es experimental y no publica un modelo en el registro.

## Recorrido operativo

1. En **Casos**, cree un seudónimo consistente por paciente y cargue las imágenes. El personal con acceso a los casos prepara la correspondencia con las etiquetas de referencia.
2. En el visor, elija **Sugerir ROI experimental** o dibuje un rectángulo. Revise la región, solicite el análisis y espere el resultado. **Descargar PDF · Análisis #** identifica el número que debe usar en el CSV.
3. Prepare un archivo UTF-8 con cabecera `analysis_id,label` y una fila por imagen. Sustituya los identificadores del ejemplo por análisis terminados de su instancia.

```csv
analysis_id,label
1,0
2,1
```

4. En **Auditoría**, un administrador o investigador importa el CSV mediante **Evaluar cohorte**. Se requiere representación de ambas clases. Cada paciente tiene una sola etiqueta. Una mezcla de lesiones benignas y malignas en el mismo paciente requiere definir previamente otro desenlace.
5. Revise el número de pacientes, imágenes y abstenciones antes de interpretar el AUROC. Descargue el informe. El intervalo solo se calcula con al menos dos pacientes por clase. La huella del CSV permite cotejar el archivo original.

El CSV referencia análisis existentes. Las auditorías dependen de la calidad de los seudónimos y de las etiquetas aportadas. Los duplicados exactos dentro de una cohorte se rechazan. Continúan pendientes la revisión perceptual entre casos y una validación externa con protocolo congelado.

## Auditoría de desarrollo de BUS-BRA

El [informe exportado por la aplicación](Auditoria_BUS_BRA_60_pacientes.pdf) corresponde a los primeros 60 identificadores numéricos de paciente, ordenados de menor a mayor, de `target_adapt_manifest.csv`. Se procesaron todas sus 105 vistas con el ensamble activo de imagen completa. Las etiquetas se tomaron de `label_idx`; 21 pacientes eran positivos. La aplicación obtuvo AUROC 0,890 (IC 95 % 0,792–0,966), Brier 0,182 y ECE 0,224. Hubo 71 imágenes fuera de dominio y tres indeterminadas. La cobertura fue 31/105. Esta es una muestra de desarrollo seleccionada por identificador.

Para reproducirla, use un seudónimo por `patient_id`, analice las vistas completas e importe el CSV con los identificadores asignados en su instancia. El número de auditoría y la huella del CSV dependen de esos identificadores. La investigación utilizó una base aislada de la instalación principal.
