"""Source and PyInstaller entry point."""

import argparse
import logging
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import contextmanager
from dataclasses import replace
from logging.handlers import RotatingFileHandler


@contextmanager
def instance_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / "studio.lock").open("a+b")
    try:
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt
            if handle.read(1) == b"":
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("这个数据目录已有拾序实例运行，请使用现有窗口") from None
    try:
        yield
    finally:
        handle.close()


def open_when_ready(url):
    # No browser opens until this server answers; bypass unrelated proxy settings.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(100):
        try:
            with opener.open(url + "api/session", timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)


def main():
    if "--pick-folder" in sys.argv:
        from originalstudio.picker import main as pick
        pick()
        return
    parser = argparse.ArgumentParser(description="拾序 · Original Studio 本地素材工作台")
    parser.add_argument("--data-dir", help="独立的数据目录")
    parser.add_argument("--port", type=int, help="本机监听端口，默认 8090")
    parser.add_argument("--no-browser", action="store_true", help="启动后不打开浏览器")
    options = parser.parse_args()
    try:
        import uvicorn
        from originalstudio.api import create_app
        from originalstudio.settings import Settings
    except ImportError as exc:
        print(f"缺少运行依赖 {exc.name}。请先双击 install.bat。")
        return 1
    from pathlib import Path

    settings = Settings.from_env()
    if options.data_dir:
        settings = replace(settings, data_dir=Path(options.data_dir))
    if options.port:
        settings = replace(settings, port=options.port)
    try:
        with instance_lock(settings.data_dir):
            logs = settings.data_dir / "logs"
            logs.mkdir(exist_ok=True)
            handler = RotatingFileHandler(logs / "studio.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
            logging.getLogger("originalstudio").addHandler(handler)
            logging.getLogger("originalstudio").setLevel(logging.INFO)
            hostname = f"[{settings.host}]" if ":" in settings.host else settings.host
            url = f"http://{hostname}:{settings.port}/"
            family = socket.AF_INET6 if ":" in settings.host else socket.AF_INET
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                try:
                    probe.bind((settings.host, settings.port))
                except OSError:
                    print(f"端口 {settings.port} 已被占用。请使用 --port 8091 选择其他端口。")
                    return 1
            app = create_app(settings)
            print(f"\n拾序 · Original Studio\n打开：{url}\n数据：{settings.data_dir}\n按 Ctrl+C 退出。\n")
            if not options.no_browser:
                threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
            uvicorn.run(app, host=settings.host, port=settings.port, workers=1, proxy_headers=False, server_header=False, log_level="info")
            handler.close()
    except RuntimeError as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
