from dataclasses import replace
from types import SimpleNamespace as S
from unittest.mock import Mock
import numpy as np
import pytest
from bot.action_executor import ActionExecutor
from bot.capture import FrameSnapshot
from bot.equipment_sell_runtime import EquipmentSellRuntime
from bot.equipment_sell_policy import EquipmentSellPolicy
from bot.equipment_sell_operation import EquipmentSellCandidate,EquipmentSellOutcome,EquipmentSellResult
from bot.equipment_sell_semantics import EquipmentItemFact,EquipmentInventoryFact,EquipmentSellConfirmationFact,EquipmentGrade as G,EquipmentType as T,EquipmentBulkGroup as B
from bot.semantic_actions import CloseEquipmentDetail
from bot.equipment_inventory_relief import execute_inventory_relief


def harness(grade=G.RARE,kind=T.GLOVES,*,policy=None,inconclusive=False,wrong_popup=False,enhance=False):
 class Source:
  sequence=2;changed=False;clock=10.
  def get_frame(self):
   self.sequence+=1;image=np.zeros((1220,2712,3),np.uint8)
   if self.changed:image[310:448,1390:2035]=255
   return FrameSnapshot(image,self.clock,self.sequence)
 source=Source();adb=Mock();n=EquipmentSellRuntime(source,Mock(),ActionExecutor(adb),clock=lambda:source.clock,sleeper=lambda _:None)
 n._scan_policy=policy or EquipmentSellPolicy();calls=[]
 before=EquipmentInventoryFact(120,112,7,22,2,10.,(1,2))
 def inventory(cursor=0,predicate=lambda _:True):
  f=source.get_frame();n._latest=f;n._after_sequence=f.sequence
  return replace(before,sequence=f.sequence,observed_at=f.timestamp,sample_sequences=(f.sequence-1,f.sequence))
 def navigate(page,expected):return inventory()
 def next_fact(method,predicate=lambda _:True):
  if method=='confirmation_sample':source.get_frame()  # Both consensus frames follow Open Sell.
  f=source.get_frame();n._latest=f;n._after_sequence=f.sequence
  if method=='detail_sample':
   if inconclusive:return None
   observed_grade=G.ETHEREAL_PLUS if source.changed else grade
   return EquipmentItemFact('Candidate',observed_grade,kind,enhance,f.sequence,10.,(f.sequence-1,f.sequence),sell_available=True,grade_visual=observed_grade)
  if method=='confirmation_sample':
   group=B.ENHANCE_GRADE if enhance else B.TYPE_GRADE if grade==G.ETHEREAL else B.EQUIPMENT_GRADE
   if wrong_popup:group=B.EQUIPMENT_GRADE if enhance else B.ENHANCE_GRADE
   return EquipmentSellConfirmationFact('Candidate',group,kind if group==B.TYPE_GRADE else None,f.sequence,10.,(f.sequence-1,f.sequence))
  return EquipmentInventoryFact(100,112,7,22,f.sequence,10.,(f.sequence-1,f.sequence))
 n._inventory_after=inventory;n._navigate_page=navigate;n._read_next=next_fact
 original=n._tap
 def tap(action):calls.append(type(action).__name__);original(action)
 n._tap=tap
 return n,source,before,EquipmentSellCandidate(7,15),calls

@pytest.mark.parametrize('grade,kind',[(G.RARE,T.GLOVES),(G.ETHEREAL,T.GLOVES)])
def test_sellable_discovery_is_authorization_one_panel_then_bulk(grade,kind):
 n,_,before,candidate,calls=harness(grade,kind)
 item=n._inspect(candidate,before);result=n._bulk_candidate(candidate,n._scan_policy.authorize(item),item)
 assert result.succeeded and result.confirm_count==1
 assert calls==['SelectEquipmentInventorySlot','OpenEquipmentSell','ConfirmEquipmentBulkSale']
 assert 'reuse_selected_panel' in result.inputs and 'select_candidate' not in result.inputs
 assert n._block_stats['sellable_panel_opens']==1 and n._block_stats['same_item_reopens']==0
 assert result.after.item_count<result.before.item_count

