import pytest

from bastion.scanning import (
    SensitiveContentBlocked,
    contains_pii,
    enforce_text_policy,
    redact,
    scan_text,
)


def test_detects_email():
    findings = scan_text("contact me at a.b@example.com please")
    assert any(f.category == "email" and f.matched_text == "a.b@example.com" for f in findings)


def test_detects_ssn():
    findings = scan_text("ssn: 123-45-6789")
    assert any(f.category == "ssn_us" for f in findings)


def test_detects_valid_credit_card_via_luhn():
    # 4111111111111111 is the standard Visa test number, passes Luhn
    findings = scan_text("card 4111111111111111 on file")
    assert any(f.category == "credit_card" for f in findings)


def test_rejects_invalid_credit_card_number():
    # same length, fails Luhn check -> should not be flagged
    findings = scan_text("order number 1234567890123456", categories=["credit_card"])
    assert findings == []


def test_detects_aws_access_key():
    findings = scan_text("key is AKIAABCDEFGHIJKLMNOP", categories=["aws_access_key_id"])
    assert len(findings) == 1


def test_detects_private_key_block():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
    findings = scan_text(text, categories=["private_key_block"])
    assert len(findings) == 1


def test_scan_respects_category_filter():
    text = "email a@b.com and ssn 123-45-6789"
    findings = scan_text(text, categories=["email"])
    assert all(f.category == "email" for f in findings)


def test_unknown_category_raises():
    with pytest.raises(ValueError, match="unknown category"):
        scan_text("hello", categories=["not_a_real_category"])


def test_redact_replaces_matches():
    result = redact("email me at a@b.com", categories=["email"])
    assert "a@b.com" not in result
    assert "[REDACTED:email]" in result


def test_contains_pii_condition():
    cond = contains_pii(["email"])
    assert cond({"body": "reach me at a@b.com"}) is True
    assert cond({"body": "no sensitive data here"}) is False


def test_enforce_text_policy_blocks_by_default():
    with pytest.raises(SensitiveContentBlocked):
        enforce_text_policy("my email is a@b.com", categories=["email"])


def test_enforce_text_policy_redacts_when_requested():
    result = enforce_text_policy("my email is a@b.com", categories=["email"], on_detect="redact")
    assert "a@b.com" not in result


def test_enforce_text_policy_passthrough_when_clean():
    text = "nothing sensitive here"
    assert enforce_text_policy(text, categories=["email"]) == text


def test_enforce_text_policy_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown on_detect mode"):
        enforce_text_policy("a@b.com", categories=["email"], on_detect="ignore")
