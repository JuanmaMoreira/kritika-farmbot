"""Shared Tk/ttk palette, scrollable settings and application-owned dialogs."""
import tkinter as tk
from tkinter import ttk, simpledialog


PALETTES = {
    "Light": dict(background="#edf0f4", surface="#fafbfc", surface_alt="#e0e5ec",
                  foreground="#202938", muted="#596678", accent="#255da1",
                  selection="#255da1", selected_text="#ffffff", border="#aab4c2"),
    "Dark": dict(background="#1c222b", surface="#252d39", surface_alt="#323e4e",
                 foreground="#e4eaf2", muted="#a1adbd", accent="#84b8f5",
                 selection="#345d8c", selected_text="#f2f6fc", border="#536174"),
}


class GuiTheme:
    def __init__(self, root):
        self.root = root
        self.style = ttk.Style(root)
        # Native Windows themes ignore several color options. Clam supports both palettes.
        self.style.theme_use("clam")
        self.appearance = "Light"

    @property
    def tokens(self):
        return PALETTES[self.appearance]

    def apply(self, appearance):
        self.appearance = appearance
        p, s = self.tokens, self.style
        s.configure(".", background=p['surface'], foreground=p['foreground'],
                    bordercolor=p['border'], lightcolor=p['surface_alt'], darkcolor=p['border'],
                    troughcolor=p['background'], selectbackground=p['selection'],
                    selectforeground=p['selected_text'], fieldbackground=p['surface'])
        s.map(".", foreground=[('disabled', p['muted'])],
              background=[('disabled', p['background'])])
        s.configure("TFrame", background=p['background'])
        s.configure("TLabel", background=p['background'])
        s.configure("Muted.TLabel", foreground=p['muted'])
        s.configure("TLabelframe", background=p['background'])
        s.configure("TLabelframe.Label", background=p['background'])
        for name in ('TButton', 'TCheckbutton', 'TRadiobutton'):
            s.configure(name, padding=5, focuscolor=p['accent'])
            s.map(name, background=[('active', p['surface_alt']), ('pressed', p['selection'])])
        for name in ('TCheckbutton', 'TRadiobutton'):
            s.configure(name, indicatorbackground=p['surface_alt'], indicatorforeground=p['foreground'])
            s.map(name, indicatorbackground=[('disabled', p['background']), ('selected', p['selection'])])
        for name in ('TEntry', 'TCombobox', 'TSpinbox'):
            s.configure(name, fieldbackground=p['surface'], insertcolor=p['foreground'],
                        arrowcolor=p['foreground'])
            s.map(name, fieldbackground=[('disabled', p['background']), ('readonly', p['surface'])],
                  foreground=[('disabled', p['muted']), ('readonly', p['foreground'])],
                  selectbackground=[('focus', p['selection'])],
                  selectforeground=[('focus', p['selected_text'])])
        s.configure("TNotebook", background=p['background'], tabmargins=(0, 3, 0, 0))
        s.configure("TNotebook.Tab", padding=(12, 6))
        s.map("TNotebook.Tab", background=[('selected', p['surface_alt']), ('active', p['surface_alt'])])
        s.configure("Treeview", background=p['surface'], fieldbackground=p['surface'],
                    rowheight=25, foreground=p['foreground'])
        s.map("Treeview", background=[('selected', p['selection'])],
              foreground=[('selected', p['selected_text'])])
        s.configure("Treeview.Heading", background=p['surface_alt'], foreground=p['foreground'], padding=5)
        s.map("Treeview.Heading", background=[('active', p['selection'])],
              foreground=[('active', p['selected_text'])])
        for name in ('Vertical.TScrollbar', 'Horizontal.TScrollbar'):
            s.configure(name, background=p['surface_alt'], arrowcolor=p['foreground'])
            s.map(name, background=[('active', p['border'])])
        s.configure("TProgressbar", background=p['accent'])
        for option, value in (('*TCombobox*Listbox.background', p['surface']),
                              ('*TCombobox*Listbox.foreground', p['foreground']),
                              ('*TCombobox*Listbox.selectBackground', p['selection']),
                              ('*TCombobox*Listbox.selectForeground', p['selected_text'])):
            self.root.option_add(option, value)
        self.style_widgets(self.root)

    def style_widgets(self, widget):
        p = self.tokens
        if isinstance(widget, (tk.Tk, tk.Toplevel, tk.Frame, tk.LabelFrame, tk.Canvas)) and not isinstance(widget, ttk.Widget):
            widget.configure(background=p['background'])
        if isinstance(widget, (tk.Listbox, tk.Text, tk.Entry)) and not isinstance(widget, ttk.Widget):
            widget.configure(background=p['surface'], foreground=p['foreground'],
                             selectbackground=p['selection'], selectforeground=p['selected_text'],
                             highlightbackground=p['border'], highlightcolor=p['accent'])
            if isinstance(widget, (tk.Text, tk.Entry)):
                widget.configure(insertbackground=p['foreground'])
            if isinstance(widget, tk.Listbox):
                widget.configure(disabledforeground=p['muted'])
        if isinstance(widget, tk.Scrollbar) and not isinstance(widget, ttk.Widget):
            widget.configure(background=p['surface_alt'], troughcolor=p['background'],
                             activebackground=p['border'])
        # Combobox dropdowns already created by Tk also need a dynamic update.
        if isinstance(widget, ttk.Combobox):
            popdown = self.root.tk.call('ttk::combobox::PopdownWindow', str(widget))
            self.root.tk.call(popdown + '.f.l', 'configure', '-background', p['surface'],
                              '-foreground', p['foreground'], '-selectbackground', p['selection'],
                              '-selectforeground', p['selected_text'])
        for child in widget.winfo_children():
            self.style_widgets(child)


