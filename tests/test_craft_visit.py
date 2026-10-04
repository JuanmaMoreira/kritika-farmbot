from dataclasses import replace
from types import SimpleNamespace as S
import pytest
from bot.craft_runtime import CraftRuntime, CraftRouteResult, CraftRouteOutcome
from bot.craft_semantics import CraftFamily
from bot.craft_operation import CraftOutcome, CraftOperationResult
from test_craft_runtime import CraftReader, runtime, InventoryReader

@pytest.mark.parametrize('amounts,expected',[
 ((98,0,0),[CraftFamily.WEAPON]),((0,98,0),[CraftFamily.ARMOR]),
 ((0,0,98),[CraftFamily.ACCESSORY]),((98,98,98),list(CraftFamily)),
 ((48,0,98),[CraftFamily.ACCESSORY]),((0,0,0),[])])
def test_one_visit_drains_only_eligible_families(amounts,expected):
 value=CraftRuntime.__new__(CraftRuntime);value.events=None
 current=CraftReader().context_sample(None,sequence=1,observed_at=100.)
 current=replace(current,weapon_material=amounts[0],armor_material=amounts[1],accessory_material=amounts[2])
 calls=[];value.cancel_requested=lambda:False;value.craft_reader=CraftReader();value._fresh=lambda f:True
 def read(*a,**kw):return current
 value._read_consensus=read
 value.observe_context=lambda **kw:CraftRouteResult(CraftRouteOutcome.ENTERED,craft_fact=current)
 def execute(request):
  nonlocal current
  calls.append(request.family);before=current
  current=replace(current,**{request.family.value+'_material':0},sequence=current.sequence+1)
  return CraftOperationResult(CraftOutcome.SUCCESS,before_fact=before,after_fact=current)
 value.execute=execute
 result=value.drain_hero_materials(max_batches=3)
 assert result.outcome is CraftOutcome.SUCCESS
 assert calls==expected
 assert len(result.batches)==len(expected)

def test_real_failure_stops_before_later_families():
 value=CraftRuntime.__new__(CraftRuntime);value.events=None
 base=CraftReader().context_sample(None,sequence=1,observed_at=100.)
 value.observe_context=lambda **kw:CraftRouteResult(CraftRouteOutcome.ENTERED,craft_fact=base)
 calls=[]
 def fail(**kw):calls.append(kw['family']);return S(outcome=CraftOutcome.FAILED,batches=(),final_fact=base,reason='recipe_verification_failed')
 value.drain_hero_material=fail
 result=value.drain_hero_materials(max_batches=3)
 assert result.outcome is CraftOutcome.FAILED and calls==[CraftFamily.WEAPON]

def test_unobservable_category_does_not_authorize_input_or_block_next():
 value=CraftRuntime.__new__(CraftRuntime);value.events=None
 base=CraftReader().context_sample(None,sequence=1,observed_at=100.)
 base=replace(base,weapon_material=None,armor_material=0,accessory_material=98)
 value.observe_context=lambda **kw:CraftRouteResult(CraftRouteOutcome.ENTERED,craft_fact=base)
 calls=[]
 def drain(**kw):calls.append(kw['family']);return S(outcome=CraftOutcome.SUCCESS,batches=(),final_fact=base)
 value.drain_hero_material=drain
 result=value.drain_hero_materials(max_batches=3)
 assert result.outcome is CraftOutcome.SUCCESS and calls==[CraftFamily.ACCESSORY]
 assert result.skipped_families==(CraftFamily.WEAPON,)

@pytest.mark.parametrize('family',[CraftFamily.ARMOR,CraftFamily.ACCESSORY])
def test_capacity_probe_uses_nonweapon_work_and_names_blocked_recipe(family):
 value,adb=runtime(sequences=range(1,30),inventory=InventoryReader(count=112,capacity=112))
 original=value.craft_reader.context_sample
 value.craft_reader.context_sample=lambda *a,**kw:replace(original(*a,**kw),
  weapon_material=0,armor_material=98 if family is CraftFamily.ARMOR else 0,
  accessory_material=98 if family is CraftFamily.ACCESSORY else 0)
 result=value.probe_equipment_capacity()
 assert result.outcome is CraftRouteOutcome.CAPACITY_BLOCKED and result.work_family is family
 assert result.inputs==('open_quick_menu','select_inventory','back_to_craft')



def test_all_families_use_one_route_entry_and_exit():
 from test_monster_wave_resource_route import _runtime, _plan, _anchor
 from bot.monster_wave_resource_route import ResourceRouteExecutionStatus
 value=CraftRuntime.__new__(CraftRuntime);value.events=None
 fact=CraftReader().context_sample(None,sequence=1,observed_at=100.)
 value.observe_context=lambda **kw:CraftRouteResult(CraftRouteOutcome.ENTERED,craft_fact=fact)
 calls=[]
 def drain(**kw):
  calls.append(kw['family'])
  return S(outcome=CraftOutcome.SUCCESS,batches=(),final_fact=fact)
 value.drain_hero_material=drain
 trace=[];route=_runtime(trace)
 route.craft_runtime.drain_hero_materials=value.drain_hero_materials
 result=route.execute_plan_once(_plan(craft=True,keys=False),_anchor(10))
 assert result.status is ResourceRouteExecutionStatus.SUCCESS
 assert calls==list(CraftFamily)
 assert trace.count('mw_qm_craft')==trace.count('craft_back')==1
