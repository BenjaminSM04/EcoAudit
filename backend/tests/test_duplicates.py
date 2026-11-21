"""Duplicados entre casos del mismo usuario al cargar imágenes."""

from __future__ import annotations

import numpy as np

from app import services
from app.models import Role
from app.pipeline.quality import NEAR_DUPLICATE_BITS, dhash, hamming

from .conftest import login, make_user, noise_pixels, png_bytes


def _case(client, headers, ref: str = "P-1") -> int:
    return client.post("/api/cases", headers=headers, json={"patient_ref": ref}).json()["id"]


def _upload_pixels(client, headers, case_id: int, pixels: np.ndarray) -> dict:
    response = client.post(
        f"/api/cases/{case_id}/images",
        headers=headers,
        files={"file": ("eco.png", png_bytes(pixels), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _slightly_different(pixels: np.ndarray) -> np.ndarray:
    """Casi idéntica: distinto SHA-256, misma huella perceptual."""
    other = pixels.copy()
    other[0, 0] = (int(other[0, 0]) + 7) % 256
    assert hamming(dhash(pixels), dhash(other)) <= NEAR_DUPLICATE_BITS
    return other


def test_exact_duplicate_in_another_case_of_the_same_user(client, medico):
    case_a, case_b = _case(client, medico, "A"), _case(client, medico, "B")
    first = _upload_pixels(client, medico, case_a, noise_pixels(1))
    second = _upload_pixels(client, medico, case_b, noise_pixels(1))

    assert first["qc_flags"] == []
    assert second["qc_flags"] == ["exact_duplicate_other_case"]
    assert second["duplicate_of_id"] == first["id"]


def test_near_duplicate_in_another_case_of_the_same_user(client, medico):
    case_a, case_b = _case(client, medico, "A"), _case(client, medico, "B")
    pixels = noise_pixels(2)
    first = _upload_pixels(client, medico, case_a, pixels)
    second = _upload_pixels(client, medico, case_b, _slightly_different(pixels))

    assert second["qc_flags"] == ["near_duplicate_other_case"]
    assert second["duplicate_of_id"] == first["id"]


def test_unrelated_image_in_another_case_has_no_flag(client, medico):
    case_a, case_b = _case(client, medico, "A"), _case(client, medico, "B")
    _upload_pixels(client, medico, case_a, noise_pixels(1))
    other = _upload_pixels(client, medico, case_b, noise_pixels(2))
    assert other["qc_flags"] == [] and other["duplicate_of_id"] is None


def test_same_case_search_has_priority_over_other_cases(client, medico):
    case_a, case_b = _case(client, medico, "A"), _case(client, medico, "B")
    pixels = noise_pixels(3)
    in_a = _upload_pixels(client, medico, case_a, pixels)
    in_b = _upload_pixels(client, medico, case_b, pixels)  # duplicado de otro caso
    again_in_b = _upload_pixels(client, medico, case_b, pixels)

    assert in_b["duplicate_of_id"] == in_a["id"]
    assert again_in_b["qc_flags"] == ["exact_duplicate"]
    assert again_in_b["duplicate_of_id"] == in_b["id"]  # el del mismo caso, no el de A

    # Un casi duplicado del mismo caso también gana frente a un exacto de otro caso.
    near = _upload_pixels(client, medico, case_b, _slightly_different(pixels))
    assert "exact_duplicate_other_case" not in near["qc_flags"]
    assert near["qc_flags"] in (["exact_duplicate"], ["near_duplicate"])
    assert near["duplicate_of_id"] in (in_b["id"], again_in_b["id"])


def test_other_users_images_are_never_compared(client, db, medico):
    make_user(db, "otro@test.bo", Role.medico)
    other = login(client, "otro@test.bo")
    _upload_pixels(client, medico, _case(client, medico), noise_pixels(1))
    mine = _upload_pixels(client, other, _case(client, other), noise_pixels(1))
    assert mine["qc_flags"] == [] and mine["duplicate_of_id"] is None


def test_owner_is_whoever_uploads_also_for_admin(client, db, medico, admin):
    medico_image = _upload_pixels(client, medico, _case(client, medico), noise_pixels(1))
    # El administrador compara con sus propios casos, no con los del médico.
    first = _upload_pixels(client, admin, _case(client, admin, "A"), noise_pixels(1))
    assert first["qc_flags"] == [] and first["duplicate_of_id"] is None
    second = _upload_pixels(client, admin, _case(client, admin, "B"), noise_pixels(1))
    assert second["qc_flags"] == ["exact_duplicate_other_case"]
    assert second["duplicate_of_id"] == first["id"] != medico_image["id"]


def test_investigador_also_gets_cross_case_flags(client, investigador):
    first = _upload_pixels(client, investigador, _case(client, investigador, "A"), noise_pixels(1))
    second = _upload_pixels(client, investigador, _case(client, investigador, "B"), noise_pixels(1))
    assert second["qc_flags"] == ["exact_duplicate_other_case"]
    assert second["duplicate_of_id"] == first["id"]


def test_near_search_is_limited_to_the_most_recent_images(client, medico, monkeypatch):
    monkeypatch.setattr(services, "RECENT_IMAGES_LIMIT", 2)
    case_a, case_b = _case(client, medico, "A"), _case(client, medico, "B")
    pixels = noise_pixels(4)
    original = _upload_pixels(client, medico, case_a, pixels)
    _upload_pixels(client, medico, case_a, noise_pixels(5))
    _upload_pixels(
        client, medico, case_a, noise_pixels(6)
    )  # el original queda fuera de las 2 más recientes

    near = _upload_pixels(client, medico, case_b, _slightly_different(pixels))
    assert near["qc_flags"] == [] and near["duplicate_of_id"] is None
    # El duplicado exacto usa el índice y no depende de ese límite.
    exact = _upload_pixels(client, medico, _case(client, medico, "C"), pixels)
    assert exact["qc_flags"] == ["exact_duplicate_other_case"]
    assert exact["duplicate_of_id"] == original["id"]
