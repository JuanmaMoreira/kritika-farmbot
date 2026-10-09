"""Pure projection of one Farming Cycle occurrence's credited owner events."""
from dataclasses import dataclass, replace
import math

from bot.flow_contracts import FlowResult


def _integer(value):
    return value if type(value) is int and value >= 0 else None


def _seconds(value):
    return value if type(value) in (float, int) and math.isfinite(value) and value >= 0 else None


@dataclass(frozen=True)
class ArenaBatchReport:
    number: int
    operation: int
    batch_id: str
    difficulty: str
    multiplier: int | None
    used: int
    won: int
    duration: float | None
    next_difficulty: str | None
    decision_reason: str | None

    @property
    def winrate(self):
        return self.won / self.used

    @property
    def battles(self):
        if self.multiplier == 8 and self.used % 8 == self.won % 8 == 0:
            return self.won // 8, self.used // 8
        return None


@dataclass(frozen=True)
class ArenaFarmingReport:
    status: str
    termination: str | None
    duration: float | None
    duration_basis: str
    batches: tuple[ArenaBatchReport, ...]
    initial_difficulty: str | None
    final_difficulty: str | None
    stamina_consumed: int | None
    stamina_budget: int | None
    budget_known: bool
    manual_entries: int | None
    monster_wave_passes: int | None
    sapphires_generated: int | None
    sapphires_consumed: int | None
    stamina_purchased: int | None
    kcoins_spent: int | None
    gaps: tuple[str, ...] = ()

    @property
    def used(self):
        return sum(batch.used for batch in self.batches) if self.batches else None

    @property
    def won(self):
        return sum(batch.won for batch in self.batches) if self.batches else None

    @property
    def lost(self):
        return self.used - self.won if self.batches else None

    @property
    def winrate(self):
        return self.won / self.used if self.batches else None

    @property
    def battles(self):
        if self.batches and all(batch.battles is not None for batch in self.batches):
            won = sum(batch.battles[0] for batch in self.batches)
            attempted = sum(batch.battles[1] for batch in self.batches)
            return won, attempted, attempted - won
        return None


def _unique(events, key, gaps, label):
    """Exact duplicates count once. Conflicting receipts are unassessed."""
    groups = {}
    for event in events:
        identity = event.fields.get(key)
        if identity is None or isinstance(identity, (list, dict)):
            gaps.append(f'{label}: missing causal identity')
            continue
        groups.setdefault(identity, []).append(event)
    values = []
    for group in groups.values():
        if any(dict(event.fields) != dict(group[0].fields) for event in group[1:]):
            gaps.append(f'{label}: conflicting duplicate')
        else:
            values.append(group[0])
    return values


def project_arena_farming(raw: FlowResult) -> ArenaFarmingReport | None:
    if not any(event.kind.startswith('arena.farming.') for event in raw.events):
        return None
    named = lambda kind: [event for event in raw.events if event.kind == kind]
    gaps = []
    terminations = named('arena.farming.terminated')
    terminal = terminations[-1].fields if terminations else {}
    batches = []
    decisions = _unique(named('arena.farming.difficulty'), 'batch_id', gaps, 'Arena')
    decisions = _unique(decisions, 'operation_index', gaps, 'Arena operation')
    for event in decisions:
        fields = event.fields
        used, won = _integer(fields.get('used_tickets')), _integer(fields.get('won_tickets'))
        operation = _integer(fields.get('operation_index'))
        if (used is None or used == 0 or won is None or won > used or not operation
                or fields.get('difficulty') not in ('EASY', 'NORMAL', 'HARD')
                or not isinstance(fields.get('batch_id'), str) or not fields['batch_id']):
            gaps.append('Arena: invalid or incomplete terminal receipt')
            continue
        batches.append(ArenaBatchReport(len(batches)+1, operation, fields['batch_id'], fields['difficulty'],
            _integer(fields.get('multiplier')), used, won, _seconds(fields.get('duration')),
            fields.get('next'), fields.get('reason')))
    batches = [replace(batch, number=index) for index, batch in enumerate(sorted(batches,
        key=lambda batch: batch.operation), 1)]
    arena_routes = {event.fields.get('operation_index') for event in named('arena.farming.routing')
                    if event.fields.get('activity') == 'arena'}
    if arena_routes - {batch.operation for batch in batches}:
        gaps.append('Arena: operations without a credited terminal result; totals cover valid batches only')

    entries = _unique(named('arena.farming.manual_entry'), 'operation_index', gaps, 'Manual')
    manual_count = _integer(terminal.get('manual_entries'))
    if manual_count is None and entries:
        if all(_integer(event.fields.get('stamina_consumed')) == 60 for event in entries):
            manual_count = len(entries)
        else:
            gaps.append('Manual: invalid or incomplete entry receipt')
    completed_mw = _unique(named('monster_wave.completed'), 'attempt_index', gaps, 'MW')
    mw_count = _integer(terminal.get('monster_wave_passes'))
    if mw_count is None and completed_mw:
        mw_count = len(completed_mw)

    generation = _unique([event for event in named('arena.farming.progress')
        if event.fields.get('activity') == 'manual_stages'], 'operation_index', gaps, 'Manual rewards')
    generated = []
    for event in generation:
        before, after = _integer(event.fields.get('sapphires_before')), _integer(event.fields.get('sapphires_after'))
        if before is not None and after is not None and after >= before:
            generated.append(after - before)
    sapphire_generation = (sum(generated) if manual_count is not None and len(generated) == manual_count else None)
    debits = _unique(named('monster_wave.sapphire_effect'), 'attempt_index', gaps, 'MW consumption')
    consumed = []
    completed_indices = {event.fields.get('attempt_index') for event in completed_mw}
    for event in debits:
        before, after = _integer(event.fields.get('before')), _integer(event.fields.get('after'))
        if (before is not None and after is not None and before >= after
                and event.fields.get('attempt_index') in completed_indices):
            consumed.append(before - after)
    sapphire_consumption = (sum(consumed) if mw_count is not None and len(consumed) == mw_count else None)

    supplies = _unique(named('arena.farming.stamina_supply'), 'operation_index', gaps, 'Trading')
    purchases = [_integer(event.fields.get('purchased')) for event in supplies]
    costs = [0 if purchased == 0 else _integer(event.fields.get('kcoin_cost'))
             for event, purchased in zip(supplies, purchases)]
    purchased = sum(purchases) if supplies and all(value is not None for value in purchases) else None
    cost = sum(costs) if supplies and all(value is not None for value in costs) else None
    duration = _seconds(terminal.get('duration'))
    basis = 'owner wall time'
    if duration is None:
        resources = named('arena.farming.resources')
        if resources and terminations:
            duration = _seconds((terminations[-1].created_at-resources[0].created_at).total_seconds())
        basis = 'observed resource routing interval'
    if sapphire_generation is None or sapphire_consumption is None or purchased is None or cost is None:
        gaps.append('Some resource or Trading totals are unavailable; N/D is not zero')
    return ArenaFarmingReport(raw.status.value.upper(), terminal.get('reason'), duration, basis, tuple(batches),
        terminal.get('initial_difficulty') or (batches[0].difficulty if batches else None),
        terminal.get('final_difficulty') or (batches[-1].next_difficulty if batches else None),
        _integer(terminal.get('stamina_consumed')), _integer(terminal.get('maximum_stamina_consumption')),
        'maximum_stamina_consumption' in terminal, manual_count, mw_count, sapphire_generation,
        sapphire_consumption, purchased, cost, tuple(dict.fromkeys(gaps)))


