"""Async facade; blocking stdlib network operations run in worker threads."""
import asyncio
import getpass
import json
from pathlib import Path
import sys
from . import auth
from .books import BookClient as SyncBookClient

DEFAULT_SESSION = '~/.config/kuaidui/session.json'

class BookClient:
    def __init__(self, session=DEFAULT_SESSION):
        self.path=Path(session).expanduser()
        self._session=None
        self._lock=asyncio.Lock()

    async def start(self, *, interactive=True):
        async with self._lock:
            if self.path.exists():
                self._session=json.loads(self.path.read_text())
                if await asyncio.to_thread(auth.check_session,self._session):return self
            if not interactive:raise auth.LoginRequired('有效登录态缺失；请运行 kuaidui login')
            if not sys.stdin.isatty():raise auth.LoginRequired('非交互终端；请先在终端运行 kuaidui login')
            phone=auth.normalize_phone(await asyncio.to_thread(input,'手机号（支持 +86）：'))
            state=await asyncio.to_thread(auth.initialize)
            await asyncio.to_thread(auth.send_sms,state,phone)
            print('验证码请求已接受。输入验证码；输入 r 并确认可重发。')
            while True:
                code=await asyncio.to_thread(getpass.getpass,'验证码（不回显）：')
                if code.lower()!='r':break
                confirm=await asyncio.to_thread(input,'再次发送短信？输入 yes 确认：')
                if confirm=='yes':await asyncio.to_thread(auth.send_sms,state,phone)
            state=await asyncio.to_thread(auth.login_sms,state,phone,code)
            if not await asyncio.to_thread(auth.check_session,state):raise auth.LoginRequired('登录后会话验证未通过')
            await asyncio.to_thread(auth.save_session,self.path,state)
            self._session=state
            return self

    async def status(self):
        if not self.path.exists():return False
        state=json.loads(self.path.read_text())
        return await asyncio.to_thread(auth.check_session,state)

    async def logout(self):
        async with self._lock:
            self.path.unlink(missing_ok=True)
            self._session=None

    async def get_book(self, value, **kwargs):
        if self._session is None:await self.start(interactive=False)
        result=await asyncio.to_thread(SyncBookClient(self._session).get_book,value,**kwargs)
        if result.get('needLogin'):raise auth.LoginRequired('服务端要求重新登录；请运行 kuaidui logout 后 login')
        if result.get('needVerify'):raise RuntimeError('服务端要求交互验证；未自动重试')
        return result
