"""Acquired Stages controls for Ads navigation and one manual battle entry."""
from dataclasses import dataclass
from enum import Enum

class StageControl(str,Enum):
    OPEN='open'; BACK='back'; NORMAL='normal'; CLAIM='claim'
    WORLD_MAP='world_map'; ABYSSAL_TAIL='abyssal_tail'; STAGE8='stage8'
    SUPPORT='support'; FILL_SUPPORT='fill_support'; CLOSE_SUPPORT='close_support'
    PENANCE='penance'; START='start'; AUTO='auto'; MAX300='max300'; VIDEO='video'
    RESULTS_OK='results_ok'; CLOSE_CONFIG='close_config'; CLOSE_START='close_start'
    CLOSE_AUTO='close_auto'; DECLINE_AD_TICKET='decline_ad_ticket'; NO_ADS_OK='no_ads_ok'
    CURRENCY='currency'; STAMINA_ROW='stamina_row'; STAMINA_INCREMENT='stamina_increment'
    LOBBY_INVENTORY='lobby_inventory'
    CHAOS='chaos'; STAGE6='stage6'; STAGE9='stage9'; X4='x4'
    BUFF1='buff1'; BUFF2='buff2'; BUFF3='buff3'; BUFF4='buff4'
    STRIKER_START='striker_start'; BATTLE_AUTO='battle_auto'; CLEAR_HOME='clear_home'
    HELL='hell'
    DEATH_ABANDON='death_abandon'; DEATH_GUIDE_CLOSE='death_guide_close'

POINTS={
    StageControl.CHAOS:(.253,.265), StageControl.STAGE6:(.762,.401),
    StageControl.STAGE9:(.548,.699), StageControl.X4:(.808,.925),
    StageControl.BUFF1:(.534,.515),StageControl.BUFF2:(.610,.515),
    StageControl.BUFF3:(.687,.515),StageControl.BUFF4:(.762,.515),
    StageControl.HELL:(.302,.906),StageControl.STRIKER_START:(.580,.876),
    StageControl.BATTLE_AUTO:(.877,.057),
    StageControl.CLEAR_HOME:(.258,.882),
    StageControl.DEATH_ABANDON:(.430,.559),StageControl.DEATH_GUIDE_CLOSE:(.766,.186),
    StageControl.OPEN:(.82,.28),StageControl.BACK:(.805,.06),StageControl.NORMAL:(.807,.181),
    StageControl.CLAIM:(.426,.93),StageControl.WORLD_MAP:(.73,.18),
    StageControl.ABYSSAL_TAIL:(.36,.265),StageControl.STAGE8:(.656,.66),
    StageControl.SUPPORT:(.749,.786),StageControl.FILL_SUPPORT:(.599,.847),
    StageControl.CLOSE_SUPPORT:(.740,.084),StageControl.PENANCE:(.451,.908),
    StageControl.START:(.733,.90),StageControl.AUTO:(.417,.88),StageControl.MAX300:(.335,.795),
    StageControl.VIDEO:(.356,.889),StageControl.RESULTS_OK:(.499,.865),
    StageControl.CLOSE_CONFIG:(.804,.166),StageControl.CLOSE_START:(.665,.09),
    StageControl.CLOSE_AUTO:(.828,.045),StageControl.CURRENCY:(.585,.24),
    StageControl.STAMINA_ROW:(.707,.424),
    # Single > acquired in the fixed Item Trade panel (separate from >>).
    StageControl.STAMINA_INCREMENT:(.672,.805),
    StageControl.DECLINE_AD_TICKET:(.568,.625),
    StageControl.NO_ADS_OK:(.500,.626),
    StageControl.LOBBY_INVENTORY:(.655,.75),
}

@dataclass(frozen=True)
class StageAction:
    control:StageControl
    def __post_init__(self):
        if not isinstance(self.control,StageControl):raise ValueError('StageControl required')
        if self.control not in POINTS:raise ValueError('control not acquired')

@dataclass(frozen=True)
class CloseAdAffordance:
    point:tuple[float,float]
    def __post_init__(self):
        if len(self.point)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not 0<=v<=1 for v in self.point):
            raise ValueError('normalized close affordance required')
