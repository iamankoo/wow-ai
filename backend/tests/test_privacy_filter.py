from app.learning.privacy_filter import RegexPrivacyFilter


def test_redacts_phone_number():
    r = RegexPrivacyFilter().redact("Call me at +91 98765 43210 please.")
    assert "98765" not in r.redacted_text
    assert r.was_modified
    assert "phone_number" in r.redaction_types


def test_redacts_email():
    r = RegexPrivacyFilter().redact("My email is aniket.raj@example.com, reply there.")
    assert "aniket.raj@example.com" not in r.redacted_text
    assert "email" in r.redaction_types


def test_redacts_otp_near_keyword():
    r = RegexPrivacyFilter().redact("The OTP is 483920, please confirm.")
    assert "483920" not in r.redacted_text
    assert "otp_or_pin" in r.redaction_types


def test_clean_text_is_not_modified():
    text = "I am busy right now, take messages instead."
    r = RegexPrivacyFilter().redact(text)
    assert r.redacted_text == text
    assert r.was_modified is False
    assert r.redaction_types == []


def test_short_name_only_text_is_not_modified():
    r = RegexPrivacyFilter().redact("Call Rahul for me.")
    assert r.was_modified is False
