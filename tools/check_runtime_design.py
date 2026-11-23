#!/usr/bin/env python3
"""DOC-only deterministic design oracle; NOT a runtime or product T31/T34 test.

Reads hand-authored traces, checks explicit expectations and deliberately unsafe
mutants. No threads, sleep, network, device ports, package dependencies or writes.
Injected durability, writer-barrier and parking certificates are assumptions;
this tool cannot establish those facts for a real adapter or storage system.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
from pathlib import Path

PUBLIC = set('REJECTED ACCEPTED PLANNING DISPATCHING EXECUTING CANCEL_REQUESTED SUCCEEDED CANCELLED FAILED TIMED_OUT INTERRUPTED'.split())
TERMINAL = set('REJECTED SUCCEEDED CANCELLED FAILED TIMED_OUT INTERRUPTED'.split())
TRACE_TAGS = set('stop-before-plan intent-inflight queued-revoked context-invalid start-equal lease-equal budget-equal before-deadline claim-before-stop accepted-before-stop receipt-not-parking early-parking no-parking complete-stop log-blocked audit-failure lost-response late-accept restart-late-send old-stop normal-cancel cancel-after-claim one-shot unknown-history-unlock stale-after-audit missing-cancel-proof'.split())
RECOVERY_TAGS = set('unknown-safe success-moving failure-writer-live no-feedback stale-feedback early-feedback receipt-only app-epoch-only local-exit-only handle-not-found binding-mismatch unauthorized audit-failure no-post-barrier-stop success-safe failure-safe no-intent-live-writer fenced-safe'.split())
OPS = set('plan intent_pending intent_saved queued claim send accepted stop cancel repeat_stop stop_ack park park_stale close_writer cancel_confirmed audit audit_fail journal_block unlock response_lost query_unknown invalidate restart old_stop authorize timeout'.split())
WRITER_PROOFS = set('NONE APP_EPOCH_ONLY LOCAL_EXIT_ONLY HANDLE_NOT_FOUND DRAIN_CONFIRMED FENCE_CONFIRMED'.split())
MOTION_PROOFS = set('NONE STALE EARLY_STOPPED STOP_ACK MOVING FRESH_STOPPED'.split())
MUTANTS = ('queued-ticket-authority', 'receipt-unlocks', 'early-parking', 'query-resubmits',
           'restart-replays', 'retarget-old-attempt', 'ignore-writer', 'ignore-audit',
           'parking-rewrites-history')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_load(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'duplicate JSON key: {key}')
            result[key] = value
        return result

    def number(token):
        value = float(token)
        require(math.isfinite(value), 'non-finite JSON number')
        return value

    def constant(token):
        raise ValueError(f'non-finite JSON constant: {token}')

    return json.loads(text, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


@dataclass
class TraceModel:
    limits: dict
    mutant: str = ''
    seq: int = 0
    now: int = 0
    state: str = 'PLANNING'
    certainty: str = 'PENDING'
    slot: bool = True
    locked: bool = False
    arming: str = 'ARMED'
    lease: bool = True
    plan: bool = False
    intent: bool = False
    intent_at: int = 0
    queued: bool = False
    ticket: str = 'none'
    claimed: bool = False
    called: bool = False
    cancelled: bool = False
    epoch_changed: bool = False
    writer_closed: bool = True
    barrier: int = 0
    stop_seq: int = 0
    parking: int = 0
    fresh: bool = False
    cancel_proof: bool = False
    authorized: bool = False
    audit_available: bool = True
    audit_stamp: tuple | None = None
    execute_calls: int = 0
    stop_calls: int = 0
    query_calls: int = 0
    target: str = 'none'
    notes: list[str] = field(default_factory=list)

    def request_stop(self):
        self.stop_calls += 1
        self.stop_seq = self.seq

    def revoke(self, clear_control=True):
        self.cancelled = True
        if not self.claimed:
            self.ticket = 'revoked'
        if clear_control:
            self.arming, self.lease = 'DISARMED', False

    def stop(self, clear_control=True):
        self.revoke(clear_control)
        self.request_stop()
        if self.state not in TERMINAL:
            if self.claimed:
                self.state, self.certainty = 'CANCEL_REQUESTED', 'PENDING'
            else:
                self.state, self.certainty = 'CANCELLED', 'CONFIRMED'
                self.slot, self.cancel_proof = False, True

    def finish(self, state):
        if self.state in TERMINAL:
            return
        self.state = state
        self.certainty = 'UNKNOWN' if self.claimed else 'CONFIRMED'
        self.slot = False
        self.revoke()
        self.request_stop()

    def stamp(self):
        return (self.barrier, self.stop_seq, self.parking, self.epoch_changed,
                self.fresh, self.cancel_proof, self.authorized, self.now)

    def ready_to_unlock(self):
        history_ok = (self.state == 'CANCEL_REQUESTED' and self.cancel_proof) or (
            self.state in TERMINAL and (self.certainty != 'UNKNOWN' or self.authorized))
        temporal = self.barrier > 0 and self.stop_seq > self.barrier and self.parking > self.stop_seq
        if self.mutant == 'early-parking':
            temporal = self.parking > 0 and self.stop_seq > 0
        return (self.claimed and self.writer_closed and self.fresh and temporal
                and history_ok and self.audit_available)

    def claim(self):
        unsafe_queue_grant = self.mutant == 'queued-ticket-authority' and self.queued and not self.claimed
        if not unsafe_queue_grant:
            if self.state != 'DISPATCHING' or self.ticket != 'open' or self.cancelled:
                return
            if self.now >= self.limits['lease_expiry']:
                self.stop()
                return
            if self.now >= self.limits['start_before'] or self.now - self.intent_at >= self.limits['budget']:
                self.finish('TIMED_OUT')
                return
            if not (self.plan and self.intent and self.queued and self.lease
                    and self.arming == 'ARMED' and not self.epoch_changed and not self.locked):
                return
        self.claimed, self.locked, self.writer_closed = True, True, False
        self.ticket, self.parking, self.fresh = 'consumed', 0, False

    def apply(self, op):
        self.seq += 1
        if op.startswith('tick:'):
            value = int(op.split(':', 1)[1])
            require(value >= self.now, 'model clock must be monotonic')
            self.now = value
        elif op == 'plan':
            self.plan = True
        elif op == 'intent_saved':
            self.intent = True
            if self.state == 'PLANNING' and self.plan and not self.cancelled:
                self.state, self.ticket, self.intent_at = 'DISPATCHING', 'open', self.now
        elif op == 'queued':
            self.queued = True
        elif op == 'claim':
            self.claim()
        elif op == 'send':
            if self.claimed and not self.called and not self.writer_closed:
                self.called = True
                self.execute_calls += 1
                self.target = 'current' if self.mutant == 'retarget-old-attempt' and self.epoch_changed else 'original'
        elif op == 'accepted':
            require(self.called, 'cannot receive acceptance without a model send')
            if self.state == 'DISPATCHING':
                self.state = 'EXECUTING'
        elif op in {'stop', 'cancel'}:
            self.stop(clear_control=op == 'stop')
        elif op == 'repeat_stop':
            self.request_stop()
        elif op == 'stop_ack':
            if self.mutant == 'receipt-unlocks':
                self.locked = False
        elif op in {'park', 'park_stale'}:
            self.parking, self.fresh = self.seq, op == 'park'
        elif op == 'close_writer':
            self.writer_closed, self.barrier = True, self.seq
        elif op == 'cancel_confirmed':
            self.cancel_proof = True
        elif op == 'authorize':
            self.authorized = True
        elif op == 'audit_fail':
            self.audit_available, self.audit_stamp = False, None
            self.revoke()
        elif op == 'audit':
            self.audit_stamp = self.stamp() if self.ready_to_unlock() else None
        elif op == 'unlock':
            if self.locked and self.ready_to_unlock() and self.audit_stamp == self.stamp():
                self.locked, self.slot = False, False
                if self.state == 'CANCEL_REQUESTED':
                    self.state, self.certainty = 'CANCELLED', 'CONFIRMED'
        elif op == 'response_lost':
            require(self.called, 'lost receipt requires a model send')
            self.finish('INTERRUPTED')
        elif op == 'query_unknown':
            self.query_calls += 1
            if self.mutant == 'query-resubmits':
                self.execute_calls += 1
        elif op in {'invalidate', 'restart'}:
            self.epoch_changed = True
            self.finish('INTERRUPTED')
            if self.mutant == 'restart-replays' and op == 'restart':
                self.execute_calls += 1
        elif op == 'timeout':
            self.finish('TIMED_OUT')
        elif op not in {'intent_pending', 'journal_block', 'old_stop'}:
            raise ValueError(f'unknown operation: {op}')
        require(self.execute_calls <= 1, 'second model execution attempt')
        require(not self.execute_calls or self.intent and self.claimed, 'send without intent and final claim')
        require(self.state in PUBLIC, 'new public command state')
        self.notes.append(f'{self.seq}:{op}:{self.state}/{self.certainty}:lock={self.locked}')

    def view(self):
        return dict(state=self.state, certainty=self.certainty, slot=self.slot,
                    locked=self.locked, execute_calls=self.execute_calls,
                    stop_calls=self.stop_calls, query_calls=self.query_calls,
                    arming=self.arming, lease=self.lease, ticket=self.ticket,
                    writer_closed=self.writer_closed, epoch_changed=self.epoch_changed,
                    target=self.target)


def recovery_view(case, mutant=''):
    evidence = case['evidence']
    writer_ok = evidence['writer_proof'] in {'DRAIN_CONFIRMED', 'FENCE_CONFIRMED'}
    if mutant == 'ignore-writer':
        writer_ok = True
    audit_ok = evidence['audit_saved'] or mutant == 'ignore-audit'
    motion_ok = evidence['motion_proof'] == 'FRESH_STOPPED' and evidence['post_barrier_stop']
    allowed = evidence['binding_matches'] and writer_ok and motion_ok and evidence['authorized'] and audit_ok
    state, certainty = case['terminal_state'], case['terminal_certainty']
    if mutant == 'parking-rewrites-history' and allowed and certainty == 'UNKNOWN':
        state, certainty = 'SUCCEEDED', 'CONFIRMED'
    return dict(may_unlock=allowed, terminal_state=state, terminal_certainty=certainty,
                arming='DISARMED', lease_restored=False, execute_calls=0,
                new_epoch=True, history_rewritten=(state, certainty) != (case['terminal_state'], case['terminal_certainty']))


def validate(data):
    require(isinstance(data, dict) and set(data) == {'schema_version', 'evidence_level', 'cases'}, 'unknown or missing manifest fields')
    require(type(data['schema_version']) is int and data['schema_version'] == 1 and data['evidence_level'] == 'DOC', 'expected DOC schema version 1')
    require(isinstance(data['cases'], list), 'cases must be a list')
    seen, themes = set(), {'T31': set(), 'T34': set()}
    for case in data['cases']:
        require(isinstance(case, dict) and case.get('test') in themes, 'expected T31 or T34 case')
        test = case['test']
        common = {'id', 'test', 'theme', 'expected'}
        fields = common | ({'limits', 'steps'} if test == 'T31' else {'terminal_state', 'terminal_certainty', 'evidence'})
        require(set(case) == fields, f'unknown or missing {test} fields')
        require(isinstance(case['theme'], str), 'theme must be a string')
        require(case['id'] == test + '/' + case['theme'] and case['id'] not in seen, 'invalid or duplicate case ID')
        seen.add(case['id'])
        themes[test].add(case['theme'])
        if test == 'T31':
            limits = case['limits']
            require(isinstance(limits, dict) and set(limits) == {'start_before', 'lease_expiry', 'budget'}, 'invalid model limits')
            require(all(type(v) is int and v > 0 for v in limits.values()), 'limits must be positive integer ticks')
            require(isinstance(case['steps'], list) and case['steps'], 'steps must be nonempty')
            for step in case['steps']:
                require(isinstance(step, str), 'step must be a string')
                tick = step.split(':', 1)
                require(step in OPS or len(tick) == 2 and tick[0] == 'tick' and tick[1].isdigit(), f'unknown step: {step}')
            sample = TraceModel(limits).view()
        else:
            require(case['terminal_state'] in TERMINAL and case['terminal_certainty'] in {'CONFIRMED', 'UNKNOWN'}, 'invalid original terminal')
            require(case['terminal_state'] not in {'SUCCEEDED', 'CANCELLED', 'REJECTED'} or case['terminal_certainty'] == 'CONFIRMED', 'invalid terminal certainty')
            evidence = case['evidence']
            bool_fields = {'binding_matches', 'post_barrier_stop', 'authorized', 'audit_saved', 'intent_exists'}
            require(isinstance(evidence, dict) and set(evidence) == bool_fields | {'writer_proof', 'motion_proof'}, 'invalid evidence fields')
            require(all(type(evidence[k]) is bool for k in bool_fields), 'evidence flags must be boolean')
            require(evidence['writer_proof'] in WRITER_PROOFS and evidence['motion_proof'] in MOTION_PROOFS, 'unknown evidence category')
            sample = recovery_view(case)
        expected = case['expected']
        require(isinstance(expected, dict) and set(expected) == set(sample), 'expected must specify the entire safety view')
        require(all(type(expected[k]) is type(sample[k]) for k in sample), 'invalid expected value type')
    require(themes['T31'] == TRACE_TAGS, 'missing or unknown mandatory T31 themes')
    require(themes['T34'] == RECOVERY_TAGS, 'missing or unknown mandatory T34 themes')
    return data['cases']


def run_case(case, mutant=''):
    try:
        if case['test'] == 'T31':
            model = TraceModel(case['limits'], mutant)
            for step in case['steps']:
                model.apply(step)
            actual = model.view()
        else:
            actual = recovery_view(case, mutant)
        wrong = {key: (case['expected'][key], value) for key, value in actual.items() if case['expected'][key] != value}
        return '' if not wrong else f'{case["id"]}: expected/actual {wrong}'
    except (ValueError, TypeError, KeyError) as exc:
        return f'{case["id"]}: {exc}'


def self_test(data, cases):
    total, failed = 0, []

    def check(name, valid, details=''):
        nonlocal total
        total += 1
        if not valid:
            failed.append(name)
            print(f'FAIL DOC self-test: {name}: {details}')

    baseline = [error for case in cases if (error := run_case(case))]
    check('all hand-authored traces', not baseline, '; '.join(baseline))
    for mutant in MUTANTS:
        killed_by = [case['id'] for case in cases if run_case(case, mutant)]
        check('kill ' + mutant, bool(killed_by))
        if killed_by:
            print(f'PASS DOC mutant rejected: {mutant} by {killed_by[0]}')
    for text, valid in [('{"x":1}', True), ('{"x":1,"x":2}', False),
                        ('{"x":NaN}', False), ('{"x":Infinity}', False),
                        ('{"x":1e400}', False), ('{"x":-1e400}', False)]:
        try:
            strict_load(text)
            accepted = True
        except ValueError:
            accepted = False
        check('strict JSON ' + text, accepted == valid)

    def bad_manifest(name, change):
        damaged = deepcopy(data)
        change(damaged)
        try:
            validate(damaged)
            rejected = False
        except (ValueError, TypeError, KeyError):
            rejected = True
        check(name, rejected)

    bad_manifest('missing mandatory theme', lambda d: d['cases'].pop(0))
    bad_manifest('duplicate ID', lambda d: d['cases'].append(deepcopy(d['cases'][0])))
    bad_manifest('unknown step', lambda d: d['cases'][0]['steps'].append('implicit_retry'))
    bad_manifest('unknown manifest field', lambda d: d.update(network='disabled'))
    bad_manifest('unknown case field', lambda d: d['cases'][0].update(hidden_override=True))
    bad_manifest('incomplete expected view', lambda d: d['cases'][0]['expected'].pop('locked'))
    bad_manifest('boolean is not numeric ticks', lambda d: d['cases'][0]['limits'].update(budget=True))
    bad_manifest('non-DOC evidence level', lambda d: d.update(evidence_level='REAL'))
    changed = deepcopy(cases[0])
    changed['steps'] = ['tick:2', 'tick:1']
    check('non-monotonic clock rejected', bool(run_case(changed)))
    print(f'{"FAIL" if failed else "PASS"} DOC: {total} oracle self-tests; {len(failed)} failed; {len(MUTANTS)} unsafe mutants checked.')
    print('INFO: design assumptions only; no product T31/T34 run and no device safety proof.')
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true', help='check oracle validation and rejection of unsafe mutants')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / 'docs/design/runtime-scenarios.json'
    try:
        data = strict_load(source.read_text(encoding='utf-8'))
        cases = validate(data)
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        print(f'FAIL DOC manifest: {exc}')
        return 1
    if args.self_test:
        return self_test(data, cases)
    errors = []
    for case in cases:
        error = run_case(case)
        if error:
            errors.append(error)
            print(f'FAIL DOC: {error}')
        else:
            print(f'PASS DOC: {case["id"]}')
    counts = {test: sum(case['test'] == test for case in cases) for test in ('T31', 'T34')}
    print(f'{"FAIL" if errors else "PASS"} DOC: {len(cases)} design cases; T31={counts["T31"]}, T34={counts["T34"]}; {len(errors)} failed.')
    print('INFO: no product T31/T34 run; no threads, device, storage, simulator, or fencing verified.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
