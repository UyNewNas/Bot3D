#!/usr/bin/env python3
"""Read-only dependency checks for the implemented pure core, not a sandbox.

The domain/application packages and package root may use permitted standard
library modules and inward core imports. Concurrency belongs to the application
layer, not the pure domain. Adapters are intentionally outside this rule.
Known dynamic-import and executable-code escape forms are rejected, but
this static policy does not prove the absence of all malicious Python behavior.
"""
from __future__ import annotations

import argparse
import ast
from importlib.util import resolve_name
from pathlib import Path
import sys

FORBIDDEN_STDLIB = {
    'http', 'urllib', 'socket', 'ssl', 'sqlite3', 'dbm', 'subprocess',
    'ctypes', 'importlib', 'builtins', 'xmlrpc', 'wsgiref',
}
DOMAIN_FORBIDDEN_STDLIB = {'threading', '_thread', 'asyncio', 'concurrent', 'multiprocessing'}
DYNAMIC_CALLS = {'__import__', 'eval', 'exec', 'compile'}
ALLOWED_INTERNAL = {
    'root': ('framework.domain', 'framework.application'),
    'domain': ('framework.domain',),
    'application': ('framework.domain', 'framework.application'),
}


def import_violations(source: str, module: str, *, layer: str, is_package: bool = False) -> list[tuple[int, str]]:
    """Check synthetic or real source without importing it."""
    if layer not in ALLOWED_INTERNAL:
        raise ValueError('unknown core layer')
    tree = ast.parse(source)
    issues = []
    package = module if is_package else module.rpartition('.')[0]

    def check_target(target, line):
        root = target.split('.', 1)[0]
        if root in FORBIDDEN_STDLIB:
            issues.append((line, f'core must not depend on {root}'))
        elif layer == 'domain' and root in DOMAIN_FORBIDDEN_STDLIB:
            issues.append((line, f'pure domain must not depend on concurrency module {root}'))
        elif root == 'framework':
            if not any(target == prefix or target.startswith(prefix + '.')
                       for prefix in ALLOWED_INTERNAL[layer]):
                issues.append((line, f'{layer} depends outward on {target}'))
        elif root not in sys.stdlib_module_names:
            issues.append((line, f'non-stdlib dependency in pure core: {target}'))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                check_target(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                try:
                    base = resolve_name('.' * node.level + base, package)
                except (ImportError, ValueError):
                    issues.append((node.lineno, 'relative import escapes core package'))
                    continue
            for alias in node.names:
                if alias.name == '*':
                    issues.append((node.lineno, 'star import obscures the dependency boundary'))
                else:
                    check_target(base + '.' + alias.name, node.lineno)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in DYNAMIC_CALLS:
                issues.append((node.lineno, f'dynamic code/import forbidden: {node.func.id}'))
    return sorted(set(issues))


def check_tree(package_root: Path) -> tuple[int, list[str]]:
    if not package_root.is_dir():
        return 0, ['framework package is missing']
    count, errors = 0, []
    for path in sorted(package_root.rglob('*.py')):
        relative = path.relative_to(package_root)
        if len(relative.parts) == 1:
            layer = 'root'
        elif relative.parts[0] in {'domain', 'application'}:
            layer = relative.parts[0]
        else:
            continue
        count += 1
        pieces = list(relative.with_suffix('').parts)
        is_package = pieces[-1] == '__init__'
        if is_package:
            pieces.pop()
        module = '.'.join(['framework', *pieces])
        try:
            issues = import_violations(path.read_text(encoding='utf-8'), module,
                                       layer=layer, is_package=is_package)
            errors.extend(f'{relative.as_posix()}:{line}: {message}' for line, message in issues)
        except (SyntaxError, UnicodeError, OSError) as exc:
            errors.append(f'{relative.as_posix()}: {exc}')
    if not count:
        errors.append('no core Python modules were checked')
    return count, errors


def self_test() -> int:
    cases = [
        ('import math', 'domain', False),
        ('from dataclasses import dataclass', 'domain', False),
        ('from .time import MonotonicInstant', 'domain', False),
        ('from ..domain.time import MonotonicInstant', 'application', False),
        ('from typing import Protocol', 'application', False),
        ('import asyncio', 'application', False),
        ('from threading import Lock', 'application', False),
        ('import rclpy', 'domain', True),
        ('import fastapi', 'domain', True),
        ('import pydantic', 'application', True),
        ('import sqlalchemy', 'domain', True),
        ('import http.client', 'domain', True),
        ('import sqlite3', 'application', True),
        ('import socket', 'domain', True),
        ('import xmlrpc.client', 'root', True),
        ('from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from xmlrpc.client import ServerProxy', 'domain', True),
        ('def connect():\n    import xmlrpc.client as rpc', 'application', True),
        ('from wsgiref.simple_server import make_server', 'application', True),
        ('from threading import Lock', 'domain', True),
        ('import _thread as threads', 'domain', True),
        ('from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import asyncio', 'domain', True),
        ('def build_executor():\n    from concurrent.futures import ThreadPoolExecutor', 'domain', True),
        ('from multiprocessing import Process', 'domain', True),
        ('from framework.adapters import clocks', 'application', True),
        ('from ..application import ports', 'domain', True),
        ('from ... import outside', 'domain', True),
        ('from .time import *', 'domain', True),
        ("__import__('rclpy')", 'domain', True),
        ("eval('1')", 'domain', True),
        ("exec('pass')", 'application', True),
        ("compile('1', '', 'eval')", 'domain', True),
        ('from importlib import import_module as load', 'domain', True),
    ]
    failures = []
    for source, layer, rejected in cases:
        issues = import_violations(source, 'framework.' + layer + '.example', layer=layer)
        if bool(issues) != rejected:
            failures.append(source)
    for source in failures:
        print('FAIL self-test: ' + source)
    print(f'{"FAIL" if failures else "PASS"}: {len(cases)} in-memory dependency-policy self-tests; {len(failures)} failed.')
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true', help='run only standard-library in-memory policy fixtures')
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    root = Path(__file__).resolve().parents[1]
    count, errors = check_tree(root / 'src/framework')
    for error in errors:
        print('FAIL: ' + error)
    if errors:
        return 1
    print(f'PASS: {count} core Python modules obey inward dependency rules.')
    print('INFO: static source policy only; runtime import tests are separate; not a sandbox.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
