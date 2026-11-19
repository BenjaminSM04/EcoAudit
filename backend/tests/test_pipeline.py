from __future__ import annotations

import io
import json

import numpy as np
import pytest
from PIL import Image

from app.pipeline.bundle import BundleError, ModelBundle, bundle_sha256, read_card
from app.pipeline.imaging import ImageDecodeError, decode_upload
from app.pipeline.quality import dhash, hamming, quality_flags
from app.pipeline.runner import RoiError, analyze, resolve_roi, sigmoid

from .conftest import noise_pixels


# ------------------------------------------------------------------ ingesta
def test_jpeg_with_exif_is_reencoded_without_metadata():
    image = Image.fromarray(noise_pixels())
    exif = Image.Exif()
    exif[0x010F] = "Fabricante secreto"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)

    decoded = decode_upload(buffer.getvalue(), "eco.jpg")

    assert decoded.source_format == "jpeg"
    assert b"Fabricante secreto" not in decoded.png_bytes
    assert not Image.open(io.BytesIO(decoded.png_bytes)).getexif()
    assert decoded.pixels.ndim == 2  # gris: se guarda un solo canal


def test_dicom_keeps_pixels_and_drops_patient_tags():
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    pixels = noise_pixels(size=160)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.6.1"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset("x.dcm", {}, file_meta=meta, preamble=b"\0" * 128)
    ds.PatientName = "PEREZ^JUANA"
    ds.PatientID = "CI-1234567"
    ds.Rows, ds.Columns = pixels.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = pixels.tobytes()
    buffer = io.BytesIO()
    ds.save_as(buffer)

    decoded = decode_upload(buffer.getvalue(), "estudio.dcm")

    assert decoded.source_format == "dicom"
    assert np.array_equal(decoded.pixels, pixels)
    assert b"PEREZ" not in decoded.png_bytes and b"1234567" not in decoded.png_bytes


def test_non_image_is_rejected():
    with pytest.raises(ImageDecodeError):
        decode_upload(b"esto no es una imagen", "notas.txt")


# ------------------------------------------------------------------ calidad
def test_dhash_detects_near_duplicates_and_separates_different_images():
    original = noise_pixels(seed=1)
    smooth = np.asarray(Image.fromarray(original).resize((64, 64)).resize((256, 256)))
    brighter = np.clip(smooth.astype(np.int16) + 12, 0, 255).astype(np.uint8)
    other = np.asarray(
        Image.fromarray(noise_pixels(seed=2)).resize((64, 64)).resize((256, 256))
    )

    assert hamming(dhash(smooth), dhash(brighter)) <= 4
    assert hamming(dhash(smooth), dhash(other)) > 10


def test_quality_flags():
    assert "low_resolution" in quality_flags(noise_pixels(size=64))
    assert "low_contrast" in quality_flags(np.full((256, 256), 90, dtype=np.uint8))
    assert quality_flags(noise_pixels()) == []


# ------------------------------------------------------------------ ROI
def test_resolve_roi_applies_margin_and_clamps():
    assert resolve_roi(None, 200, 100, 0.1) == (0, 0, 200, 100)
    assert resolve_roi({"x": 50, "y": 20, "w": 100, "h": 50}, 200, 100, 0.1) == (40, 15, 160, 75)
    assert resolve_roi({"x": 0, "y": 0, "w": 100, "h": 50}, 200, 100, 0.5) == (0, 0, 150, 75)


@pytest.mark.parametrize(
    "roi",
    [
        {"x": 150, "y": 0, "w": 100, "h": 50},  # se sale por la derecha
        {"x": 0, "y": 0, "w": 2, "h": 2},  # degenerado
        {"x": 0, "y": 0, "w": "a", "h": 5},
        {"x": 0, "y": 0},
    ],
)
def test_resolve_roi_rejects_invalid(roi):
    with pytest.raises(RoiError):
        resolve_roi(roi, 200, 100, 0.0)


# ------------------------------------------------------------------ bundle y análisis
def test_bundle_self_check_and_hash_are_stable(demo_bundle_dir):
    bundle = ModelBundle(demo_bundle_dir)
    bundle.self_check()
    assert bundle_sha256(demo_bundle_dir) == bundle_sha256(demo_bundle_dir)


def test_bundle_with_wrong_head_fails_self_check(demo_bundle_dir, tmp_path):
    import shutil

    broken = tmp_path / "broken"
    shutil.copytree(demo_bundle_dir, broken)
    with np.load(broken / "member_0_head.npz") as head:
        np.savez(broken / "member_0_head.npz", weight=head["weight"] * 3.0, bias=head["bias"])
    with pytest.raises(BundleError, match="no coincide"):
        ModelBundle(broken).self_check()


def test_card_validation_rejects_bad_thresholds(demo_bundle_dir, tmp_path):
    import shutil

    broken = tmp_path / "broken"
    shutil.copytree(demo_bundle_dir, broken)
    card = json.loads((broken / "model_card.json").read_text("utf-8"))
    card["decision"] = {"abstain_low": 0.8, "abstain_high": 0.2}
    (broken / "model_card.json").write_text(json.dumps(card), "utf-8")
    with pytest.raises(BundleError, match="abstain"):
        read_card(broken)


def test_analysis_follows_protocol_rules(demo_bundle_dir):
    bundle = ModelBundle(demo_bundle_dir)
    rgb = np.stack([noise_pixels(seed=5)] * 3, axis=-1)

    result = analyze(rgb, None, bundle)

    prediction = bundle.predict(rgb)
    mean_logit = float(prediction.logits.mean())
    temperature = bundle.card["calibration"]["temperature"]
    assert result.probability_raw == pytest.approx(sigmoid(mean_logit))
    assert result.probability == pytest.approx(sigmoid(mean_logit / temperature))
    # La temperatura > 1 acerca la probabilidad a 0.5.
    assert abs(result.probability - 0.5) <= abs(result.probability_raw - 0.5)
    assert result.shift_flag is False
    assert "demo_model" in result.warnings

    overlay = Image.open(io.BytesIO(result.cam_overlay_png))
    assert overlay.mode == "RGBA" and overlay.size == (256, 256)


def test_out_of_domain_image_is_flagged_and_overrides_decision(demo_bundle_dir):
    bundle = ModelBundle(demo_bundle_dir)
    flat_white = np.full((256, 256, 3), 255, dtype=np.uint8)

    result = analyze(flat_white, None, bundle)

    assert result.shift_flag is True
    assert result.decision == "out_of_domain"
    assert "out_of_domain" in result.warnings


def test_roi_limits_the_cam_to_the_selected_region(demo_bundle_dir):
    bundle = ModelBundle(demo_bundle_dir)
    rgb = np.stack([noise_pixels(seed=7)] * 3, axis=-1)

    result = analyze(rgb, {"x": 100, "y": 100, "w": 80, "h": 60}, bundle)

    alpha = np.asarray(Image.open(io.BytesIO(result.cam_overlay_png)))[..., 3]
    assert alpha[:90, :].max() == 0 and alpha[:, :90].max() == 0  # fuera del ROI + margen
    assert alpha[92:168, 92:188].max() > 0
    assert "roi_not_expected" in result.warnings  # el demo se declara de imagen completa
