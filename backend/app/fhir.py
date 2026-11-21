"""Exportación de un resultado como colección HL7 FHIR R4."""

from collections.abc import Iterable
from uuid import uuid4

from .models import Analysis, ClinicalReading
from .reports import DECISION_LABELS

_ABSENT = {
    "dataAbsentReason": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
                "code": "unknown",
            }
        ]
    }
}


def _quantity(value: float | None) -> dict:
    return {"valueQuantity": {"value": value}} if value is not None else _ABSENT


def analysis_bundle(analysis: Analysis, readings: Iterable[ClinicalReading]) -> dict:
    entries = []

    def add(resource_type: str, **fields) -> dict:
        url = uuid4().urn
        entries.append({"fullUrl": url, "resource": {"resourceType": resource_type, **fields}})
        return {"reference": url}

    model = analysis.model_version
    patient = add("Patient", identifier=[{"value": analysis.image.case.patient_ref}])
    device = add(
        "Device",
        deviceName=[{"name": model.name, "type": "model-name"}],
        version=[{"value": model.version}],
        identifier=[{"type": {"text": "SHA-256 del paquete"}, "value": model.bundle_sha256}],
    )
    date = (analysis.finished_at or analysis.created_at).isoformat()
    decision = DECISION_LABELS.get(
        analysis.decision, analysis.decision or "Sin decisión registrada"
    )
    results = [
        add(
            "Observation",
            status="final",
            code={"text": "Probabilidad calibrada de malignidad"},
            subject=patient,
            device=device,
            effectiveDateTime=date,
            interpretation=[{"text": decision}],
            component=[
                {
                    "code": {"text": "Dispersión entre miembros"},
                    **_quantity(analysis.member_spread),
                },
                {
                    "code": {"text": "Puntaje de cambio de dominio"},
                    **_quantity(analysis.shift_score),
                },
                {
                    "code": {"text": "Alerta de cambio de dominio"},
                    **(
                        _ABSENT
                        if analysis.shift_flag is None
                        else {"valueBoolean": analysis.shift_flag}
                    ),
                },
            ],
            **_quantity(analysis.probability),
        )
    ]
    for reading in readings:
        results.append(
            add(
                "Observation",
                status="final",
                code={"text": "Categoría BI-RADS"},
                subject=patient,
                effectiveDateTime=reading.created_at.isoformat(),
                valueCodeableConcept={"text": reading.birads},
            )
        )
    add(
        "DiagnosticReport",
        status="final",
        code={"text": "Análisis de ecografía mamaria"},
        subject=patient,
        effectiveDateTime=date,
        result=results,
        conclusion=f"{decision}. Prototipo de investigación. No usar para decidir la atención de un paciente.",
    )
    return {"resourceType": "Bundle", "type": "collection", "entry": entries}
