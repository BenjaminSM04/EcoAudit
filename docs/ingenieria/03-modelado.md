# Modelado de EcoAudit

Se utilizan tres vistas C4 en Mermaid. I4 señala el incremento de interoperabilidad, lectura independiente e indicadores. La SPA visible y las integraciones en desarrollo pueden encontrarse en revisiones distintas.

## C4 · Contexto

```mermaid
flowchart LR
    M["Persona · Médico"] -->|"Revisa ecografías y registra lecturas"| E["Sistema · EcoAudit"]
    I["Persona · Investigador"] -->|"Audita cohortes y compara modelos"| E
    A["Persona · Administrador"] -->|"Gestiona cuentas, versiones y bitácora"| E
    O["Persona · Operador técnico"] -->|"Instala y registra paquetes"| E
    P["Sistema externo · PACS o pasarela"] -.->|"Envía estudios STOW-RS · I4"| E
    E -.->|"Entrega una exportación R4 a un integrador · I4"| H["Sistema externo · HCE de ensayo"]
```

## C4 · Contenedores

```mermaid
flowchart LR
    B[Navegador]
    PACS[PACS o pasarela]
    HCE[Consumidor FHIR]
    subgraph S[EcoAudit]
      WEB["nginx · Estáticos y proxy"]
      SPA["SPA · React, TypeScript y Vite"]
      API["API · FastAPI"]
      W["Worker · Python y ONNX Runtime CPU"]
      DB[("PostgreSQL · SQLite en desarrollo")]
      FS[("Almacén · PNG, CAM y paquetes")]
      CLI["CLI · Administración y migraciones"]
    end
    B -->|Carga la SPA| WEB
    WEB --> SPA
    SPA -->|HTTPS y JSON vía proxy| WEB
    WEB -->|/api| API
    PACS -.->|POST STOW-RS I4| WEB
    WEB -.->|Descarga FHIR I4| HCE
    API -->|SQLAlchemy| DB
    API -->|Guarda y lee archivos| FS
    W -->|Reclama filas y persiste resultados| DB
    W -->|Lee entradas y escribe CAM| FS
    CLI -->|Alembic y SQLAlchemy| DB
    CLI -->|Copia paquetes| FS
```

En Compose el worker es un proceso separado. En desarrollo el modo inline ejecuta el mismo procesamiento en tareas de la API. El HTTPS se añade en un proxy de despliegue.

## C4 · Componentes

```mermaid
flowchart TD
    UI["App.tsx y páginas"]
    subgraph API[API FastAPI]
      AUTH["routers/auth.py, deps.py y security.py"]
      CASE["routers/cases.py · casos, imágenes y análisis"]
      COH["routers/cohorts.py · lotes y exportaciones"]
      ADM["routers/users.py y model_registry.py"]
      OPS["I4 · stats, STOW-RS, bitácora y comparación"]
      L["I4 · lectura y exportación /reading y /fhir"]
      ING["services.py · preparación y duplicados"]
      AG["cohorts.py · agrupación y métricas"]
      REP["reports.py y fhir.py"]
    end
    DB[("models.py, db.py · SQL")]
    FS[("storage.py")]
    W["worker.py"]
    RUN["pipeline/runner.py"]
    ONNX["pipeline/bundle.py · ONNX Runtime"]
    UI --> AUTH
    UI --> CASE
    UI --> COH
    UI --> ADM
    UI -.-> OPS
    UI -.-> L
    AUTH --> DB
    CASE --> AUTH
    CASE --> ING
    CASE --> REP
    COH --> ING
    COH --> AG
    COH --> REP
    ADM --> DB
    OPS -.-> DB
    L --> REP
    L --> DB
    ING --> DB
    ING --> FS
    W --> DB
    W --> FS
    W --> RUN
    W --> AG
    RUN --> ONNX
```

## Entidad–relación

Se representan las tablas de aplicación y la tabla técnica de Alembic. `audit_log.entity_id` es una referencia polimórfica sin FK. El par `clinical_readings(analysis_id, reader_id)` es único mediante `uq_reading_analysis_reader`. La FK al análisis tiene borrado en cascada. Los valores seudonimizados de `cohort_items.patient_ref` se copian para agrupar por paciente.

