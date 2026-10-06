"""Rewarded-ad lifecycle. Android owns location; the caller owns reward proof."""
from dataclasses import dataclass
from enum import Enum
import re
import time
import cv2
import numpy as np

from bot.event_log import record_best_effort


class AdsOutcome(str, Enum):
    RETURNED = 'returned'
    UNAVAILABLE = 'unavailable'
    EXHAUSTED = 'exhausted'
    ABORTED_RECOVERED = 'AD_ABORTED_RECOVERED'
    RECOVERY_FAILED = 'AD_RECOVERY_FAILED'
    CANCELLED = 'cancelled'


@dataclass(frozen=True)
class AdObservation:
    snapshot: object
    active: bool = False
    returned: bool = False
    unavailable: bool = False
    skip_ticket: bool = False
    external: bool = False
    game_present: bool = False
    back_ready: bool = False
    close_point: tuple[float, float] | None = None
    close_key: str | None = None
    activity: str | None = None
    exhausted: bool = False
    ad_compatible: bool = False
    progress: float | None = None
    intermediate: str | None = None


def read_sdk_progress(frame):
    """Acquired Google SDK top bar; never reads advertising content.

    Native replay shows contiguous yellow fill .264→.918 in the first 30s.
    Android ownership is required by the observer before calling this reader.
    A missing/fragmented bar is unknown, not completion or a close affordance.
    """
    if not isinstance(frame,np.ndarray):return None
    h,w=frame.shape[:2]
    strip=frame[:round(.012*h),round(.038*w):round(.946*w)]
    if not strip.size:return None
    hsv=cv2.cvtColor(strip,cv2.COLOR_BGR2HSV)
    mask=(hsv[:,:,0]>=18)&(hsv[:,:,0]<=35)&(hsv[:,:,1]>=60)&(hsv[:,:,2]>=160)
    columns=mask.mean(axis=0)>.65
    if not columns[:max(2,round(w*.003))].all():return None
    gaps=np.flatnonzero(~columns)
    end=int(gaps[0]) if len(gaps) else len(columns)
    if end<len(columns)*.03 or columns[min(end+3,len(columns)):].any():return None
    return float(end/len(columns))


@dataclass(frozen=True)
class AdsResult:
    outcome: AdsOutcome
    snapshot: object = None
    close_steps: int = 0
    elapsed_seconds: float = 0.


