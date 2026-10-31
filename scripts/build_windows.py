"""Build a windowless directory distribution without personal data."""
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def make_source_snapshot(root, output):
    # Explicit allowlist: never include local history, credentials or build caches.
    names = ['main.py', 'runtime.py', 'utils.py', 'display.py', 'README.md', 'LICENSE',
             '.gitignore', 'pytest.ini', 'sample-hashes.json', 'requirements.in', 'requirements.txt',
             'requirements-dev.in', 'requirements-dev.txt', 'templates/index.html',
             'static/dashboard.js', 'static/plotly-latest.min.js', 'static/plotly-LICENSE.txt',
             'static/plotly-provenance.json', 'scripts/build_windows.py', 'scripts/install.ps1',
             'scripts/install.cmd', 'scripts/installer-functions.ps1', 'docs/security-review.md',
             'docs/dependency-audit.json', 'docs/README-upstream.md', 'docs/implementation.md']
    names += [p.relative_to(root).as_posix() for p in (root / 'tests').glob('*.py')]
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(names)):
            archive.write(root / name, name)
    return {'file': output.name, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def build():
    if sys.platform != 'win32' or sys.version_info[:3] < (3, 13, 18):
        raise SystemExit('Build requires patched Windows Python >= 3.13.18.')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--windowed', '--onedir', '--name', 'KMCounter', '--distpath', str(ROOT / 'dist'),
                    '--workpath', str(ROOT / 'build'), '--specpath', str(ROOT / 'build'),
                    '--add-data', f'{ROOT / "templates"};templates',
                    '--add-data', f'{ROOT / "static"};static',
                    '--add-data', f'{ROOT / "sample-hashes.json"};.',
                    '--hidden-import', 'pynput.keyboard._win32', '--hidden-import', 'pynput.mouse._win32',
                    '--hidden-import', 'pystray._win32', str(ROOT / 'main.py')], cwd=ROOT, check=True)
    target = ROOT / 'dist' / 'KMCounter'
    for name in ('LICENSE', 'README.md', 'requirements.txt'):
        shutil.copy2(ROOT / name, target / name)
    licenses = target / 'licenses'
    licenses.mkdir(exist_ok=True)
    runtime = re.findall(r'^([\w-]+)==', (ROOT / 'requirements.txt').read_text(), flags=re.M)
    versions = {}
    for name in runtime:
        distribution = metadata.distribution(name)
        versions[name] = distribution.version
        for file in distribution.files or ():
            if re.search(r'(?i)(license|copying|notice)', file.name):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    destination = licenses / name / str(file).replace('..', '_')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    for license in Path(sys.base_prefix).glob('LICENSE*'):
        shutil.copy2(license, licenses / ('Python-' + license.name))
    shutil.copy2(ROOT / 'static' / 'plotly-LICENSE.txt', licenses / 'Plotly-LICENSE.txt')
    shutil.copy2(ROOT / 'scripts' / 'install.ps1', target / 'install.ps1')
    shutil.copy2(ROOT / 'scripts' / 'install.cmd', target / 'install.cmd')
    shutil.copy2(ROOT / 'scripts' / 'installer-functions.ps1', target / 'installer-functions.ps1')
    source = make_source_snapshot(ROOT, target / 'KMCounter-source.zip')
    manifest = {'python': sys.version.split()[0], 'runtime_dependencies': versions,
                'source': 'https://github.com/Aurora-0123/KMCounter',
                'source_snapshot': source,
                'personal_data_included': False,
                'exe_sha256': hashlib.sha256((target / 'KMCounter.exe').read_bytes()).hexdigest()}
    (target / 'BUILD-INFO.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    output = ROOT / 'release' / 'KMCounter-Windows.zip'
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(target.rglob('*')):
            if path.is_file():
                archive.write(path, Path('KMCounter') / path.relative_to(target))
    print('Built:', output)
    print('SHA256:', hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    build()
