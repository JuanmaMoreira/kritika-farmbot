"""Productive Lobby-to-Lobby Character Mail flow."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Protocol

from bot.action_executor import ActionExecutor
from bot.catalog import (
    ACTIVITY_MAILBOX_CLAIM_PROCESSING,
    MODE_MAILBOX_CHARACTER_MAIL,
    SCREEN_LOBBY,
    SCREEN_MAILBOX,
    STATUS_MAILBOX_CLAIMABLE,
    STATUS_MAILBOX_READ_MAIL_PRESENT,
)
from bot.component_contracts import ComponentRequirement
from bot.event_log import EventSink
from bot.flow_contracts import FlowContract, FlowEvent, FlowResult, FlowScope, FlowStatus
from bot.runtime_observer import (
    RuntimeObserver,
    RuntimeSnapshot,
    RuntimeWaitAborted,
    RuntimeWaitCancelled,
    RuntimeWaitTimeout,
)
from bot.semantic_actions import (
    ClaimAllCharacterMail,
    CloseMailbox,
    DeleteReadCharacterMail,
    OpenMailbox,
    SelectCharacterMail,
)
from bot.state import ResolutionStatus


MAILBOX_NOOP = "mailbox.noop"
MAILBOX_CLAIM_ALL_SKIPPED = "mailbox.claim_all_skipped"
MAILBOX_CLAIM_PROCESSING_OBSERVED = "mailbox.claim_processing_observed"
MAILBOX_CLAIM_PROCESSING_COMPLETED = "mailbox.claim_processing_completed"
MAILBOX_CLAIM_ALL_NO_EFFECT = "mailbox.claim_all_no_effect"
MAILBOX_CLAIMS_LEFTOVER = "mailbox.claims_leftover"
MAILBOX_DELETE_READ_EXECUTED = "mailbox.delete_read_executed"
MAILBOX_DELETE_READ_SKIPPED = "mailbox.delete_read_skipped"


@dataclass(frozen=True)
class MailboxFlowResult(FlowResult):
    no_op: bool = False
    claim_all_executed: bool = False
    processing_observed: bool = False
    processing_completed: bool = False
    claim_all_no_effect: bool = False
    claims_leftover: bool = False
    delete_read_executed: bool = False


class _Observer(Protocol):
    def observe(self) -> RuntimeSnapshot: ...

    def wait_until(
        self,
        condition: Callable[[RuntimeSnapshot], bool],
        *,
        after_sequence: int,
        timeout: float,
        abort_if: Callable[[RuntimeSnapshot], bool] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
        stable_for: float = 0.0,
    ) -> RuntimeSnapshot: ...


class MailboxFlow:
    """Claim Character Mail once, delete read mail, and return to Lobby."""

    name = "mailbox"
    scope = FlowScope.PER_CHARACTER
    contract = FlowContract(
        precondition=ComponentRequirement.exact_state(SCREEN_LOBBY),
        successful_postconditions=(
            ComponentRequirement.exact_state(SCREEN_LOBBY),
        ),
    )

    def __init__(
        self,
        observer: RuntimeObserver,
        actions: ActionExecutor,
        events: EventSink,
        *,
        navigation_timeout: float = 6.0,
        activity_onset_timeout: float = 2.0,
        processing_timeout: float = 20.0,
        no_effect_timeout: float = 3.0,
        delete_timeout: float = 6.0,
        navigation_stable_for: float = 0.25,
        processing_stable_for: float = 0.75,
        no_effect_stable_for: float = 0.5,
        delete_stable_for: float = 0.5,
        cancel_requested: Callable[[], bool] = lambda: False,
    ) -> None:
        if not callable(getattr(observer, "observe", None)) or not callable(
            getattr(observer, "wait_until", None)
        ):
            raise ValueError("observer must provide observe() and wait_until()")
        if not callable(getattr(actions, "execute", None)):
            raise ValueError("actions must provide execute()")
        if not callable(getattr(events, "record", None)):
            raise ValueError("events must provide record()")
        if not callable(cancel_requested):
            raise ValueError("cancel_requested must be callable")
        self.observer: _Observer = observer
        self.actions = actions
        self.events = events
        self.cancel_requested = cancel_requested
        self.navigation_timeout = _positive_duration(
            navigation_timeout, "navigation_timeout"
        )
        self.activity_onset_timeout = _positive_duration(
            activity_onset_timeout, "activity_onset_timeout"
        )
        self.processing_timeout = _positive_duration(
            processing_timeout, "processing_timeout"
        )
        self.no_effect_timeout = _positive_duration(
            no_effect_timeout, "no_effect_timeout"
        )
        self.delete_timeout = _positive_duration(delete_timeout, "delete_timeout")
        self.navigation_stable_for = _non_negative_duration(
            navigation_stable_for, "navigation_stable_for"
        )
        self.processing_stable_for = _non_negative_duration(
            processing_stable_for, "processing_stable_for"
        )
        self.no_effect_stable_for = _non_negative_duration(
            no_effect_stable_for, "no_effect_stable_for"
        )
        self.delete_stable_for = _non_negative_duration(
            delete_stable_for, "delete_stable_for"
        )

    def run(self) -> MailboxFlowResult:
        events: list[FlowEvent] = []
        claim_all_executed = False
        processing_observed = False
        processing_completed = False
        claim_all_no_effect = False
        claims_leftover = False
        delete_read_executed = False
        no_op = False
        try:
            if self._cancelled():
                return self._cancel(events)
            lobby = self._initial_lobby()
            mailbox = self._act_and_wait(
                OpenMailbox(),
                lobby,
                expected=_is_mailbox,
                abort_if=_has_incompatible_mailbox_navigation,
                timeout=self.navigation_timeout,
                stable_for=self.navigation_stable_for,
            )
            if not _is_character_mail(mailbox):
                mailbox = self._act_and_wait(
                    SelectCharacterMail(),
                    mailbox,
                    expected=_is_character_mail,
                    abort_if=_has_incompatible_character_mail_entry,
                    timeout=self.navigation_timeout,
                    stable_for=self.navigation_stable_for,
                )

            initial_claims = _has_status(mailbox, STATUS_MAILBOX_CLAIMABLE)
            initial_read = _has_status(mailbox, STATUS_MAILBOX_READ_MAIL_PRESENT)
            if not initial_claims:
                self._append_event(events, MAILBOX_CLAIM_ALL_SKIPPED)
            else:
                claim_all_executed = True
                self.actions.execute(ClaimAllCharacterMail(), mailbox.geometry)
                self._record("mailbox.claim_all_executed")
                try:
                    active = self.observer.wait_until(
                        _has_claim_processing_activity,
                        after_sequence=mailbox.sequence,
                        timeout=self.activity_onset_timeout,
                        abort_if=_has_incompatible_processing_state,
                        cancel_requested=self.cancel_requested,
                    )
                except RuntimeWaitTimeout as onset_timeout:
                    anchor = onset_timeout.last_snapshot or mailbox
                    mailbox = self.observer.wait_until(
                        _is_character_mail_claimable_without_activity,
                        after_sequence=anchor.sequence,
                        timeout=self.no_effect_timeout,
                        abort_if=_has_incompatible_processing_state,
                        cancel_requested=self.cancel_requested,
                        stable_for=self.no_effect_stable_for,
                    )
                    claim_all_no_effect = True
                    self._append_event(events, MAILBOX_CLAIM_ALL_NO_EFFECT)
                else:
                    processing_observed = True
                    self._append_event(
                        events, MAILBOX_CLAIM_PROCESSING_OBSERVED
                    )
                    mailbox = self.observer.wait_until(
                        _is_character_mail_without_activity,
                        after_sequence=active.sequence,
                        timeout=self.processing_timeout,
                        abort_if=_has_incompatible_processing_state,
                        cancel_requested=self.cancel_requested,
                        stable_for=self.processing_stable_for,
                    )
                    processing_completed = True
                    self._append_event(
                        events, MAILBOX_CLAIM_PROCESSING_COMPLETED
                    )

            claims_leftover = _has_status(mailbox, STATUS_MAILBOX_CLAIMABLE)
            if claims_leftover:
                self._append_event(events, MAILBOX_CLAIMS_LEFTOVER)

            if _has_status(mailbox, STATUS_MAILBOX_READ_MAIL_PRESENT):
                delete_read_executed = True
                self._append_event(events, MAILBOX_DELETE_READ_EXECUTED)
                mailbox = self._act_and_wait(
                    DeleteReadCharacterMail(),
                    mailbox,
                    expected=_is_character_mail_without_read,
                    abort_if=_has_incompatible_delete_state,
                    timeout=self.delete_timeout,
                    stable_for=self.delete_stable_for,
                )
                if (
                    not claims_leftover
                    and _has_status(mailbox, STATUS_MAILBOX_CLAIMABLE)
                ):
                    claims_leftover = True
                    self._append_event(events, MAILBOX_CLAIMS_LEFTOVER)
            else:
                self._append_event(events, MAILBOX_DELETE_READ_SKIPPED)

            no_op = not initial_claims and not initial_read
            if no_op:
                self._append_event(events, MAILBOX_NOOP)

            lobby = self._act_and_wait(
                CloseMailbox(),
                mailbox,
                expected=_is_clean_lobby,
                abort_if=_has_incompatible_close_state,
                timeout=self.navigation_timeout,
                stable_for=self.navigation_stable_for,
            )
            assert _is_clean_lobby(lobby)
            return MailboxFlowResult(
                FlowStatus.COMPLETED,
                tuple(events),
                no_op=no_op,
                claim_all_executed=claim_all_executed,
                processing_observed=processing_observed,
                processing_completed=processing_completed,
                claim_all_no_effect=claim_all_no_effect,
                claims_leftover=claims_leftover,
                delete_read_executed=delete_read_executed,
            )
        except RuntimeWaitCancelled:
            return self._cancel(events)
        except (RuntimeWaitTimeout, RuntimeWaitAborted) as error:
            return self._failed(events, f"state_wait_failed: {error}")
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            return self._failed(events, f"{type(error).__name__}: {error}")

    def _initial_lobby(self) -> RuntimeSnapshot:
        initial = self.observer.observe()
        if _is_clean_lobby(initial):
            return initial
        if not _is_passive_unknown(initial):
            raise RuntimeError("precondition_lobby_failed")
        return self.observer.wait_until(
            _is_clean_lobby,
            after_sequence=initial.sequence,
            timeout=self.navigation_timeout,
            abort_if=_has_incompatible_lobby_state,
            cancel_requested=self.cancel_requested,
            stable_for=self.navigation_stable_for,
        )

    def _act_and_wait(
        self,
        action,
        before: RuntimeSnapshot,
        *,
        expected,
        abort_if,
        timeout: float,
        stable_for: float,
    ) -> RuntimeSnapshot:
        if self._cancelled():
            raise RuntimeWaitCancelled("mailbox flow cancelled")
        self.actions.execute(action, before.geometry)
        return self.observer.wait_until(
            expected,
            after_sequence=before.sequence,
            timeout=timeout,
            abort_if=abort_if,
            cancel_requested=self.cancel_requested,
            stable_for=stable_for,
        )

    def _append_event(self, events: list[FlowEvent], kind: str) -> None:
        events.append(FlowEvent(kind))
        self._record(kind)

    def _cancel(self, events: list[FlowEvent]) -> MailboxFlowResult:
        self._record("mailbox.cancelled")
        return MailboxFlowResult(FlowStatus.CANCELLED, tuple(events))

    def _failed(self, events: list[FlowEvent], error: str) -> MailboxFlowResult:
        self._record("mailbox.failed", error=error)
        return MailboxFlowResult(FlowStatus.FAILED, tuple(events), error)

    def _record(self, event: str, **fields: object) -> None:
        try:
            self.events.record(event, **fields)
        except Exception:
            pass

    def _cancelled(self) -> bool:
        try:
            return self.cancel_requested() is True
        except Exception:
            return False


def _has_status(snapshot: RuntimeSnapshot, status: str) -> bool:
    return status in snapshot.state.overlays


def _has_claim_processing_activity(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.RESOLVED
        and snapshot.state.base_context == SCREEN_MAILBOX
        and snapshot.observations.best(ACTIVITY_MAILBOX_CLAIM_PROCESSING)
        is not None
    )


def _is_clean_lobby(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_LOBBY
        and not state.overlays
    )


def _is_mailbox(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.RESOLVED
        and state.base_context == SCREEN_MAILBOX
        and set(state.overlays)
        <= {
            MODE_MAILBOX_CHARACTER_MAIL,
            STATUS_MAILBOX_CLAIMABLE,
            STATUS_MAILBOX_READ_MAIL_PRESENT,
        }
    )


def _is_character_mail(snapshot: RuntimeSnapshot) -> bool:
    return (
        _is_mailbox(snapshot)
        and MODE_MAILBOX_CHARACTER_MAIL in snapshot.state.overlays
    )


def _is_character_mail_without_activity(snapshot: RuntimeSnapshot) -> bool:
    return _is_character_mail(snapshot) and not _has_claim_processing_activity(
        snapshot
    )


def _is_character_mail_claimable_without_activity(
    snapshot: RuntimeSnapshot,
) -> bool:
    return (
        _is_character_mail_without_activity(snapshot)
        and _has_status(snapshot, STATUS_MAILBOX_CLAIMABLE)
    )


def _is_character_mail_without_read(snapshot: RuntimeSnapshot) -> bool:
    return (
        _is_character_mail(snapshot)
        and not _has_status(snapshot, STATUS_MAILBOX_READ_MAIL_PRESENT)
        and not _has_claim_processing_activity(snapshot)
    )


def _is_passive_unknown(snapshot: RuntimeSnapshot) -> bool:
    return (
        snapshot.state.status is ResolutionStatus.UNKNOWN
        and not snapshot.state.overlays
    )


def _has_incompatible_lobby_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or bool(state.overlays)
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_LOBBY
        )
    )


def _has_incompatible_mailbox_navigation(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context not in {SCREEN_LOBBY, SCREEN_MAILBOX}
        )
        or bool(
            set(state.overlays)
            - {
                MODE_MAILBOX_CHARACTER_MAIL,
                STATUS_MAILBOX_CLAIMABLE,
                STATUS_MAILBOX_READ_MAIL_PRESENT,
            }
        )
    )


def _has_incompatible_character_mail_entry(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_MAILBOX
        )
        or bool(
            set(state.overlays)
            - {
                MODE_MAILBOX_CHARACTER_MAIL,
                STATUS_MAILBOX_CLAIMABLE,
                STATUS_MAILBOX_READ_MAIL_PRESENT,
            }
        )
    )


def _has_incompatible_processing_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_MAILBOX
        )
    )


def _has_incompatible_delete_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context != SCREEN_MAILBOX
        )
        or bool(
            set(state.overlays)
            - {
                MODE_MAILBOX_CHARACTER_MAIL,
                STATUS_MAILBOX_CLAIMABLE,
                STATUS_MAILBOX_READ_MAIL_PRESENT,
            }
        )
    )


def _has_incompatible_close_state(snapshot: RuntimeSnapshot) -> bool:
    state = snapshot.state
    return (
        state.status is ResolutionStatus.AMBIGUOUS
        or (
            state.status is ResolutionStatus.RESOLVED
            and state.base_context not in {SCREEN_MAILBOX, SCREEN_LOBBY}
        )
        or bool(
            set(state.overlays)
            - {
                MODE_MAILBOX_CHARACTER_MAIL,
                STATUS_MAILBOX_CLAIMABLE,
                STATUS_MAILBOX_READ_MAIL_PRESENT,
            }
        )
    )


def _positive_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a positive finite number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _non_negative_duration(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a non-negative finite number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a non-negative finite number")
    return result


__all__ = (
    "MAILBOX_CLAIMS_LEFTOVER",
    "MAILBOX_CLAIM_ALL_NO_EFFECT",
    "MAILBOX_CLAIM_ALL_SKIPPED",
    "MAILBOX_CLAIM_PROCESSING_COMPLETED",
    "MAILBOX_CLAIM_PROCESSING_OBSERVED",
    "MAILBOX_DELETE_READ_EXECUTED",
    "MAILBOX_DELETE_READ_SKIPPED",
    "MAILBOX_NOOP",
    "MailboxFlow",
    "MailboxFlowResult",
)