class AdsManager:
    """Close reward-ready SDK variants immediately, with bounded observation.

    Verified SDK progress/reset extends observation, with a 15s idle grace and
    absolute 180s bound for multipart ads. Motion never authorizes a close.

    SDK ownership alone and elapsed time never authorize a close. Game return
    stops Android input even when results are absent. The caller verifies reward.
    """

    def __init__(self, observe, close, refuse_ticket, android_back, *, events=None,
                 cancel_requested=lambda: False, clock=time.monotonic,
                 sleeper=time.sleep, deadline=60., launch_deadline=12.,
                 poll_interval=.5, return_grace=4., back_grace=1.,
                 max_close_steps=6, progress_grace=15., max_duration=180.):
        self.observe = observe
        self.close = close
        self.refuse_ticket = refuse_ticket
        self.android_back = android_back
        self.events = events
        self.cancel_requested = cancel_requested
        self.clock = clock
        self.sleeper = sleeper
        self.deadline = deadline
        self.launch_deadline = launch_deadline
        self.poll_interval = poll_interval
        self.return_grace = return_grace
        self.back_grace = back_grace
        self.max_close_steps = max_close_steps
        self.progress_grace,self.max_duration=progress_grace,max_duration
        if min(deadline, launch_deadline, poll_interval, return_grace,
               back_grace, max_close_steps,progress_grace,max_duration) <= 0:
            raise ValueError('positive ads bounds required')
        if max_duration<deadline:raise ValueError('max duration must cover fallback deadline')

    def complete_requested_launch(self):
        start = self.clock()
        active = refused = False
        steps = normal_backs = external_backs = 0
        previous_key = last_phase = None
        last = None
        next_back_at = start
        previous_progress=None;progress_at=None;last_progress_log=start

        def phase(name, observation=None):
            nonlocal last_phase
            if name != last_phase:
                record_best_effort(self.events, 'ads.phase', phase=name,
                                   activity=getattr(observation, 'activity', None),
                                   source_sequence=getattr(getattr(observation, 'snapshot', None), 'sequence', None),
                                   frame_timestamp=getattr(getattr(observation, 'snapshot', None), 'timestamp', None),
                                   progress=getattr(observation, 'progress', None),
                                   close_key=getattr(observation, 'close_key', None),
                                   intermediate=getattr(observation, 'intermediate', None),
                                   elapsed_seconds=self.clock() - start)
                last_phase = name

        def finish(outcome, observation):
            record_best_effort(self.events,'ads.result',outcome=outcome.value,
                               close_steps=steps,elapsed_seconds=self.clock()-start)
            return AdsResult(outcome, observation.snapshot if observation else None,
                             steps, self.clock() - start)

        def observe_return(observation):
            # No further Back while waiting for results after game return.
            phase('returned_kritika', observation)
            until = self.clock() + self.return_grace
            while True:
                if self.cancel_requested():
                    return finish(AdsOutcome.CANCELLED, observation)
                # A game-owned alert can arrive during the result grace window.
                # Preserve its explicit business identity instead of ad-abort.
                if observation.exhausted:
                    phase('daily_exhausted', observation)
                    return finish(AdsOutcome.EXHAUSTED, observation)
                if observation.unavailable:
                    phase('unavailable', observation)
                    return finish(AdsOutcome.UNAVAILABLE, observation)
                if active and observation.returned:
                    return finish(AdsOutcome.RETURNED, observation)
                if self.clock() >= until:
                    outcome = (AdsOutcome.ABORTED_RECOVERED
                               if observation.game_present or observation.returned
                               else AdsOutcome.RECOVERY_FAILED)
                    return finish(outcome, observation)
                self.sleeper(self.poll_interval)
                observation = self.observe()

        phase('launch_requested')
        while True:
            if self.cancel_requested():
                return finish(AdsOutcome.CANCELLED, last)
            last = self.observe()
            if last.exhausted:
                phase('daily_exhausted', last)
                return finish(AdsOutcome.EXHAUSTED, last)
            if last.unavailable:
                phase('unavailable', last)
                return finish(AdsOutcome.UNAVAILABLE, last)
            if last.returned or (active and last.game_present):
                return observe_return(last)
            if last.active and last.progress is not None:
                # Actual motion/reset of SDK chrome, not a static screenshot,
                # keeps a multipart ad alive. Never authorizes a tap/Back.
                if previous_progress is not None and abs(last.progress-previous_progress)>=.01:
                    progress_at=self.clock()
                if previous_progress is None or abs(last.progress-previous_progress)>=.01:
                    previous_progress=last.progress
                if self.clock()-last_progress_log>=5.:
                    record_best_effort(self.events,'ads.progress',fraction=last.progress,
                                       elapsed_seconds=self.clock()-start)
                    last_progress_log=self.clock()
            elapsed=self.clock()-start
            progressing=progress_at is not None and self.clock()-progress_at<=self.progress_grace
            stalled_for=self.clock()-(progress_at if progress_at is not None else start)
            if elapsed>=self.max_duration:
                record_best_effort(self.events,'ads.recovery_authority',
                    reason='absolute_bound',elapsed_seconds=elapsed,stalled_seconds=stalled_for)
                break
            if stalled_for>=self.deadline and not progressing:
                # Unknown/stalled ads stop observation, without closing an
                # uncredited reward. A verified
                # moving progress bar makes the 60s estimate inapplicable.
                # A part's bar disappearing is not completion: unknown/stall
                # fallback is measured from the last verified SDK movement.
                if not (last.back_ready and normal_backs<2) and last.close_point is None:
                    record_best_effort(self.events,'ads.recovery_authority',
                        reason='unknown_or_stalled',elapsed_seconds=elapsed,stalled_seconds=stalled_for)
                    break
            if last.skip_ticket:
                if not refused:
                    phase('refuse_skip_ticket', last)
                    self.refuse_ticket(last.snapshot)
                    refused = True
            elif last.external:
                active = True
                if external_backs < 2 and steps < self.max_close_steps and self.clock() >= next_back_at:
                    phase('external_return', last)
                    self.android_back(last.snapshot)
                    external_backs += 1
                    steps += 1
                    next_back_at = self.clock() + self.back_grace
            elif last.active:
                # A fresh SDK return closes that external excursion. Multipart
                # ads may open the store once per part; keep the per-excursion
                # bound and the total input budget, rather than starving part 3.
                external_backs = 0
                if not active:
                    phase('active', last)
                active = True
                if (last.back_ready and normal_backs < 2 and
                        steps < self.max_close_steps and self.clock() >= next_back_at):
                    phase('sdk_back', last)
                    self.android_back(last.snapshot)
                    normal_backs += 1
                    steps += 1
                    next_back_at = self.clock() + self.back_grace
                elif last.close_point is not None and not last.back_ready:
                    if last.close_key != previous_key and steps < self.max_close_steps:
                        phase('visual_close', last)
                        self.close(last.snapshot, last.close_point)
                        previous_key = last.close_key
                        steps += 1
                else:
                    phase('multipart_next' if last.intermediate else 'waiting_closable', last)
            elif not active and self.clock() - start >= self.launch_deadline and last.game_present:
                phase('launch_unconfirmed', last)
                return observe_return(last)
            self.sleeper(self.poll_interval)

        phase('terminal_recovery', last)
        # Bounds are not reward evidence. Only fresh accredited SDK terminal
        # chrome or an external visit can authorize an input here.
        for terminal_step in range(2):
            if self.cancel_requested():
                return finish(AdsOutcome.CANCELLED, last)
            last = self.observe()
            if last.game_present or last.returned:
                return observe_return(last)
            if steps >= self.max_close_steps:
                break
            if last.external and external_backs < 2:
                self.android_back(last.snapshot)
                external_backs += 1
            elif last.active and last.back_ready and normal_backs < 2:
                self.android_back(last.snapshot)
                normal_backs += 1
            elif (last.active and last.close_point is not None and
                    not last.back_ready and last.close_key != previous_key):
                self.close(last.snapshot, last.close_point)
                previous_key = last.close_key
            else:
                break
            steps += 1
            until = self.clock() + self.back_grace
            while True:
                last = self.observe()
                if last.game_present or last.returned:
                    return observe_return(last)
                if self.clock() >= until:
                    break
                if self.cancel_requested():
                    return finish(AdsOutcome.CANCELLED, last)
                self.sleeper(self.poll_interval)
        phase('recovery_failed', last)
        return finish(AdsOutcome.RECOVERY_FAILED, last)


