"""Recepción STOW-RS con instancias sintéticas y verificación de los píxeles."""

import hmac
import io
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image as PillowImage
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, UltrasoundImageStorage, generate_uid
from sqlalchemy import select

from app.config import get_settings
from app.models import AuditLog, Case, Image

from .conftest import noise_pixels

URL = "/api/dicomweb/studies"


def _dicom(patient_id: str, pixels: np.ndarray) -> bytes:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = UltrasoundImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    instance = FileDataset("prueba.dcm", {}, file_meta=meta, preamble=b"\0" * 128)
    instance.PatientID = patient_id
    instance.PatientName = "PACIENTE^FICTICIO"
    instance.Rows, instance.Columns = pixels.shape
    instance.SamplesPerPixel = 1
    instance.PhotometricInterpretation = "MONOCHROME2"
    instance.BitsAllocated = instance.BitsStored = 8
    instance.HighBit = 7
    instance.PixelRepresentation = 0
    instance.PixelData = pixels.tobytes()
    buffer = io.BytesIO()
    instance.save_as(buffer)
    return buffer.getvalue()


def _multipart(*parts: tuple[str, bytes]) -> tuple[str, bytes]:
    boundary = b"instancias:eco"
    media = 'multipart/related; type="application/dicom"; boundary="instancias:eco"'
    body = b"".join(
        b"--"
        + boundary
        + b"\r\nContent-Type: "
        + content_type.encode()
        + b"\r\n\r\n"
        + instance
        + b"\r\n"
        for content_type, instance in parts
    )
    return media, body + b"--" + boundary + b"--\r\n"


def test_stow_single_multipart_duplicates_and_privacy(client, db, medico, investigador, admin):
    pixels = noise_pixels(size=160)
    patient_id = "CI-FICTICIO-1234"
    instance = _dicom(patient_id, pixels)
    single = {"Content-Type": "application/dicom"}
    first = client.post(URL, headers=medico | single, content=instance)
    assert first.status_code == 200, first.text
    (received,) = first.json()["instancias"]
    expected = (
        "PAC-"
        + hmac.digest(get_settings().secret_key.encode(), patient_id.encode(), "sha256").hex()[:12]
    )
    assert received["patient_ref"] == expected
    assert first.json()["fallos"] == []
    media, body = _multipart(
        ("application/dicom", instance),
        ("text/plain", b"no es instancia"),
        ("application/dicom", _dicom("", pixels)),
        ("application/dicom", _dicom("OTRO", noise_pixels(9))),
    )
    response = client.post(URL, headers=medico | {"Content-Type": media}, content=body)
    assert response.status_code == 202, response.text
    repeat, other = response.json()["instancias"]
    assert repeat["case_id"] == received["case_id"]
    assert other["case_id"] != repeat["case_id"]
    assert "exact_duplicate" in repeat["qc_flags"]
    assert [f["indice"] for f in response.json()["fallos"]] == [2, 3]
    assert patient_id not in response.text
    stored = db.get(Image, repeat["image_id"])
    assert stored.duplicate_of_id == received["image_id"] and stored.source_format == "dicom"
    assert db.get(Case, received["case_id"]).patient_ref == expected
    png = client.get(f"/api/images/{repeat['image_id']}/file", headers=medico).content
    assert b"FICTICIO" not in png
    assert np.array_equal(np.asarray(PillowImage.open(io.BytesIO(png))), pixels)
    assert client.post(URL, headers=investigador | single, content=instance).status_code == 403
    global_user = client.post(URL, headers=admin | single, content=instance).json()["instancias"][0]
    assert global_user["patient_ref"] == expected and global_user["case_id"] != repeat["case_id"]
    log = db.scalars(select(AuditLog).where(AuditLog.action == "image_uploaded")).all()
    assert len(log) == 4 and all(
        row.detail == {"source_format": "dicom", "via": "stow"} for row in log
    )


def test_stow_invalid_requests(client, medico):
    bad = client.post(
        URL, headers=medico | {"Content-Type": "application/dicom"}, content=b"invalido"
    )
    assert bad.status_code == 400
    assert bad.json()["instancias"] == [] and bad.json()["fallos"][0]["indice"] == 1
    media, body = _multipart(("application/dicom", _dicom("PRUEBA", noise_pixels())))
    headers = medico | {"Content-Type": media}
    assert (
        client.post(URL, headers=headers, content=body.split(b"--instancias:eco--")[0]).status_code
        == 400
    )
    assert (
        client.post(
            URL, headers=medico | {"Content-Type": "application/json"}, content=b"{}"
        ).status_code
        == 415
    )


def test_simultaneous_stow_reuses_case(client, medico):
    headers = medico | {"Content-Type": "application/dicom"}
    instance = _dicom("PRUEBA", noise_pixels())

    def send():
        response = client.post(URL, headers=headers, content=instance)
        assert response.status_code == 200, response.text
        return response.json()["instancias"][0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(send)
        second = pool.submit(send)
        rows = sorted((first.result(), second.result()), key=lambda row: row["image_id"])
    assert rows[0]["case_id"] == rows[1]["case_id"]
    assert "exact_duplicate" not in rows[0]["qc_flags"]
    assert "exact_duplicate" in rows[1]["qc_flags"]
