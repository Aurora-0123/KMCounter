import hashlib
from pathlib import Path
import zipfile

from scripts.build_windows import make_source_snapshot


def test_release_has_exact_source_and_no_personal_data(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / 'source.zip'
    result = make_source_snapshot(root, output)
    assert result['sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert {'main.py', 'runtime.py', 'requirements.txt', 'scripts/build_windows.py', 'LICENSE'} <= names
        assert archive.read('main.py') == (root / 'main.py').read_bytes()
        assert not any(part in name.split('/') for name in names
                       for part in ('data', '.work', '.venv', '.git', 'release'))
