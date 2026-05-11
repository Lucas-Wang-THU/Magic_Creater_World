#!/usr/bin/env python3
"""从项目根目录启动 Web 服务（FastAPI + 静态前端）。"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser


def main() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)
    os.chdir(root)

    parser = argparse.ArgumentParser(description="启动 Magic Creater World 本地服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="端口")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="开发模式：代码变更后自动重载（仅本机调试建议开启）",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="启动后不自动打开系统浏览器",
    )
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError as e:
        print("未找到 uvicorn，请先安装依赖：pip install -r requirements.txt", file=sys.stderr)
        raise SystemExit(1) from e

    browser_host = "127.0.0.1" if args.host in ("0.0.0.0", "::", "::0") else args.host
    if browser_host == "::1":
        url = f"http://[::1]:{args.port}/"
    else:
        url = f"http://{browser_host}:{args.port}/"

    if not args.no_browser:
        def _open_browser() -> None:
            import time

            time.sleep(0.9)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()
        print(f"即将在浏览器中打开：{url}（可用 --no-browser 关闭）")
    else:
        print(f"请在浏览器中访问：{url}")

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=False,
    )


if __name__ == "__main__":
    main()
