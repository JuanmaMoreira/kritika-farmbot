"""Translate typed actions to normalized physical Android input."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral

from bot.adb import AdbClient
from bot.geometry import (
    PixelPoint,
    RelativePoint,
    frame_dimensions,
    relative_point_to_pixel,
)
from bot.semantic_actions import (
    AcceptPurchaseConfirmation,
    AcceptPetInventoryFull,
    AcceptSocketInventoryFull,
    AcknowledgeEtherealNoMaterial,
    AcknowledgeInventoryFull,
    AcknowledgePetCombineNoMaterial,
    AcknowledgeSocketNoMaterial,
    AcknowledgeWorldBossPreviousRewards,
    ClaimAllCharacterMail,
    ClaimAllDailyQuests,
    ClaimDailyQuestsProgressReward,
    CheckInGuildAttendance,
    CloseBlackMarket,
    CloseDailyQuests,
    CloseFriends,
    CloseMailbox,
    ClosePets,
    ClosePetSummonResult,
    ConfirmCharacterSelection,
    ContinueAfterWorldBossRaid,
    CancelSocketSell,
    CloseSocketEnhanceAll,
    ConfirmCombineAll,
    ConfirmEtherealMassCombine,
    ConfirmPetCombineAll,
    ConfirmPetMassEvolve,
    DismissWorldBossBagFull,
    DeleteReadCharacterMail,
    ExitSocket,
    ExitCombine,
    OpenBlackMarket,
    OpenPets,
    OpenEpicPetSummon,
    OpenPremiumPetSummon,
    OpenSingleEpicPet,
    OpenTenEpicPets,
    OpenSinglePremiumPet,
    OpenPetCombineAll,
    OpenPetMassEvolve,
    OpenFriends,
    OpenGuild,
    OpenQuests,
    OpenMailbox,
    OpenBattleModeSelect,
    OpenCharacterSelect,
    OpenQuickMenu,
    OpenSocketEnhanceAll,
    OpenSocketEquipmentHome,
    OpenSocketSell,
    OpenAwakenedTransmute,
    OpenCombineAll,
    OpenEquipmentCombine,
    OpenEtherealMassCombine,
    OpenEtherealRandomPart,
    QuickMenuLayout,
    OpenWorldBossSelector,
    RejectInsufficientGold,
    RejectPetEpicRunesFull,
    RejectPetInventoryFull,
    RejectSocketInventoryFull,
    SelectSocketEnhanceGold,
    SelectSocketOpalSlot,
    SelectCombineFuse,
    SelectCombineTransmute,
    SelectCharacterMail,
    SelectDailyQuests,
    SelectPetCombine,
    SelectPetLowTierCandidate,
    SelectPetSummon,
    SelectQuickMenuLobby,
    SelectQuickMenuGuild,
    SendStaminaToAllFriends,
    SellSocketInBulk,
    SelectLastVisibleCharacter,
    SelectAvailableWorldBoss,
    SelectBlackMarketSlot,
    SemanticAction,
    Swipe,
    ToggleAutoBattle,
    TapSocketEnhanceAnimation,
    TapCombineAnimation,
    CancelPetMassEvolveSelection,
    NextPetCombinePage,
    StartWorldBossBattle,
)


@dataclass(frozen=True)
class FrameGeometry:
    """Frame dimensions already derived from the actual captured ndarray."""

    width: int
    height: int

    def __post_init__(self) -> None:
        for name in ("width", "height"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
            object.__setattr__(self, name, int(value))

    @classmethod
    def from_frame(cls, frame: object) -> "FrameGeometry":
        """Build geometry from ``frame.shape`` without querying device metadata."""

        width, height = frame_dimensions(frame)
        return cls(width=width, height=height)


@dataclass(frozen=True)
class BlackMarketActionTargets:
    """Normalized targets validated for the current landscape layout."""

    open_black_market: RelativePoint = (0.1667, 0.8930)
    close_black_market: RelativePoint = (0.8097, 0.1324)
    slots: tuple[RelativePoint, ...] = (
        (0.4491, 0.3415),
        (0.7592, 0.3415),
        (0.4506, 0.4698),
        (0.7570, 0.4706),
        (0.4524, 0.5948),
        (0.7507, 0.6095),
        (0.4539, 0.7337),
        (0.7592, 0.7377),
        (0.4454, 0.8725),
        (0.7592, 0.8717),
    )
    accept_purchase: RelativePoint = (0.4347, 0.6340)
    reject_insufficient_gold: RelativePoint = (0.5690, 0.6307)
    acknowledge_inventory_full: RelativePoint = (0.5006, 0.6270)

    def __post_init__(self) -> None:
        slots = tuple(self.slots)
        if len(slots) != 10:
            raise ValueError("slots must contain exactly ten row-major targets")
        points = (
            self.open_black_market,
            self.close_black_market,
            *slots,
            self.accept_purchase,
            self.reject_insufficient_gold,
            self.acknowledge_inventory_full,
        )
        for point in points:
            # Reuse the production point validator without fixing a resolution.
            relative_point_to_pixel(point, 1, 1)
        object.__setattr__(self, "slots", slots)


DEFAULT_BLACK_MARKET_ACTION_TARGETS = BlackMarketActionTargets()


@dataclass(frozen=True)
class DailyQuestsActionTargets:
    """Normalized targets acquired from the live Daily Quests route."""

    open_quests: RelativePoint = (0.6540, 0.9200)
    select_daily_quests: RelativePoint = (0.2570, 0.2250)
    claim_all: RelativePoint = (0.6930, 0.1413)
    claim_progress_reward: RelativePoint = (0.6890, 0.3252)
    close_daily_quests: RelativePoint = (0.8223, 0.0989)

    def __post_init__(self) -> None:
        for point in (
            self.open_quests,
            self.select_daily_quests,
            self.claim_all,
            self.claim_progress_reward,
            self.close_daily_quests,
        ):
            relative_point_to_pixel(point, 1, 1)


DEFAULT_DAILY_QUESTS_ACTION_TARGETS = DailyQuestsActionTargets()


@dataclass(frozen=True)
class FriendsActionTargets:
    """Normalized targets acquired from the live Send Stamina route."""

    open_friends: RelativePoint = (0.8374, 0.0784)
    send_all: RelativePoint = (0.7750, 0.8900)
    close_friends: RelativePoint = (0.8190, 0.0980)

    def __post_init__(self) -> None:
        for point in (self.open_friends, self.send_all, self.close_friends):
            relative_point_to_pixel(point, 1, 1)


DEFAULT_FRIENDS_ACTION_TARGETS = FriendsActionTargets()


@dataclass(frozen=True)
class PetActionTargets:
    """Normalized targets acquired from the Pet Summon and Combine routes."""

    open_pets: RelativePoint = (0.8599, 0.7745)
    select_summon: RelativePoint = (0.2030, 0.1800)
    select_combine: RelativePoint = (0.3610, 0.1800)
    close_pets: RelativePoint = (0.8000, 0.0700)
    open_epic: RelativePoint = (0.5730, 0.8700)
    open_premium: RelativePoint = (0.4100, 0.8700)
    open_single_epic: RelativePoint = (0.5630, 0.7420)
    open_ten_epic: RelativePoint = (0.6370, 0.7420)
    open_single_premium: RelativePoint = (0.3950, 0.7420)
    close_summon_result: RelativePoint = (0.9000, 0.5000)
    accept_inventory_full: RelativePoint = (0.4320, 0.6300)
    reject_inventory_full: RelativePoint = (0.5680, 0.6300)
    open_combine_all: RelativePoint = (0.6073, 0.9297)
    confirm_combine_all: RelativePoint = (0.4320, 0.6300)
    acknowledge_combine_no_material: RelativePoint = (0.5000, 0.6300)
    reject_epic_runes_full: RelativePoint = (0.5680, 0.6300)
    open_mass_evolve: RelativePoint = (0.7520, 0.8000)
    confirm_mass_evolve: RelativePoint = (0.4320, 0.6300)
    cancel_mass_evolve_selection: RelativePoint = (0.4800, 0.2600)
    next_combine_page: RelativePoint = (0.8020, 0.9300)

    def __post_init__(self) -> None:
        for point in (
            self.open_pets,
            self.select_summon,
            self.select_combine,
            self.close_pets,
            self.open_epic,
            self.open_premium,
            self.open_single_epic,
            self.open_ten_epic,
            self.open_single_premium,
            self.close_summon_result,
            self.accept_inventory_full,
            self.reject_inventory_full,
            self.open_combine_all,
            self.confirm_combine_all,
            self.acknowledge_combine_no_material,
            self.reject_epic_runes_full,
            self.open_mass_evolve,
            self.confirm_mass_evolve,
            self.cancel_mass_evolve_selection,
            self.next_combine_page,
        ):
            relative_point_to_pixel(point, 1, 1)


DEFAULT_PET_ACTION_TARGETS = PetActionTargets()


@dataclass(frozen=True)
class MailboxActionTargets:
    """Normalized targets acquired from the live Character Mail route."""

    open_mailbox: RelativePoint = (0.8890, 0.0550)
    select_character_mail: RelativePoint = (0.3820, 0.2737)
    claim_all: RelativePoint = (0.4775, 0.3521)
    delete_read: RelativePoint = (0.2826, 0.3521)
    close_mailbox: RelativePoint = (0.8182, 0.1683)

    def __post_init__(self) -> None:
        for point in (
            self.open_mailbox,
            self.select_character_mail,
            self.claim_all,
            self.delete_read,
            self.close_mailbox,
        ):
            relative_point_to_pixel(point, 1, 1)


DEFAULT_MAILBOX_ACTION_TARGETS = MailboxActionTargets()


@dataclass(frozen=True)
class RotationActionTargets:
    """Normalized targets measured from the current 2712x1224 layout.

    The character card target describes the first column of the final visible
    row. It is a layout rule and is intentionally independent of the configured
    number of characters.
    """

    # Shared live-confirmed hit target inside the player header. It opens and
    # closes Quick Menu from both Lobby and World Boss at the current geometry.
    open_quick_menu: RelativePoint = (0.1940, 0.0564)
    select_lobby: RelativePoint = (0.2020, 0.2050)
    select_guild: RelativePoint = (0.2650, 0.6500)
    select_guild_shifted: RelativePoint = (0.3946, 0.6500)
    open_character_select: RelativePoint = (0.0704, 0.7835)
    open_character_select_shifted: RelativePoint = (0.2000, 0.7835)
    last_visible_character: RelativePoint = (0.5500, 0.7300)
    confirm_character_selection: RelativePoint = (0.6855, 0.9101)

    def __post_init__(self) -> None:
        for point in (
            self.open_quick_menu,
            self.select_lobby,
            self.select_guild,
            self.select_guild_shifted,
            self.open_character_select,
            self.open_character_select_shifted,
            self.last_visible_character,
            self.confirm_character_selection,
        ):
            relative_point_to_pixel(point, 1, 1)


DEFAULT_ROTATION_ACTION_TARGETS = RotationActionTargets()


@dataclass(frozen=True)
class GuildActionTargets:
    """Normalized targets acquired from the live Guild surface."""

    open_guild: RelativePoint = (0.7891, 0.0858)
    attendance: RelativePoint = (0.4330, 0.4300)

    def __post_init__(self) -> None:
        for point in (self.open_guild, self.attendance):
            relative_point_to_pixel(point, 1, 1)


DEFAULT_GUILD_ACTION_TARGETS = GuildActionTargets()


@dataclass(frozen=True)
class BattleActionTargets:
    """Normalized targets acquired from the live World Boss route."""

    open_battle_mode_select: RelativePoint = (0.8097, 0.4297)
    open_world_boss_selector: RelativePoint = (0.3514, 0.7843)
    select_available_world_boss: RelativePoint = (0.4974, 0.5449)
    acknowledge_previous_rewards: RelativePoint = (0.5000, 0.9200)
    start_world_boss_battle: RelativePoint = (0.7740, 0.9346)
    toggle_auto_battle: RelativePoint = (0.8625, 0.0480)
    continue_after_raid: RelativePoint = (0.5000, 0.9100)
    dismiss_world_boss_bag_full: RelativePoint = (0.6700, 0.3100)

    def __post_init__(self) -> None:
        for point in (
            self.open_battle_mode_select,
            self.open_world_boss_selector,
            self.select_available_world_boss,
            self.acknowledge_previous_rewards,
            self.start_world_boss_battle,
            self.toggle_auto_battle,
            self.continue_after_raid,
            self.dismiss_world_boss_bag_full,
        ):
            relative_point_to_pixel(point, 1, 1)


DEFAULT_BATTLE_ACTION_TARGETS = BattleActionTargets()


@dataclass(frozen=True)
class SocketActionTargets:
    """Normalized targets acquired from the live Socket relief route."""

    accept_inventory_full: RelativePoint = (0.433974, 0.640779)
    reject_inventory_full: RelativePoint = (0.5690, 0.6307)
    exit_socket: RelativePoint = (0.8000, 0.0700)
    open_enhance_all: RelativePoint = (0.6250, 0.9400)
    enhance_gold: RelativePoint = (0.3750, 0.8400)
    acknowledge_no_material: RelativePoint = (0.5000, 0.6250)
    close_enhance_all: RelativePoint = (0.7500, 0.1550)
    open_equipment_home: RelativePoint = (0.3030, 0.1800)
    opal_slots: tuple[RelativePoint, ...] = tuple(
        (x, y)
        for y in (0.400, 0.540, 0.680, 0.820)
        for x in (0.583, 0.650, 0.718, 0.785)
    )
    open_sell: RelativePoint = (0.3700, 0.9300)
    sell_bulk: RelativePoint = (0.4000, 0.6330)
    cancel_sell: RelativePoint = (0.6000, 0.6330)
    animation_safe_tap: RelativePoint = (0.0800, 0.5000)

    def __post_init__(self) -> None:
        if len(self.opal_slots) != 16:
            raise ValueError("opal_slots must contain exactly sixteen targets")
        for point in (
            self.accept_inventory_full,
            self.reject_inventory_full,
            self.exit_socket,
            self.open_enhance_all,
            self.enhance_gold,
            self.acknowledge_no_material,
            self.close_enhance_all,
            self.open_equipment_home,
            *self.opal_slots,
            self.open_sell,
            self.sell_bulk,
            self.cancel_sell,
            self.animation_safe_tap,
        ):
            relative_point_to_pixel(point, 1, 1)


DEFAULT_SOCKET_ACTION_TARGETS = SocketActionTargets()


@dataclass(frozen=True)
class EquipmentActionTargets:
    """Normalized targets acquired from the live equipment relief route."""

    open_combine: RelativePoint = (0.5000, 0.6300)
    select_transmute: RelativePoint = (0.3000, 0.1800)
    select_fuse: RelativePoint = (0.2200, 0.1800)
    # Input-space target: the frame-space center is not equivalent on this
    # rotated device.  Reconfirmed from a physical tap on 2026-08-30.
    open_combine_all: RelativePoint = (0.6073, 0.9297)
    confirm_combine_all: RelativePoint = (0.4500, 0.7200)
    open_awakened_transmute: RelativePoint = (0.3300, 0.9300)
    open_ethereal_random_part: RelativePoint = (0.2700, 0.4300)
    open_ethereal_mass_combine: RelativePoint = (0.3400, 0.6400)
    confirm_ethereal_mass_combine: RelativePoint = (0.4300, 0.6200)
    acknowledge_ethereal_no_material: RelativePoint = (0.5000, 0.6200)
    animation_tap: RelativePoint = (0.5000, 0.7800)
    exit_combine: RelativePoint = (0.8000, 0.0700)

    def __post_init__(self) -> None:
        for point in (
            self.open_combine,
            self.select_transmute,
            self.select_fuse,
            self.open_combine_all,
            self.confirm_combine_all,
            self.open_awakened_transmute,
            self.open_ethereal_random_part,
            self.open_ethereal_mass_combine,
            self.confirm_ethereal_mass_combine,
            self.acknowledge_ethereal_no_material,
            self.animation_tap,
            self.exit_combine,
        ):
            relative_point_to_pixel(point, 1, 1)


DEFAULT_EQUIPMENT_ACTION_TARGETS = EquipmentActionTargets()


@dataclass(frozen=True)
class ActionExecution:
    """Diagnostic receipt for one physical action already sent to ADB."""

    action: SemanticAction
    normalized_target: RelativePoint
    pixel_target: PixelPoint


@dataclass(frozen=True)
class SwipeExecution:
    """Diagnostic receipt for one physical swipe already sent to ADB."""

    action: Swipe
    normalized_start: RelativePoint
    normalized_end: RelativePoint
    pixel_start: PixelPoint
    pixel_end: PixelPoint
    duration_ms: int


class ActionExecutor:
    """Resolve one intent to physical input without recognizing game state."""

    def __init__(
        self,
        adb: AdbClient,
        *,
        targets: BlackMarketActionTargets = DEFAULT_BLACK_MARKET_ACTION_TARGETS,
        daily_quests_targets: DailyQuestsActionTargets = (
            DEFAULT_DAILY_QUESTS_ACTION_TARGETS
        ),
        friends_targets: FriendsActionTargets = DEFAULT_FRIENDS_ACTION_TARGETS,
        pet_targets: PetActionTargets = DEFAULT_PET_ACTION_TARGETS,
        mailbox_targets: MailboxActionTargets = DEFAULT_MAILBOX_ACTION_TARGETS,
        rotation_targets: RotationActionTargets = DEFAULT_ROTATION_ACTION_TARGETS,
        guild_targets: GuildActionTargets = DEFAULT_GUILD_ACTION_TARGETS,
        battle_targets: BattleActionTargets = DEFAULT_BATTLE_ACTION_TARGETS,
        socket_targets: SocketActionTargets = DEFAULT_SOCKET_ACTION_TARGETS,
        equipment_targets: EquipmentActionTargets = DEFAULT_EQUIPMENT_ACTION_TARGETS,
    ) -> None:
        if not callable(getattr(adb, "tap", None)):
            raise ValueError("adb must provide tap(x, y)")
        if not isinstance(targets, BlackMarketActionTargets):
            raise ValueError("targets must be BlackMarketActionTargets")
        if not isinstance(daily_quests_targets, DailyQuestsActionTargets):
            raise ValueError("daily_quests_targets must be DailyQuestsActionTargets")
        if not isinstance(friends_targets, FriendsActionTargets):
            raise ValueError("friends_targets must be FriendsActionTargets")
        if not isinstance(pet_targets, PetActionTargets):
            raise ValueError("pet_targets must be PetActionTargets")
        if not isinstance(mailbox_targets, MailboxActionTargets):
            raise ValueError("mailbox_targets must be MailboxActionTargets")
        if not isinstance(rotation_targets, RotationActionTargets):
            raise ValueError("rotation_targets must be RotationActionTargets")
        if not isinstance(guild_targets, GuildActionTargets):
            raise ValueError("guild_targets must be GuildActionTargets")
        if not isinstance(battle_targets, BattleActionTargets):
            raise ValueError("battle_targets must be BattleActionTargets")
        if not isinstance(socket_targets, SocketActionTargets):
            raise ValueError("socket_targets must be SocketActionTargets")
        if not isinstance(equipment_targets, EquipmentActionTargets):
            raise ValueError("equipment_targets must be EquipmentActionTargets")
        self.adb = adb
        self.targets = targets
        self.daily_quests_targets = daily_quests_targets
        self.friends_targets = friends_targets
        self.pet_targets = pet_targets
        self.mailbox_targets = mailbox_targets
        self.rotation_targets = rotation_targets
        self.guild_targets = guild_targets
        self.battle_targets = battle_targets
        self.socket_targets = socket_targets
        self.equipment_targets = equipment_targets

    def execute(
        self, action: SemanticAction, geometry: FrameGeometry
    ) -> ActionExecution | SwipeExecution:
        """Translate one semantic action to exactly one ADB input command."""

        if not isinstance(geometry, FrameGeometry):
            raise ValueError("geometry must be FrameGeometry")
        if isinstance(action, Swipe):
            return self._execute_swipe(action, geometry)
        target = self._target_for(action)
        pixel = relative_point_to_pixel(target, geometry.width, geometry.height)
        self.adb.tap(*pixel)
        return ActionExecution(
            action=action,
            normalized_target=target,
            pixel_target=pixel,
        )

    def _target_for(self, action: SemanticAction) -> RelativePoint:
        if isinstance(action, OpenBlackMarket):
            return self.targets.open_black_market
        if isinstance(action, CloseBlackMarket):
            return self.targets.close_black_market
        if isinstance(action, OpenQuests):
            return self.daily_quests_targets.open_quests
        if isinstance(action, SelectDailyQuests):
            return self.daily_quests_targets.select_daily_quests
        if isinstance(action, ClaimAllDailyQuests):
            return self.daily_quests_targets.claim_all
        if isinstance(action, ClaimDailyQuestsProgressReward):
            return self.daily_quests_targets.claim_progress_reward
        if isinstance(action, CloseDailyQuests):
            return self.daily_quests_targets.close_daily_quests
        if isinstance(action, OpenFriends):
            return self.friends_targets.open_friends
        if isinstance(action, SendStaminaToAllFriends):
            return self.friends_targets.send_all
        if isinstance(action, CloseFriends):
            return self.friends_targets.close_friends
        if isinstance(action, OpenPets):
            return self.pet_targets.open_pets
        if isinstance(action, SelectPetSummon):
            return self.pet_targets.select_summon
        if isinstance(action, SelectPetCombine):
            return self.pet_targets.select_combine
        if isinstance(action, ClosePets):
            return self.pet_targets.close_pets
        if isinstance(action, OpenEpicPetSummon):
            return self.pet_targets.open_epic
        if isinstance(action, OpenPremiumPetSummon):
            return self.pet_targets.open_premium
        if isinstance(action, OpenSingleEpicPet):
            return self.pet_targets.open_single_epic
        if isinstance(action, OpenTenEpicPets):
            return self.pet_targets.open_ten_epic
        if isinstance(action, OpenSinglePremiumPet):
            return self.pet_targets.open_single_premium
        if isinstance(action, ClosePetSummonResult):
            return self.pet_targets.close_summon_result
        if isinstance(action, AcceptPetInventoryFull):
            return self.pet_targets.accept_inventory_full
        if isinstance(action, RejectPetInventoryFull):
            return self.pet_targets.reject_inventory_full
        if isinstance(action, OpenPetCombineAll):
            return self.pet_targets.open_combine_all
        if isinstance(action, ConfirmPetCombineAll):
            return self.pet_targets.confirm_combine_all
        if isinstance(action, AcknowledgePetCombineNoMaterial):
            return self.pet_targets.acknowledge_combine_no_material
        if isinstance(action, RejectPetEpicRunesFull):
            return self.pet_targets.reject_epic_runes_full
        if isinstance(action, SelectPetLowTierCandidate):
            return action.target
        if isinstance(action, OpenPetMassEvolve):
            return self.pet_targets.open_mass_evolve
        if isinstance(action, ConfirmPetMassEvolve):
            return self.pet_targets.confirm_mass_evolve
        if isinstance(action, CancelPetMassEvolveSelection):
            return self.pet_targets.cancel_mass_evolve_selection
        if isinstance(action, NextPetCombinePage):
            return self.pet_targets.next_combine_page
        if isinstance(action, OpenMailbox):
            return self.mailbox_targets.open_mailbox
        if isinstance(action, SelectCharacterMail):
            return self.mailbox_targets.select_character_mail
        if isinstance(action, ClaimAllCharacterMail):
            return self.mailbox_targets.claim_all
        if isinstance(action, DeleteReadCharacterMail):
            return self.mailbox_targets.delete_read
        if isinstance(action, CloseMailbox):
            return self.mailbox_targets.close_mailbox
        if isinstance(action, OpenGuild):
            return self.guild_targets.open_guild
        if isinstance(action, SelectBlackMarketSlot):
            return self.targets.slots[action.slot_index]
        if isinstance(action, AcceptPurchaseConfirmation):
            return self.targets.accept_purchase
        if isinstance(action, RejectInsufficientGold):
            return self.targets.reject_insufficient_gold
        if isinstance(action, AcknowledgeInventoryFull):
            return self.targets.acknowledge_inventory_full
        if isinstance(action, OpenQuickMenu):
            return self.rotation_targets.open_quick_menu
        if isinstance(action, SelectQuickMenuLobby):
            return self.rotation_targets.select_lobby
        if isinstance(action, SelectQuickMenuGuild):
            return (
                self.rotation_targets.select_guild
                if action.layout is QuickMenuLayout.LOBBY
                else self.rotation_targets.select_guild_shifted
            )
        if isinstance(action, OpenCharacterSelect):
            return (
                self.rotation_targets.open_character_select
                if action.layout is QuickMenuLayout.LOBBY
                else self.rotation_targets.open_character_select_shifted
            )
        if isinstance(action, CheckInGuildAttendance):
            return self.guild_targets.attendance
        if isinstance(action, SelectLastVisibleCharacter):
            return self.rotation_targets.last_visible_character
        if isinstance(action, ConfirmCharacterSelection):
            return self.rotation_targets.confirm_character_selection
        if isinstance(action, ToggleAutoBattle):
            return self.battle_targets.toggle_auto_battle
        if isinstance(action, OpenBattleModeSelect):
            return self.battle_targets.open_battle_mode_select
        if isinstance(action, OpenWorldBossSelector):
            return self.battle_targets.open_world_boss_selector
        if isinstance(action, SelectAvailableWorldBoss):
            return self.battle_targets.select_available_world_boss
        if isinstance(action, AcknowledgeWorldBossPreviousRewards):
            return self.battle_targets.acknowledge_previous_rewards
        if isinstance(action, StartWorldBossBattle):
            return self.battle_targets.start_world_boss_battle
        if isinstance(action, ContinueAfterWorldBossRaid):
            return self.battle_targets.continue_after_raid
        if isinstance(action, AcceptSocketInventoryFull):
            return self.socket_targets.accept_inventory_full
        if isinstance(action, RejectSocketInventoryFull):
            return self.socket_targets.reject_inventory_full
        if isinstance(action, ExitSocket):
            return self.socket_targets.exit_socket
        if isinstance(action, OpenSocketEnhanceAll):
            return self.socket_targets.open_enhance_all
        if isinstance(action, SelectSocketEnhanceGold):
            return self.socket_targets.enhance_gold
        if isinstance(action, AcknowledgeSocketNoMaterial):
            return self.socket_targets.acknowledge_no_material
        if isinstance(action, CloseSocketEnhanceAll):
            return self.socket_targets.close_enhance_all
        if isinstance(action, OpenSocketEquipmentHome):
            return self.socket_targets.open_equipment_home
        if isinstance(action, SelectSocketOpalSlot):
            return self.socket_targets.opal_slots[action.slot_index]
        if isinstance(action, OpenSocketSell):
            return self.socket_targets.open_sell
        if isinstance(action, SellSocketInBulk):
            return self.socket_targets.sell_bulk
        if isinstance(action, CancelSocketSell):
            return self.socket_targets.cancel_sell
        if isinstance(action, TapSocketEnhanceAnimation):
            return self.socket_targets.animation_safe_tap
        if isinstance(action, OpenEquipmentCombine):
            return self.equipment_targets.open_combine
        if isinstance(action, SelectCombineTransmute):
            return self.equipment_targets.select_transmute
        if isinstance(action, SelectCombineFuse):
            return self.equipment_targets.select_fuse
        if isinstance(action, OpenCombineAll):
            return self.equipment_targets.open_combine_all
        if isinstance(action, ConfirmCombineAll):
            return self.equipment_targets.confirm_combine_all
        if isinstance(action, OpenAwakenedTransmute):
            return self.equipment_targets.open_awakened_transmute
        if isinstance(action, OpenEtherealRandomPart):
            return self.equipment_targets.open_ethereal_random_part
        if isinstance(action, OpenEtherealMassCombine):
            return self.equipment_targets.open_ethereal_mass_combine
        if isinstance(action, ConfirmEtherealMassCombine):
            return self.equipment_targets.confirm_ethereal_mass_combine
        if isinstance(action, AcknowledgeEtherealNoMaterial):
            return self.equipment_targets.acknowledge_ethereal_no_material
        if isinstance(action, TapCombineAnimation):
            return self.equipment_targets.animation_tap
        if isinstance(action, ExitCombine):
            return self.equipment_targets.exit_combine
        if isinstance(action, DismissWorldBossBagFull):
            return self.battle_targets.dismiss_world_boss_bag_full
        raise ValueError("unsupported semantic action")

    def _execute_swipe(
        self,
        action: Swipe,
        geometry: FrameGeometry,
    ) -> SwipeExecution:
        swipe = getattr(self.adb, "swipe", None)
        if not callable(swipe):
            raise ValueError("adb must provide swipe(x1, y1, x2, y2, duration_ms)")
        start = action.start
        end = action.end
        pixel_start = relative_point_to_pixel(start, geometry.width, geometry.height)
        pixel_end = relative_point_to_pixel(end, geometry.width, geometry.height)
        duration = action.duration_ms
        swipe(*pixel_start, *pixel_end, duration)
        return SwipeExecution(
            action=action,
            normalized_start=start,
            normalized_end=end,
            pixel_start=pixel_start,
            pixel_end=pixel_end,
            duration_ms=duration,
        )


__all__ = (
    "ActionExecution",
    "ActionExecutor",
    "BlackMarketActionTargets",
    "BattleActionTargets",
    "DEFAULT_BATTLE_ACTION_TARGETS",
    "DEFAULT_BLACK_MARKET_ACTION_TARGETS",
    "DEFAULT_DAILY_QUESTS_ACTION_TARGETS",
    "DEFAULT_EQUIPMENT_ACTION_TARGETS",
    "DEFAULT_FRIENDS_ACTION_TARGETS",
    "DEFAULT_GUILD_ACTION_TARGETS",
    "DEFAULT_MAILBOX_ACTION_TARGETS",
    "DEFAULT_PET_ACTION_TARGETS",
    "DEFAULT_ROTATION_ACTION_TARGETS",
    "DEFAULT_SOCKET_ACTION_TARGETS",
    "FrameGeometry",
    "FriendsActionTargets",
    "GuildActionTargets",
    "DailyQuestsActionTargets",
    "EquipmentActionTargets",
    "RotationActionTargets",
    "MailboxActionTargets",
    "PetActionTargets",
    "SocketActionTargets",
    "SwipeExecution",
)
