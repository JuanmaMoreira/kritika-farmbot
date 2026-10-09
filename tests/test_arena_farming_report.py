from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path

import pytest

from bot.arena_farming_report import arena_batch_rows, project_arena_farming
from bot.flow_contracts import FlowEvent, FlowResult, FlowStatus
from bot.session import CharacterContext, SessionCharacterResult, SessionResult, SessionStatus
from bot.session_report import build_session_report, render_session_report
from tests.test_gui_entrypoint import build_gui_shell


FIXTURE = Path(__file__).parent / 'fixtures/session_report_arena/crimson_cycle.json'


def crimson_flow():
    replay = json.loads(FIXTURE.read_text(encoding='utf8'))
    events = tuple(FlowEvent(event['kind'], fields=event['fields'],
        created_at=datetime.fromisoformat(event['created_at'])) for event in replay['events'])
    return FlowResult(FlowStatus.COMPLETED, events)


def crimson_session(*flows):
    replay = json.loads(FIXTURE.read_text(encoding='utf8'))
    character = SessionCharacterResult(1, CharacterContext(replay['character'], .99, replay['character_id']),
        flows or (crimson_flow(),), completed=True, meteorites=replay['meteorites'])
    return SessionResult(SessionStatus.COMPLETED, 1, 1, (character,), duration=replay['session_duration'],
        flow_names=('arena',)*len(character.flow_results), expected_character_count=1,
        run_id=replay['run_id'], session_id=replay['session_id'], change_meteorites=True)


def decision(identity, operation, used, won, **fields):
    return FlowEvent('arena.farming.difficulty', fields=dict(batch_id=identity, operation_index=operation,
        used_tickets=used, won_tickets=won, difficulty='HARD', multiplier=8, **fields))


def project(*events, status=FlowStatus.COMPLETED):
    return project_arena_farming(FlowResult(status, events))


def test_crimson_real_replay_all_expected_totals_and_sources():
    summary = project_arena_farming(crimson_flow())
    assert (len(summary.batches), summary.used, summary.won, summary.lost) == (4, 408, 336, 72)
    assert summary.winrate == pytest.approx(336/408)
    assert summary.battles == (42, 51, 9)
    assert [batch.battles for batch in summary.batches] == [(10, 13), (11, 13), (9, 12), (12, 13)]
    assert (summary.manual_entries, summary.monster_wave_passes) == (6, 4)
    assert (summary.stamina_consumed, summary.stamina_budget) == (360, 360)
    assert (summary.sapphires_generated, summary.sapphires_consumed) == (408, 400)
    assert (summary.stamina_purchased, summary.kcoins_spent) == (100, 400)
    assert summary.termination == 'stamina_budget_reached'
    assert summary.status == 'COMPLETED' and summary.gaps == ()
    assert summary.duration == pytest.approx(2993.965139)
    assert summary.duration_basis == 'observed resource routing interval'
    assert [batch.difficulty for batch in summary.batches] == ['HARD', 'HARD', 'NORMAL', 'NORMAL']
    assert [batch.next_difficulty for batch in summary.batches] == ['HARD', 'NORMAL', 'NORMAL', 'HARD']
    assert [batch.decision_reason for batch in summary.batches] == ['collect_recent_batches',
        'adjacent_uncertainty', 'collect_recent_batches', 'recent_reward_advantage']
    assert summary.batches[0].duration == pytest.approx(525.1665978)
    report = build_session_report(crimson_session())
    text = render_session_report(report)
    for value in ('Crimson Assassin [crimson_assassin]', '82.35%', '408 / 336 / 72',
                  '51 attempted / 42 won / 9 lost', '360 / 360', '408 / 400', '100 / 400',
                  'RELEASED, 11 Equip / 11 Unequip'):
        assert value in text


def test_weighted_global_rate_not_average_of_different_batch_sizes():
    summary = project(decision('a', 1, 80, 0), decision('b', 2, 8, 8))
    assert summary.winrate == pytest.approx(8/88)
    assert summary.winrate != .5
    assert summary.batches[0].winrate == 0
    assert summary.battles == (1, 11, 10)


@pytest.mark.parametrize('used,won', [(104, 77), (105, 80)])
def test_nondivisible_badges_remain_valid_but_do_not_invent_battles(used, won):
    summary = project(decision('a', 1, used, won))
    assert summary.used == used and summary.won == won
    assert summary.winrate == won / used
    assert summary.battles is None and summary.batches[0].battles is None


def test_missing_multiplier_duration_decision_are_nd_not_inferred():
    event = decision('a', 1, 80, 40)
    event = replace(event, fields={key: value for key, value in event.fields.items() if key != 'multiplier'})
    summary = project(event)
    assert summary.used == 80 and summary.battles is None
    assert summary.batches[0].duration is None
    assert summary.batches[0].next_difficulty is None


@pytest.mark.parametrize('fields', [{'used_tickets': 0}, {'won_tickets': None}, {'won_tickets': 81},
                                  {'won_tickets': -1}, {'won_tickets': True}, {'batch_id': None}])
def test_invalid_or_ambiguous_receipt_never_becomes_zero_wins(fields):
    event = decision('a', 1, 80, 0)
    event = replace(event, fields={**event.fields, **fields})
    summary = project(event)
    assert summary.batches == () and summary.won is None and summary.winrate is None
    assert summary.gaps


def test_routed_operation_without_terminal_is_partial_not_a_zero_batch():
    summary = project(decision('a', 1, 80, 40), FlowEvent('arena.farming.routing',
        fields={'activity': 'arena', 'operation_index': 2}))
    assert len(summary.batches) == 1 and summary.won == 40
    assert any('without a credited terminal' in gap for gap in summary.gaps)


