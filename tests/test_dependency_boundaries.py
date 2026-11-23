"""T26/imports: positive/negative policy fixtures plus a real isolated import."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.t26_imports
ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('_boundary_policy', ROOT / 'tools/check_import_boundaries.py')
assert spec is not None and spec.loader is not None
policy = module_from_spec(spec)
spec.loader.exec_module(policy)


def test_implemented_core_obeys_inward_dependencies():
    count, errors = policy.check_tree(ROOT / 'src/framework')
    assert count >= 5
    assert not errors, errors


@pytest.mark.parametrize('source,layer', [
    ('import math', 'domain'),
    ('from dataclasses import dataclass', 'domain'),
    ('from .time import MonotonicInstant', 'domain'),
    ('from ..domain.time import MonotonicInstant', 'application'),
    ('from typing import Protocol', 'application'),
])
def test_allowed_imports(source, layer):
    assert not policy.import_violations(source, f'framework.{layer}.example', layer=layer)


@pytest.mark.parametrize('layer', ['root', 'domain', 'application'])
@pytest.mark.parametrize('source', [
    'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from xmlrpc.client import ServerProxy',
    'def connect():\n    import xmlrpc.client as rpc',
    'from wsgiref.simple_server import make_server',
])
def test_core_rejects_stdlib_http_transports(source, layer):
    module = 'framework' if layer == 'root' else f'framework.{layer}.example'
    assert policy.import_violations(source, module, layer=layer, is_package=layer == 'root')


@pytest.mark.parametrize('source', [
    'from threading import Lock',
    'import _thread as threads',
    'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import asyncio',
    'def build_executor():\n    from concurrent.futures import ThreadPoolExecutor',
    'from multiprocessing import Process',
])
def test_domain_rejects_concurrency_dependencies(source):
    assert policy.import_violations(source, 'framework.domain.example', layer='domain')


@pytest.mark.parametrize('source', ['import asyncio', 'from threading import Lock'])
def test_application_can_use_concurrency_primitives(source):
    assert not policy.import_violations(source, 'framework.application.example', layer='application')


@pytest.mark.parametrize('source', [
    'import rclpy', 'import moveit', 'import fastapi', 'import pydantic',
    'import sqlalchemy', 'import UnityEngine', 'import http.client',
    'import socket', 'import sqlite3', 'import urllib.request',
    'from framework.adapters.clocks import ManualMonotonicClock',
    'from ..adapters import clocks', 'from ..application.ports import MonotonicClock',
    'from ... import outside', 'from .time import *',
    "__import__('pydantic')", "eval('1')", "exec('pass')", "compile('1', '', 'eval')",
    'from importlib import import_module as load',
    'from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import rclpy',
])
def test_outward_and_hidden_imports_rejected(source):
    assert policy.import_violations(source, 'framework.domain.example', layer='domain')


def test_application_port_cannot_import_an_adapter():
    source = 'from framework.adapters.clocks import SystemMonotonicClock'
    assert policy.import_violations(source, 'framework.application.ports', layer='application')


def test_package_relative_import_resolution():
    assert not policy.import_violations('from .time import MonotonicInstant',
                                        'framework.domain', layer='domain', is_package=True)


def test_missing_package_cannot_pass_with_zero_checked_modules(tmp_path):
    count, errors = policy.check_tree(tmp_path / 'absent')
    assert count == 0 and errors


def test_inward_helper_cannot_hide_a_transitive_adapter_dependency(tmp_path):
    root = tmp_path / 'framework'
    domain = root / 'domain'
    domain.mkdir(parents=True)
    (root / '__init__.py').write_text('')
    (domain / '__init__.py').write_text('from .helper import value')
    (domain / 'helper.py').write_text('from framework.adapters import value')
    count, errors = policy.check_tree(root)
    assert count == 3
    assert any('helper.py' in item and 'outward' in item for item in errors)


def test_installed_core_import_has_no_transport_dependencies_or_service_start(tmp_path):
    code = '''
import sys
blocked = {'rclpy', 'moveit', 'UnityEngine', 'fastapi', 'pydantic', 'sqlalchemy',
           'http', 'urllib', 'socket', 'sqlite3', 'xmlrpc', 'wsgiref'}
class BlockOuterDependencies:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in blocked:
            raise RuntimeError('outer dependency imported: ' + fullname)
        return None

def deny_io(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen', 'os.system'}:
        raise RuntimeError('unexpected I/O on core import: ' + event)
sys.meta_path.insert(0, BlockOuterDependencies())
sys.addaudithook(deny_io)
import framework
from framework.domain.time import MonotonicInstant
from framework.domain.geometry import Quaternion, RigidTransform
from framework.domain.targets import PoseGoal
from framework.domain.values import FrameId, RobotId, ToolId, Vector3
from framework.application.ports import MonotonicClock
assert not any(name.split('.')[0] in blocked for name in sys.modules)
assert MonotonicInstant('plain', 0).tick_ns == 0
base = FrameId('arm-fixture/base')
world = FrameId('cell/world')
identity = Quaternion(0, 0, 0, 1)
goal = PoseGoal(RobotId('arm-fixture'), base, ToolId('tool0'), Vector3(0, 0, 0), identity)
assert goal.transformed(RigidTransform(world, base, Vector3(1, 2, 3), identity)).frame_id == world
print('isolated core dependency boundary OK')
'''
    result = subprocess.run([sys.executable, '-I', '-c', code], cwd=tmp_path,
                            check=True, capture_output=True, text=True)
    assert result.stdout.strip() == 'isolated core dependency boundary OK'
