"""Static reconstruction of Kuaidui 6.98.0 libbaseutil.so.

No native execution/emulation. Requires the genuine 10-byte token established
by nativeSetToken; the APK does not contain a universal replacement token.
The caller is responsible for having completed valid initialization.
"""
import base64
import hashlib


def _md5(data: bytes) -> bytes:
    return hashlib.md5(data).hexdigest().encode('ascii')


def _token(token: str | bytes) -> bytes:
    value = token.encode('ascii') if isinstance(token, str) else bytes(token)
    if len(value) != 10 or b'\0' in value:
        raise ValueError('nativeSetToken supplies exactly 10 non-NUL token bytes')
    return value


def _mutf8(value: str) -> bytes:
    """JNI GetStringUTFChars encoding, including NUL/surrogate semantics."""
    raw = value.encode('utf-16-be', errors='surrogatepass')
    out = bytearray()
    for pos in range(0, len(raw), 2):
        c = int.from_bytes(raw[pos:pos + 2], 'big')
        if 0 < c < 128:
            out.append(c)
        elif c < 2048:
            out.extend((0xc0 | (c >> 6), 0x80 | (c & 63)))
        else:
            out.extend((0xe0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63)))
    return bytes(out)


def _swap_ends(data: bytes, pairs: int) -> bytes:
    out = bytearray(data)
    if pairs * 2 > len(out):
        raise ValueError('overlapping exchange not supported')
    for i in range(pairs):
        j = len(out) - 1 - i
        out[i], out[j] = out[j], out[i]
    return bytes(out)


def derive_rc4_key(version: str, token: str | bytes) -> str:
    """nativeGetKey on initialized state; current normal input is '1690'."""
    t = _token(token)
    if version == '0':
        return 'error'
    first = _md5(b'@#AIjd83#@6B')
    second = _md5(_mutf8(version))
    third = _swap_ends(_md5(b'[' + t + b']@'), 15)
    combined = _swap_ends(first + second + third, 3)
    return _swap_ends(combined + _md5(combined), 60).decode('ascii')


def native_get_sign(base64_params: str, token: str | bytes) -> str:
    """nativeGetSign on initialized state. Input is already Base64, not raw params."""
    return _md5(b'8&%d*[' + _md5(_token(token)) + b']@' + _mutf8(base64_params)).decode('ascii')


def sign_parameter_list(params: list[str], token: str | bytes, *,
                        server_seconds: int, init_elapsed_realtime_ms: int) -> str:
    """BaseUtil.e wrapper; no mutation of caller list; no guessed time/state.

    params must contain exactly the preprocessed strings collected by Net;
    this function intentionally does not guess query escaping/body inclusion.
    Java String ordering is UTF-16 code-unit ordering (not Unicode code points).
    """
    extras = [f'_t_={server_seconds}', f'kakorrhaphiophobia={init_elapsed_realtime_ms}']
    ordered = sorted([*params, *extras], key=lambda s: s.encode('utf-16-be', errors='surrogatepass'))
    joined = ''.join(ordered)
    # Normal well-formed Java strings: UTF-8 followed by Base64.NO_WRAP.
    payload = base64.b64encode(joined.encode('utf-8', errors='replace')).decode('ascii')
    return native_get_sign(payload, token) + '&' + '&'.join(extras)
