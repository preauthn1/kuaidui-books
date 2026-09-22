"""Offline orchestration checks; synthetic auth, never sends SMS."""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch
from kuaidui import BookClient, LoginRequired

async def check():
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'session.json';client=BookClient(p)
        try:await client.start(interactive=False)
        except LoginRequired:pass
        else:raise AssertionError('must require login')
        state={'kduss':'synthetic-only'}
        with patch('sys.stdin.isatty',return_value=True), patch('builtins.input',return_value='+8613800000000'), patch('getpass.getpass',return_value='0000'), patch('kuaidui.auth.initialize',return_value={}), patch('kuaidui.auth.send_sms') as sms, patch('kuaidui.auth.login_sms',return_value=state), patch('kuaidui.auth.check_session',return_value=True):
            assert await client.start() is client
            assert sms.call_count==1
            assert p.stat().st_mode & 0o777==0o600
            assert await BookClient(p).start(interactive=False)
            assert sms.call_count==1
        await client.logout(); assert not p.exists()
    print('PASS missing-session, interactive-flow, single-SMS, permissions, reuse, logout (mocked auth)')
asyncio.run(check())
