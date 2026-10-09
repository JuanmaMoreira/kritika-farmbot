"""Incremental OCR evaluation confined to the newly acquired Lobby pair reader."""
import hashlib
import json
from pathlib import Path
import cv2
from bot.arena_farming_resources import ArenaFarmingResourceReader
from bot.arena_flow_reader import ArenaFlowReader
from bot.ocr import RapidOcrEngine

ROOT = Path(__file__).resolve().parents[1]


def main():
    entries = json.loads((ROOT/'tests/fixtures/arena_farming/manifest.json').read_text())['entries']
    stock = json.loads((ROOT/'tests/fixtures/arena_farming/buff_stock_manifest.json').read_text())
    entries.append({**stock, 'id': 'buff1_stock_999', 'kind': 'stock'})
    output = ROOT/'artifacts/arena_farming/evaluation'; output.mkdir(parents=True, exist_ok=True)
    cache_path = output/'cache.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    fingerprint = hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in (
        'bot/arena_farming_resources.py', 'bot/arena_flow_reader.py', 'bot/ocr.py'))).hexdigest()
    reader = ArenaFarmingResourceReader(None, RapidOcrEngine())
    stock_reader = ArenaFlowReader(reader.engine)
    results = []; reused = 0
    for entry in entries:
        path = ROOT/entry['path']; digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry['sha256']: raise ValueError('fixture provenance mismatch')
        key = fingerprint + digest
        if key in cache:
            value = cache[key]; reused += 1
        else:
            image = cv2.imread(str(path))
            value = (stock_reader._stock_integer(image, (0, 0, 1, 1), lambda: False)
                     if entry.get('kind') == 'stock' else reader._pair(image, (0, 0, 1, 1)))
            cache[key] = value
        results.append(dict(id=entry['id'], expected=entry['expected'], observed=value,
                            passed=value == entry['expected']))
    report = dict(results=results, samples=len(results), reused=reused,
                  computed=len(results)-reused, wrong=sum(not r['passed'] for r in results))
    cache_path.write_text(json.dumps(cache, indent=2)+'\n', encoding='utf8')
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf8')
    print(json.dumps(report))
    return bool(report['wrong'])


if __name__ == '__main__': raise SystemExit(main())
