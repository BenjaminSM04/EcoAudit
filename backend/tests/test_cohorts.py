import pytest

from app.routers.cohorts import summarize


def test_calibration_and_tied_auc():
    result = summarize({"a": (0, [0.25]), "b": (1, [0.25]), "c": (1, [0.75]), "d": (0, [0.75])})
    assert result["auc"] == 0.5
    assert result["brier"] == pytest.approx(0.3125)
    assert result["ece"] == pytest.approx(0.25)
    assert result["ci"][0] <= 0.5 <= result["ci"][1]


def test_grouping_uses_logits_and_preserves_patients():
    result = summarize({"p": (0, [0.1, 0.8]), "q": (1, [0.75])})
    assert result["patients"] == 2
    assert result["ci"] is None
    assert result["bins"][0]["predicted"] == pytest.approx(0.4)


def test_single_class_and_empty_cohort():
    for groups in ({}, {"p": (0, [0.3])}):
        with pytest.raises(ValueError):
            summarize(groups)


def test_csv_validation_and_authorization(client, admin, medico):
    for content in (
        b"",
        b"analysis_id,label\n",
        b"analysis_id,label\n-1,0",
        b"analysis_id,label\n1,benign",
        b"analysis_id,label\n1,1,2",
    ):
        assert (
            client.post(
                "/api/cohorts", headers=admin, files={"file": ("c.csv", content)}
            ).status_code
            == 422
        )
    assert (
        client.post("/api/cohorts", headers=medico, files={"file": ("c.csv", b"")}).status_code
        == 403
    )
