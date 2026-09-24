"""Pure, transient human projection of session results. No IO or runtime policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Mapping

from bot.failure_cause import FailureCause
from bot.flow_contracts import FlowResult, FlowStatus
from bot.session import SessionResult, SessionStatus


class ReportStatus(str, Enum):
    COMPLETE = "complete"
    SKIPPED_NOT_ELIGIBLE = "skipped_not_eligible"
    BUSINESS_INCOMPLETE = "business_incomplete"
    TECHNICAL_FAILURE = "technical_failure"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ReportReason:
    """Existing business event identifier and its human interpretation."""

    event_kind: str
    message: str


@dataclass(frozen=True)
class FlowReport:
    flow_id: str | None
    label: str
    status: ReportStatus | None
    completed: bool
    reasons: tuple[ReportReason, ...] = ()
    failure: FailureCause | None = None
    no_op: bool = False


@dataclass(frozen=True)
class CharacterReport:
    index: int
    label: str
    status: ReportStatus | None
    flows: tuple[FlowReport, ...]
    advance_completed: bool
    failure: FailureCause | None = None
    failure_component: str | None = None


@dataclass(frozen=True)
class ReportCounts:
    """Exclusive counts of represented characters; never counts unstarted ones."""

    complete: int = 0
    business_incomplete: int = 0
    technical_failure: int = 0
    cancelled: int = 0
    unassessed: int = 0


@dataclass(frozen=True)
class SessionReport:
    # None means insufficient legacy data, never business or technical failure.
    status: ReportStatus | None
    execution_status: SessionStatus
    duration: float | None
    characters_processed: int
    expected_character_count: int | None
    flows_completed: int
    advances_completed: int
    counts: ReportCounts
    characters: tuple[CharacterReport, ...]
    failure: FailureCause | None = None
    data_gaps: tuple[str, ...] = ()
    run_id: str | None = None
    session_id: str | None = None


# Explicit projection of existing business contracts, not a failure taxonomy.
# Do not infer causal explanations from detail/error text or diagnostic events.
_INCOMPLETE = {
    'monster_wave.tickets_missing_purchase_disabled': 'SKIP activation tickets missing (<30/30); purchase disabled',
    'monster_wave.insufficient_sapphires': 'insufficient sapphires for SKIP',
    'monster_wave.daily_sapphires_below_minimum': 'Daily requires 4 fresh sapphires; SKIP intentionally not started',
    'monster_wave.inventory_warning_declined': 'non-blocking inventory warning declined',
    'monster_wave.manual_resolution': 'Monster Wave requires manual resolution; acquired return unavailable',
    "black_market.low_gold": "insufficient GOLD for a purchase",
    "black_market.inventory_full": "inventory full; purchase not completed",
    "send_stamina.daily_pending": "Daily still pending after All had no effect",
    "send_stamina.all_no_effect": "Daily still pending after All had no effect",
    "summon_pet_daily.insufficient_gold": "insufficient GOLD for the Daily summon",
    "summon_pet_daily.space_relief_unavailable": "pet space relief unavailable",
    "summon_pet_daily.manual_resolution": "pet inventory requires manual resolution",
    "mailbox.claims_leftover": "unclaimed mail remains",
    "mailbox.claim_all_no_effect": "Claim All had no effect",
    "world_boss.insufficient_sapphires": "insufficient sapphires to enter",
    "world_boss.inventory_full": "socket inventory full; raid not completed",
    "world_boss.bag_full": "equipment inventory full; raid not completed",
    "world_boss.meteor_full": "meteor inventory full; raid not completed",
}
_NOOPS = frozenset(f"{name}.noop" for name in (
    "send_stamina", "summon_pet_daily", "daily_quests", "guild_check_in", "mailbox",
))
_INFORMATIONAL = _NOOPS | frozenset({
    'monster_wave.completed', 'monster_wave.tickets_purchased',
    "send_stamina.all_executed", "send_stamina.completed",
    "summon_pet_daily.completed", "guild_check_in.tap_executed",
    "guild_check_in.attendance_completed", "daily_quests.claim_all_executed",
    "daily_quests.claim_all_completed", "daily_quests.progress_reward_executed",
    "daily_quests.progress_reward_completed", "mailbox.claim_all_skipped",
    "mailbox.claim_processing_observed", "mailbox.claim_processing_completed",
    "mailbox.delete_read_executed", "mailbox.delete_read_skipped",
    "world_boss.previous_rewards",
})
_LABELS = {
    'monster_wave': 'Monster Wave',
    "black_market": "Black Market", "world_boss": "World Boss",
    "send_stamina": "Send Stamina Daily", "summon_pet_daily": "Summon Pet Daily",
    "daily_quests": "Daily Quests", "mailbox": "Mailbox",
    "guild_check_in": "Guild Check-In",
}


def _flow_report(raw: FlowResult, name: str | None, label: str) -> FlowReport:
    if raw.status is FlowStatus.SKIPPED_NOT_ELIGIBLE:
        return FlowReport(
            name, label, ReportStatus.SKIPPED_NOT_ELIGIBLE, False,
            (ReportReason("eligibility.not_eligible", raw.skip_reason),),
        )
    kinds = tuple(
        event.kind if "." in event.kind or name is None else f"{name}.{event.kind}"
        for event in raw.events
    )
    # Black Market's historical unprefixed identifiers are unambiguous.
    kinds = tuple(f"black_market.{kind}" if kind in {"low_gold", "inventory_full"}
                  else kind for kind in kinds)
    reasons = tuple(ReportReason(kind, _INCOMPLETE[kind]) for kind in dict.fromkeys(kinds)
                    if kind in _INCOMPLETE)
    # Prefer the final pending signal over its preceding no-effect observation.
    if "send_stamina.daily_pending" in kinds:
        reasons = tuple(r for r in reasons if r.event_kind != "send_stamina.all_no_effect")
    if "mailbox.claims_leftover" in kinds:
        reasons = tuple(r for r in reasons if r.event_kind != "mailbox.claim_all_no_effect")
    if not reasons and getattr(raw, "daily_pending", False) is True:
        reasons = (ReportReason("daily_pending", "Daily remains pending"),)
    if not reasons and getattr(raw, "claims_leftover", False) is True:
        reasons = (ReportReason("claims_leftover", "unclaimed mail remains"),)
    if raw.status is FlowStatus.CANCELLED:
        status = ReportStatus.CANCELLED
    elif raw.status is FlowStatus.FAILED:
        status = ReportStatus.TECHNICAL_FAILURE
    elif reasons:
        status = ReportStatus.BUSINESS_INCOMPLETE
    elif any(kind not in _INFORMATIONAL for kind in kinds):
        status = None
    else:
        status = ReportStatus.COMPLETE
    return FlowReport(
        name, label, status, raw.status is FlowStatus.COMPLETED, reasons,
        raw.failure if status is ReportStatus.TECHNICAL_FAILURE else None,
        bool(_NOOPS.intersection(kinds)) or getattr(raw, "no_op", False) is True,
    )


def build_session_report(
    result: SessionResult,
    *,
    expected_character_count: int | None = None,
    flow_names: tuple[str, ...] = (),
    flow_labels: Mapping[str, str] | None = None,
) -> SessionReport:
    """Project a finished result; caller metadata only fills absent legacy fields.

    Preserve execution order for flows and sort characters by their session index.
    FailureCause stays intact for diagnostic consumers; rendering is a whitelist.
    """
    expected = result.expected_character_count
    if expected is None:
        expected = expected_character_count
    names = result.flow_names or tuple(flow_names)
    labels = {**_LABELS, **(flow_labels or {})}
    gaps: list[str] = []
    if result.duration is None:
        gaps.append("Duration unavailable")
    if expected is None:
        gaps.append("Expected character count unavailable")
    if not names:
        gaps.append("Flow plan unavailable; positional labels used")
    characters: list[CharacterReport] = []
    for character in sorted(result.character_results, key=lambda item: item.index):
        flows = []
        terminal_here = (
            result.status is SessionStatus.FAILED
            and result.failure_character_index == character.index
        )
        terminal_position = result.failure_flow_position
        if terminal_here and terminal_position is None and result.failure_flow:
            matching = [i for i, name in enumerate(names) if name == result.failure_flow]
            if len(matching) == 1:
                terminal_position = matching[0]
            elif len(matching) > 1:
                gaps.append(f"Character {character.index}: failed flow occurrence unavailable")
        for position, raw in enumerate(character.flow_results):
            name = names[position] if position < len(names) else None
            label = labels.get(name, name) if name else f"Flow {position + 1}"
            flow = _flow_report(raw, name, label)
            if terminal_here and position == terminal_position:
                # A successful run() can still fail the runner's postcondition.
                flow = replace(flow, status=ReportStatus.TECHNICAL_FAILURE,
                               completed=False, failure=result.failure or flow.failure)
            flows.append(flow)
        if terminal_here and result.failure_flow and (
            terminal_position is None or terminal_position >= len(flows)
        ):
            # Precondition failed before run(): retain the failed flow without
            # inventing results for any of the unexecuted subsequent flows.
            flows.append(FlowReport(
                result.failure_flow, labels.get(result.failure_flow, result.failure_flow),
                ReportStatus.TECHNICAL_FAILURE, False, failure=result.failure,
            ))
        failed_flow = next((f for f in flows if f.status is ReportStatus.TECHNICAL_FAILURE), None)
        rotation_failed = character.advance_result is not None and not character.advance_result.succeeded
        failure = result.failure if terminal_here else None
        if failure is None and failed_flow is not None:
            failure = failed_flow.failure
        if failure is None and rotation_failed:
            failure = character.advance_result.failure
        if terminal_here or failed_flow is not None or rotation_failed:
            status = ReportStatus.TECHNICAL_FAILURE
        elif any(f.status is ReportStatus.CANCELLED for f in flows) or (
            result.status is SessionStatus.CANCELLED and not character.completed
        ):
            status = ReportStatus.CANCELLED
        elif any(raw.status is FlowStatus.MANUAL_RESOLUTION for raw in character.flow_results):
            status = ReportStatus.BUSINESS_INCOMPLETE
        elif (not character.completed or not flows
              or (names and len(character.flow_results) != len(names))):
            status = None
        elif any(f.status is ReportStatus.BUSINESS_INCOMPLETE for f in flows):
            status = ReportStatus.BUSINESS_INCOMPLETE
        elif any(f.status is None for f in flows):
            status = None
        else:
            status = ReportStatus.COMPLETE
        if status is None or any(f.status is None for f in flows):
            gaps.append(f"Character {character.index}: incomplete result or unclassified business outcome")
        characters.append(CharacterReport(
            character.index,
            character.character_context.name or f"Character {character.index}",
            status, tuple(flows),
            character.completed, failure,
            (result.failure_flow or "rotation") if terminal_here else (
                failed_flow.flow_id if failed_flow is not None else "rotation" if rotation_failed else None
            ),
        ))
    if result.characters_processed > sum(c.completed for c in result.character_results):
        gaps.append("Some processed characters have no complete detailed result")
    counts = ReportCounts(**{
        key: sum(c.status is status for c in characters)
        for key, status in (
            ("complete", ReportStatus.COMPLETE),
            ("business_incomplete", ReportStatus.BUSINESS_INCOMPLETE),
            ("technical_failure", ReportStatus.TECHNICAL_FAILURE),
            ("cancelled", ReportStatus.CANCELLED), ("unassessed", None),
        )
    })
    if result.status is SessionStatus.FAILED or counts.technical_failure:
        status = ReportStatus.TECHNICAL_FAILURE
    elif result.status is SessionStatus.CANCELLED or counts.cancelled:
        status = ReportStatus.CANCELLED
    elif counts.business_incomplete:
        status = ReportStatus.BUSINESS_INCOMPLETE
    elif (not characters or counts.unassessed or counts.complete != result.characters_processed
          or (expected is not None and result.characters_processed != expected)):
        status = None
    else:
        status = ReportStatus.COMPLETE
    if result.status is SessionStatus.COMPLETED and expected is not None and result.characters_processed != expected:
        gaps.append("Completed execution does not cover the expected character count")
    failure = result.failure if status is ReportStatus.TECHNICAL_FAILURE else None
    if failure is None and status is ReportStatus.TECHNICAL_FAILURE:
        failure = next((c.failure for c in characters if c.failure is not None), None)
    return SessionReport(
        status, result.status, result.duration, result.characters_processed, expected,
        sum(f.completed for c in characters for f in c.flows), result.advances_completed,
        counts, tuple(characters), failure, tuple(gaps), result.run_id, result.session_id,
    )


def _failure_lines(failure: FailureCause | None, prefix: str = "") -> list[str]:
    # Raw messages can contain embedded perception/sequence/exception dumps.
    lines = [f"{prefix}Technical failure: {failure.type if failure else 'cause unavailable'}"]
    if failure is not None and failure.evidence_ref:
        lines.append(f"{prefix}Evidence reference (availability not checked): {failure.evidence_ref}")
    return lines


def render_session_report(report: SessionReport) -> str:
    """Deterministic human text; no diagnostic parsing, filesystem access or clock."""
    titles = {
        ReportStatus.COMPLETE: "Session completed",
        ReportStatus.BUSINESS_INCOMPLETE: "Session completed with business / Daily incomplete",
        ReportStatus.TECHNICAL_FAILURE: "Session technical failure",
        ReportStatus.CANCELLED: "Session cancelled",
        None: "Session assessment unavailable",
    }
    expected = report.expected_character_count
    duration = "unavailable"
    if report.duration is not None:
        seconds = max(0, int(report.duration))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        duration = f"{hours:02}:{minutes:02}:{seconds:02}"
    lines = [
        f"{titles[report.status]} — {report.characters_processed}/{expected if expected is not None else '?'}",
        f"Duration: {duration}", f"Flows completed: {report.flows_completed}",
        f"Advances / rotation: {report.advances_completed}", "",
        "Characters:", f"{report.counts.complete} complete",
        f"{report.counts.business_incomplete} business / Daily incomplete",
        f"{report.counts.technical_failure} technical failure",
        f"{report.counts.cancelled} cancelled",
    ]
    if report.counts.unassessed:
        lines.append(f"{report.counts.unassessed} unassessed")
    if report.status is ReportStatus.TECHNICAL_FAILURE:
        lines.extend(_failure_lines(report.failure))
    hidden_complete = 0
    for character in report.characters:
        if character.status is ReportStatus.COMPLETE and character.failure is None:
            # Clean characters (including routine skips) stay counted above;
            # detail only shows characters needing attention.
            hidden_complete += 1
            continue
        lines.extend(("", character.label))
        if character.status is None:
            # Assessment uncertain: do not hide any flow.
            visible_flows = character.flows
        else:
            visible_flows = tuple(f for f in character.flows if f.status is not ReportStatus.COMPLETE)
        for flow in visible_flows:
            label = {
                ReportStatus.COMPLETE: "complete (no-op)" if flow.no_op else "complete",
                ReportStatus.SKIPPED_NOT_ELIGIBLE: "skipped (not eligible)",
                ReportStatus.BUSINESS_INCOMPLETE: "business / Daily incomplete",
                ReportStatus.TECHNICAL_FAILURE: "technical failure",
                ReportStatus.CANCELLED: "cancelled", None: "assessment unavailable",
            }[flow.status]
            reason = "; ".join(r.message for r in flow.reasons)
            lines.append(f"- {flow.label}: {label}" + (f": {reason}" if reason else ""))
            if flow.failure is not None and flow.failure != report.failure:
                lines.extend(_failure_lines(flow.failure, "  "))
        if character.failure is not None and character.failure != report.failure and not any(
            f.failure == character.failure for f in character.flows
        ):
            lines.extend(_failure_lines(character.failure, "- "))
        if character.status is ReportStatus.CANCELLED:
            lines.append("- Character processing cancelled")
        elif character.status is ReportStatus.TECHNICAL_FAILURE:
            component = "Rotation" if character.failure_component == "rotation" else "Character processing"
            lines.append(f"- {component} ended with technical failure")
        elif character.status is None and not visible_flows and character.failure is None:
            lines.append("- Assessment unavailable")
    if hidden_complete:
        noun = "character" if hidden_complete == 1 else "characters"
        lines.extend(("", f"{hidden_complete} {noun} had no issues."))
    if report.data_gaps:
        lines.extend(("", "Report limitations: " + "; ".join(report.data_gaps)))
    return "\n".join(lines)
