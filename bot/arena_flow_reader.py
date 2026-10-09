"""Focal preparation/navigation, sharing Phase A numeric and terminal reader."""
import json
from pathlib import Path
import cv2
import numpy as np
import re
import hashlib
from bot.arena_semantics import ArenaBalances, ArenaSingleExecution
from bot.arena_reader import ArenaResultReader, ArenaVisuals, crop
from bot.arena_semantics import ArenaEconomyFacts

ECONOMY_ROIS = ((.624,.041,.667,.086), (.573,.237,.603,.289),
                (.679,.237,.710,.289), (.786,.237,.818,.289))


class ArenaFlowVisuals(ArenaVisuals):
    def __init__(self, *, asset_root=None):
        super().__init__(asset_root=asset_root)
        root = Path(asset_root or Path(__file__).resolve().parents[1])
        manifest = root/'datasets/arena_b1_assets_manifest.json'
        b2 = root/'datasets/arena_b2_assets_manifest.json'
        specs=(json.loads(manifest.read_text(encoding='utf8'))['assets']
               + json.loads(b2.read_text(encoding='utf8'))['assets'])
        for spec in specs:
            template = cv2.imread(str(root/spec['path']))
            if template is None:
                raise FileNotFoundError(spec['path'])
            self._specs[spec['id']] = spec
            self._templates[spec['id']] = template
        self.asset_paths += tuple(root/spec['path'] for spec in specs)+(manifest,b2)

    def score(self, frame, name):
        shape = self._specs[name].get('reference_shape')
        if shape is not None and tuple(frame.shape[:2]) != tuple(shape):
            # Resize the whole native image before cropping so integer ROI
            # rounding shares the template's sampling phase. B1 is unchanged.
            frame = cv2.resize(frame, (shape[1], shape[0]), interpolation=cv2.INTER_AREA)
        return super().score(frame, name)

    def clear(self, frame, name):
        """NCC alone can match controls dimmed behind an unknown modal."""
        if not self.has(frame, name):
            return False
        observed = crop(frame, self._specs[name]['roi'])
        reference = self._templates[name]
        return (np.mean(cv2.cvtColor(observed,cv2.COLOR_BGR2HSV)[:,:,2])
                >= .82*np.mean(cv2.cvtColor(reference,cv2.COLOR_BGR2HSV)[:,:,2]))

    def clean_challenge(self, frame):
        return (self.challenge(frame) and (self.clear(frame,'challenge_controls') or self.clear(frame,'challenge_controls_native')) and self.clear(frame,'challenge_vs')
                and not (self.insufficient(frame) or self.config(frame) or self.ranking(frame) or self.terminal(frame) or self.quick_menu(frame)))

    def quick_menu(self, frame):
        return self.clear(frame,'flow_quick_menu_arena')

    def single_result(self, frame):
        return (all(self.clear(frame,n) for n in ('single_win_title','single_stats_labels','single_reward_label'))
                and (self.clear(frame,'single_tap_screen') or self.clear(frame,'single_tap_screen_stream')))

    def single_active(self, frame):
        return self.has(frame,'battle_vs') and self.clear(frame,'single_battle_pause')

    def back_visible(self, frame):
        return ((self.clear(frame,'flow_challenge_back_button') or self.clear(frame,'flow_challenge_back_native')) if self.clean_challenge(frame)
                else self.clear(frame,'flow_back_button') or self.clear(frame,'flow_back_native'))

    def challenge(self, frame):
        return (super().challenge(frame)
                or (self.clear(frame,'challenge_controls_native') and self.clear(frame,'challenge_vs')))

    def toggle(self, frame, prefix):
        value = super().toggle(frame, prefix)
        if prefix=='x8' and value is None and self.clear(frame,'x8_on_native'):
            return True
        return value

    def selection(self, frame):
        return all(self.clear(frame,'select_'+name) for name in ('easy','normal','hard'))

    def config(self, frame):
        return super().config(frame) and self.clear(frame,'config_start') and not self.loading(frame)

    def terminal(self, frame):
        return super().terminal(frame) and self.clear(frame,'result_ok') and self.clear(frame,'badge_label')

    def insufficient(self, frame):
        return self.clear(frame,'insufficient')

    def ranking(self, frame):
        return super().ranking(frame) and self.clear(frame,'ranking') and self.clear(frame,'ranking_arena')

    def upon_defeat(self, frame):
        if not self.config(frame):
            return None
        matched=(self.has(frame,'upon_defeat_off') or
                 ('flow_upon_defeat_off' in self._specs and self.has(frame,'flow_upon_defeat_off')))
        # Explicit empty interior supplements the positive border template. A
        # filled check or an unknown crop must not pass as the acquired OFF box.
        inside=crop(frame,(.655,.755,.668,.782))
        empty=np.percentile(cv2.cvtColor(inside,cv2.COLOR_BGR2HSV)[:,:,2],99)<80
        return False if matched and empty else None

    def lobby(self, frame):
        return self.clear(frame,'flow_lobby_battle')

    def select_mode(self, frame):
        return ((self.clear(frame,'flow_select_title') and self.clear(frame,'flow_arena_card'))
                or (self.clear(frame,'flow_select_title_native') and self.clear(frame,'flow_arena_card_native')))

    def loading(self, frame):
        return self.has(frame,'flow_loading')


