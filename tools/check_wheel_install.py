#!/usr/bin/env python3
"""T26/package: install our wheel in a disposable empty venv, fully offline.

The environment has no pip/pytest/build dependencies, uses the current Python,
and is removed on exit. No repository path is injected into the consumer import.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib

CONSUMER_CHECKS = '''
from importlib import metadata
from pathlib import Path
import platform
import sys
import framework
names = {item.metadata['Name'].casefold() for item in metadata.distributions()}
assert names == {'bot3d-kernel'}, names
assert metadata.version('bot3d-kernel') == sys.argv[1]
assert not metadata.requires('bot3d-kernel')
assert Path(framework.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
'''

CONSUMER_REPORT = '''
print('PASS: clean wheel consumer; only bot3d-kernel installed; no source path or runtime dependencies.')
print('PASS: typed goal and framed transform work in the clean consumer.')
print('PASS: read-only registry preserves mock identity and unknown feedback.')
print('PASS: a synthetic session acquires, activates, and expires within its scoped authority.')
print('PASS: command retries retain original journal facts and immutable UNKNOWN terminal history.')
print('INFO: consumer Python ' + platform.python_version() + '; no device connection.')
'''


def run(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)
    if result.returncode:
        raise RuntimeError(f'subcommand failed with exit {result.returncode}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', nargs='?', type=Path, help='one locally built wheel; default: the unique project wheel in dist')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if sys.version_info[:2] != (3, 12):
        print('FAIL: run this check with the selected CPython 3.12 environment.')
        return 1
    uv = shutil.which('uv')
    if not uv:
        print('FAIL: uv is required for offline installation without pip seeding.')
        return 1
    if args.wheel:
        wheel = args.wheel.resolve()
    else:
        wheels = list((root / 'dist').glob('bot3d_kernel-*.whl'))
        if len(wheels) != 1:
            print('FAIL: build first; dist must contain exactly one project wheel, or pass its path.')
            return 1
        wheel = wheels[0].resolve()
    if not wheel.is_file():
        print('FAIL: wheel does not exist.')
        return 1
    version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    try:
        probe = (root / 'tools/installed_api_probe.py').read_text(encoding='utf-8')
        with TemporaryDirectory(prefix='kernel-wheel-check-') as directory:
            temporary = Path(directory)
            environment = temporary / 'consumer'
            print('INFO: creating an empty disposable consumer outside the repository.')
            run([sys.executable, '-I', '-m', 'venv', '--without-pip', str(environment)], temporary)
            executable = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
            run([uv, 'pip', 'install', '--offline', '--no-index', '--no-deps',
                 '--python', str(executable), str(wheel)], temporary)
            code = CONSUMER_CHECKS + probe + CONSUMER_REPORT
            run([str(executable), '-I', '-c', code, version], temporary)
    except (OSError, RuntimeError) as exc:
        print(f'FAIL: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
