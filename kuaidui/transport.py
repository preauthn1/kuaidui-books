"""Offline-first single-question request builder, statically traced from APK 6.98.0.

No native signer, device identity generation, account acquisition, or response
unlocking. Caller supplies legitimately obtained identity/ticket/session values
and a signer accepting unescaped key=value strings. See README.md for evidence
and unresolved Java HashMap ordering / MIME implementation details.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import http.client
import re
import secrets
import ssl
from typing import Callable, Mapping, Sequence
from urllib.parse import parse_qsl, quote_plus, urlsplit

SINGLE_PATH = "/picsearch/submit/singlesearch"
COLLEGE_PATH = "/kdtools/collegesearch/singlesearch"
FORBIDDEN = frozenset({"imei", "_imei", "imsi", "_imsi", "oaid", "_oaid"})
# Observed client population, NOT a claim that every field is server-required.
OBSERVED_COMMON = frozenset("cuid channel token vc vcname os sdk device pkgName operatorid appId province city area osVersion brand abis appBit adid phoneDevice identityIdV2 occupationType isPad digGrade".split())


def java_encode(value: str | None) -> str:
    """Java URLEncoder UTF-8: space -> +, * safe, ~ -> %7E; null -> null."""
    if value is None:
        return "null"
    return quote_plus(value, safe="*-._", encoding="utf-8").replace("~", "%7E")


def _scalar(value: str | int | None) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def page_from(source: str | None) -> str:
    return {"home": "homePage", "overScreen": "overScreen", "historyResult": "historyResult", "history_result_again": "historyResult"}.get(source or "", "otherPage")


@dataclass(frozen=True)
class PreparedRequest:
    url: str
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)
    signing_items: tuple[str, ...] = field(repr=False)
    encoded_query: str = field(repr=False)
    fields: tuple[tuple[str, str], ...] = field(repr=False)
    method: str = "POST"


def prepare_single_search(
    image: bytes, *, common: Mapping[str, str], signer: Callable[[Sequence[str]], str],
    user_agent: str, dp_ticket: str, ref: int, referer: int, grade: int,
    abtest: str, source: str | None, kduss: str | None = None,
    page_extra_info: str = "", host: str = "https://www.kuaiduizuoye.com",
    nt: str = "wifi", college: bool = False, boundary: str | None = None,
    signing_key_order: Sequence[str] | None = None,
) -> PreparedRequest:
    """Build only; does not send. Common values are raw, not URL-encoded.

    signing_key_order can reproduce a captured Java iteration order; without it
    use insertion order (not claimed identical to Android HashMap order).
    Signer must implement the native contract; no fallback bogus signature.
    The encoded intermediate query is decoded back to multipart text fields,
    exactly as HWRequest.setUrl does. The transmitted URL has NO query.
    """
    if not isinstance(image, bytes) or not image:
        raise ValueError("image must be nonempty original bytes")
    parsed = urlsplit(host)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("host must be an HTTPS origin without credentials/path")
    if nt not in ("wifi", "mobile"):
        raise ValueError("nt must be wifi or mobile")
    if "cuid" not in common or "token" not in common:
        raise ValueError("supply your own cuid and app token")
    values = {"picMD5": hashlib.md5(image).hexdigest().upper(), "shumei": "", "ref": ref,
              "pageExtraInfo": page_extra_info, "referer": referer, "isStudentMode": 1,
              "grade": grade, "from": page_from(source), "abtest": abtest}
    for key, value in common.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("invalid common key")
        if key.lower() in FORBIDDEN:
            raise ValueError("forbidden device identifier parameter")
        if key in ("sign", "nt", "_t_", "kakorrhaphiophobia"):
            raise ValueError("sign and nt are managed by the builder")
        if not isinstance(value, str):
            raise TypeError("common values must be strings")
        if key not in values:  # InputBase params take precedence over common.
            values[key] = value
    values["nt"] = nt
    raw = {key: _scalar(value) for key, value in values.items()}
    keys = list(signing_key_order) if signing_key_order is not None else list(raw)
    if len(keys) != len(raw) or set(keys) != set(raw):
        raise ValueError("signing_key_order must contain each effective key once")
    signing_items = tuple(key + "=" + raw[key] for key in keys)
    signature = signer(signing_items)
    # Java appends signature verbatim; only accept query-safe output here.
    if not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{32}&_t_=[0-9]+&kakorrhaphiophobia=[0-9]+", signature):
        raise ValueError("signer must return native digest plus _t_ and kakorrhaphiophobia")
    query = "&" + "&".join(key + "=" + java_encode(value) for key, value in raw.items()) + "&sign=" + signature
    fields = tuple(parse_qsl(query, keep_blank_values=True, encoding="utf-8"))
    boundary = boundary or ''.join(secrets.choice('-_1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(30 + secrets.randbelow(11)))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,70}", boundary):
        raise ValueError("invalid multipart boundary")
    if any(boundary.encode() in blob for blob in [image] + [v.encode() for _, v in fields]):
        raise ValueError("multipart boundary collides with content")
    pieces: list[bytes] = []
    def part(name: str, payload: bytes, filename: str | None, content_type: str, transfer: str) -> None:
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        pieces.append((f"--{boundary}\r\n{disposition}\r\nContent-Type: {content_type}\r\nContent-Transfer-Encoding: {transfer}\r\n\r\n").encode("ascii"))
        pieces.extend([payload, b"\r\n"])
    part("image", image, "image", "application/octet-stream", "binary")
    for key, value in fields:
        part(key, value.encode("utf-8"), None, "text/plain; charset=UTF-8", "8bit")
    pieces.append(f"--{boundary}--\r\n".encode("ascii"))
    body = b"".join(pieces)
    cookies = ["cuid=" + java_encode(common["cuid"])]
    if kduss:
        cookies.append("KDUSS=" + java_encode(kduss))
    headers = {"Accept-Encoding": "identity", "X-Wap-Proxy-Cookie": "none",
               "Cookie": "; ".join(cookies), "User-Agent": user_agent, "Dp-Ticket": dp_ticket,
               "Content-Type": "multipart/form-data; boundary=" + boundary,
               "Content-Length": str(len(body))}
    for value in headers.values():
        if not isinstance(value, str) or any(ord(c) < 32 or ord(c) >= 127 for c in value):
            raise ValueError("headers must contain printable ASCII only")
    return PreparedRequest(host.rstrip("/") + (COLLEGE_PATH if college else SINGLE_PATH), headers, body, signing_items, query, fields)


def send_prepared(request: PreparedRequest, *, allow_network: bool = False,
                  timeout: float = 30, max_response_bytes: int = 8 * 1024 * 1024) -> tuple[int, Mapping[str, str], bytes]:
    """Explicit opt-in HTTPS POST, no redirects/retries, bounded response bytes.

    Not exercised against any endpoint. Return raw status/headers/body; do not
    interpret encrypted fields, evade account checks, or auto-retry submissions.
    """
    if not allow_network:
        raise PermissionError("network disabled; explicit authorization required")
    parsed = urlsplit(request.url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("HTTPS URL required")
    if request.method != "POST" or parsed.path not in (SINGLE_PATH, COLLEGE_PATH) or parsed.query or parsed.fragment:
        raise ValueError("only prepared single-search paths are supported")
    if max_response_bytes <= 0 or timeout <= 0:
        raise ValueError("positive limits required")
    connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=timeout, context=ssl.create_default_context())
    try:
        connection.request("POST", parsed.path, body=request.body, headers=dict(request.headers))
        response = connection.getresponse()
        body = response.read(max_response_bytes + 1)
        if len(body) > max_response_bytes:
            raise ValueError("response exceeds configured size limit")
        return response.status, dict(response.getheaders()), body
    finally:
        connection.close()
