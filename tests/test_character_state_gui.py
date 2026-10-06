import json
from types import SimpleNamespace
import pytest
from bot.routines import RoutineSpec,RoutineStep,RoutineEditor,RoutineStore
from bot.flow_registry import DEFAULT_FLOW_REGISTRY
from bot.character_state import CharacterStateStore
from tools.gui import KritikaFarmBotGui
from test_gui_entrypoint import Var

@pytest.mark.parametrize('mode',['DAILY_QUEST','CURRENT_WB_NOT_PARTICIPATED','GENERAL'])
@pytest.mark.parametrize('snapshot_mode',['OFF','BEFORE_CHARACTER_ROTATION'])
def test_wb_per_occurrence_snapshot_save_duplicate_reopen(tmp_path,mode,snapshot_mode):
    store=RoutineStore(tmp_path/'routines.json',DEFAULT_FLOW_REGISTRY)
    editor=RoutineEditor(store)
    editor.create('Tracked')
    editor.add('world_boss');editor.add('world_boss')
    editor.configure(0,{'world_boss':{'eligibility':mode}})
    editor.configure(1,{'world_boss':{'eligibility':'DAILY_QUEST'}})
    editor.set_resource_snapshot_mode(snapshot_mode)
    editor.save()
    editor.create('Copy',duplicate=True)
    editor.save()
    reopened=RoutineEditor(store)
    assert reopened.draft.resource_snapshot_mode==snapshot_mode
    assert reopened.draft.steps[0].config['world_boss']['eligibility']==mode
    assert reopened.draft.steps[1].config['world_boss']['eligibility']=='DAILY_QUEST'

def test_v1_legacy_unchanged_and_invalid_wb_safe_default(tmp_path):
    store=RoutineStore(tmp_path/'routines.json',DEFAULT_FLOW_REGISTRY)
    store.path.write_text(json.dumps(dict(version=1,selected_id='r',routines=[
        dict(id='r',name='Legacy',steps=[dict(flow_id='world_boss',config={'world_boss':{'eligibility':'corrupt'}}),dict(flow_id='mailbox')])])),encoding='utf-8')
    values,_=store.load()
    assert values[0].resource_snapshot_mode=='BEFORE_CHARACTER_ROTATION'
    assert values[0].steps[0].enabled
    assert values[0].steps[0].config['world_boss']['eligibility']=='DAILY_QUEST'
    assert values[0].steps[1].config=={}
    store.save(values,'r')
    assert store.load()[0]==values

@pytest.mark.parametrize('malformed',[None,[],{},123])
def test_malformed_config_types_recover_without_dropping_routine(tmp_path,malformed):
    store=RoutineStore(tmp_path/'routines.json',DEFAULT_FLOW_REGISTRY)
    store.path.write_text(json.dumps(dict(version=1,selected_id='r',routines=[dict(
        id='r',name='Legacy',resource_snapshot_mode=malformed,steps=[dict(flow_id='world_boss',
        config={'world_boss':{'eligibility':malformed}})])])),encoding='utf-8')
    routines,_=store.load()
    assert len(routines)==1
    assert routines[0].resource_snapshot_mode=='OFF'
    assert routines[0].steps[0].enabled
    assert routines[0].steps[0].config['world_boss']['eligibility']=='DAILY_QUEST'

class Table:
    def __init__(self): self.rows={}
    def exists(self,cid): return cid in self.rows
    def item(self,cid,*,values): self.rows[cid]=values
    def insert(self,parent,index,*,iid,values): self.rows[iid]=values

def test_gui_loads_28_and_reflects_reset_without_visits_or_restart(tmp_path):
    now=[1_000_000.]
    store=CharacterStateStore(tmp_path/'state.db',now=lambda:now[0])
    store.clock.calibrate(3600)
    app=KritikaFarmBotGui.__new__(KritikaFarmBotGui)
    callbacks=[]
    app.root=SimpleNamespace(winfo_exists=lambda:True,after=lambda delay,callback:callbacks.append(callback))
    app.character_store=store
    app.character_table=Table()
    app.reset_clock_var=Var()
    app._refresh_character_state()
    assert len(app.character_table.rows)==28
    assert all(v[1]=='UNKNOWN' for v in app.character_table.rows.values())
    now[0]+=5400
    callbacks[-1]()
    assert all(v[1]==2 for v in app.character_table.rows.values())
    assert all(v[3]=='NO' for v in app.character_table.rows.values())
    store.close()
    reopen=CharacterStateStore(tmp_path/'state.db',now=lambda:now[0])
    app.character_store=reopen
    app._refresh_character_state()
    assert len(app.character_table.rows)==28
    assert all(v[1]==2 for v in app.character_table.rows.values())
    reopen.close()