def number(value):
    return 'N/D' if value is None else str(value)


def percentage(value):
    return 'N/D' if value is None else f'{value:.2%}'


def duration_text(value):
    if value is None:
        return 'N/D'
    minutes, seconds = divmod(value, 60)
    return f'{int(minutes)}m{seconds:05.2f}s'


def render_arena_farming(summary, *, character, character_id, occurrence, meteorites):
    budget = number(summary.stamina_budget) if summary.stamina_budget is not None else ('unlimited' if summary.budget_known else 'N/D')
    battles = ('N/D' if summary.battles is None else
        f'{summary.battles[1]} attempted / {summary.battles[0]} won / {summary.battles[2]} lost')
    sequence = ' → '.join(batch.difficulty for batch in summary.batches) or 'N/D'
    lifecycle = 'N/D' if meteorites is None else (
        f"{meteorites.get('status', 'N/D')}, {len(meteorites.get('equip_effects', ()))} Equip / "
        f"{len(meteorites.get('unequip_effects', ()))} Unequip (character lifecycle)")
    lines = [f'Arena Farming Cycle — {character} [{character_id or "N/D"}] — occurrence {occurrence}',
        f'Result: {summary.status} | Termination: {summary.termination or "N/D"}',
        f'Duration: {duration_text(summary.duration)} ({summary.duration_basis})',
        f'Valid Arena batches: {len(summary.batches)} | Badges used / won / lost: '
        f'{number(summary.used)} / {number(summary.won)} / {number(summary.lost)} | Global winrate: {percentage(summary.winrate)}',
        f'Battles: {battles}',
        f'Difficulty: initial {summary.initial_difficulty or "N/D"}; sequence {sequence}; controller final {summary.final_difficulty or "N/D"}',
        f'Stamina consumed / budget: {number(summary.stamina_consumed)} / {budget} | Manual entries: {number(summary.manual_entries)} | MW passes: {number(summary.monster_wave_passes)}',
        f'Sapphires generated (Manual) / consumed (MW): {number(summary.sapphires_generated)} / {number(summary.sapphires_consumed)}',
        f'Trading Stamina acquired / K Coins spent: {number(summary.stamina_purchased)} / {number(summary.kcoins_spent)}',
        f'Shared Meteorites: {lifecycle}']
    if summary.gaps:
        lines.append('Partial information: ' + '; '.join(summary.gaps))
    return '\n'.join(lines)


BATCH_COLUMNS = ('Occurrence / character', 'Batch', 'Difficulty', 'Multiplier', 'Used', 'Won', 'Winrate',
                 'Battles won / total', 'Owner duration', 'Next', 'Decision')


def arena_batch_rows(report):
    """Formatted rows for the GUI table; no runtime or game dependencies."""
    rows = []
    if report is None:
        return rows
    for character in report.characters:
        occurrence = 0
        for flow in character.flows:
            summary = flow.arena_farming
            if summary is None:
                continue
            occurrence += 1
            for batch in summary.batches:
                rows.append((f'{character.index}.{occurrence} {character.label} [{character.character_id or "N/D"}]',
                    str(batch.number), batch.difficulty, f'x{batch.multiplier}' if batch.multiplier else 'N/D',
                    str(batch.used), str(batch.won), percentage(batch.winrate),
                    f'{batch.battles[0]} / {batch.battles[1]}' if batch.battles else 'N/D',
                    duration_text(batch.duration), batch.next_difficulty or 'N/D', batch.decision_reason or 'N/D'))
    return rows
