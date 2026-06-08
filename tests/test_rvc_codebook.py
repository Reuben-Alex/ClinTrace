"""Tests for NHAMCS RVC codebook decoding."""

from verification.rvc_codebook import decode_rfv_code, decode_rfv_codes, load_rvc_codebook


def test_codebook_loads():
    df = load_rvc_codebook()
    assert len(df) > 100
    assert "variable" in df.columns
    assert "code" in df.columns
    assert "label" in df.columns


def test_decode_missing_returns_none():
    assert decode_rfv_code(-9) is None
    assert decode_rfv_code(0) is None


def test_decode_known_code():
    df = load_rvc_codebook()
    sample = df[df["variable"] == "RFV13D"].iloc[0]
    label = decode_rfv_code(int(sample["code"]))
    assert label == sample["label"]


def test_decode_rfv_codes_dedupes():
    code = load_rvc_codebook()
    row = code[code["variable"] == "RFV13D"].iloc[0]
    c = int(row["code"])
    labels = decode_rfv_codes(c, c, -9)
    assert len(labels) == 1