```mermaid
erDiagram
    users ||--o{ cases : crea
    users ||--o{ analyses : solicita
    users ||--o{ cohorts : posee
    users |o--o{ audit_log : realiza
    users ||--o{ clinical_readings : registra
    cases ||--o{ images : contiene
    images |o--o{ images : duplica
    images ||--o{ analyses : origina
    analyses ||--o{ clinical_readings : recibe
    model_versions ||--o{ analyses : produce
    model_versions ||--o{ cohorts : respalda
    cohorts ||--o{ cohort_items : agrupa
    analyses ||--o{ cohort_items : referencia

    users {
        int id PK
        string email UK
        string full_name
        string password_hash
        string role
        boolean is_active
        datetime created_at
        datetime password_changed_at
    }
    cases {
        int id PK
        string patient_ref
        text notes
        int created_by_id FK
        datetime created_at
    }
    images {
        int id PK
        int case_id FK
        string storage_key
        string pixel_sha256
        string dhash
        int width
        int height
        string source_format
        json qc_flags
        int duplicate_of_id FK
        datetime created_at
    }
    model_versions {
        int id PK
        string name
        string version
        string bundle_sha256 UK
        string storage_key
        json card
        boolean is_active
        datetime created_at
    }
    analyses {
        int id PK
        int image_id FK
        int requested_by_id FK
        int model_version_id FK
        string status
        json roi
        int attempts
        float probability_raw
        float probability
        float member_spread
        string decision
        float shift_score
        boolean shift_flag
        json warnings
        string cam_key
        text error
        datetime created_at
        datetime started_at
        datetime finished_at
    }
    clinical_readings {
        int id PK
        int analysis_id FK
        int reader_id FK
        string birads
        boolean blinded
        text notes
        datetime created_at
    }
    cohorts {
        int id PK
        string name
        string source
        string status
        int owner_id FK
        int model_version_id FK
        string csv_hash
        json results
        text error
        datetime created_at
        datetime finished_at
    }
    cohort_items {
        int id PK
        int cohort_id FK
        int analysis_id FK
        string patient_ref
        int label
    }
    audit_log {
        int id PK
        int user_id FK
        string action
        string entity
        int entity_id
        json detail
        datetime created_at
    }
    alembic_version {
        string version_num PK
    }
```

## Clases del pipeline

```mermaid
classDiagram
    class DecodedImage
    class PreparedImage
    class DuplicateFinder
    class ModelBundle {
      +card
      +preprocess(rgb)
      +predict(rgb) Prediction
      +shift_score(embeddings)
      +self_check(tolerance)
    }
    class Prediction {
      +logits
      +embeddings
      +cam
    }
    class AnalysisResult {
      +probability_raw
      +probability
      +member_spread
      +decision
      +shift_score
      +shift_flag
      +warnings
      +cam_overlay_png
    }
    class RoiError
    class BundleError
    class Runner {
      <<module>>
      +resolve_roi(roi, width, height, margin)
      +analyze(rgb, roi, bundle) AnalysisResult
      +render_cam_overlay(cam, box, width, height)
    }
    class ImageIngestion {
      <<module>>
      +prepare_image(data, filename) PreparedImage
    }
    ImageIngestion ..> DecodedImage : decodifica
    ImageIngestion ..> PreparedImage : construye
    DuplicateFinder ..> PreparedImage : compara huellas
    Runner ..> ModelBundle : ejecuta ensamble
    ModelBundle ..> Prediction : devuelve
    ModelBundle ..> BundleError : validación
    Runner ..> AnalysisResult : devuelve
    Runner ..> RoiError : validación
```

`runner.py` es un módulo. El promedio de logits se aplica antes de dividir por la temperatura. La alerta de dominio se decide por la referencia de vecinos coseno del paquete y prevalece sobre los umbrales de probabilidad. El CAM se reconstruye a partir de mapas y pesos de la cabeza lineal. [Contrato ONNX](../model-bundle.md)

## Secuencia · Análisis individual

