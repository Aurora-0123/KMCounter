"""KMCounter Windows desktop entry point."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from display import BASE_URL, create_app
from runtime import Controller, SingleInstance, local_appdata, set_autostart, show_error
from utils import StatsStore


def open_existing():
    # Bypass proxies: this is exclusively a loopback connection.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(50):
        try:
            with opener.open(BASE_URL + '/status', timeout=0.3) as response:
                state = json.load(response)
            if state.get('version') == '2.0.0' and state.get('running'):
                webbrowser.open(BASE_URL)
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    raise OSError('已运行的实例没有响应，请检查托盘或退出旧实例后重试。')


def main(argv=None):
    parser = argparse.ArgumentParser(description='本机键盘与鼠标统计')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--background', action='store_true', help='后台运行，不打开网页')
    mode.add_argument('--show', action='store_true', help='打开统计页')
    parser.add_argument('--data-dir', type=Path, help='使用指定数据目录')
    parser.add_argument('--import-data', action='append', type=Path, default=[], help='导入旧版 data 目录')
    parser.add_argument('--enable-autostart', action='store_true', help='启用当前用户登录启动')
    parser.add_argument('--disable-autostart', action='store_true', help='关闭登录启动并退出')
    args = parser.parse_args(argv)
    instance = SingleInstance()
    try:
        if args.disable_autostart:
            set_autostart(False)
            return 0
        if not instance.acquire():
            if args.import_data or args.enable_autostart:
                raise OSError('程序正在运行。请先从托盘退出，再安装或导入历史记录。')
            if not args.background:
                open_existing()
            return 0
        root = local_appdata() / 'KMCounter'
        directory = args.data_dir.resolve() if args.data_dir else root / 'data'
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory.parent / 'kmcounter.log', maxBytes=256_000,
                                      backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.WARNING)
        store = StatsStore(directory)
        samples_path = Path(__file__).with_name('sample-hashes.json')
        samples = json.loads(samples_path.read_text(encoding='utf-8'))
        for source in args.import_data:
            store.import_legacy(source, samples)
        store.snapshot()  # Detect damaged history before listeners start.
        if args.enable_autostart:
            set_autostart(True)
        controller = Controller(store)
        app = create_app(store, controller)
        controller.run(app, show=not args.background)
        return 0
    except (OSError, ValueError) as error:
        logging.getLogger('kmcounter').error('Application could not start or finish saving.')
        # Native message must be actionable; never include captured input.
        message = str(error) if isinstance(error, ValueError) else (
            '程序无法启动或保存。请检查是否已有程序占用 127.0.0.1:5000、数据目录权限和磁盘空间。\n'
            '如果刚刚执行了安装或导入，请先退出已有的 KMCounter 实例。')
        show_error(message)
        return 1
    finally:
        instance.close()


if __name__ == '__main__':
    sys.exit(main())
