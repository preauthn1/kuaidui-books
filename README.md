# kuaidui-books

## v0.3.1：固定去掉第一张

书籍 `export_pdf()` / `kuaidui pdf` 固定跳过 `answerList[0]`（已验收样本中为上传者署名页），从第二张开始导出。不做内容识别；其他书籍也应用此固定规则。只有一张时返回错误而非生成空 PDF。原始 `get_book()` 返回值不裁剪；通用 `images_to_pdf()` 保留调用者显式传入的全部图片，防止重复跳过。


## v0.3.0：导出 PDF

```bash
pip install -U "kuaidui-books[pdf] @ git+https://github.com/preauthn1/kuaidui-books.git"
kuaidui login
kuaidui pdf YOUR_BOOK_ID -o answers.pdf
```

异步调用：

```python
await client.start()
result = await client.export_pdf('YOUR_BOOK_ID', 'answers.pdf')
print(result['pages'], result['path'])
```

本地已有图片可用 `from kuaidui.pdf_export import images_to_pdf`，然后 `images_to_pdf(有序图片路径列表, 'answers.pdf')`，无需登录或联网。

- 按 answerList 的原始顺序，一图一页，保持原图比例，JPEG 不重新压缩。
- 这是图片型 PDF，不含 OCR 可搜索文本。
- 任一图片失败、损坏或尺寸不符即停止，不发布缺页 PDF；已有输出文件不覆盖。
- 临时图片自动清理；CDN 下载不发送登录 Cookie，只接受代码白名单中的 HTTPS 原图域名，不跟随重定向。
- 每张限 25 MB、累计限 1 GB，顺序下载，每次请求有超时。
- PDF 是可选依赖：img2pdf 与 Pillow；基础接口仍不需要 ARM 或模拟器。
- 验证：161 张本地原图生成 161 页，逐页嵌入的 JPEG 字节与源文件完全一致、顺序一致；另实测一张 CDN 下载→PDF 路径。


## v0.2.0：交互登录与异步入口

```bash
python -m pip install .
kuaidui login
kuaidui status
kuaidui book YOUR_BOOK_ID
kuaidui logout
```

```python
import asyncio
from kuaidui import BookClient

async def main():
    client = BookClient(session='~/.config/kuaidui/session.json')
    await client.start()  # 有效会话复用，否则终端提示手机号及验证码
    book = await client.get_book('YOUR_BOOK_ID')
    for page in book.get('answerList', []):
        print(page['origin'])

asyncio.run(main())
```

验证码用 getpass 输入，不回显、不保存；凭证原子写入、权限 0600。默认不自动重发短信，输入 r 后还需 yes 确认。服务器任务使用 `await client.start(interactive=False)`；没有有效登录态时抛出 LoginRequired。网络错误、图形验证、验证码错误不会被当作登录成功。明确的接口错误保留为异常，不盲目触发重新登录。

`kuaidui --session /secure/path/session.json status` 可指定文件。logout 只删除本地文件。旧同步 API 改名为 `SyncBookClient`，或继续从 `kuaidui.books` 导入旧类。

现已附带从 APK 提取的**公开应用常量及公开签名证书** app_profile.json，用于首次初始化；它们不是用户凭证或私钥。新生成的 CUID、初始化 token 和 KDUSS 仅保存在用户本地。CLI 当前支持中国大陆手机号（11位或 +86）。

验证：离线模拟交互流程检查通过；独立虚拟环境安装与 CLI status 通过；现有真实会话经异步 start→get_book 返回 161 条资源。本次没有再次向用户发送短信，完整交互分支使用模拟认证验证，SMS HTTP 协议此前已真实登录验证。


快对 Android 6.98.0 书籍详情与答案图片资源接口的 Python 重实现。目标是**书籍答案**，不是拍照单题检索。

运行时仅使用 Python 标准库，不加载 ARM `.so`，不使用模拟器、Frida、Unidbg 或远程签名服务。仓库不包含 APK、反编译代码、账号、手机号、验证码、登录态、真实设备标识或书籍答案图片。

## 状态

- 已在维护者私有环境完成：服务端初始化、合法短信登录后的书籍查询、响应解密、读取 `answerList`。
- 一个书籍样本返回 161 个不重复原图 URL，全部下载并通过图片完整性及尺寸校验。
- `answerListTotal` 在该样本为 0，不能拿它替代真实数组长度；161 是返回资源数，不是经纸质目录确认的完整书籍页数。
- 服务端实现、账号权限和验证要求可能变化。当前未实现图形验证码、购买、付费权限获取、会话自动刷新。
- 已发布交互登录 CLI；实际测试记录和用户会话不发布。首次使用需要用户交互接收验证码。

## 安装

```bash
python -m pip install .
```

## 获取书籍答案列表

```python
from kuaidui import SyncBookClient

# 文件必须位于仓库外，使用自己的合法会话；不要提交到 Git。
client = SyncBookClient.from_session_file('/secure/path/session.json')
book = client.get_book('YOUR_32_CHARACTER_BOOK_ID')
print(book['name'])
for index, resource in enumerate(book.get('answerList', []), 1):
    print(index, resource['origin'])
```

