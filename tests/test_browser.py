"""Real-browser checks use synthetic aggregates, never global input hooks."""
from pathlib import Path
import threading
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright, expect

from display import BASE_URL, create_app
from runtime import Controller, create_local_server
from utils import StatsStore


def test_offline_dashboard_live_controls_and_no_external_requests(tmp_path, monkeypatch):
    monkeypatch.setattr('runtime.autostart_enabled', lambda: False)
    store = StatsStore(tmp_path)
    for _ in range(3):
        store.count_key('a')
    for _ in range(2):
        store.count_click('Button.left', 20, 30, (0, 0, 100, 100))
    controller = Controller(store)
    server = create_local_server(create_app(store, controller))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    requests, errors = [], []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                                                  headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1100})
            page.on('request', lambda request: requests.append(request.url))
            page.on('pageerror', lambda error: errors.append(str(error)))
            # Simulate no access to the internet while preserving loopback access.
            page.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).hostname == '127.0.0.1'
                       else route.abort())
            response = page.goto(BASE_URL)
            assert response.status == 200, (response.status, page.url, page.content()[:1000])
            assert page.locator('#keyboard-total').count() == 1, page.content()[:2500]
            expect(page.locator('#keyboard-total')).to_have_text('3')
            assert page.locator('#mouse-total').inner_text() == '2'
            assert page.locator('#error').inner_text() == ''
            assert page.locator('#heatmap .heatmaplayer').count() == 1
            page.screenshot(path='.work/dashboard.png', full_page=True)
            page.locator('#pause-button').click()
            expect(page.locator('#status')).to_have_text('已暂停')
            store.count_key('a')
            assert sum(v.get('A', 0) for v in store.snapshot().values()) == 3
            page.locator('#pause-button').click()
            expect(page.locator('#status')).to_have_text('正在统计')
            store.count_key('a')
            expect(page.locator('#keyboard-total')).to_have_text('4', timeout=8000)
            page.locator('#start-datetime').fill('2020-01-01T00:00')
            page.locator('#end-datetime').fill('2020-01-02T00:00')
            page.locator('#check-button').click()
            expect(page.locator('#keyboard-total')).to_have_text('0')
            assert page.locator('#start-datetime').input_value() == '2020-01-01T00:00'
            assert not page.locator('#live').is_checked()
            page.on('dialog', lambda dialog: dialog.accept())
            page.locator('#stop-button').click()
            expect(page.locator('#status')).to_have_text('程序已退出')
            assert controller.stop_event.is_set()
            assert not errors
            assert requests and all(urlsplit(url).hostname == '127.0.0.1' for url in requests)
            browser.close()
    finally:
        server.close()
        server.task_dispatcher.shutdown(timeout=2)
        thread.join(timeout=3)