class ScrollableSettings(ttk.Frame):
    """A bounded viewport; grows vertically through a real scrollbar and wheel."""
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, width=300, height=150, takefocus=True)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        bar.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=bar.set)
        self.content = ttk.Frame(self.canvas, padding=12)
        self.content.columnconfigure(0, weight=1)
        self.window = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.content.bind('<Configure>', self._resize_content)
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        # A local bindtag catches wheel events over children without hijacking other panels.
        self.wheel_tag = 'SettingsWheel' + str(self)
        self.bind_class(self.wheel_tag, '<MouseWheel>', self._wheel)
        self.canvas.bind('<Next>', lambda _: self.canvas.yview_scroll(1, 'pages'))
        self.canvas.bind('<Prior>', lambda _: self.canvas.yview_scroll(-1, 'pages'))

    def _resize_content(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        width = max(100, event.width - 24)
        for child in self.content.winfo_children():
            if isinstance(child, ttk.Label) and child.cget('wraplength') and child.winfo_pixels(child.cget('wraplength')) > 0:
                if child.winfo_pixels(child.cget('wraplength')) != width:
                    child.configure(wraplength=width)

    def bind_content(self):
        def visit(widget):
            if self.wheel_tag not in widget.bindtags():
                widget.bindtags((self.wheel_tag,) + widget.bindtags())
            for child in widget.winfo_children():
                visit(child)
        visit(self)

    def _wheel(self, event):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), 'units')
            return 'break'

    def reset(self):
        self.canvas.yview_moveto(0)


class AppDialog(simpledialog.Dialog):
    def __init__(self, parent, theme, title, prompt, *, initialvalue=None, choices=('OK',)):
        self.theme, self.prompt = theme, prompt
        self.initialvalue, self.choices = initialvalue, choices
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text=self.prompt, wraplength=420, padding=12).pack(fill='x')
        if self.initialvalue is not None:
            self.entry = ttk.Entry(master, width=42)
            self.entry.insert(0, self.initialvalue)
            self.entry.pack(fill='x', padx=12, pady=6)
            return self.entry

    def buttonbox(self):
        box = ttk.Frame(self, padding=12)
        box.pack(fill='x')
        for label in self.choices:
            ttk.Button(box, text=label, command=lambda value=label: self._choose(value)).pack(side='left', padx=4)
        self.bind('<Escape>', self.cancel)
        self.bind('<Return>', lambda _: self._choose(self.choices[0]))
        self.theme.style_widgets(self)

    def _choose(self, choice):
        if choice == 'Cancel':
            self.cancel()
            return
        self.result = self.entry.get() if self.initialvalue is not None else choice
        self.cancel()
