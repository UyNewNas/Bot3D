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

PROBE = '''
from importlib import metadata
from pathlib import Path
import platform
import sys
import framework
from framework.adapters.clocks import ManualMonotonicClock, SystemMonotonicClock
from framework.application.ports import MonotonicClock
from framework.domain.time import MonotonicInstant, ClockDomainMismatch
from framework.domain.geometry import Quaternion, RigidTransform
from framework.domain.targets import PoseGoal
from framework.domain.values import FrameId, RobotId, ToolId, Vector3, mm_to_m
names = {item.metadata['Name'].casefold() for item in metadata.distributions()}
assert names == {'bot3d-kernel'}, names
assert metadata.version('bot3d-kernel') == sys.argv[1]
assert not metadata.requires('bot3d-kernel')
assert Path(framework.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
clock = ManualMonotonicClock(clock_id='clean-consumer')
start = clock.now()
clock.advance_ns(9)
assert clock.now().elapsed_ns_since(start) == 9
assert isinstance(SystemMonotonicClock().now(), MonotonicInstant)
try:
    start.elapsed_ns_since(MonotonicInstant('other-clock', 0))
except ClockDomainMismatch:
    pass
else:
    raise AssertionError('cross-clock arithmetic accepted')
base = FrameId('arm-fixture/base')
world = FrameId('cell/world')
robot = RobotId('arm-fixture')
tool = ToolId('tool0')
identity = Quaternion.from_xyzw([0, 0, 0, 1])
goal = PoseGoal(robot, base, tool, Vector3(mm_to_m(1000), 0, 0), identity)
moved = goal.transformed(RigidTransform(world, base, Vector3(1, 2, 3), identity))
assert (moved.robot_id, moved.frame_id, moved.tool_id) == (robot, world, tool)
assert moved.position_m.as_tuple() == (2.0, 2.0, 3.0)
assert moved.orientation_xyzw == identity
assert goal.frame_id == base
assert sys.version_info[:2] == (3, 12)
print('PASS: clean wheel consumer; only bot3d-kernel installed; no source path or runtime dependencies.')
print('PASS: typed goal and framed transform work in the clean consumer.')
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
        with TemporaryDirectory(prefix='kernel-wheel-check-') as directory:
            temporary = Path(directory)
            environment = temporary / 'consumer'
            print('INFO: creating an empty disposable consumer outside the repository.')
            run([sys.executable, '-I', '-m', 'venv', '--without-pip', str(environment)], temporary)
            executable = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
            run([uv, 'pip', 'install', '--offline', '--no-index', '--no-deps',
                 '--python', str(executable), str(wheel)], temporary)
            run([str(executable), '-I', '-c', PROBE, version], temporary)
    except (OSError, RuntimeError) as exc:
        print(f'FAIL: {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
