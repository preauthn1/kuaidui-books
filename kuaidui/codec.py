"""Pure Python answer decoding, recovered from Kuaidui Android 6.98.0.
Evidence: utils/decrypt/c.java lines 1231-1244, 1518-1530;
com/baidu/android/common/security/RC4.java.
No native library or ARM emulator is used.
"""
import base64
import binascii
import copy
import io
import gzip


def rc4(data: bytes, key: bytes | str) -> bytes:
    if isinstance(key, str):
        key = key.encode('utf-8')
    if not key:
        raise ValueError('RC4 key must not be empty')
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) & 255
        state[i], state[j] = state[j], state[i]
    x = y = 0
    result = bytearray(len(data))
    for n, value in enumerate(data):
        x = (x + 1) & 255
        y = (y + state[x]) & 255
        state[x], state[y] = state[y], state[x]
        result[n] = value ^ state[(state[x] + state[y]) & 255]
    return bytes(result)


def decode_field(value: str, key: bytes | str | None = None,
                 compressed: bool = False, max_output: int = 16_000_000) -> str:
    if not value:
        return ''
    # Android Base64 accepts omitted padding and whitespace; malformed input
    # follows the Java helper's fallback to the original UTF-8 bytes.
    raw = ''.join(value.split()).encode('utf-8')
    try:
        data = base64.b64decode(raw + b'=' * (-len(raw) % 4), validate=True)
    except (binascii.Error, ValueError):
        data = value.encode('utf-8')
    if key is not None:
        data = rc4(data, key)
    if compressed:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(max_output + 1)
    if len(data) > max_output:
        raise ValueError('decoded answer exceeds output limit')
    return data.decode('utf-8', errors='replace')


def decode_single_result(result: dict, key: bytes | str | None = None) -> dict:
    """Decode the *data object*, not the HTTP envelope, without modifying input.

    encode == 1: Base64 (+ optional gzip), no RC4.
    otherwise: Base64 -> RC4 with application key.
    encryption == 1 additionally wraps each page using its decrypted tid.
    """
    decoded = copy.deepcopy(result)
    answers = decoded.get('answers')
    if not isinstance(answers, dict):
        raise ValueError('missing answers object; this is not a successful search result')
    tids = answers.get('tids', [])
    pages = answers.get('mainPageInfo', [])
    if not isinstance(tids, list) or not isinstance(pages, list):
        raise ValueError('tids and mainPageInfo must be arrays')
    zipped = answers.get('gzip', 0) == 1
    if decoded.get('encode', 0) == 1:
        answers['tids'] = [decode_field(t) for t in tids]
        answers['mainPageInfo'] = [decode_field(p, compressed=zipped) for p in pages]
    else:
        if not key:
            raise ValueError('application RC4 key required for encode != 1')
        if answers.get('encryption', 0) == 1:
            # The original helper returns immediately when either list is empty.
            if not tids or not pages:
                return decoded
            tids = [decode_field(t, key) for t in tids]
            answers['tids'] = tids
            for index in range(min(len(tids), len(pages))):
                inner = decode_field(pages[index], tids[index])
                pages[index] = decode_field(inner, key, zipped)
            answers['mainPageInfo'] = pages
        else:
            answers['tids'] = [decode_field(t, key) for t in tids]
            answers['mainPageInfo'] = [decode_field(p, key, zipped) for p in pages]
    return decoded