@pytest.mark.parametrize('grade,kind',[(G.ETHEREAL,T.WEAPON),(G.ETHEREAL_PLUS,T.GLOVES)])
def test_protected_panel_closes_then_scan_never_bulk(grade,kind):
 n,_,before,candidate,calls=harness(grade,kind)
 item=n._inspect(candidate,before)
 assert n._scan_policy.authorize(item) is None and n._selected_sale is None
 assert calls==['SelectEquipmentInventorySlot','CloseEquipmentDetail']


def test_inconclusive_panel_closes_safely_no_sale():
 n,_,before,candidate,calls=harness(inconclusive=True)
 assert n._inspect(candidate,before) is None
 assert n._selected_sale is None and calls[-1]=='CloseEquipmentDetail'

@pytest.mark.parametrize('change',['candidate','context','stale','input'])
def test_selected_evidence_loss_never_consumes(change):
 n,source,before,candidate,calls=harness();item=n._inspect(candidate,before);authorization=n._scan_policy.authorize(item)
 if change=='candidate':candidate=EquipmentSellCandidate(7,14)
 if change=='context':source.changed=True
 if change=='stale':source.clock=13.
 if change=='input':n._not_before+=1.
 result=n._bulk_candidate(candidate,authorization,item)
 assert not result.succeeded and result.confirm_count==0
 assert 'OpenEquipmentSell' not in calls and 'ConfirmEquipmentBulkSale' not in calls


def test_contradictory_bulk_popup_never_confirms():
 n,_,before,candidate,calls=harness(wrong_popup=True);item=n._inspect(candidate,before)
 result=n._bulk_candidate(candidate,n._scan_policy.authorize(item),item)
 assert not result.succeeded and result.confirm_count==0 and calls[-1]=='CancelEquipmentSale'


def test_any_input_invalidates_retained_panel():
 n,_,before,candidate,_=harness();n._inspect(candidate,before)
 n._tap(CloseEquipmentDetail());assert n._selected_sale is None


def test_inventory_owner_accepts_retained_before_only_with_same_strong_item():
 n,_,before,candidate,_=harness();current=[before];selected=[None]
 def inspect(c,b):
  item=EquipmentItemFact('Candidate',G.RARE,T.GLOVES,False,4,10.,(3,4),sell_available=True,grade_visual=G.RARE)
  selected[0]=item;return item
 def bulk(c,a,item):
  after=replace(before,item_count=100,sequence=8,sample_sequences=(7,8));current[0]=after
  return EquipmentSellResult(EquipmentSellOutcome.SUCCESS,'item_count_decreased',before=before,item=item,after=after,inputs=('reuse_selected_panel','open_confirmation','confirm_bulk'))
 result=execute_inventory_relief(EquipmentSellPolicy(),read_inventory=lambda cursor:current[0],inspect=inspect,bulk_sell=bulk,expand=lambda b:pytest.fail('expansion'))
 assert result.succeeded and result.reason=='bulk_freed_capacity'


def panel_replay_frame(version,*,protected=False):
 import cv2,json
 from pathlib import Path
 root=Path(__file__).parent/'fixtures/equipment_selected_panel'
 m=json.loads((root/'manifest.json').read_text(encoding='utf-8'));w,h=m['geometry']
 image=np.zeros((h,w,3),np.uint8)
 for i,(x1,y1,x2,y2) in enumerate(m['regions']):
  name=f'protected_ethereal_plus_{i}.png' if protected and i<2 else f'positive_{version}_{i}.png'
  image[round(y1*h):round(y2*h),round(x1*w):round(x2*w)]=cv2.imread(str(root/name))
 return image

