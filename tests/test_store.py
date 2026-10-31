import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import patch

import pytest

from utils import StatsStore, normalize_key


def test_keys_are_normalized_and_unknown_text_is_not_saved():
    assert normalize_key('a') == 'A'
    assert normalize_key('!') == '1'
    assert normalize_key('\x01') == 'A'
    assert normalize_key('Key.shift_l') == 'Key.shift'
    assert normalize_key('private sentence') == 'Key.unknown'


def test_midnight_restart_and_no_first_occurrence_order(tmp_path):
    now = [datetime(2026, 10, 30, 23, 59)]
    store = StatsStore(tmp_path, clock=lambda: now[0])
    store.count_key('z')
    store.count_key('a')
    now[0] = datetime(2026, 10, 31, 0, 0)
    store.count_key('b')
    store.flush()
    old = (tmp_path / '2026-10-30.json').read_text()
    assert old.index('"A"') < old.index('"Z"')
    restarted = StatsStore(tmp_path, clock=lambda: now[0])
    restarted.count_key('b')
    assert restarted.snapshot()['2026-10-31 00:00']['B'] == 2


def test_concurrent_counts_pause_and_mouse_positions(tmp_path):
    store = StatsStore(tmp_path, clock=lambda: datetime(2026, 10, 31, 12))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: store.count_key('a'), range(500)))
    store.count_click('Button.left', -1920, 0, (-1920, 0, 3840, 1080))
    store.count_click('Button.right', 1920, 1080, (-1920, 0, 3840, 1080))
    store.set_paused(True)
    store.count_key('a')
    counts = next(iter(store.snapshot().values()))
    assert counts['A'] == 500
    assert counts['Button.left_position_0_0'] == 1
    assert counts['Button.right_position_99_99'] == 1
    assert sum(n for key, n in counts.items() if '_position_' not in key) == 502


def test_failed_write_keeps_original_and_retries(tmp_path):
    store = StatsStore(tmp_path)
    store.count_key('a')
    store.flush()
    path = next(tmp_path.glob('*.json'))
    original = path.read_bytes()
    store.count_key('b')
    with patch('utils.os.replace', side_effect=OSError('disk full')):
        with pytest.raises(OSError):
            store.flush()
    assert path.read_bytes() == original
    assert store.errors
    store.flush()
    assert not store.errors
    assert 'B' in next(iter(json.loads(path.read_text()).values()))


def test_corrupt_file_is_not_overwritten(tmp_path):
    day = datetime.now().strftime('%Y-%m-%d')
    path = tmp_path / f'{day}.json'
    path.write_text('{broken')
    store = StatsStore(tmp_path)
    with pytest.raises(ValueError):
        store.count_key('a')
    assert store.errors
    assert path.read_text() == '{broken'


def test_import_is_idempotent_and_skips_shipped_sample(tmp_path):
    import hashlib
    source = tmp_path / 'legacy'
    source.mkdir()
    sample = b'{"2024-09-28 00:00":{"A":1}}'
    (source / '2024-09-28.json').write_bytes(sample)
    history = {'2026-10-31 12:00': {'a': 3, '!': 2}}
    (source / '2026-10-31.json').write_text(json.dumps(history))
    store = StatsStore(tmp_path / 'new')
    store.import_legacy(source, {hashlib.sha256(sample).hexdigest()})
    store.import_legacy(source, {hashlib.sha256(sample).hexdigest()})
    restarted = StatsStore(tmp_path / 'new')
    restarted.import_legacy(source, {hashlib.sha256(sample).hexdigest()})
    assert restarted.snapshot() == {'2026-10-31 12:00': {'A': 3, '1': 2}}
    assert json.loads((source / '2026-10-31.json').read_text()) == history
