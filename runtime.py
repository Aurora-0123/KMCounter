"""Windows desktop lifecycle, tray and current-user startup integration."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
import socket
from pathlib import Path
import subprocess
import sys
import threading
import time
import webbrowser

from display import BASE_URL
from utils import VERSION, normalize_key

LOG = logging.getLogger('kmcounter')
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'KMCounter'
_startup_cache = None
_startup_lock = threading.Lock()
_OEM_KEYS = {186: ';', 187: '=', 188: ',', 189: '-', 190: '.', 191: '/',
             192: '`', 219: '[', 220: '\\', 221: ']', 222: "'", 226: '\\'}


def local_appdata() -> Path:
    # Known Folder API avoids cwd and environment-variable redirection.
    import uuid
    guid = (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID('f1b32785-6fba-4fcf-9d55-7b8e7f157091').bytes_le)
    path = ctypes.c_wchar_p()
    shell = ctypes.WinDLL('shell32')
    shell.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
                                          ctypes.POINTER(ctypes.c_wchar_p)]
    result = shell.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path))
    if result != 0:
        raise OSError('Unable to locate LocalAppData')
    try:
        return Path(path.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(path, ctypes.c_void_p))


def startup_command(executable=None):
    if executable is not None:
        command = f'"{Path(executable).resolve()}" --background'
    elif getattr(sys, 'frozen', False):
        command = f'"{Path(sys.executable).resolve()}" --background'
    else:
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        command = f'"{pythonw}" "{Path(__file__).with_name("main.py")}" --background'
    if len(command) > 260:
        raise ValueError('启动路径过长，请安装到较短的目录。')
    return command


def _startup_helper(action, command=''):
    helper = (Path(sys.executable).parent / 'installer-functions.ps1' if getattr(sys, 'frozen', False)
              else Path(__file__).parent / 'scripts' / 'installer-functions.ps1')
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
             '-File', str(helper), '-StartupAction', action],
            env={**os.environ, 'KMC_STARTUP_COMMAND': command},
            capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        raise OSError('Windows 无法更新登录启动设置，请检查当前用户的权限。') from None
    if result.returncode:
        raise OSError('Windows 未能确认登录启动设置已更新。')
    return result


def autostart_enabled():
    global _startup_cache
    try:
        command = startup_command()
    except ValueError:
        return False
    with _startup_lock:
        # Status is polled by both the page and tray; avoid spawning a helper on
        # every poll while still noticing outside changes within thirty seconds.
        if _startup_cache and _startup_cache[0] == command and time.monotonic() < _startup_cache[1]:
            return _startup_cache[2]
        answer = _startup_helper('Check', command).stdout.strip()
        if answer not in (b'enabled', b'disabled'):
            raise OSError('Windows 未能读取登录启动设置。')
        enabled = answer == b'enabled'
        _startup_cache = (command, time.monotonic() + 30, enabled)
        return enabled


def set_autostart(enabled):
    global _startup_cache
    _startup_helper('Enable' if enabled else 'Disable', startup_command() if enabled else '')
    with _startup_lock:
        _startup_cache = None


class SingleInstance:
    def __init__(self, name='Local\\KMCounter-2.0'):
        self.name = name
        self.handle = None
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]

    def acquire(self):
        self.handle = self.kernel.CreateMutexW(None, False, self.name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def key_name(key):
    name = getattr(key, 'name', None)
    if name:
        return normalize_key('Key.' + name)
    vk = getattr(key, 'vk', None)
    if isinstance(vk, int):
        if 65 <= vk <= 90 or 48 <= vk <= 57:
            return chr(vk)
        if 96 <= vk <= 105:
            return str(vk - 96)
        if vk in _OEM_KEYS:
            return _OEM_KEYS[vk]
    return 'Key.unknown'


def screen_bounds():
    user32 = ctypes.windll.user32
    return tuple(user32.GetSystemMetrics(i) for i in (76, 77, 78, 79))


def create_local_server(app, port=5000):
    from waitress import create_server
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(('127.0.0.1', port))
        return create_server(app, sockets=[listener], threads=4,
                             asyncore_loop_timeout=0.2, clear_untrusted_proxy_headers=True)
    except BaseException:
        listener.close()
        raise


def show_error(message):
    ctypes.windll.user32.MessageBoxW(None, message, 'KMCounter', 0x10)


class Controller:
    def __init__(self, store):
        self.store = store
        self.stop_event = threading.Event()
        self.server = None
        self.icon = None
        self.listeners = []
        self.runtime_errors = []
        self.lock = threading.RLock()

    def status(self):
        errors = self.store.errors + list(self.runtime_errors)
        try:
            autostart = autostart_enabled()
        except OSError:
            autostart = None
            errors.append('无法读取登录启动设置，请检查当前用户的权限。')
        return {'version': VERSION, 'pid': os.getpid(), 'running': not self.stop_event.is_set(),
                'paused': self.store.paused, 'errors': errors,
                'autostart': autostart, 'data_directory': str(self.store.directory)}

    def refresh_tray(self):
        if self.icon:
            state = self.status()
            label = '需要处理错误' if state['errors'] else ('已暂停' if state['paused'] else '正在统计')
            self.icon.title = 'KMCounter · ' + label
            self.icon.update_menu()

    def set_paused(self, paused):
        with self.lock:
            if self.stop_event.is_set():
                return
            try:
                self.store.set_paused(paused)
            finally:
                self.refresh_tray()

    def request_stop(self):
        with self.lock:
            # Pause first so no event can arrive between final flush and shutdown.
            try:
                self.store.set_paused(True)
            finally:
                self.refresh_tray()
            self.stop_event.set()

    def _record(self, function, *args):
        try:
            function(*args)
        except (OSError, ValueError):
            self.store.paused = True
            LOG.error('Input aggregation paused: storage unavailable.')
            self.refresh_tray()

    def start_listeners(self):
        from pynput import keyboard, mouse
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass
        keyboard_listener = keyboard.Listener(
            on_press=lambda key: self._record(self.store.count_key, key_name(key)))

        def click(x, y, button, pressed):
            if pressed:
                self._record(self.store.count_click, str(button), x, y, screen_bounds())

        self.listeners = [keyboard_listener, mouse.Listener(on_click=click)]
        for listener in self.listeners:
            listener.start()
            listener.wait()

    def _watch(self):
        while not self.stop_event.wait(5):
            try:
                self.store.flush()
            except OSError:
                LOG.error('Statistics save failed; will retry.')
            if any(not listener.is_alive() for listener in self.listeners):
                message = '输入监听已停止，请退出后重新启动程序。'
                if message not in self.runtime_errors:
                    self.runtime_errors.append(message)
                    self.store.paused = True
            self.refresh_tray()

    def _shutdown_when_requested(self):
        self.stop_event.wait()
        for listener in self.listeners:
            listener.stop()
        if self.server:
            self.server.close()
        if self.icon:
            self.icon.stop()

    def run(self, app, show=False):
        import pystray
        from PIL import Image, ImageDraw

        # Bind first; a port conflict must never leave unseen input listeners.
        self.server = create_local_server(app)
        image = Image.new('RGBA', (64, 64), '#295d9e')
        drawing = ImageDraw.Draw(image)
        drawing.rounded_rectangle((8, 18, 56, 47), radius=5, outline='white', width=3)
        for x in (17, 27, 37, 47):
            drawing.line((x, 26, x, 31), fill='white', width=3)
        drawing.line((20, 39, 44, 39), fill='white', width=3)

        def guarded(function):
            def action(icon, item):
                try:
                    function()
                except (OSError, ValueError):
                    show_error('操作失败。请查看统计页中的错误提示，检查数据目录或磁盘空间。')
                self.refresh_tray()
            return action

        self.icon = pystray.Icon('KMCounter', image, 'KMCounter', menu=pystray.Menu(
            pystray.MenuItem('查看统计', lambda *_: webbrowser.open(BASE_URL), default=True),
            pystray.MenuItem(lambda item: '继续统计' if self.store.paused else '暂停统计',
                            guarded(lambda: self.set_paused(not self.store.paused))),
            pystray.MenuItem('登录后自动启动', guarded(lambda: set_autostart(not autostart_enabled())),
                            checked=lambda item: self.status()['autostart'] is True),
            pystray.MenuItem('打开数据目录', lambda *_: subprocess.Popen(
                ['explorer.exe', str(self.store.directory)])),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出程序', guarded(self.request_stop))))
        server_thread = threading.Thread(target=self.server.run, name='dashboard', daemon=True)
        writer = threading.Thread(target=self._watch, name='save-statistics', daemon=True)
        closer = threading.Thread(target=self._shutdown_when_requested, name='shutdown', daemon=True)
        try:
            self.start_listeners()
            server_thread.start()
            writer.start()
            self.refresh_tray()

            def tray_ready(icon):
                LOG.info('Tray message loop ready.')
                if not self.stop_event.is_set():
                    icon.visible = True
                # pystray.stop is effective only after its message loop starts.
                closer.start()
                if show and not self.stop_event.is_set():
                    webbrowser.open(BASE_URL)

            self.icon.run(setup=tray_ready)
        finally:
            self.store.paused = True
            self.stop_event.set()
            for listener in self.listeners:
                listener.stop()
            self.server.close()
            self.store.flush()
            writer.join(timeout=6) if writer.is_alive() else None
            self.server.task_dispatcher.shutdown(timeout=3)
