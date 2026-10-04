from pathlib import Path
import json
from types import SimpleNamespace as S
from unittest.mock import Mock
import cv2,pytest
from bot.perception import build_default_perception
from bot.catalog import build_default_resolver
from bot.capture import FrameSnapshot
from bot.runtime_observer import RuntimeObserver
from bot.socket_inventory_relief import SocketInventoryRelief, _is_clean_socket, _is_tappable_animation, _is_no_material

def test_native_socket_scope_preserves_safe_inputs_completion_and_upper_layers():
 root=Path(__file__).resolve().parents[1]
 entries=json.loads((root/'datasets/socket_inventory_relief_semantic_manifest.json').read_text())['entries']
 if not all((root/e['path']).is_file() for e in entries):pytest.skip('historical native Socket corpus absent')
 full=build_default_perception();resolver=build_default_resolver()
 operation=SocketInventoryRelief(RuntimeObserver(Mock(),full,resolver),Mock(),Mock(),Mock())
 narrow=operation.tap_through.observer.perception
 assert len(narrow.detectors)==8
 for i,e in enumerate(entries,1):
  frame=FrameSnapshot(cv2.imread(str(root/e['path'])),float(i),i)
  signatures=[]
  for pe in (full,narrow):
   batch=pe.analyze(frame);s=S(state=resolver.resolve(batch),observations=batch)
   signatures.append((_is_tappable_animation(s),_is_clean_socket(s),_is_no_material(s)))
  assert signatures[0]==signatures[1],e['path']
 assert operation.animation_policy.tap_interval==.2
