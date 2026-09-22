"""Ordered image-only PDF export with atomic output and bounded downloads."""
import os
from pathlib import Path
import tempfile
import urllib.request
from urllib.parse import urlsplit


def images_to_pdf(images, output):
    """One image per page; JPEG data is embedded without recompression."""
    try:
        import img2pdf
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError('Install PDF support: pip install "kuaidui-books[pdf]"') from exc
    paths=[Path(p) for p in images]
    if not paths:raise ValueError('No images to export')
    for path in paths:
        if path.stat().st_size>25_000_000:raise ValueError('Image exceeds 25MB')
        with Image.open(path) as im:
            if getattr(im,'n_frames',1)!=1:raise ValueError('Multi-frame images are not supported')
            im.verify()
    output=Path(output).expanduser()
    if output.exists():raise FileExistsError('Output already exists')
    output.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.pdf-',dir=output.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            img2pdf.convert(*[str(p) for p in paths],outputstream=stream)
            stream.flush();os.fsync(stream.fileno())
        # Exclusive destination: never overwrite an existing user document.
        os.link(name,output)
        return {'path':str(output),'pages':len(paths),'bytes':output.stat().st_size}
    finally:
        if os.path.exists(name):os.unlink(name)


def export_book_pdf(book, output, *, timeout=45):
    """Download returned origin URLs in array order, then create a PDF.

    No cookies or authentication headers are sent to CDN hosts. Temporary
    images are deleted on both failure and success; partial PDF is not published.
    """
    if book.get('needLogin') or book.get('needVerify'):
        raise ValueError('Book requires login or verification')
    rows=book.get('answerList')
    if not isinstance(rows,list) or not rows:raise ValueError('No answer images returned')
    if Path(output).expanduser().exists():raise FileExistsError('Output already exists')
    # Fail before downloading if optional dependency is missing.
    try:
        import img2pdf
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError('Install PDF support: pip install "kuaidui-books[pdf]"') from exc
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(NoRedirect)
    total=0
    with tempfile.TemporaryDirectory(prefix='kuaidui-pdf-') as tmp:
        paths=[]
        for i,row in enumerate(rows,1):
            url=row.get('origin',''); parsed=urlsplit(url)
            if parsed.scheme!='https' or parsed.username or parsed.password or parsed.hostname not in ('kd-book.cdnjtzy.com','img.zuoyebang.cc','cdn.kuaiduizuoye.com'):
                raise ValueError(f'Unsupported resource origin at page {i}')
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            with opener.open(req,timeout=timeout) as response:
                data=response.read(25_000_001)
            if len(data)>25_000_000:raise ValueError(f'Image too large at page {i}')
            total+=len(data)
            if total>1_000_000_000:raise ValueError('Book exceeds 1GB download limit')
            path=Path(tmp)/f'{i:06d}.img';path.write_bytes(data)
            with Image.open(path) as im:
                if row.get('w') and row.get('h') and im.size!=(row['w'],row['h']):
                    raise ValueError(f'Dimensions mismatch at page {i}')
                im.verify()
            paths.append(path)
        return images_to_pdf(paths,output)
