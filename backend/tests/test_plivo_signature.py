"""app.providers.telephony.plivo_signature - real X-Plivo-Signature-V3
validation. test_string_matches_plivo_s_own_documented_worked_example
uses the exact URL/params from Plivo's own official docs page
(https://www.plivo.com/docs/voice/concepts/signature-validation) as a
real, sourced test vector - not invented."""

import base64
import hashlib
import hmac

from app.providers.telephony.plivo_signature import (
    build_signed_string,
    compute_v3_signature,
    validate_v3_signature,
)


def test_string_matches_plivo_s_own_documented_worked_example():
    url = "https://example.com/abcd?foo=bar"
    params = {
        "Digits": "1234",
        "To": "+15555555555",
        "From": "+15551111111",
        "CallUUID": "4vbcpem8-0u46-x1ha-9af1-438vc92bf374",
    }
    nonce = "kjsdhfsd87sd7yisud2"

    signed_string = build_signed_string(url, params, nonce)

    assert signed_string == (
        "https://example.com/abcd?foo=bar."
        "CallUUID4vbcpem8-0u46-x1ha-9af1-438vc92bf374"
        "Digits1234"
        "From+15551111111"
        "To+15555555555"
        ".kjsdhfsd87sd7yisud2"
    )


def test_params_are_sorted_alphabetically_by_name_not_insertion_order():
    signed_string = build_signed_string(
        "https://example.com/x", {"Zeta": "1", "Alpha": "2"}, "n"
    )
    # Alpha (A) must come before Zeta (Z) regardless of dict insertion order.
    assert signed_string == "https://example.com/x.Alpha2Zeta1.n"


def test_compute_v3_signature_matches_a_manually_computed_hmac():
    url = "https://example.com/abcd?foo=bar"
    params = {"To": "+15555555555"}
    nonce = "nonce123"
    auth_token = "my-auth-token"

    signature = compute_v3_signature(url, params, nonce, auth_token)

    expected_string = build_signed_string(url, params, nonce)
    expected_digest = hmac.new(
        auth_token.encode("utf-8"), expected_string.encode("utf-8"), hashlib.sha256
    ).digest()
    expected_signature = base64.b64encode(expected_digest).decode("ascii")
    assert signature == expected_signature


def test_validate_accepts_a_real_matching_signature():
    url = "https://example.com/telephony/plivo/answer"
    params = {"CallUUID": "abc-123", "From": "+919876543210"}
    nonce = "real-nonce"
    auth_token = "real-secret-token"
    real_signature = compute_v3_signature(url, params, nonce, auth_token)

    assert validate_v3_signature(url, params, nonce, auth_token, real_signature) is True


def test_validate_rejects_a_tampered_parameter():
    url = "https://example.com/telephony/plivo/answer"
    params = {"CallUUID": "abc-123", "From": "+919876543210"}
    nonce = "real-nonce"
    auth_token = "real-secret-token"
    real_signature = compute_v3_signature(url, params, nonce, auth_token)

    tampered_params = {"CallUUID": "abc-123", "From": "+911111111111"}  # attacker-modified
    assert validate_v3_signature(url, tampered_params, nonce, auth_token, real_signature) is False


def test_validate_rejects_the_wrong_auth_token():
    url = "https://example.com/x"
    params = {"a": "1"}
    nonce = "n"
    real_signature = compute_v3_signature(url, params, nonce, "correct-token")

    assert validate_v3_signature(url, params, nonce, "wrong-token", real_signature) is False


def test_validate_rejects_an_empty_or_missing_signature_header():
    assert validate_v3_signature("https://x", {}, "n", "token", "") is False
    assert validate_v3_signature("https://x", {}, "n", "token", None) is False


def test_validate_accepts_a_match_within_a_comma_separated_multi_token_list():
    """Plivo sends a comma-separated list of signatures when more than one
    Auth Token is active on the account - a match against any is valid."""
    url = "https://example.com/x"
    params = {"a": "1"}
    nonce = "n"
    real_signature = compute_v3_signature(url, params, nonce, "token-2")
    header = f"garbage-signature-from-token-1,{real_signature}"

    assert validate_v3_signature(url, params, nonce, "token-2", header) is True
