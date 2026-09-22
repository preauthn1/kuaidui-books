"""Book answer retrieval, statically traced from SearchBookSearch 6.98.0."""
import copy,json,re,time,http.client,ssl
from pathlib import Path
from .native import sign_parameter_list,derive_rc4_key
from .transport import java_encode
from .client import unwrap_response,SearchError
from .codec import decode_field

def book_id(value):
    m=re.fullmatch(r'(?:https://www\.kuaiduizuoye\.com/bookid)?([0-9a-f]{32})',value)
    if not m:raise ValueError('expected exact bookId or official book URL')
    return m.group(1)

def decode_book(data,key):
    d=copy.deepcopy(data)
    def fields(obj,names):
        for n in names:
            if isinstance(obj.get(n),str):obj[n]=decode_field(obj[n],key)
    fields(d,['name','primaryName','subName','cover','shareCover','originCover'])
    for n in ['answers','oriAnswers']:
        if isinstance(d.get(n),list):d[n]=[decode_field(x,key) for x in d[n]]
    for p in d.get('pageList',[]):
        fields(p,['thumbnail','url'])
        for n in ['locs','tids']:
            if isinstance(p.get(n),list):p[n]=[decode_field(x,key) for x in p[n]]
    for p in d.get('dayupInfo',{}).get('pageList',[]):fields(p,['url'])
    for p in d.get('offlineCase',{}).get('suggest',[]):fields(p,['cover','name'])
    for p in d.get('recommendList',[]):fields(p,['cover','primaryName','subName','name'])
    return d

class BookClient:
    def __init__(self,session):self.session=session
    @classmethod
    def from_session_file(cls,path):return cls(json.loads(Path(path).read_text()))
    def get_book(self,value,*,grade=0,resolution='',ticket='',rand_str='',timeout=30):
        s=self.session
        p={**s['common'],'bookId':book_id(value),'ticket':ticket,'randStr':rand_str,'isXposed':'0','isEmulator':'0','isHitDayup':'0','grade':str(grade),'resolution':resolution,'nt':'wifi'}
        from .codec import rc4
        import base64
        key=derive_rc4_key(p['vc'],s['native_token'])
        names=['bookId','ticket','randStr','isXposed','isEmulator','isHitDayup','grade','resolution']
        inner='&'+'&'.join(k+'='+java_encode(p[k]) for k in names)
        p={**s['common'],'data':base64.b64encode(rc4(inner.encode(),key)).decode(),'nt':'wifi'}
        sign=sign_parameter_list([k+'='+v for k,v in p.items()],s['native_token'],server_seconds=int(time.time()),init_elapsed_realtime_ms=s['init_elapsed_realtime_ms'])
        body=('&'+'&'.join(k+'='+java_encode(v) for k,v in p.items())+'&sign='+sign).encode()
        cookies='cuid='+java_encode(p['cuid'])
        if s.get('kduss'):cookies+='; KDUSS='+java_encode(s['kduss'])
        c=http.client.HTTPSConnection('www.kuaiduizuoye.com',timeout=timeout,context=ssl.create_default_context())
        try:
            c.request('POST','/search/submit/booksearch',body=body,headers={'User-Agent':s['user_agent'],'Cookie':cookies,'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','Accept-Encoding':'identity','X-Wap-Proxy-Cookie':'none','Dp-Ticket':s.get('dp_ticket','')})
            r=c.getresponse();raw=r.read(16000001)
            if len(raw)>16000000:raise ValueError('response exceeds limit')
            if r.status!=200:raise SearchError(r.status,'book request failed')
            data=unwrap_response(raw)
            if isinstance(data.get('data'),str):
                data=json.loads(decode_field(data['data'],key))
                return decode_book(data,key)
            return decode_book(data,key)
        finally:c.close()