`get_book` 也接受 `https://www.kuaiduizuoye.com/bookid` 加 32 位小写十六进制 ID 的完整链接。示例占位符不会通过验证，请换成实际 ID。

返回原始字段结构（已处理已知加密字段），包括 `answerList[].origin`、`thumbnail`、`w`、`h`。不要把旧字段 `answers`、`oriAnswers` 或 `pageList` 为空当成没有资源。

会话字段约定：

- `common`：客户端公共参数字符串字典，包括 `cuid`、`token`（应用公共参数，**不是**下面的 native token）、`vc`、`vcname`、`channel`、`os` 等。
- `native_token`：正常初始化交换得到的 10 字节 ASCII token。
- `init_elapsed_realtime_ms`：初始化成功时记录的单调时钟毫秒。
- `user_agent`：请求 UA。
- `kduss`：调用者自己的登录态。
- `dp_ticket`：可选设备票据；缺省为空，是否接受由服务端决定。

`abis` 是是否支持 ARM64 的 **0/1 标志**，不是 `armeabi-v7a` 字符串。`appBit` 为进程位数，例如 `32`。公共参数不要凭字段名猜值。

低层模块包括初始化加密与校验 (`bootstrap_native`)、正常初始化 HTTP 交换 (`bootstrap`)、签名与密钥派生 (`native`)。它们需要调用者提供正确的 CUID 和实际 APK 签名证书 DER 的十六进制字符串；仓库仅打包公开应用证书，不打包用户会话。设备/账号条件不足时应返回错误，不制造通过状态。

## 技术原理

### 1. 初始化

客户端以 CUID、APK 签名证书和随机 nonce 构造 signA，调用 `/napi/user/antispam`，从真实 signB 中校验 nonce 并恢复 token。内部密码算法采用 DES 形状的位运算，但字节位序及 PC2 表并非标准 DES：`PC2[35]` 是 46 而非 47。填充为零字节加末字节长度，不是 PKCS#7。代码直接实现这些运算，不执行原生库。

### 2. 请求签名

业务参数、公共参数及时间参数组成原始 `key=value` 字符串列表。添加 `_t_` 和 `kakorrhaphiophobia`（初始化时的单调时钟值），按 Java UTF-16 字符串次序排序，无分隔拼接，UTF-8 后 Base64，最后通过 token 派生的 MD5 结构生成签名。

注意签名输入是**原始值**，不是 URL 编码后的字符串。`_t_` 和 `kakorrhaphiophobia` 是独立表单字段，不是签名摘要本身。

### 3. 书籍专用加密外壳

`POST /search/submit/booksearch` 的业务字段为 `bookId`、`ticket`、`randStr`、`isXposed`、`isEmulator`、`isHitDayup`、`grade`、`resolution`。

先按 Java `URLEncoder` 规则组成以 `&bookId=` 开头的查询片段，再使用初始化派生的 RC4 key 加密、Base64 成 `data`。外层表单是 `data` 加公共参数及签名。直接提交明文业务参数的实测错误为 `4000: param invalid need encrypted data`。

### 4. 响应处理

先检查 HTTP 状态及 `errNo`/`errno`。若存在内层字符串 `data`，先 Base64/RC4 解开并解析 JSON；书名、封面等已知字段仍可能需要按客户端模型进行字段级解密。`answerList` 的原图 URL 在已验收样本中是明文。

返回字段需要逐一对应，不能递归把所有字符串都当密文，也不能把网页预览图数量当整个接口的资源数量。图片从返回的 CDN URL 获取，不需要额外 ARM 图像算法。

### 5. 128 字符 RC4 key

`H(x)` 表示小写 MD5 十六进制文本；`S_n` 表示交换首尾 n 对字符：

```
A = H(fixed application constant)
B = H(versionCode)
C = S_15(H('[' + token + ']@'))
X = S_3(A + B + C)
key = S_60(X + H(X))
```

最终 key 是 128 个 ASCII 字符，不是将它 hex-decode 后的 64 字节。具体常量和算法位于 `native.py`。

## 验证边界

RC4 与原 APK Java 实现进行过 4096 字节比对；初始化运算有独立整数实现对照和真实服务端 nonce 校验。公开仓库不附带可重放的用户响应。离线算法检查不等价于所有账号、所有版本、所有书籍都可用。

`client.py`/`transport.py` 保留底层通用及早期单题实现，但**不作为本项目验收目标**。单题结果匹配正确性没有通过验收。

## 隐私

只从独立发布目录提交白名单文件。实际会话、验证码、设备标识、测试书籍 ID、图片、响应记录均排除；不要把 `BookClient.session` 打印到日志。失效或登录要求不自动重试短信，不自动购买内容。

## 分析方法参考

使用 [newliver666/apk-reverse](https://github.com/newliver666/apk-reverse) 的静态分析工作流辅助定位；本仓库不复制其脚本或 APK 反编译源码。
