"""Normal unsigned application initialization transport (not a login flow).

Static evidence: Net.postSync defaults false,false; PlutoAntispam.Input;
a0 URL rewriter /pluto/app/antispam -> /napi/user/antispam.
Native signA/signB transformations belong to bootstrap_native module.
"""
import http.client
import ssl
from urllib.parse import urlsplit
from .transport import java_encode
from .client import unwrap_response, SearchError


def exchange_sign_a(sign_a: str, common: dict[str, str], *, user_agent: str,
                    dp_ticket: str = '', timeout: float = 30,
                    host: str = 'https://www.kuaiduizuoye.com') -> dict:
    origin = urlsplit(host)
    if origin.scheme != 'https' or not origin.hostname or origin.username or origin.password or origin.path not in ('', '/') or origin.query or origin.fragment:
        raise ValueError('bootstrap host must be HTTPS origin')
    values = {'data': sign_a}
    for k, v in common.items():
        if k not in values:
            values[k] = v
    body = '&'.join(java_encode(k)+'='+java_encode(v) for k,v in values.items()).encode('ascii')
    headers = {'User-Agent':user_agent,'Dp-Ticket':dp_ticket,
               'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8',
               'X-Wap-Proxy-Cookie':'none','Accept-Encoding':'identity'}
    for v in headers.values():
        if any(ord(c)<32 or ord(c)>126 for c in v):
            raise ValueError('header must be printable ASCII')
    conn = http.client.HTTPSConnection(origin.hostname, origin.port or 443,
         timeout=timeout, context=ssl.create_default_context())
    try:
        conn.request('POST','/napi/user/antispam',body=body,headers=headers)
        response=conn.getresponse()
        data=response.read(1_000_001)
        if len(data)>1_000_000:
            raise ValueError('bootstrap response too large')
        if response.status!=200:
            raise SearchError(response.status,'bootstrap HTTP failed; no retry')
        result=unwrap_response(data)
        if not isinstance(result.get('data'),str) or not result['data']:
            raise ValueError('bootstrap did not return signB')
        return result
    finally:
        conn.close()
