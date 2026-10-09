"""Promote small runtime templates from reviewed, local Manual Stages acquisition."""
from pathlib import Path
import json
import cv2
from bot.arena_reader import crop
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'artifacts/manual_stages'
OUT=ROOT/'assets/ui/landmarks/manual_stages'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    profile={}
    path=OUT/'profile.json'
    if path.exists():profile=json.loads(path.read_text())
    def add(name,source,roi):
        image=cv2.imread(str(RAW/source))
        if image is None:raise ValueError(source)
        cv2.imwrite(str(OUT/(name+'.png')),crop(image,roi))
        profile[name]=dict(source='artifacts/manual_stages/'+source,crop=roi,
            search=[roi[0]-.003,roi[1]-.006,roi[2]+.003,roi[3]+.006])
    add('chaos','chaos_base/after.png',(.472,.169,.532,.184))
    add('config6','chaos_config/after.png',(.255,.178,.472,.218))
    add('number6','chaos_config/after.png',(.196,.228,.218,.254))
    if (RAW/'bb_config/after.png').exists():
        add('config9','bb_config/after.png',(.255,.178,.507,.218))
        add('number9','bb_config/after.png',(.196,.228,.218,.254))
    add('x4_on','chaos_x4/after.png',(.786,.858,.812,.904))
    add('x4_off','chaos_base/after.png',(.786,.858,.812,.904))
    add('config_start','chaos_config/after.png',(.674,.875,.798,.945))
    add('penance_on','chaos_config/after.png',(.421,.829,.482,.945))
    if (RAW/'monk_chaos_hell/after.png').exists():
        add('penance_off','monk_chaos_hell/after.png',(.421,.829,.482,.945))
        add('hell_on','monk_chaos_hell/after.png',(.271,.829,.333,.945))
        add('hell_off','chaos_config/after.png',(.271,.829,.333,.945))
    for index in range(4):
        x=.496+index*.076
        roi=(x,.429,x+.029,.485)
        add(f'buff{index+1}_on','chaos_buffs/after.png',roi)
        add(f'buff{index+1}_off','chaos_config/after.png',roi)
    add('striker_start','chaos_striker/after.png',(.52,.843,.64,.916))
    add('stage6','chaos_base/after.png',(.750,.389,.772,.421))
    add('stage9','bb_base/after.png',(.537,.682,.560,.714))
    add('battle_pause','chaos_battle_guarded_02/after.png',(.933,.035,.948,.079))
    add('battle_auto_text','chaos_battle_guarded_02/after.png',(.860,.039,.895,.070))
    add('death_title','chaos_terminal/after.png',(.470,.257,.536,.296))
    add('death_abandon','chaos_terminal/after.png',(.375,.53,.482,.589))
    add('guide_title','chaos_abandon/after.png',(.492,.199,.598,.237))
    add('guide_close','chaos_abandon/after.png',(.75,.153,.782,.211))
    if (RAW/'bb_clear_acquire/after.png').exists():
        add('clear_time','bb_clear_acquire/after.png',(.281,.300,.419,.366))
        add('clear_home','bb_clear_acquire/after.png',(.199,.834,.323,.923))
    path.write_text(json.dumps(profile,indent=2)+'\n',encoding='utf8')
    # World Map's previous asset was the selected Abyssal tile. Ep.11 is
    # stable across selection, and keeps the dropdown above Normal's chrome.
    legacy=ROOT/'assets/ui/landmarks/stages'
    p=json.loads((legacy/'profile.json').read_text())
    roi=(.179,.265,.208,.296)
    image=cv2.imread(str(RAW/'map_01/after.png'))
    cv2.imwrite(str(legacy/'world_map_chrome.png'),crop(image,roi))
    p['world_map_chrome']=dict(source='artifacts/manual_stages/map_01/after.png',crop=roi,
        search=[.175,.26,.213,.302])
    (legacy/'profile.json').write_text(json.dumps(p,indent=2)+'\n',encoding='utf8')
if __name__=='__main__':main()
