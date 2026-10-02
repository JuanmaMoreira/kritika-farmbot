"""Re-enter the selected character without executing a Rotation step."""
from bot.character_identity import LobbyNameRecognizer, KNOWN_LOBBY_NAME_OCR_VARIANTS
from bot.semantic_actions import OpenQuickMenu, OpenCharacterSelect, ConfirmCharacterSelection
from bot.catalog import SCREEN_CHARACTER_SELECT, MENU_QUICK
from bot.stages_runtime import lobby
from bot.event_log import record_best_effort

class SameCharacterReentry:
    def __init__(self, navigation, balances):
        self.nav = navigation
        self.balances = balances
        self.identity = LobbyNameRecognizer(balances.engine)

    def __call__(self):
        n = self.nav
        before = n.wait(lobby)
        identity = self.identity.recognize(before)
        if identity is None:
            raise ValueError('same-character identity unavailable; no selection input')
        n.act(OpenQuickMenu(), before)
        menu = n.wait(lambda s: set(s.state.overlays) == {MENU_QUICK})
        n.act(OpenCharacterSelect(), menu)
        selected = n.wait(lambda s: s.state.base_context == SCREEN_CHARACTER_SELECT and not s.state.overlays)
        text = self.balances.text(selected, (.49, .19, .620, .240)).strip()
        name = KNOWN_LOBBY_NAME_OCR_VARIANTS.get(text, text)
        if name != identity.personal_name:
            raise ValueError('same-character selection identity mismatch; no confirmation')
        n.act(ConfirmCharacterSelection(), selected)
        after = n.wait(lobby, timeout=12.)
        restored = self.identity.recognize(after)
        if restored is None or restored.personal_name != identity.personal_name:
            raise ValueError('same-character Lobby identity unverified')
        record_best_effort(n.events, 'character.same_character_reentered', personal_name=identity.personal_name)
        return after
