"""Real Plivo X-Plivo-Signature-V3 webhook validation - the exact
mechanism documented at https://www.plivo.com/docs/voice/concepts/signature-validation
(verified against that official page directly, not invented, not the
deprecated V2 scheme). No `plivo` SDK dependency: HMAC-SHA256 and
Base64 are both stdlib (`hmac`, `hashlib`, `base64`), and this project
avoids adding a vendor SDK dependency for one function when the
documented algorithm is simple enough to implement directly - the same
discipline already applied to app/media/audio_codec.py.

Signature generation, quoted from Plivo's own docs:

    Plivo signs all HTTP requests from its servers to your application
    server, and assembles the request to your application server by
    concatenating the final request URL (the full URL with the scheme,
    port, and query string) and any POST parameters. If your request is
    a POST, Plivo will take all the POST parameters, sort them
    alphabetically by name (using Unix-style case-sensitive sorting),
    and append the parameter name and value pairs to the end of the URL
    [...] The assembled request string [...] is then appended with a
    randomly generated nonce string [...] passed separately in the HTTP
    header X-Plivo-Signature-V3-Nonce [...] The output of this step is
    then signed using HMAC-SHA256 and your Plivo Auth Token as the key.
    The resulting signed hashes are Base64-encoded.

Worked example from that page (used directly as this module's test
vector): URL `https://example.com/abcd?foo=bar`, POST params
`Digits=1234, To=+15555555555, From=+15551111111,
CallUUID=4vbcpem8-0u46-x1ha-9af1-438vc92bf374` assemble (params sorted
alphabetically by name: CallUUID, Digits, From, To) to:

    https://example.com/abcd?foo=bar.CallUUID4vbcpem8-0u46-x1ha-9af1-438vc92bf374Digits1234From+15551111111To+15555555555
"""

import base64
import hashlib
import hmac


def build_signed_string(url: str, params: dict[str, str], nonce: str) -> str:
    """The exact string Plivo signs (see module docstring): the request
    URL, followed by each POST parameter's name and value concatenated in
    alphabetically-sorted-by-name order with no separators, followed by a
    "." and the nonce."""
    sorted_items = sorted(params.items(), key=lambda kv: kv[0])
    params_part = "".join(f"{name}{value}" for name, value in sorted_items)
    return f"{url}.{params_part}.{nonce}"


def compute_v3_signature(url: str, params: dict[str, str], nonce: str, auth_token: str) -> str:
    """HMAC-SHA256(auth_token, signed_string), Base64-encoded - exactly as
    documented. `auth_token` must come from Settings.plivo_auth_token
    (environment-sourced only - see app/config.py), never hardcoded."""
    signed_string = build_signed_string(url, params, nonce)
    digest = hmac.new(
        auth_token.encode("utf-8"), signed_string.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def validate_v3_signature(
    url: str, params: dict[str, str], nonce: str, auth_token: str, signature_header: str
) -> bool:
    """Real, constant-time comparison (hmac.compare_digest - never a plain
    `==` on secret-derived values, which would leak timing information)
    against the X-Plivo-Signature-V3 header. `signature_header` may
    legitimately be a comma-separated list (Plivo sends one signature per
    active Auth Token when more than one is active on the account) - a
    match against ANY of them is a valid signature, per Plivo's own
    documented behavior for that case."""
    if not signature_header:
        return False
    expected = compute_v3_signature(url, params, nonce, auth_token)
    candidates = [s.strip() for s in signature_header.split(",")]
    return any(hmac.compare_digest(expected, candidate) for candidate in candidates)
