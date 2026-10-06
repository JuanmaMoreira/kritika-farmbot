"""Composition of the concrete Daily caller with existing productive owners."""
from bot.ads_manager import AdsManager, AndroidAdsObserver
from bot.perception import ScopeSpec, select_detectors, STRONG_LOBBY_COMPLETION_SPEC_NAMES, STRONG_LOBBY_COMPLETION_SPECIALIZED_TYPES
from bot.perception.engine import PerceptionEngine
from bot.perception.stages import StagesDetector, StagesClaimDetector, surface
from bot.stages_actions import CloseAdAffordance, StageControl
from bot.stages_runtime import StagesNavigation
from bot.stages_balances import StagesBalanceReader
from bot.stamina_purchase import StaminaPurchase
from bot.same_character_reentry import SameCharacterReentry
from bot.stages_daily_flow import StagesDailyFlow
from bot.ocr import RapidOcrEngine
import re

def is_no_ads_alert(snapshot, balances):
    if surface(snapshot)=='no_ads':return True
    if surface(snapshot)!='alert':return False
    # Literal No Ads text fallback; acquired Loading/Select Character uses CV.
    # Called only after Android verifies
    # main activity/window; the acquired single-OK alert supplies the body ROI.
    try:text=balances.text(snapshot,(.350,.385,.650,.565))
    except ValueError:return False
    return re.sub(r'[^a-z]','',text.casefold()).startswith('noadsavailable')

def ensure_lobby_entry(dependencies):
    """The economic caller requests its next required entry from Navigation."""
    from bot.component_contracts import ComponentRequirement
    result = dependencies.build_preconditions().ensure(ComponentRequirement.exact_state('screen.lobby'))
    if not result.succeeded:
        raise ValueError(result.error or 'lobby_entry_unconfirmed')
    return result


def build_stages_daily(dependencies, monster_wave):
    scope = ScopeSpec('stages_daily', STRONG_LOBBY_COMPLETION_SPEC_NAMES,
                      (*STRONG_LOBBY_COMPLETION_SPECIALIZED_TYPES, StagesDetector))
    observer = dependencies.observer.scoped(select_detectors(dependencies.observer.perception, scope))
    detector = next(d for d in observer.perception.detectors if isinstance(d, StagesDetector))
    nav = StagesNavigation(observer, dependencies.actions, events=dependencies.events,
                           cancel_requested=dependencies.cancel_requested)
    nav.claim_observer=observer.scoped(PerceptionEngine((StagesClaimDetector(detector),)))
    balances = StagesBalanceReader(nav, getattr(dependencies,"ocr_engine",None) or RapidOcrEngine())
    # Ad content never goes through the game's full landmark family or OCR.
    ads_scope = ScopeSpec('ads_android_return',
        frozenset({'landmark.lobby_trading_center_label'}), (StagesDetector,))
    ads_observer = observer.scoped(select_detectors(observer.perception, ads_scope))
    android = AndroidAdsObserver(ads_observer, dependencies.actions.adb,
        dependencies.config.game_package, detector,
        returned=lambda s: surface(s)=='results',
        unavailable=lambda s:is_no_ads_alert(s,balances),
        skip_ticket=lambda s: surface(s)=='skip_ticket',
        exhausted=lambda s: surface(s)=='daily_exhausted',
        game_visible=lambda s: surface(s) is not None or
            s.observations.best('landmark.lobby_trading_center_label') is not None,
        chrome_ocr=balances.engine)
    def ad_input(operation, *args):
        operation(*args)
        android.input_dispatched()
    ads = AdsManager(android,
        lambda s,p: ad_input(nav.act, CloseAdAffordance(p),s),
        lambda s: ad_input(nav.tap, StageControl.DECLINE_AD_TICKET,s),
        lambda s: ad_input(dependencies.actions.adb.shell,'input','keyevent','4'),
        events=dependencies.events, cancel_requested=dependencies.cancel_requested)
    from bot.stages_reliefs import StagesReliefs
    nav.relief = StagesReliefs(nav, dependencies, monster_wave.equipment_relief)
    return StagesDailyFlow(nav, balances, StaminaPurchase(nav,balances,detector),ads,
        monster_wave=monster_wave, reenter_same_character=SameCharacterReentry(nav,balances),
        ensure_lobby=lambda: ensure_lobby_entry(dependencies),
        entry_snapshot=dependencies.observer.observe)
