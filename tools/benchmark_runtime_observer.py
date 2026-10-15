"""Offline, deterministic observer comparison; no device or wall-clock sleeps.

Run from the repository root with tools/agent_run.ps1 tools.benchmark_runtime_observer.
Only runtime_observer is loaded from --baseline; transition/executor wiring is
the working tree in both subprocesses. Analysis cost is simulated at 5 ms.
"""

import argparse
import json
import subprocess
import sys
from types import SimpleNamespace


def measure(revision):
    if revision != 'worktree':
        import bot.runtime_observer as observer_module

        source = subprocess.run(
            ['git', 'show', f'{revision}:bot/runtime_observer.py'],
            check=True, capture_output=True, text=True,
        ).stdout
        exec(compile(source, f'{revision}:bot/runtime_observer.py', 'exec'), observer_module.__dict__)

    import numpy as np
    from bot.action_executor import ActionExecutor, FrameGeometry
    from bot.capture import FrameSnapshot
    from bot.observations import ObservationBatch
    from bot.resolver import ContextResolver
    from bot.runtime_observer import RuntimeObserver, RuntimeFacts, RuntimeSnapshot, RuntimeEvidenceRequirements, RuntimeWaitCancelled
    from bot.semantic_actions import OpenQuickMenu
    from bot.verified_transition import VerifiedTransition, VerifiedTransitionPolicy

    rows = {}
    for name in ('static_baseline', 'static_pending', 'immediate_success', 'new_frame',
                 'predispatch_then_new', 'late_native', 'blocker', 'cancel_static',
                 'slow_postcondition'):
        now = [10.]
        counts = dict(analyses=0, dispatches=0, polls=0)
        image = np.zeros((20, 40, 3), np.uint8)

        def get_frame():
            counts['polls'] += 1
            seq, timestamp = 2, 10.
            if name in {'static_baseline', 'cancel_static', 'new_frame'}:
                seq = 1
            if name in {'predispatch_then_new', 'late_native'}:
                timestamp = 9.9  # Includes the acquisition start of a late native frame.
            if name in {'new_frame', 'predispatch_then_new'} and now[0] >= 10.02:
                seq, timestamp = 3, 10.02
            return FrameSnapshot(image.copy(), timestamp, seq, source_id='lifetime')

        class Perception:
            def analyze(self, frame):
                counts['analyses'] += 1
                now[0] += .005
                return ObservationBatch(frame.sequence, frame.timestamp, coverage={'guard'})

        class Adb:
            def tap(self, *args):
                counts['dispatches'] += 1

        def expected(s):
            if name == 'slow_postcondition':
                now[0] += .125
            return name in {'immediate_success', 'blocker', 'slow_postcondition'} or (
                name in {'new_frame', 'predispatch_then_new'} and s.sequence == 3)

        def sleep(seconds):
            now[0] += seconds

        observer = RuntimeObserver(
            SimpleNamespace(get_frame=get_frame),
            Perception(), ContextResolver(), poll_interval=.01,
            clock=lambda: now[0], metrics_clock=lambda: now[0], sleeper=sleep,
        )
        frame = FrameSnapshot(image, 9.99, 1, source_id='lifetime')
        batch = ObservationBatch(1, 9.99, coverage={'guard'})
        before = RuntimeSnapshot(frame, batch, ContextResolver().resolve(batch), RuntimeFacts(), FrameGeometry(40, 20))
        transition = VerifiedTransition(observer, ActionExecutor(Adb()), clock=lambda: now[0])
        evidence = (RuntimeEvidenceRequirements(max_age=.05, required_coverage={'guard'})
                    if name in {'late_native', 'predispatch_then_new'} else None)
        try:
            result = transition.execute(
                name, OpenQuickMenu(), before, expected=expected,
                abort_if=(lambda s: True) if name == 'blocker' else None,
                cancel_requested=(lambda: now[0] >= 10.03) if name == 'cancel_static' else None,
                evidence=evidence,
                policy=VerifiedTransitionPolicy(normal_timeout=1, grace_timeout=1,
                                                max_attempts=1, total_timeout=.125),
            )
            outcome = result.outcome.value
            ready = result.ready
        except RuntimeWaitCancelled:
            outcome, ready = 'cancelled', False
        rows[name] = {**counts, 'elapsed_ms': round((now[0] - 10.) * 1000, 3),
                      'outcome': outcome, 'ready': ready}
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='5000b57')
    parser.add_argument('--revision', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.revision:
        print(json.dumps(measure(args.revision)))
        return
    results = {}
    for revision in (args.baseline, 'worktree'):
        child = subprocess.run(
            [sys.executable, '-m', 'tools.benchmark_runtime_observer', '--revision', revision],
            check=True, capture_output=True, text=True,
        )
        results[revision] = json.loads(child.stdout)
    for name, before in results[args.baseline].items():
        after = results['worktree'][name]
        assert (before['outcome'], before['ready'], before['dispatches']) == (
            after['outcome'], after['ready'], after['dispatches']), name
        if before['ready']:
            assert after['elapsed_ms'] <= before['elapsed_ms'], name
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
