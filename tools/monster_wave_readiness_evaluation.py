"""Offline full/scope context equivalence on existing curated evidence."""
from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path

from bot.catalog import build_default_resolver
from bot.observations import ObservationBatch
from bot.perception import (
    MONSTER_WAVE_ENTRY_READINESS_SCOPE, build_default_perception, select_detectors,
)
from tools.incremental_perception_evaluation import evaluate_detector_frame_pairs


def evaluate(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    manifest = root/'datasets/monster_wave_readiness_manifest.json'
    entries = json.loads(manifest.read_text())['entries']
    for entry in entries:
        path = (root/entry['path']).resolve()
        assert path.is_relative_to(root), entry['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], entry['path']
    full = build_default_perception(root)
    scoped = select_detectors(full, MONSTER_WAVE_ENTRY_READINESS_SCOPE)
    resolver = build_default_resolver()
    output.mkdir(parents=True, exist_ok=True)
    reports, states = {}, {}
    for label, engine in (('full', full), ('scoped', scoped)):
        frames, stats = evaluate_detector_frame_pairs(root, [e['path'] for e in entries],
            engine.detectors, cache_path=output/'pairs.json')
        reports[label] = asdict(stats)
        states[label] = []
        for seq, (frame, entry) in enumerate(zip(frames, entries), 1):
            state = resolver.resolve(ObservationBatch(seq, float(seq), frame.observations))
            actual = dict(status=state.status.value, base_context=state.base_context,
                          overlays=list(state.overlays))
            assert actual == entry['expected'], (label, entry['path'], actual, entry['expected'])
            states[label].append(actual)
    assert states['full'] == states['scoped']
    report = dict(frames=len(entries), equivalent=len(states['full']),
        full_detectors=len(full.detectors), scoped_detectors=len(scoped.detectors),
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        evaluation=reports, wrong=0)
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', default='.')
    parser.add_argument('--output', default='artifacts/mw_readiness_validation/current')
    args = parser.parse_args()
    evaluate(args.repo_root, args.output)


if __name__ == '__main__':
    main()