class AndroidAdsObserver:
    """Fresh native pixels plus resumed activity and focused window.

    Acquired SDK hierarchy exposes only a WebView: no accessibility selector is
    assumed. CV identifies SDK reward-ready chrome, independent of ad content.
    """

    def __init__(self, observer, adb, game_package, detector, *, returned,
                 unavailable, skip_ticket, game_visible, exhausted=lambda s: False,
                 chrome_ocr=None):
        self.observer = observer
        self.adb = adb
        self.game_package = game_package
        self.detector = detector
        self.returned = returned
        self.unavailable = unavailable
        self.skip_ticket = skip_ticket
        self.game_visible = game_visible
        self.exhausted = exhausted
        self.chrome_ocr = chrome_ocr
        self._not_before = 0.
        self._force_native = False

    def input_dispatched(self):
        self._not_before = time.monotonic()
        self._force_native = True

    def __call__(self):
        snapshot = self.observer.observe()
        if (self._force_native or snapshot.timestamp <= self._not_before or
                time.monotonic() - snapshot.timestamp > 1.):
            self.observer.source.refresh_native()
            snapshot = self.observer.observe()
            self._force_native = False
        activity_text = self.adb.shell('dumpsys', 'activity', 'activities').stdout
        # Samsung's windows subcommand omits mCurrentFocus; the complete dump
        # includes the global focus authority as well as the individual windows.
        window_text = self.adb.shell('dumpsys', 'window').stdout
        match = re.search(r'(?:mResumedActivity|topResumedActivity).*?\s([\w.]+)/([\w.$]+)', activity_text)
        focused = re.search(r'mCurrentFocus=.*?\s([\w.]+)/([\w.$]+)', window_text)
        package, activity = match.groups() if match else (None, None)
        focus = focused.groups() if focused else None
        agrees = focus == (package, activity)
        game_activity = bool(package == self.game_package and
                             activity == 'com.hive.HiveUnityPlayerActivity' and agrees)
        sdk_activity = bool(package == self.game_package and activity and
                            'AdActivity' in activity and agrees)
        dark = self.detector.present(snapshot.frame.image, 'ad_reward_close')
        light = self.detector.present(snapshot.frame.image, 'ad_reward_close_light')
        sdk_chrome = dark or light
        round_close = False
        intermediate = None
        reward_text = False
        if sdk_activity and activity == 'com.google.android.gms.ads.AdActivity':
            primitive_reader = getattr(self.detector, 'sdk_close_scores', None)
            black_x, white_x, sound = (primitive_reader(snapshot.frame.image)
                if callable(primitive_reader) else (0.,0.,0.))
            # Read only the acquired SDK text field, never the creative.
            if self.chrome_ocr is not None:
                frame = snapshot.frame.image
                h,w = frame.shape[:2]
                try:
                    label = self.chrome_ocr.recognize(frame[
                        round(.027*h):round(.095*h),round(.795*w):round(.902*w)].copy())
                    text = re.sub(r'[^a-z]', '', label.text.casefold())
                    if label.confidence >= .85:
                        reward_text = text == 'rewardgranted'
                        if text == 'nextad': intermediate = 'next_ad'
                except Exception:
                    pass
            sdk_chrome = intermediate is None and (
                sdk_chrome or (reward_text and max(black_x,white_x) >= .94))
            # X alone requires both acquired fixed SDK primitives. Unknown
            # content X and part transitions never publish this authority.
            round_close = (not sdk_chrome and intermediate is None
                           and black_x >= .94 and sound >= .94)
        # Main activity plus old SDK pixels cannot authorize another Back.
        # Unacquired embedded layouts never authorize timer-only cleanup.
        active = sdk_activity
        loading = self.detector.present(snapshot.frame.image,'loading')
        game_visible = self.game_visible(snapshot)
        game_present = game_activity and not active and (game_visible or loading)
        ad_compatible = game_activity and not active and not game_visible and not loading
        external = bool(package and package != self.game_package and agrees)
        # Android checks and SDK text OCR must not turn old pixels into a new
        # close authority. A slow observation waits for the next fresh frame.
        terminal_fresh = 0. <= time.monotonic() - snapshot.timestamp <= 2.
        sdk_chrome = sdk_chrome and terminal_fresh
        round_close = round_close and terminal_fresh
        return AdObservation(
            snapshot, active=active,
            returned=game_present and self.returned(snapshot),
            unavailable=game_present and self.unavailable(snapshot),
            skip_ticket=game_present and self.skip_ticket(snapshot),
            external=external, game_present=game_present,
            back_ready=sdk_activity and sdk_chrome,
            # Fixed native SDK control, normalized to frame geometry. Main/
            # external ownership and unacquired X layouts publish no hitbox.
            close_point=(.922,.059) if round_close else None,
            close_key=(('reward_granted_text' if reward_text else
                        'reward_granted_light' if light else 'reward_granted_dark')
                       if sdk_chrome else 'sdk_round_close' if round_close else None),
            activity=activity, exhausted=game_present and self.exhausted(snapshot),
            ad_compatible=ad_compatible,
            progress=read_sdk_progress(snapshot.frame.image) if sdk_activity else None,
            intermediate=intermediate)