class ArenaFlowReader(ArenaResultReader):
    def __init__(self, engine, **kwargs):
        if 'visuals' not in kwargs:
            kwargs['visuals']=ArenaFlowVisuals()
        # Live native acquisition measured 2.407s before warm focal OCR. Keep
        # the original acquisition timestamp; allow a bounded four-second age.
        kwargs.setdefault('max_age',4.)
        super().__init__(engine, **kwargs)

    def prewarm(self, snapshot):
        # Lazy backend initialization outside preparation and terminal deadlines.
        self.ocr_calls += 1
        self.engine.recognize(cv2.resize(crop(snapshot.image,ECONOMY_ROIS[0]),None,fx=3,fy=3))

    def single_terminal(self, snapshot, execution, *, run_id, source_id):
        return (isinstance(execution,ArenaSingleExecution) and execution.start_verified is True
                and execution.run_id==run_id and execution.source_id==source_id
                and snapshot.sequence>execution.after_sequence and snapshot.timestamp>execution.started_at
                and 0<=self.clock()-snapshot.timestamp<=self.max_age
                and self.visuals.single_result(snapshot.image))

    def balances(self, snapshot, *, cancel_requested=lambda:False):
        image=snapshot.image.copy()
        if (cancel_requested() or not 0<=self.clock()-snapshot.timestamp<=self.max_age
                or not (self.visuals.clean_challenge(image) or self.visuals.selection(image))
                or self.visuals.quick_menu(image) or self.visuals.ranking(image)):
            return None
        values=[self._integer(image,roi,cancel_requested)[0] for roi in
                (ECONOMY_ROIS[0],(.355,.044,.445,.087),(.502,.044,.565,.087))]
        if (any(v is None for v in values) or cancel_requested()
                or not 0<=self.clock()-snapshot.timestamp<=self.max_age):
            return None
        return ArenaBalances(*values,snapshot.sequence,snapshot.timestamp,hashlib.sha256(image.tobytes()).hexdigest())

    def economy(self, snapshot, *, cancel_requested=lambda:False):
        """Flow supplies a native refresh; never reconstruct a damaged stream HUD."""
        image=snapshot.image.copy()
        if (cancel_requested() or not 0 <= self.clock()-snapshot.timestamp <= self.max_age
                or not self.visuals.clean_challenge(image)):
            return None
        prep=self.visuals.preparation(image)
        if prep.difficulty is None or prep.x8 is not True or any(v is None for v in prep.buffs):
            return None
        values=[self._integer(image,ECONOMY_ROIS[0],cancel_requested)[0]]
        # USER_GT: buffs 1/2 need selection/effect only, never stock OCR.
        # Only premium-sensitive Double Points retains ticket coverage authority.
        values.extend((None, None, self._stock_integer(image,ECONOMY_ROIS[3],cancel_requested)))
        if (values[0] is None or cancel_requested()
                or not 0 <= self.clock()-snapshot.timestamp <= self.max_age):
            return None
        return ArenaEconomyFacts(values[0],tuple(values[1:]),prep,snapshot.sequence,snapshot.timestamp)

    def _stock_integer(self, image, roi, cancel_requested):
        value = self._integer(image, roi, cancel_requested)[0]
        if value is not None or cancel_requested():
            return value
        # Native 999 touches the stock box border; grayscale recognition lost
        # confidence despite intact glyphs. Same-frame black margin restores
        # segmentation. Both color/grayscale must still agree at >=.95.
        # Confined to free buff stocks, never Badge balances or batch results.
        region = crop(image, roi)
        padding = max(1, round(region.shape[0] * .08))
        padded = cv2.copyMakeBorder(region, padding, padding, padding, padding, cv2.BORDER_CONSTANT)
        return self._integer(padded, (0, 0, 1, 1), cancel_requested)[0]

    def _reserved_deficit(self, image, roi, cancel_requested):
        """Signed red reservation display for mandatory Gold buffs only.

        It is a displayed deficit, never free inventory or purchase authority.
        Two independent red isolations preserve the minus glyph that grayscale
        drops on the acquired native -2. Badge/result integer readers stay strict.
        """
        region=crop(image,roi)
        hsv=cv2.cvtColor(region,cv2.COLOR_BGR2HSV)
        hue=(cv2.inRange(hsv,(0,150,80),(10,255,255))
             | cv2.inRange(hsv,(170,150,80),(180,255,255)))
        b,g,r=(region[:,:,i].astype(int) for i in (0,1,2))
        channels=((r>100)&(r-g>60)&(r-b>60)).astype(np.uint8)*255
        values=[]
        for mask in (hue,channels):
            if cancel_requested(): return None
            self.ocr_calls+=1
            read=self.engine.recognize(cv2.resize(255-mask,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC))
            if (read.confidence<.95 or dict(read.metadata).get('line_count',1)!=1
                    or not re.fullmatch(r'-[1-8]',read.text.strip())):
                return None
            values.append(int(read.text.strip()))
        return values[0] if values[0]==values[1] else None
