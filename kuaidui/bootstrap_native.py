"""Reviewed bootstrap API. Offline only; no native execution or network access.

Uses the literal nonstandard DES PC2 table in bootstrap.py/des_tables.json.
A decoded signB is structurally/identity validated, not proof of server origin.
The caller MUST supply signB obtained from the real HTTPS exchange or app cache.
"""
import string
from .bootstrap_cipher import (BOOTSTRAP_KEY, PREFIX, cipher_block, encrypt, decrypt,
                       encode_wire, decode_wire, make_sign_a as _make_sign_a)
from .native import _md5, _mutf8

ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits
MAX_WIRE = 65536


def nonce_from_rand_values(values):
    """Exact 0x2b20 mapping of ten already-observed libc rand() return values.

    Native seeds srand((time(NULL)+clock()) mod 2**32). The underlying libc
    PRNG is not inside libbaseutil; supplying a nonce avoids guessing its state.
    """
    values = tuple(values)
    if len(values) != 10 or any(type(v) is not int or not 0 <= v <= 0x7fffffff for v in values):
        raise ValueError('need ten nonnegative signed-32-bit rand values')
    return ''.join(ALPHABET[v % 62] for v in values)


def signature_chars_from_der(certificate_der):
    """Android Signature.toCharsString for the first package signature's DER.

    Supply the actual signer certificate bytes, NOT its fingerprint or APK hash.
    Does not independently verify the APK signature or identify its first signer.
    """
    if not isinstance(certificate_der, bytes) or not certificate_der:
        raise ValueError('nonempty DER bytes required')
    return certificate_der.hex()


def make_sign_a(cuid, signature_chars, nonce=None):
    if len(_mutf8(cuid)) > 8192 or len(_mutf8(signature_chars)) > 32768:
        raise ValueError('identity input exceeds defensive size limit')
    return _make_sign_a(cuid, signature_chars, nonce)


def _wire(text):
    if not isinstance(text, str) or not text or len(text) > MAX_WIRE or len(text) % 32:
        raise ValueError('wire must contain complete encrypted blocks')
    if any(c not in string.hexdigits for c in text):
        raise ValueError('wire contains nonhex characters')
    return decode_wire(text)


def validate_sign_a(sign_a, *, cuid, signature_chars):
    """Return nonce after native identity checks plus canonical framing checks."""
    a = decrypt(_wire(sign_a), BOOTSTRAP_KEY)
    if len(a) < 53 or b'\0' in a:
        raise ValueError('bad signA length or embedded C terminator')
    if a[:7] != PREFIX + b'##' or a[17:19] != b'##' or a[51:53] != b'##':
        raise ValueError('bad signA framing')
    nonce = a[7:17]
    if any(c not in ALPHABET.encode('ascii') for c in nonce):
        raise ValueError('bad nonce alphabet')
    if a[19:51] != _md5(_mutf8(signature_chars)):
        raise ValueError('signature mismatch')
    if a[53:] != _mutf8(cuid):
        raise ValueError('CUID mismatch')
    return nonce


def set_token(sign_a, sign_b, *, cuid, signature_chars):
    """Decode a genuine server/cache signB; never synthesize a replacement.

    Native checks signB strlen == 22, nonce length == 10, token length == 10,
    and equality of the nonce. We also forbid NUL in its skipped separator.
    Native DOES NOT check the two separator bytes equal '##', so neither do we.
    """
    nonce = validate_sign_a(sign_a, cuid=cuid, signature_chars=signature_chars)
    b = decrypt(_wire(sign_b), nonce[:5] + b'#G4')
    if len(b) != 22 or b'\0' in b:
        raise ValueError('bad signB length or embedded C terminator')
    if b[:10] != nonce:
        raise ValueError('server nonce mismatch')
    return b[12:22]