def test_retries_and_reconciliation_deduplicate_real_batch_and_resources():
    flow = crimson_flow()
    summary = project_arena_farming(replace(flow, events=flow.events+flow.events))
    assert (summary.used, summary.won, summary.sapphires_generated, summary.sapphires_consumed) == (408, 336, 408, 400)
    assert (summary.stamina_purchased, summary.kcoins_spent, len(summary.batches)) == (100, 400, 4)
    assert summary.gaps == ()


def test_conflicting_duplicate_batch_is_excluded_and_marked_partial():
    event = decision('a', 1, 80, 40)
    summary = project(event, replace(event, fields={**event.fields, 'won_tickets': 48}))
    assert summary.batches == () and summary.won is None
    assert any('conflicting duplicate' in gap for gap in summary.gaps)


def test_different_receipts_on_same_operation_do_not_double_count():
    summary = project(decision('a', 1, 80, 40), decision('b', 1, 80, 40))
    assert summary.used is None and summary.gaps


def test_batch_table_orders_by_causal_operation_not_delivery_order():
    summary = project(decision('b', 2, 80, 40), decision('a', 1, 80, 48))
    assert [(batch.number, batch.batch_id) for batch in summary.batches] == [(1, 'a'), (2, 'b')]


def test_different_characters_and_occurrences_remain_separate():
    raw = crimson_session(crimson_flow(), crimson_flow())
    second = replace(raw.character_results[0], index=2,
        character_context=CharacterContext('Other', .99, 'other'))
    raw = replace(raw, character_results=(*raw.character_results, second),
                  expected_character_count=2, characters_processed=2, advances_completed=2)
    report = build_session_report(raw)
    summaries = [flow.arena_farming for character in report.characters for flow in character.flows]
    assert len(summaries) == 4 and all(summary.used == 408 for summary in summaries)
    rows = arena_batch_rows(report)
    assert len(rows) == 16
    assert rows[0][0].startswith('1.1 ') and rows[4][0].startswith('1.2 ')
    assert rows[8][0].startswith('2.1 Other') and rows[12][0].startswith('2.2 Other')


@pytest.mark.parametrize('reason,status', [('stamina_budget_reached', FlowStatus.COMPLETED),
    ('easy_zero_wins', FlowStatus.COMPLETED), ('technical_failure', FlowStatus.FAILED),
    ('cancelled', FlowStatus.CANCELLED), ('ambiguous', FlowStatus.MANUAL_RESOLUTION)])
def test_terminal_status_and_reason_preserved_without_making_functional_stop_failed(reason, status):
    summary = project(FlowEvent('arena.farming.terminated', fields={'reason': reason}), status=status)
    assert summary.status == status.value.upper() and summary.termination == reason


def test_legacy_unknowns_never_turn_into_zero_or_a_farming_section_on_gold_single_auto():
    for kind in ('gold_farming.completed', 'arena.single.completed', 'arena.auto_repeat.completed'):
        assert project(FlowEvent(kind)) is None
    summary = project(FlowEvent('arena.farming.terminated', fields={'reason': 'easy_zero_wins'}))
    assert summary.duration is summary.stamina_consumed is summary.manual_entries is None
    assert summary.stamina_purchased is summary.kcoins_spent is summary.sapphires_generated is None


def test_confirmed_cost_is_required_and_ledger_does_not_follow_balance_or_claim():
    flow = crimson_flow()
    events = tuple(replace(event, fields={key: value for key, value in event.fields.items() if key != 'kcoin_cost'})
                   if event.kind == 'arena.farming.stamina_supply' else event for event in flow.events)
    summary = project_arena_farming(replace(flow, events=events))
    assert summary.stamina_purchased == 100 and summary.kcoins_spent is None
    assert summary.stamina_consumed == 360 and summary.stamina_budget == 360


def test_owner_cycle_duration_is_used_when_available():
    summary = project(FlowEvent('arena.farming.terminated', fields={'duration': 320.75,
        'maximum_stamina_consumption': None}))
    assert summary.duration == 320.75 and summary.duration_basis == 'owner wall time'
    assert summary.budget_known and summary.stamina_budget is None


@pytest.mark.parametrize('consumed', [None, 0, 60.0, True])
def test_incomplete_manual_entry_does_not_invent_zero_count_or_rewards(consumed):
    summary = project(FlowEvent('arena.farming.manual_entry', fields={
        'operation_index': 1, 'stamina_consumed': consumed}))
    assert summary.manual_entries is summary.sapphires_generated is None
    assert any('incomplete entry receipt' in gap for gap in summary.gaps)


def test_gui_summary_batch_table_expand_collapse_and_new_report_clear():
    app = build_gui_shell(lambda: 0)
    report = build_session_report(crimson_session())
    app._show_report(report)
    assert '82.35%' in app.report_text.text and '336' in app.report_text.text
    assert not app.arena_batch_frame.visible and app.arena_batch_button.options['state'] == 'normal'
    assert len(app.arena_batch_table.rows) == 4
    assert app.arena_batch_table.rows[0][1:8] == ('1', 'HARD', 'x8', '104', '80', '76.92%', '10 / 13')
    app._toggle_arena_batches()
    assert app.arena_batch_frame.visible and app.arena_batch_button.options['text'] == 'Hide Arena batches'
    app._toggle_arena_batches()
    assert not app.arena_batch_frame.visible
    app._show_report(None)
    assert app.arena_batch_table.rows == [] and app.arena_batch_button.options['state'] == 'disabled'
    assert app.report_text.text == 'No session report available.'
