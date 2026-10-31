from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from runtime import SingleInstance, Controller, key_name, startup_command, create_local_server
from utils import StatsStore


@pytest.fixture(autouse=True)
def registry_boundary(monkeypatch):
    monkeypatch.setattr('runtime.autostart_enabled', lambda: False)


def test_virtual_keys_do_not_save_generated_characters():
    assert key_name(SimpleNamespace(vk=65, char='\x01')) == 'A'
    assert key_name(SimpleNamespace(vk=49, char='!')) == '1'
    assert key_name(SimpleNamespace(vk=186, char=':')) == ';'
    assert key_name(SimpleNamespace(vk=0, char='私密文本')) == 'Key.unknown'


def test_named_mutex_releases_ownership():
    first = SingleInstance('Local\\KMCounter-test-instance')
    second = SingleInstance('Local\\KMCounter-test-instance')
    assert first.acquire()
    try:
        assert not second.acquire()
    finally:
        second.close()
        first.close()
    assert second.acquire()
    second.close()


def test_startup_command_quotes_paths():
    command = startup_command(Path('C:/Users/Example User/KMCounter.exe'))
    assert command.startswith('"C:') and command.endswith('KMCounter.exe" --background')


def test_controller_reports_write_errors_and_can_retry(tmp_path):
    store = StatsStore(tmp_path)
    controller = Controller(store)
    store.count_key('a')
    with patch('utils.os.replace', side_effect=OSError('full')):
        with pytest.raises(OSError):
            controller.set_paused(True)
    assert controller.status()['errors']
    assert controller.status()['paused']
    controller.set_paused(False)
    assert not controller.status()['errors']


def test_stop_waits_for_flush_success(tmp_path):
    store = StatsStore(tmp_path)
    store.count_key('a')
    controller = Controller(store)
    with patch('utils.os.replace', side_effect=OSError('full')):
        with pytest.raises(OSError):
            controller.request_stop()
    assert not controller.stop_event.is_set()
    controller.request_stop()
    assert controller.stop_event.is_set()
    assert not controller.status()['running']


def test_existing_port_is_never_reused():
    import socket
    with socket.socket() as existing:
        existing.bind(('127.0.0.1', 0))
        existing.listen()
        port = existing.getsockname()[1]
        with pytest.raises(OSError):
            create_local_server(lambda environ, start_response: [], port=port)


def test_stop_during_startup_waits_until_tray_is_ready(tmp_path, monkeypatch):
    import threading
    controller = Controller(StatsStore(tmp_path))
    monkeypatch.setattr(controller, 'start_listeners', lambda: None)
    server = SimpleNamespace(run=lambda: controller.request_stop(), close=lambda: None,
                             task_dispatcher=SimpleNamespace(shutdown=lambda **kwargs: None))
    monkeypatch.setattr('runtime.create_local_server', lambda app: server)

    class Icon:
        def __init__(self, *args, **kwargs):
            self.running = False
            self.stopped = threading.Event()

        def update_menu(self):
            pass

        def stop(self):
            if self.running:
                self.stopped.set()

        def run(self, setup=None):
            assert controller.stop_event.wait(1), 'Stop request was not delivered'
            self.running = True
            if setup:
                setup(self)
            assert self.stopped.wait(1), 'Tray was never stopped after startup'

    monkeypatch.setattr('pystray.Icon', Icon)
    controller.run(lambda environ, start_response: [])
