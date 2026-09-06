"""出网的两个坑，收在一处。

`core/r2.py` 和 `core/notify.py` 都要发 HTTPS 请求，都会踩同样两件事。
这段绕坑逻辑**不能抄两份** —— 它花了很久才定位清楚，抄一份就多一份会漂的副本。

## 坑一：CERTIFICATE_VERIFY_FAILED，但根因往往不是证书

两种完全不同的原因，症状一字不差：

1. **真的没有根证书** —— macOS 上的 Python（python.org 安装包 / homebrew /
   pyenv 都可能）默认指向一个不存在的 openssl 目录。换台机器就好了。
2. **本机开着抓包代理**（Reqable / Charles / mitmproxy）—— 代理做的就是
   中间人，它出示自己签的证书，本来就不在任何公共信任库里。certifi 也救不了。

识别第二种：`scutil --proxy | grep HTTPSProxy` 有值就是它。
解法是配一份**合并了代理根证书**的 pem（代理的 CA 通常在系统钥匙串里，
可以导出来和 certifi 的拼在一起），或者关掉代理。

**不要改成不验证证书。** 这里传的是要公开分发的资产、用的是能写整个桶的密钥。

## 坑二：Broken pipe，也不是网络问题

同一个抓包代理吞不下几 MB 的 PUT —— 它为了能展示请求体会先整个缓存下来，
大文件直接把它撑爆。而且资产上传本来也没有抓包的价值。

所以默认**绕过系统代理**。

这两条是同一个问题的两半：代理先让证书验不过，信任了它之后再让大文件传不上去。
只解决前一半会以为快好了，其实还差一半。
"""
from __future__ import annotations

import ssl
import urllib.request
from pathlib import Path


def ssl_context(ca_bundle: str = "") -> ssl.SSLContext:
    """带根证书的 SSL context。`ca_bundle` 优先，其次 certifi，最后系统默认。"""
    if ca_bundle and Path(ca_bundle).expanduser().is_file():
        return ssl.create_default_context(cafile=str(Path(ca_bundle).expanduser()))
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def opener(ca_bundle: str = "", use_proxy: bool = False) -> urllib.request.OpenerDirector:
    """构造 opener。默认绕过系统代理（见模块头「坑二」）。

    真需要经过代理（比如公司网络只允许代理出网）就传 `use_proxy=True`。
    """
    handlers: list = [urllib.request.HTTPSHandler(context=ssl_context(ca_bundle))]
    if not use_proxy:
        handlers.append(urllib.request.ProxyHandler({}))   # 空 dict = 不走任何代理
    return urllib.request.build_opener(*handlers)
