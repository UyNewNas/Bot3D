"""T26/package: run against the installed, non-editable distribution."""
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

import pytest
import framework

pytestmark = pytest.mark.t26_package
ROOT = Path(__file__).resolve().parents[1]


def test_exact_reference_python_is_used():
    assert sys.version_info[:2] == (3, 12)
    assert platform.python_implementation() == 'CPython'
    assert platform.python_version() == (ROOT / '.python-version').read_text().strip()


def test_distribution_metadata_and_no_runtime_dependencies():
    info = metadata.metadata('bot3d-kernel')
    assert info['Version'] == '0.1.0'
    assert set(info['Requires-Python'].split(',')) == {'>=3.12', '<3.13'}
    assert not info.get_all('Requires-Dist', [])


def test_package_origin_is_installed_not_the_source_checkout():
    origin = Path(framework.__file__).resolve()
    assert not origin.is_relative_to(ROOT / 'src')
    assert any(part.casefold() == 'site-packages' for part in origin.parts)
    distribution = metadata.distribution('bot3d-kernel')
    direct = distribution.read_text('direct_url.json')
    if direct:
        assert not json.loads(direct).get('dir_info', {}).get('editable', False)


def test_isolated_import_from_outside_the_repository(tmp_path):
    code = '''
import framework
from framework.domain.time import MonotonicInstant
from framework.domain.geometry import Quaternion, RigidTransform
from framework.domain.targets import PoseGoal
from framework.domain.values import FrameId, RobotId, ToolId, Vector3
from framework.application.ports import MonotonicClock
from framework.adapters.clocks import ManualMonotonicClock, SystemMonotonicClock
clock = ManualMonotonicClock(clock_id='isolated-wheel')
assert clock.now() == MonotonicInstant('isolated-wheel', 0)
clock.advance_ns(7)
assert clock.now().tick_ns == 7
base = FrameId('arm-fixture/base')
world = FrameId('cell/world')
identity = Quaternion.from_xyzw((0, 0, 0, 1))
goal = PoseGoal(RobotId('arm-fixture'), base, ToolId('tool0'), Vector3(1, 0, 0), identity)
moved = goal.transformed(RigidTransform(world, base, Vector3(1, 2, 3), identity))
assert (moved.frame_id, moved.position_m.as_tuple()) == (world, (2.0, 2.0, 3.0))
print('isolated installed package import OK')
'''
    result = subprocess.run([sys.executable, '-I', '-c', code], cwd=tmp_path,
                            check=True, capture_output=True, text=True)
    assert result.stdout.strip() == 'isolated installed package import OK'
