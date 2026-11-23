#!/usr/bin/env python3
"""Read-only checks for the repository's Markdown and project tracking tables.

Standard library only; no network, subprocesses, imports from the project, or writes.
This is a deliberately small checker for the inline-link/pipe-table Markdown used
here, not a general Markdown renderer or a verifier of product correctness.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import posixpath
import re
from typing import Callable
from urllib.parse import unquote, urlsplit

REQ = 'docs/project/requirements.md'
DEV = 'docs/project/backlog.md'
TEST = 'docs/project/test-plan.md'
GATE = 'docs/project/acceptance.md'
ITER = 'docs/project/iterations/I01-M1-foundation.md'
RECORD = 'docs/project/records/AR-0001-tracking-bootstrap.md'
REQUIRED = (REQ, DEV, TEST, GATE, ITER, RECORD, 'docs/README.md',
            'docs/project/README.md')
REQ_HEAD = ('需求 ID', '优先级', '状态', '需求', '验收标准', '来源')
DEV_HEAD = ('开发 ID', '状态', '交付物与完成条件', '前置开发')
TEST_HEAD = ('测试 ID', '环境 / 子场景', '输入 / 故障', '必须断言')
GATE_HEAD = ('闸门 ID', '范围 / 前置', '必须证据与出口')
MAP_HEAD = ('需求 ID', '开发 ID', '测试 ID', '首次闸门', '必须复验闸门')
AR_HEAD = ('记录 ID', '日期', '范围', '记录')
KINDS = {
    'REQ': r'REQ-\d{3}', 'AC': r'AC-\d{3}',
    'DEV': r'DEV-(?:M[1-5]|OPT)-\d{2}', 'T': r'T\d{2}',
    'G': r'G-(?:DOC|I\d{2}|M[1-5]|EXT)', 'AR': r'AR-\d{4}',
}
ID_RE = re.compile(r'(?<![A-Za-z0-9_-])(?:' + '|'.join(KINDS.values())
                   + r')(?![A-Za-z0-9_-])')
REQ_STATES = set('DRAFT READY DEVELOPING TESTING ACCEPTANCE ACCEPTED BLOCKED DEFERRED'.split())
DEV_STATES = set('DRAFT TODO DOING DONE BLOCKED DEFERRED'.split())
ITER_STATES = set('PLANNED ACTIVE IN_ACCEPTANCE CLOSED BLOCKED'.split())
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
LINK = re.compile(r'!?\[[^\]\n]*\]\(([^\n)]+)\)')


def strict_json(text: str) -> object:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result

    def number(token):
        value = float(token)
        if not math.isfinite(value):
            raise ValueError(f'non-finite JSON number: {token}')
        return value

    def constant(token):
        raise ValueError(f'non-finite JSON constant: {token}')

    return json.loads(text, object_pairs_hook=pairs, parse_float=number,
                      parse_constant=constant)


def cells(line: str) -> tuple[str, ...]:
    """Split pipe tables, respecting escaped pipes and escaped backslashes."""
    parts, current, escaped = [], [], False
    for char in line.strip():
        if char == '|' and not escaped:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
        escaped = not escaped if char == chr(92) else False
    parts.append(''.join(current).strip())
    return tuple(parts[1:-1])


@dataclass
class Table:
    path: str
    line: int
    header: tuple[str, ...]
    rows: list[tuple[int, tuple[str, ...]]]


@dataclass
class Audit:
    errors: list[str] = field(default_factory=list)
    stats: Counter = field(default_factory=Counter)
    definitions: dict[str, set[str]] = field(default_factory=lambda: {k: set() for k in KINDS})

    def error(self, code: str, location: str, message: str) -> None:
        self.errors.append(f'{location}: {code}: {message}')


def parse_document(path: str, text: str, audit: Audit) -> tuple[list[str], list[Table], set[str]]:
    lines = text.splitlines()
    visible = [''] * len(lines)
    fence = None
    block: list[str] = []
    block_start = 0
    for index, line in enumerate(lines):
        location = f'{path}:{index + 1}'
        if line.rstrip() != line:
            audit.error('whitespace', location, 'trailing whitespace')
        match = FENCE.match(line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= fence[1] and not match[2].strip():
                if fence[2] == 'json':
                    audit.stats['json'] += 1
                    try:
                        strict_json('\n'.join(block))
                    except (ValueError, RecursionError) as exc:
                        audit.error('json', f'{path}:{block_start}', str(exc))
                fence = None
            else:
                block.append(line)
        elif match:
            fence = (match[1][0], len(match[1]), match[2].strip().lower())
            block, block_start = [], index + 1
        else:
            visible[index] = line
    if fence:
        audit.error('fence', f'{path}:{block_start}', 'unclosed fenced block')
    if not text.endswith('\n'):
        audit.error('newline', path, 'missing final newline')
    titles = [line for line in visible if line.startswith('# ')]
    if len(titles) != 1 or not lines or not lines[0].startswith('# '):
        audit.error('title', path, 'expected exactly one H1 at the start')

    anchors, seen = set(), Counter()
    for line in visible:
        heading = re.match(r'^#{1,6} (.+?)\s*#*$', line)
        if heading:
            slug = re.sub(r'<[^>]*>', '', heading[1]).lower().replace('`', '')
            slug = re.sub(r'[^\w -]', '', slug).replace(' ', '-')
            suffix = f'-{seen[slug]}' if seen[slug] else ''
            seen[slug] += 1
            anchors.add(slug + suffix)
    tables, index = [], 0
    while index < len(visible):
        if not visible[index].lstrip().startswith('|'):
            index += 1
            continue
        start, group = index, []
        while index < len(visible) and visible[index].lstrip().startswith('|'):
            line = visible[index].strip()
            if not line.endswith('|'):
                audit.error('table', f'{path}:{index + 1}', 'table row must end with a pipe')
            group.append((index + 1, cells(line)))
            index += 1
        width = len(group[0][1])
        if len(group) < 2 or not all(re.fullmatch(r':?-{3,}:?', c) for c in group[1][1]):
            audit.error('table', f'{path}:{start + 1}', 'missing table separator')
        if any(len(row) != width for _, row in group):
            audit.error('table', f'{path}:{start + 1}', 'inconsistent table column count')
        tables.append(Table(path, start + 1, group[0][1], group[2:]))
    audit.stats['tables'] += len(tables)
    return visible, tables, anchors


def tokens(text: str, kind: str) -> set[str]:
    return {item for item in ID_RE.findall(text) if re.fullmatch(KINDS[kind], item)}


def check_graph(graph: dict[str, set[str]], audit: Audit) -> None:
    active, done = [], set()

    def visit(node):
        if node in active:
            audit.error('cycle', DEV, ' -> '.join(active[active.index(node):] + [node]))
            return
        if node in done:
            return
        active.append(node)
        for parent in sorted(graph[node]):
            if parent not in graph:
                audit.error('dependency', DEV, f'{node} depends on undefined {parent}')
            else:
                visit(parent)
        active.pop()
        done.add(node)

    for node in sorted(graph):
        visit(node)


def audit_documents(documents: dict[str, str], exists: Callable[[str], bool] | None = None) -> Audit:
    audit = Audit()
    if exists is None:
        exists = lambda name: name in documents
    for name in REQUIRED:
        if name not in documents:
            audit.error('required', name, 'required document missing')
    parsed = {name: parse_document(name, text, audit) for name, text in sorted(documents.items())}
    audit.stats['documents'] = len(documents)
    for name, (visible, _, _) in parsed.items():
        for number, line in enumerate(visible, 1):
            for match in LINK.finditer(line):
                target = match[1].strip()
                # Current docs use inline links without optional titles.
                if target.startswith('<') and target.endswith('>'):
                    target = target[1:-1]
                try:
                    url = urlsplit(target)
                except ValueError as exc:
                    audit.error('link', f'{name}:{number}', str(exc))
                    continue
                if url.scheme in {'https', 'http', 'mailto'} or url.netloc:
                    continue  # Never fetch external links.
                audit.stats['links'] += 1
                decoded = unquote(url.path)
                if url.scheme or decoded.startswith('/') or chr(92) in decoded:
                    audit.error('link', f'{name}:{number}', f'unsupported local target: {target}')
                    continue
                local = posixpath.normpath(posixpath.join(posixpath.dirname(name), decoded)) if decoded else name
                if local == '..' or local.startswith('../') or not exists(local):
                    audit.error('link', f'{name}:{number}', f'missing or out-of-root target: {target}')
                elif url.fragment and local in parsed and unquote(url.fragment) not in parsed[local][2]:
                    audit.error('anchor', f'{name}:{number}', f'unknown heading anchor: {target}')

    def rows(name, header):
        tables = parsed.get(name, ([], [], set()))[1]
        selected = [table for table in tables if table.header == header]
        if not selected:
            audit.error('definition-table', name, f'missing authoritative table: {header[0]}')
        for table in selected:
            for number, row in table.rows:
                if len(row) == len(header):
                    if not all(row):
                        audit.error('empty-cell', f'{name}:{number}', 'authoritative cells must not be empty')
                    yield number, row

    def define(kind, item, location):
        if not re.fullmatch(KINDS[kind], item):
            audit.error('id', location, f'invalid {kind} ID: {item}')
        elif item in audit.definitions[kind]:
            audit.error('duplicate', location, f'duplicate definition: {item}')
        else:
            audit.definitions[kind].add(item)

    def status_totals(name, counts):
        preface = '\n'.join(parsed.get(name, ([], [], set()))[0]).split('\n## ', 1)[0]
        declared_pairs = re.findall(r'(\d+) 项 ([A-Z_]+)', preface)
        declared = {state: int(count) for count, state in declared_pairs}
        if len(declared) != len(declared_pairs) or declared != dict(counts):
            audit.error('status-count', name, f'declared {declared}; actual {dict(counts)}')
        for states in re.findall(r'没有 ([A-Z_]+(?: 或 [A-Z_]+)*) 项', preface):
            for state in states.split(' 或 '):
                if counts[state]:
                    audit.error('status-count', name, f'claims no {state}, found {counts[state]}')

    req_counts, dev_counts, graph = Counter(), Counter(), {}
    for number, row in rows(REQ, REQ_HEAD):
        item, priority, state, _, ac, _ = row
        location = f'{REQ}:{number}'
        define('REQ', item, location)
        ac_ids = re.findall(KINDS['AC'], ac)
        if ac_ids != ['AC-' + item.removeprefix('REQ-')]:
            audit.error('ac-pair', location, 'expected exactly one matching AC ID')
        for ac_id in ac_ids:
            define('AC', ac_id, location)
        if state not in REQ_STATES or priority not in {'P0', 'P1', 'P2'}:
            audit.error('status', location, f'invalid priority/state: {priority}/{state}')
        req_counts[state] += 1
    for number, row in rows(DEV, DEV_HEAD):
        item, state, _, dependencies = row
        location = f'{DEV}:{number}'
        define('DEV', item, location)
        if state not in DEV_STATES:
            audit.error('status', location, f'invalid development state: {state}')
        dev_counts[state] += 1
        graph[item] = tokens(dependencies, 'DEV')
        if not graph[item] and dependencies != '无':
            audit.error('dependency', location, 'expected DEV IDs or 无')
    status_totals(REQ, req_counts)
    status_totals(DEV, dev_counts)
    for path, header, kind in ((TEST, TEST_HEAD, 'T'), (GATE, GATE_HEAD, 'G')):
        for number, row in rows(path, header):
            define(kind, row[0], f'{path}:{number}')
    for name, (visible, _, _) in parsed.items():
        if re.fullmatch(r'docs/project/records/AR-\d{4}-[^/]+\.md', name):
            item = Path(name).name[:7]
            define('AR', item, name)
            if not visible or not re.match(r'^# ' + item + r'(?!\d)', visible[0]):
                audit.error('record-title', name, 'record title must match filename ID')
        if re.fullmatch(r'docs/project/iterations/I\d{2}-[^/]+\.md', name):
            states = re.findall(r'^- 迭代状态：([A-Z_]+)$', '\n'.join(visible), re.M)
            if len(states) != 1 or states[0] not in ITER_STATES:
                audit.error('iteration-state', name, 'expected one valid iteration state')
            audit.stats['iterations'] += 1

    mapped, used_dev, used_tests = set(), set(), set()
    for number, row in rows(REQ, MAP_HEAD):
        item, developments, tests, first_gate, repeat_gates = row
        location = f'{REQ}:{number}'
        if item in mapped:
            audit.error('matrix', location, f'duplicate matrix row: {item}')
        mapped.add(item)
        dev_ids, test_ids = tokens(developments, 'DEV'), tokens(tests, 'T')
        if not dev_ids or not test_ids or len(tokens(first_gate, 'G')) != 1:
            audit.error('matrix', location, 'need development, test, and one first gate')
        if repeat_gates not in {'无', '-'} and not tokens(repeat_gates, 'G'):
            audit.error('matrix', location, 'repeat gate must be defined or explicitly 无')
        used_dev.update(dev_ids)
        used_tests.update(test_ids)
    if mapped != audit.definitions['REQ']:
        audit.error('matrix', REQ, f'matrix/REQ mismatch: {sorted(mapped ^ audit.definitions["REQ"])}')
    for kind, used in (('DEV', used_dev), ('T', used_tests)):
        missing = audit.definitions[kind] - used
        if missing:
            audit.error('coverage', REQ, f'unmapped {kind}: {sorted(missing)}')
    indexed = set()
    for number, row in rows(GATE, AR_HEAD):
        item = row[0]
        if item in indexed:
            audit.error('record-index', f'{GATE}:{number}', f'duplicate record index: {item}')
        indexed.add(item)
        if not re.search(r'records/' + re.escape(item) + r'-[^)]+\.md', row[3]):
            audit.error('record-index', f'{GATE}:{number}', 'record link must match its ID')
    if indexed != audit.definitions['AR']:
        audit.error('record-index', GATE, 'record files and index differ')
    all_ids = set().union(*audit.definitions.values())
    for name, (visible, _, _) in parsed.items():
        for number, line in enumerate(visible, 1):
            for item in sorted(set(ID_RE.findall(line)) - all_ids):
                audit.error('reference', f'{name}:{number}', f'undefined ID: {item}')
    check_graph(graph, audit)
    audit.stats['dependencies'] = sum(map(len, graph.values()))
    return audit


def fixture() -> dict[str, str]:
    def table(header, data):
        return ('| ' + ' | '.join(header) + ' |\n| ' + ' | '.join('---' for _ in header)
                + ' |\n' + ''.join('| ' + ' | '.join(row) + ' |\n' for row in data))

    documents = {name: '# Fixture\n' for name in REQUIRED}
    documents[REQ] += ('\n- 当前状态：1 项 READY；没有 ACCEPTED 项\n\n'
        + table(REQ_HEAD, [('REQ-001', 'P0', 'READY', 'Goal', 'AC-001: test', 'Design')])
        + '\n' + table(MAP_HEAD, [('REQ-001', 'DEV-M1-01', 'T01', 'G-M1', '无')]))
    documents[DEV] += ('\n- 当前状态：1 项 TODO；没有 DONE 项\n\n'
        + table(DEV_HEAD, [('DEV-M1-01', 'TODO', 'Deliver', '无')]))
    documents[TEST] += '\n' + table(TEST_HEAD, [('T01', 'MOCK', 'Input', 'Assert')])
    documents[GATE] += ('\n' + table(GATE_HEAD, [('G-M1', 'MOCK', 'Evidence')]) + '\n'
        + table(AR_HEAD, [('AR-0001', '2026-11-20', 'DOC',
                          '[Record](records/AR-0001-tracking-bootstrap.md)')]))
    documents[ITER] += '\n- 迭代状态：PLANNED\n'
    documents[RECORD] = '# AR-0001: Fixture\n'
    return documents


def self_test() -> int:
    checks, failed = 0, 0

    def check(name, condition, details=''):
        nonlocal checks, failed
        checks += 1
        if not condition:
            failed += 1
            print(f'FAIL self-test: {name}: {details}')

    for text, valid in [('{"a":[0,1.5,true,null]}', True),
                        ('{"a":1,"a":2}', False), ('{"x":{"a":1,"a":2}}', False),
                        ('{"x":NaN}', False), ('{"x":Infinity}', False),
                        ('{"x":-Infinity}', False), ('{"x":1e400}', False),
                        ('{"x":-1e400}', False), ('{"a":1} trailing', False)]:
        try:
            strict_json(text)
            accepted = True
        except ValueError:
            accepted = False
        check(f'strict JSON {text}', accepted == valid)
    check('escaped pipe', cells('| a' + chr(92) + '|b | c |') == ('a' + chr(92) + '|b', 'c'))
    check('escaped backslash', len(cells('| a' + chr(92) * 2 + '| b |')) == 2)

    base = fixture()

    def scenario(name, path=None, change=None, expected=None):
        documents = dict(base)
        if path:
            if change is None:
                del documents[path]
            else:
                documents[path] = change(documents[path])
        result = audit_documents(documents)
        ok = not result.errors if expected is None else any(f': {expected}:' in e for e in result.errors)
        check(name, ok, '; '.join(result.errors))

    scenario('valid tracking fixture')
    scenario('missing document', ITER, expected='required')
    scenario('missing newline', 'docs/README.md', lambda s: s.rstrip(), 'newline')
    scenario('missing H1', 'docs/README.md', lambda s: s.replace('# ', '## '), 'title')
    scenario('trailing whitespace', 'docs/README.md', lambda s: s + 'text  \n', 'whitespace')
    scenario('unclosed fence', 'docs/README.md', lambda s: s + '\n```json\n{}\n', 'fence')
    scenario('bad JSON block', 'docs/README.md', lambda s: s + '\n```json\n{"x":1e400}\n```\n', 'json')
    scenario('table width', TEST, lambda s: s.replace('| T01 | MOCK |', '| T01 | MOCK | extra |'), 'table')
    scenario('missing separator', TEST, lambda s: s.replace('| --- | --- | --- | --- |', '| x | y | z | w |'), 'table')
    scenario('missing link', 'docs/README.md', lambda s: s + '[missing](missing.md)\n', 'link')
    scenario('out of root link', 'docs/README.md', lambda s: s + '[escape](../../outside.md)\n', 'link')
    scenario('valid anchor', 'docs/README.md', lambda s: s + '[ok](#fixture)\n')
    scenario('invalid anchor', 'docs/README.md', lambda s: s + '[bad](#absent)\n', 'anchor')
    scenario('external link not fetched', 'docs/README.md', lambda s: s + '[outside](https://example.invalid/a)\n')
    scenario('fenced template ignored', 'docs/README.md', lambda s: s + '\n```markdown\nREQ-999\n| broken\n```\n')
    scenario('duplicate definition', TEST, lambda s: s + '| T01 | MOCK | Again | Assert |\n', 'duplicate')
    scenario('AC mismatch', REQ, lambda s: s.replace('AC-001:', 'AC-002:'), 'ac-pair')
    scenario('invalid task state', DEV, lambda s: s.replace('| TODO |', '| INVALID |'), 'status')
    scenario('stale status counts', REQ, lambda s: s.replace('1 项 READY', '2 项 READY'), 'status-count')
    scenario('false no-DONE claim', DEV, lambda s: s.replace('| TODO |', '| DONE |'), 'status-count')
    scenario('missing matrix row', REQ,
             lambda s: s.replace('| REQ-001 | DEV-M1-01 | T01 | G-M1 | 无 |\n', ''), 'matrix')
    scenario('duplicate matrix row', REQ,
             lambda s: s + '| REQ-001 | DEV-M1-01 | T01 | G-M1 | 无 |\n', 'matrix')
    scenario('missing definition table', TEST, lambda s: s.replace('测试 ID', 'Other'), 'definition-table')
    scenario('undefined reference', 'docs/README.md', lambda s: s + 'REQ-999\n', 'reference')
    scenario('unmapped test', TEST, lambda s: s + '| T02 | MOCK | Extra | Assert |\n', 'coverage')
    scenario('unknown dependency', DEV, lambda s: s.replace('Deliver | 无', 'Deliver | DEV-M1-99'), 'dependency')
    scenario('self cycle', DEV, lambda s: s.replace('Deliver | 无', 'Deliver | DEV-M1-01'), 'cycle')
    scenario('record title mismatch', RECORD, lambda s: s.replace('AR-0001', 'AR-0002'), 'record-title')
    scenario('record index mismatch', GATE,
             lambda s: s.replace('| AR-0001 |', '| AR-0002 |'), 'record-index')
    scenario('iteration state', ITER, lambda s: s.replace('PLANNED', 'DONE'), 'iteration-state')
    graph_audit = Audit()
    check_graph({'a': {'b'}, 'b': {'a'}}, graph_audit)
    check('two-node cycle', any(': cycle:' in e for e in graph_audit.errors))
    graph_audit = Audit()
    check_graph({'a': {'b', 'c'}, 'b': {'c'}, 'c': set()}, graph_audit)
    check('DAG accepted', not graph_audit.errors)
    print(f'{"FAIL" if failed else "PASS"}: {checks} in-memory self-tests; {failed} failed; no files written.')
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true', help='run in-memory positive and negative fixtures only')
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    root = Path(__file__).resolve().parents[1]
    try:
        paths = sorted((root / 'docs').rglob('*.md'))
        if (root / 'README.md').is_file():
            paths.insert(0, root / 'README.md')
        documents = {path.relative_to(root).as_posix(): path.read_text(encoding='utf-8')
                     for path in paths}
    except (OSError, UnicodeError) as exc:
        print(f'FAIL: could not read documentation: {exc}')
        return 1

    def exists(name):
        target = (root / name).resolve()
        return target.is_relative_to(root) and target.exists()

    result = audit_documents(documents, exists)
    if result.errors:
        for error in result.errors:
            print(f'FAIL: {error}')
        print(f'FAIL: {len(result.errors)} documentation issues; no product tests run.')
        return 1
    counts = result.stats
    print(f'PASS: {counts["documents"]} Markdown documents; structure, {counts["tables"]} tables, '
          f'{counts["json"]} strict JSON blocks.')
    print(f'PASS: {counts["links"]} local links and heading anchors resolve; external links not fetched.')
    print('PASS: authoritative IDs and references: '
          + ', '.join(f'{key}={len(value)}' for key, value in result.definitions.items()) + '.')
    print(f'PASS: one matrix row per REQ; all DEV and T definitions mapped; '
          f'{counts["dependencies"]} development dependencies exist and are acyclic.')
    print(f'PASS: ledger status totals, {counts["iterations"]} iteration state(s), and AR index agree.')
    print('INFO: documentation checks only; no product, simulator, XR, REAL, or acceptance tests run.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