```mermaid
sequenceDiagram
    actor M as Usuario
    participant A as API
    participant D as BD
    participant W as Worker
    participant F as Almacén
    participant N as ONNX Runtime
    M->>A: POST /api/images/{image_id}/analyses
    A->>D: Consulta modelo activo y guarda pending, ROI y evento
    A-->>M: 202 con identificador
    W->>D: UPDATE condicionado pending a running e incrementa attempts
    W->>F: Lee PNG y carga bundle por versión si falta en caché
    W->>N: Inferencia por miembro del ensamble
    N-->>W: Logits y mapas de características
    alt Inferencia y escritura correctas
        W->>W: Calibra, evalúa dominio y compone CAM
        W->>F: Guarda CAM PNG
        W->>D: Persiste done y finished_at
    else Excepción de procesamiento
        W->>D: Persiste failed, error y finished_at
    end
    M->>A: GET /api/analyses/{analysis_id}
    A->>D: Consulta estado y resultado
    A-->>M: Estado, salida o error
```

## Secuencia · Auditoría por lote

```mermaid
sequenceDiagram
    actor R as Investigador
    participant A as API
    participant D as BD
    participant F as Almacén
    participant W as Worker
    R->>A: POST /api/cohorts/batch con manifiesto e imágenes
    A->>A: Valida correspondencia, clases y archivos
    A->>D: Crea casos por seudónimo, imágenes, análisis e ítems
    A->>F: Escribe PNG reconstruidos
    A->>D: Confirma cohorte processing
    A-->>R: Devuelve detalle inicial
    loop Por análisis
        W->>D: Procesa fila y refresca cohorte
    end
    R->>A: GET /api/cohorts/{cohort_id}
    A->>D: Actualiza y consulta resumen
    alt Quedan análisis pendientes o en curso
        A-->>R: processing y progreso
    else Todos terminaron y alguno falló o las métricas son inválidas
        A-->>R: failed y error
    else Todos terminaron y las métricas son válidas
        A-->>R: done y métricas por paciente
    end
```

## Secuencia · Recepción DICOMweb I4

```mermaid
sequenceDiagram
    participant P as PACS o pasarela
    participant A as API STOW-RS
    participant I as Ingesta
    participant D as BD
    participant S as Almacén
    P->>A: POST /api/dicomweb/studies
    A->>A: Comprueba rol, formato y tamaño
    loop Instancias admitidas
        A->>I: Deriva seudónimo a partir de PatientID y decodifica
        I->>S: Guarda PNG reconstruido
        I->>D: Vincula caso e imagen
    end
    A-->>P: JSON con instancias y fallos
```

El manejador visible admite cuenta médica o administradora, agrupa por seudónimo y dueño y responde `200` para recepción completa, `202` para parcial y `400` si ninguna instancia se acepta. El cliente de ensayo debe interpretar el JSON propio de EcoAudit. [Contrato de la API hospitalaria](../api-hospitalaria.md)

## Secuencia · Exportación FHIR I4

```mermaid
sequenceDiagram
    actor U as Consumidor autorizado
    participant A as Ruta de análisis
    participant D as BD
    participant F as analysis_bundle
    U->>A: GET /api/analyses/{analysis_id}/fhir
    A->>D: Recupera análisis autorizado
    alt Recurso inaccesible o análisis sin resultado
        A-->>U: 404 o 409 según el caso
    else Análisis done
        A->>D: Consulta lecturas visibles para el rol
        A->>F: Construye Bundle collection con referencias internas
        F-->>A: Patient, Device, Observation y DiagnosticReport
        A->>D: Registra analysis_fhir_exported
        A-->>U: application/fhir+json
    end
```

## Estados del análisis

```mermaid
stateDiagram-v2
    [*] --> pending: Encolado
    pending --> running: Reclamación atómica e incremento de attempts
    running --> done: Resultado y CAM persistidos
    running --> failed: Excepción de procesamiento
    running --> pending: Interrupción vencida con attempts menor que 3
    running --> failed: Interrupción vencida con attempts al menos 3
    done --> [*]
    failed --> [*]
```

`requeue_stale` usa `started_at` con un límite configurable de 300 s por defecto. El worker separado lo ejecuta en su bucle y la API al arrancar. `pending` conserva el contador en la recuperación. El diagrama recoge el reclamo atómico, sin atribuir al mecanismo una garantía de ejecución única frente a un trabajo que sigue vivo tras superar el tiempo de corte.
