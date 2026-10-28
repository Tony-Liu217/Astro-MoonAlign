"""Build an offline Windows GUI folder and zip with the current Python environment.

Rebuild on Windows x64 with Python 3.10:
  python -m venv .build-venv
  .build-venv\\Scripts\\python -m pip install -r requirements-build.txt
  .build-venv\\Scripts\\python build_portable.py
No application or Python installation is required on recipients' computers.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.metadata import distribution, version
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from moonalign import __version__

ROOT = Path(__file__).resolve().parent
VERSION = __version__


def check_dependency_versions() -> dict[str, str]:
    """Fail before building a release with different declared dependencies."""
    actual = {}
    for filename in ('requirements.txt', 'requirements-build.txt'):
        for raw in (ROOT / filename).read_text(encoding='utf-8').splitlines():
            requirement = raw.split('#', 1)[0].strip()
            if not requirement or requirement.startswith('-r '):
                continue
            if '==' not in requirement:
                raise RuntimeError(f'Release dependency must be pinned: {requirement}')
            name, expected = map(str.strip, requirement.split('==', 1))
            actual[name] = version(name)
            if actual[name] != expected:
                raise RuntimeError(f'{name}: installed {actual[name]}, expected {expected}; install requirements-build.txt before building.')
    return actual


def source_hashes() -> dict[str, str]:
    return {
        item.relative_to(ROOT).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in [ROOT / 'launch.py', *sorted((ROOT / 'moonalign').glob('*.py'))]
        if item.is_file()
    }


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def collect_licenses() -> None:
    """Copy real distribution license texts; include wheel-bundled notices."""
    target = ROOT / 'licenses'
    target.mkdir(exist_ok=True)
    for name in ('numpy', 'opencv-python', 'Pillow', 'PyInstaller', 'typing_extensions'):
        dist = distribution(name)
        for item in dist.files or []:
            parts = Path(str(item)).parts
            filename = Path(str(item)).name.lower()
            if ('license' in filename or filename in ('copying', 'copying.txt', 'notice', 'notice.txt')) and not filename.endswith('.xml'):
                source = Path(dist.locate_file(item))
                if source.is_file() and all(p != '..' for p in parts):
                    copy_file(source, target / name / Path(str(item)))
    # Python ships the PSF license and the Tk distribution contains both licenses.
    base = Path(sys.base_prefix)
    for name in ('LICENSE.txt', 'LICENSE'):
        if (base / name).is_file():
            copy_file(base / name, target / 'Python' / name)
    for item in (base / 'tcl').rglob('license*'):
        if item.is_file():
            copy_file(item, target / 'TclTk' / item.relative_to(base / 'tcl'))
    required = [target / name for name in ('numpy', 'opencv-python', 'Pillow', 'PyInstaller', 'typing_extensions', 'Python', 'TclTk')]
    missing = [str(path) for path in required if not path.exists() or not any(path.rglob('*'))]
    if missing:
        raise RuntimeError('Missing distribution licenses: ' + ', '.join(missing))


def make_zip(folder: Path, destination: Path) -> None:
    # A single top-level folder helps users keep the executable and runtime together.
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in sorted(folder.rglob('*')):
            if item.is_file():
                archive.write(item, folder.name + '/' + item.relative_to(folder).as_posix())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=f'MoonAlign {VERSION}')
    stages = parser.add_mutually_exclusive_group()
    stages.add_argument('--archives-only', action='store_true', help='Refresh documentation and archives after an existing build.')
    stages.add_argument('--build-only', action='store_true', help='Build the portable folder for acceptance testing without creating release archives.')
    parser.add_argument('--distpath', type=Path, default=ROOT / 'release' / f'v{VERSION}' / 'dist', help='Portable-folder parent; defaults to a directory specific to this application version.')
    parser.add_argument('--release-dir', type=Path, default=ROOT / 'release' / f'v{VERSION}', help='Archive destination; defaults to release/v<application version>.')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise SystemExit('Build the Windows edition on Windows x64.')
    dependencies = check_dependency_versions()
    release = args.release_dir.resolve()
    if release.name.startswith('v') and release.name != f'v{VERSION}':
        raise SystemExit('Refusing to write this version into another version\'s release directory.')
    collect_licenses()
    original_hashes = source_hashes()
    distpath = args.distpath.resolve()
    if not args.archives_only:
        # Avoid capturing unrelated DLLs from another application's PATH.
        build_environment = os.environ.copy()
        windows_folder = Path(os.environ.get('SystemRoot', r'C:\Windows'))
        build_environment['PATH'] = os.pathsep.join(map(str, (
            Path(sys.executable).parent, Path(sys.base_prefix),
            Path(sys.base_prefix) / 'DLLs', windows_folder / 'System32', windows_folder,
        )))
        build_environment.pop('PYTHONPATH', None)
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--workpath', str(ROOT / 'build' / f'v{VERSION}'), '--distpath', str(distpath), str(ROOT / 'MoonAlign.spec')], cwd=ROOT, env=build_environment, check=True)
    portable = distpath / 'MoonAlign'
    if not (portable / 'MoonAlign.exe').is_file():
        raise RuntimeError('The portable executable has not been built.')
    if source_hashes() != original_hashes:
        raise RuntimeError('Application source changed while building; rebuild before distributing.')
    previous_manifest = portable / 'build_info.json'
    previous_build = None
    if args.archives_only:
        previous_build = json.loads(previous_manifest.read_text(encoding='utf-8')) if previous_manifest.is_file() else None
        if not previous_build or previous_build.get('source_sha256') != original_hashes:
            raise RuntimeError('Application source differs from the existing executable; a full rebuild is required.')
    for name in ('README.md', 'README_使用说明.txt', '快速入门.txt', '验证记录.txt', 'LICENSE', 'THIRD_PARTY_NOTICES.txt'):
        if (ROOT / name).is_file():
            copy_file(ROOT / name, portable / name)
    shutil.copytree(ROOT / 'licenses', portable / 'licenses', dirs_exist_ok=True)
    if (ROOT / 'docs').is_dir():
        shutil.copytree(ROOT / 'docs', portable / 'docs', dirs_exist_ok=True)
    if (ROOT / 'CHANGELOG.md').is_file():
        copy_file(ROOT / 'CHANGELOG.md', portable / 'CHANGELOG.md')
    manifest = {
        'application': 'MoonAlign', 'version': VERSION,
        'built_utc': datetime.now(timezone.utc).isoformat(),
        'python': sys.version, 'architecture': 'Windows x64',
        'dependencies': dependencies,
        'entrypoint': 'MoonAlign.exe', 'distribution': 'onedir',
        'source_sha256': original_hashes,
    }
    if previous_build:
        manifest = dict(previous_build, documentation_updated_utc=datetime.now(timezone.utc).isoformat())
    (portable / 'build_info.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.build_only:
        print(json.dumps({'version': VERSION, 'portable': str(portable), 'archives_created': False}, ensure_ascii=False, indent=2))
        return
    release.mkdir(parents=True, exist_ok=True)
    portable_zip = release / f'MoonAlign_Windows_x64_v{VERSION}.zip'
    make_zip(portable, portable_zip)
    source_zip = release / f'MoonAlign_Source_v{VERSION}.zip'
    with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        # Explicit inclusion avoids photographs, build caches, tests' output, and virtual environments.
        paths = [ROOT / name for name in (
            'launch.py', 'build_portable.py', 'MoonAlign.spec', 'requirements.txt',
            'requirements-build.txt', 'README.md', 'README_使用说明.txt', '快速入门.txt', '验证记录.txt',
            'LICENSE', 'THIRD_PARTY_NOTICES.txt', 'CHANGELOG.md', '.gitignore', '.gitattributes',
        )]
        paths += list((ROOT / 'moonalign').rglob('*.py'))
        paths += list(ROOT.glob('test*.py'))
        paths += list((ROOT / 'tests').rglob('*.py')) if (ROOT / 'tests').exists() else []
        paths += [p for p in (ROOT / 'licenses').rglob('*') if p.is_file()]
        paths += [p for p in (ROOT / 'docs').rglob('*') if p.is_file()]
        for item in sorted(set(paths)):
            if item.is_file() and '__pycache__' not in item.parts:
                archive.write(item, 'MoonAlign_Source/' + item.relative_to(ROOT).as_posix())
    checksums = {
        archive.name: hashlib.sha256(archive.read_bytes()).hexdigest()
        for archive in (portable_zip, source_zip)
    }
    (release / 'SHA256SUMS.txt').write_text(''.join(f'{checksum}  {name}\n' for name, checksum in checksums.items()), encoding='utf-8')
    print(json.dumps({'version': VERSION, 'portable': str(portable), 'portable_zip': str(portable_zip), 'portable_zip_bytes': portable_zip.stat().st_size, 'source_zip': str(source_zip), 'source_zip_bytes': source_zip.stat().st_size, 'sha256': checksums}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