def test_real_same_selected_panel_survives_codec_and_background_noise():
 n,source,before,candidate,calls=harness(G.ETHEREAL,T.BOOTS)
 item=n._inspect(candidate,before)
 old=replace(n._latest,image=panel_replay_frame(0));n._latest=old
 n._selected_sale=replace(n._selected_sale,frame=old)
 source.sequence=old.sequence
 def next_replay():
  source.sequence+=1
  return FrameSnapshot(panel_replay_frame(1),10.,source.sequence)
 source.get_frame=next_replay
 result=n._bulk_candidate(candidate,n._scan_policy.authorize(item),item)
 assert result.succeeded and result.confirm_count==1
 assert calls==['SelectEquipmentInventorySlot','OpenEquipmentSell','ConfirmEquipmentBulkSale']
 assert n._block_stats['same_item_reopens']==0

def test_real_protected_ethereal_plus_panel_change_invalidates_selected_evidence():
 n,source,before,candidate,calls=harness(G.ETHEREAL,T.BOOTS)
 item=n._inspect(candidate,before)
 old=replace(n._latest,image=panel_replay_frame(0));n._latest=old
 n._selected_sale=replace(n._selected_sale,frame=old)
 source.changed=True  # The strong reader also observes the actual protected change.
 source.get_frame=lambda:FrameSnapshot(panel_replay_frame(1,protected=True),10.,old.sequence+1)
 result=n._bulk_candidate(candidate,n._scan_policy.authorize(item),item)
 assert result.outcome is EquipmentSellOutcome.DENIED and result.confirm_count==0
 assert calls==['SelectEquipmentInventorySlot']


@pytest.mark.parametrize('fresh_state',[
 'same','unknown','changed','stale','unconfirmed','sell_disabled','visual_mismatch','input','cancelled'])
def test_pixel_miss_revalidates_once_without_input_before_single_bulk(monkeypatch,fresh_state):
 n,source,before,candidate,calls=harness(G.EPIC,T.PANTS,enhance=True)
 item=n._inspect(candidate,before)
 old=replace(n._latest,image=panel_replay_frame(0));n._latest=old
 n._selected_sale=replace(n._selected_sale,frame=old)
 source.sequence=old.sequence
 def frames():
  source.sequence+=1
  return FrameSnapshot(panel_replay_frame(1),10.,source.sequence)
 source.get_frame=frames
 # The Ice Warlock incident rejected .998975 at the unchanged .999 threshold.
 monkeypatch.setattr('bot.equipment_sell_runtime.cv2.matchTemplate',
                     lambda *args,**kwargs:np.array([[.998975]],dtype=np.float32))
 original=n._read_next;reads=[]
 def reverify(method,predicate=lambda _:True):
  if method!='detail_sample':return original(method,predicate)
  reads.append(method)
  fresh=original(method,predicate)
  if fresh_state=='unknown':return None
  if fresh_state=='changed':return replace(fresh,grade=G.ETHEREAL_PLUS,grade_visual=G.ETHEREAL_PLUS)
  if fresh_state=='stale':return replace(fresh,sequence=item.sequence,sample_sequences=item.sample_sequences)
  if fresh_state=='unconfirmed':return replace(fresh,sample_sequences=(fresh.sequence,))
  if fresh_state=='sell_disabled':return replace(fresh,sell_available=False)
  if fresh_state=='visual_mismatch':return replace(fresh,grade_visual=G.ETHEREAL_PLUS)
  if fresh_state=='input':n._not_before+=1
  if fresh_state=='cancelled':n.cancel_requested=lambda:True
  return fresh
 n._read_next=reverify
 result=n._bulk_candidate(candidate,n._scan_policy.authorize(item),item)
 assert reads==['detail_sample']
 if fresh_state=='same':
  assert result.succeeded and result.confirm_count==1
  assert calls==['SelectEquipmentInventorySlot','OpenEquipmentSell','ConfirmEquipmentBulkSale']
 else:
  assert not result.succeeded and result.confirm_count==0
  assert calls==['SelectEquipmentInventorySlot']
