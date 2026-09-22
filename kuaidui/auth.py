"""Normal SMS authentication; no retries or credential logging."""
import base64
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import tempfile
import time
import uuid
from .bootstrap import exchange_sign_a
from .bootstrap_native import make_sign_a, set_token
from .native import sign_parameter_list, derive_rc4_key
from .codec import rc4, decode_field
from .transport import java_encode
from .client import unwrap_response, SearchError

class LoginRequired(RuntimeError):
    pass


def save_session(path, session):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.session-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(session, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def initialize():
    profile = json.loads(Path(__file__).with_name('app_profile.json').read_text())
    common = dict(cuid=uuid.uuid4().hex.upper()+'|0', token=profile['app_token'],
                  vc='1690', vcname='6.98.0', channel='10003e4', os='android',
                  sdk='30', device='ProtocolTest', pkgName='com.kuaiduizuoye.scan',
                  appId='scancode', operatorid='', osVersion='11', brand='ProtocolTest',
                  abis='0', appBit='32', isPad='0')
    ua = 'Mozilla/5.0 (Linux; Android 11; ProtocolTest Build/TEST; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/83.0.4103.106 Mobile Safari/537.36'
    a = make_sign_a(common['cuid'], profile['certificate_hex'])
    reply = exchange_sign_a(a, common, user_agent=ua)
    token = set_token(a, reply['data'], cuid=common['cuid'], signature_chars=profile['certificate_hex'])
    return dict(common=common, user_agent=ua, native_token=token.decode('ascii'),
                init_elapsed_realtime_ms=int(time.monotonic()*1000))


def request(session, host, path, params, *, encrypted=False):
    key = derive_rc4_key(session['common']['vc'], session['native_token'])
    if encrypted:
        inner='&'+'&'.join(k+'='+java_encode(str(v)) for k,v in params.items())
        params={'data':base64.b64encode(rc4(inner.encode(),key)).decode()}
    values={**session['common'], **{k:str(v) for k,v in params.items()}, 'nt':'wifi'}
    signature=sign_parameter_list([k+'='+v for k,v in values.items()],session['native_token'],server_seconds=int(time.time()),init_elapsed_realtime_ms=session['init_elapsed_realtime_ms'])
    body=('&'+'&'.join(k+'='+java_encode(v) for k,v in values.items())+'&sign='+signature).encode()
    cookie='cuid='+java_encode(values['cuid'])
    if session.get('kduss'):cookie+='; KDUSS='+java_encode(session['kduss'])
    conn=http.client.HTTPSConnection(host,timeout=30,context=ssl.create_default_context())
    try:
        conn.request('POST',path,body=body,headers={'User-Agent':session['user_agent'],'Cookie':cookie,'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','Accept-Encoding':'identity','X-Wap-Proxy-Cookie':'none','Dp-Ticket':session.get('dp_ticket','')})
        response=conn.getresponse(); raw=response.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('response too large')
        if response.status!=200:raise SearchError(response.status,'authentication HTTP error')
        result=unwrap_response(raw)
        if isinstance(result.get('data'),str):
            result=json.loads(decode_field(result['data'],key))
        return result
    finally:conn.close()


def normalize_phone(phone):
    # Explicit mainland-China scope, not a generic international login parser.
    if re.fullmatch(r'\+861\d{10}',phone):return phone[3:]
    if re.fullmatch(r'1\d{10}',phone):return phone
    raise ValueError('手机号须为11位中国大陆号码，或 +86 前缀')


def send_sms(session, phone):
    return request(session,'passport.kuaiduizuoye.com','/session/submit/tokengettokenv2',{'phone':normalize_phone(phone)})


def login_sms(session, phone, code):
    if not re.fullmatch(r'\d{4,8}',code):raise ValueError('验证码格式错误')
    data=request(session,'www.kuaiduizuoye.com','/session/submit/tokenloginv2',dict(phone=normalize_phone(phone),tokenCode=code,inviteCode='',idfa='',yongsterStatus=0))
    if not isinstance(data.get('kduss'),str) or not data['kduss']:raise LoginRequired('登录未返回有效凭证')
    return {**session,'kduss':data['kduss']}


def check_session(session):
    if not session.get('kduss'):return False
    data=request(session,'www.kuaiduizuoye.com','/kdcore/user/userinfov3',dict(getAchievement=0,isHitCoupon=0,scenePage='other'),encrypted=True)
    return bool(data.get('uid') or data.get('userId'))
