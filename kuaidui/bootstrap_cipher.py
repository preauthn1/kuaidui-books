"""Statically reconstructed initialized-context bootstrap; no HTTP or native code.

Tables in des_tables.json are literal uint32 arrays extracted from the SO.
This is the library's DES-shaped LSB-first cipher, not standard DES bytes.
Only feed set_token an actual server signB; no substitute server reply is made.
"""
from pathlib import Path
import json,secrets,string
from .native import _md5,_mutf8
T=json.loads(Path(__file__).with_name('des_tables.json').read_text())

def _bits(data): return [(v>>i)&1 for v in data for i in range(8)]
def _perm(bits,table): return [bits[i] for i in table]
def _pack(bits): return bytes(sum(bits[j+i]<<i for i in range(8)) for j in range(0,len(bits),8))
def _keys(key):
 if len(key)!=8: raise ValueError('cipher key must be 8 bytes')
 x=_perm(_bits(key),T['PC1']); keys=[]
 for n in T['SHIFT']:
  a,b=x[:28],x[28:];x=a[n:]+a[:n]+b[n:]+b[:n]
  keys.append(_perm(x,T['PC2']))
 return keys

def cipher_block(block,key,*,decrypt=False):
 if len(block)!=8: raise ValueError('block must be 8 bytes')
 x=_perm(_bits(block),T['IP']);left,right=x[:32],x[32:]
 keys=_keys(key)
 if decrypt: keys=keys[::-1]
 for k in keys:
  e=[a^b for a,b in zip(_perm(right,T['E']),k)];s=[]
  for box in range(8):
   z=e[box*6:box*6+6]
   row=2*z[0]+z[5];col=8*z[1]+4*z[2]+2*z[3]+z[4]
   v=T['SBOX'][box*64+row*16+col]
   s.extend((v>>i)&1 for i in (3,2,1,0))
  f=_perm(s,T['P'])
  left,right=right,[a^b for a,b in zip(left,f)]
 return _pack(_perm(right+left,T['FP']))

def encrypt(data,key):
 # 0x3f78–0x3f98: zero-fill then last-byte count (NOT PKCS#7).
 n=8-len(data)%8;data+=b'\0'*(n-1)+bytes([n])
 return b''.join(cipher_block(data[i:i+8],key) for i in range(0,len(data),8))
def decrypt(data,key):
 if not data or len(data)%8: raise ValueError('invalid ciphertext length')
 x=b''.join(cipher_block(data[i:i+8],key,decrypt=True) for i in range(0,len(data),8))
 n=x[-1]
 if not 1<=n<=8: raise ValueError('invalid padding count')
 # Native only uses last byte; we also reject malformed zero padding.
 if x[-n:-1]!=b'\0'*(n-1): raise ValueError('invalid zero padding')
 return x[:-n]

def _rev4(n): return ((n&1)<<3)|((n&2)<<1)|((n&4)>>1)|((n&8)>>3)
def encode_wire(data):
 # 0x30dc: each byte -> reversed low nibble then reversed high nibble,
 # each formatted as two hex digits, hence four wire chars per input byte.
 return ''.join(f'{_rev4(v&15):02x}{_rev4(v>>4):02x}' for v in data)
def decode_wire(text):
 if len(text)%4: raise ValueError('wire length not a multiple of 4')
 out=bytearray()
 for i in range(0,len(text),4):
  a,b=int(text[i:i+2],16),int(text[i+2:i+4],16)
  if a>15 or b>15: raise ValueError('wire nibbles must have a leading zero')
  out.append(_rev4(a)|(_rev4(b)<<4))
 return bytes(out)

PREFIX=b'8&%d*'
BOOTSTRAP_KEY=b'@fG2SuLA'

def make_sign_a(cuid: str, signature_chars: str, nonce: str | None=None) -> str:
 """nativeInitBaseUtil given Java Signature.toCharsString() and CUID.

 nonce is ten alphanumeric chars. Default uses secure randomness, not Android
 libc's weak srand(time+clock)/rand sequence; format and cipher are equivalent.
 No package name/device model is included in this plaintext.
 """
 if nonce is None: nonce=''.join(secrets.choice(string.ascii_uppercase+string.ascii_lowercase+string.digits) for _ in range(10))
 if len(nonce)!=10 or any(c not in string.ascii_letters+string.digits for c in nonce): raise ValueError('nonce must be 10 ASCII alphanumerics')
 c=_mutf8(cuid);sig=_mutf8(signature_chars)
 plaintext=PREFIX+b'##'+nonce.encode()+b'##'+_md5(sig)+b'##'+c
 return encode_wire(encrypt(plaintext,BOOTSTRAP_KEY))

def set_token(sign_a: str, sign_b: str, *, cuid: str, signature_chars: str) -> bytes:
 """Validate real bootstrap strings and recover native's ten-byte token.

 Implements nativeSetToken's success path, with stricter malformed-input checks
 rather than reproducing unsafe allocations/out-of-bounds reads.
 """
 a=decrypt(decode_wire(sign_a),BOOTSTRAP_KEY)
 if len(a)<53: raise ValueError('signA plaintext too short')
 nonce=a[7:17]
 if len(nonce)!=10 or b'\0' in nonce: raise ValueError('bad nonce')
 if a[53:]!=_mutf8(cuid): raise ValueError('CUID mismatch')
 if a[19:51]!=_md5(_mutf8(signature_chars)): raise ValueError('signature mismatch')
 b=decrypt(decode_wire(sign_b),nonce[:5]+b'#G4')
 if len(b)!=22 or b'\0' in b[:10] or b'\0' in b[12:]: raise ValueError('bad signB layout')
 if b[:10]!=nonce: raise ValueError('server nonce mismatch')
 return b[12:]
