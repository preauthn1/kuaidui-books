import argparse
import asyncio
import json
import sys
from .async_client import BookClient, DEFAULT_SESSION
from .auth import LoginRequired
from .client import SearchError

async def run(args):
    client=BookClient(session=args.session)
    if args.command=='login':
        await client.start(); print('登录态已验证并保存。')
    elif args.command=='status':
        valid=await client.status(); print('有效' if valid else '未登录或已失效');return 0 if valid else 1
    elif args.command=='logout':
        await client.logout();print('本地凭证已删除（非服务端注销）。')
    elif args.command=='pdf':
        await client.start(interactive=False)
        print(json.dumps(await client.export_pdf(args.book,args.output),ensure_ascii=False))
    elif args.command=='book':
        await client.start(interactive=False)
        print(json.dumps(await client.get_book(args.book),ensure_ascii=False,indent=2))
    return 0

def main():
    parser=argparse.ArgumentParser(prog='kuaidui')
    parser.add_argument('--session',default=DEFAULT_SESSION)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('login','status','logout'):sub.add_parser(name)
    sub.add_parser('book').add_argument('book')
    pdf=sub.add_parser('pdf')
    pdf.add_argument('book')
    pdf.add_argument('-o','--output',required=True)
    args=parser.parse_args()
    try:return asyncio.run(run(args))
    except (LoginRequired,SearchError):
        print('认证或服务端校验失败；未自动重试。请检查会话或在官方客户端完成验证。',file=sys.stderr);return 1
    except (OSError,ValueError,KeyError,RuntimeError):
        print('操作失败：检查网络、输入或会话文件。未输出敏感响应。',file=sys.stderr);return 1
    except (KeyboardInterrupt,EOFError):return 130

if __name__=='__main__':sys.exit(main())
