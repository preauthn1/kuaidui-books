"""Single-question client; explicit device/session context, no ARM runtime."""
from dataclasses import dataclass, field
import json
import time
from pathlib import Path
from .codec import decode_single_result
from .transport import prepare_single_search, send_prepared


class SearchError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f'search error {code}: {message}')


def unwrap_response(body: bytes) -> dict:
    envelope = json.loads(body)
    code = envelope.get('errNo', envelope.get('errno'))
    if code != 0:
        raise SearchError(code, envelope.get('errstr', 'missing success envelope'))
    data = envelope.get('data')
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise SearchError('schema', 'missing data object')
    return data


@dataclass
class Client:
    common: dict[str, str] = field(repr=False)
    native_token: str = field(repr=False)
    init_elapsed_realtime_ms: int
    user_agent: str
    dp_ticket: str = field(default='', repr=False)
    kduss: str | None = field(default=None, repr=False)
    server_time_offset_seconds: int = 0
    host: str = 'https://www.kuaiduizuoye.com'

    def prepare(self, image: bytes, *, ref: int, referer: int, grade: int,
                abtest: str = '', source: str = 'home', college: bool = False):
        from .native import sign_parameter_list
        seconds = int(time.time()) + self.server_time_offset_seconds
        def signer(items):
            return sign_parameter_list(list(items), self.native_token,
                server_seconds=seconds,
                init_elapsed_realtime_ms=self.init_elapsed_realtime_ms)
        return prepare_single_search(image, common=self.common, signer=signer,
            user_agent=self.user_agent, dp_ticket=self.dp_ticket, kduss=self.kduss,
            ref=ref, referer=referer, grade=grade, abtest=abtest,
            source=source, college=college, host=self.host)

    def search(self, image: bytes | str | Path, *, ref: int, referer: int,
               grade: int, abtest: str = '', source: str = 'home',
               college: bool = False, timeout: float = 30) -> dict:
        from .native import derive_rc4_key
        raw = image if isinstance(image, bytes) else Path(image).read_bytes()
        if len(raw) > 20_000_000:
            raise ValueError('image exceeds 20 MB limit')
        request = self.prepare(raw, ref=ref, referer=referer, grade=grade,
            abtest=abtest, source=source, college=college)
        status, headers, body = send_prepared(request, allow_network=True, timeout=timeout)
        if status != 200:
            raise SearchError(status, 'HTTP request failed; not retried')
        data = unwrap_response(body)
        key = derive_rc4_key(self.common['vc'], self.native_token)
        return decode_single_result(data, key)
