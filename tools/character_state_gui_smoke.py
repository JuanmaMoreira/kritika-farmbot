"""Construct and reopen the real Tk Character State view without device access."""
import json
import tkinter as tk
from pathlib import Path
from tools.gui import KritikaFarmBotGui

def main():
    views=[]
    for _ in range(2):
        root=tk.Tk()
        root.withdraw()
        app=KritikaFarmBotGui(root)
        root.update_idletasks()
        rows={cid:app.character_table.item(cid,'values') for cid in app.character_table.get_children()}
        views.append(rows)
        app.character_store.close()
        root.destroy()
    assert len(views[0])==len(views[1])==28
    assert views[0]==views[1]
    payload=dict(rows=28,reopen_equal=True,views=views)
    Path('artifacts/character_state_tk_reopen.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Tk Character State: 28 rows / reopen identical')

if __name__=='__main__': main()
