"""Folio Chord's look (C3-08): the classic iTunes window — brushed-grey top bar, the status
display in the middle, the blue-grey source list, striped song lists — in a light and a dark
version. Every colour is set here so the desktop theme never shows through (X2-01)."""

LIGHT = dict(
    accent="#3d6aa8", accent_dark="#2c5189", accent_fg="#ffffff",
    bg="#e8e8e8", fg="#1e1e1e", dim="#5f5f5f", line="#b5b5b5",
    top1="#e4e4e4", top2="#b9b9b9", top_fg="#262626",
    lcd1="#f3f4ea", lcd2="#dfe3d0", lcd_fg="#1e2316", lcd_dim="#525a44", lcd_line="#8f9a7c",
    lcd_trough="#c3c9b1", lcd_fill="#59634a",
    src="#dbe1ea", src_fg="#1e1e1e", src_head="#6a7280", src_sel1="#5d8ad2", src_sel2="#3d6aa8",
    list="#ffffff", stripe="#f0f4fa", list_fg="#1e1e1e", sel="#3d6aa8", sel_fg="#ffffff",
    sel_dim="#c9d6ea", head1="#f7f7f7", head2="#e3e3e3", head_fg="#262626",
    bottom1="#dcdcdc", bottom2="#bdbdbd", btn1="#fbfbfb", btn2="#dadada", btn_fg="#262626",
    btn_line="#9a9a9a", hover="#e9eef7", entry="#ffffff", entry_fg="#1e1e1e",
    menu="#f7f7f7", menu_fg="#1e1e1e", menu_hover="#3d6aa8", menu_hover_fg="#ffffff",
    browse="#ffffff", grid="#f5f5f5", tip="#fffbe6", tip_fg="#1e1e1e", scroll="#9c9c9c",
    star="#4a4a4a", star_off="#c4c4c4", badge="#7c8ba1", badge_fg="#ffffff", vis="#000000",
)
DARK = dict(
    accent="#5b8fd9", accent_dark="#3f72bd", accent_fg="#ffffff",
    bg="#2a2a2a", fg="#ececec", dim="#a6a6a6", line="#474747",
    top1="#4a4a4a", top2="#2e2e2e", top_fg="#ececec",
    lcd1="#20251c", lcd2="#171b13", lcd_fg="#e3edd2", lcd_dim="#a9b694", lcd_line="#4c5641",
    lcd_trough="#3a4232", lcd_fill="#c9d6b3",
    src="#262b33", src_fg="#e6e6e6", src_head="#9aa4b4", src_sel1="#4f7fc8", src_sel2="#33609f",
    list="#1f1f1f", stripe="#262a30", list_fg="#ececec", sel="#3f72bd", sel_fg="#ffffff",
    sel_dim="#34465f", head1="#3a3a3a", head2="#2f2f2f", head_fg="#ececec",
    bottom1="#3a3a3a", bottom2="#2a2a2a", btn1="#4b4b4b", btn2="#363636", btn_fg="#ececec",
    btn_line="#1c1c1c", hover="#323a46", entry="#1b1b1b", entry_fg="#ececec",
    menu="#2f2f2f", menu_fg="#ececec", menu_hover="#3f72bd", menu_hover_fg="#ffffff",
    browse="#1f1f1f", grid="#232323", tip="#3a3a32", tip_fg="#f0f0e6", scroll="#6a6a6a",
    star="#e0e0e0", star_off="#5a5a5a", badge="#5d6b80", badge_fg="#ffffff", vis="#000000",
)

FONT = '"Lucida Grande", "Segoe UI", "Noto Sans", "Open Sans", "Ubuntu", sans-serif'

CSS = """
.chord-own, .chord-own.background, .chord-dialog, .chord-dialog.background, .chord-dialog .dialog-vbox,
.chord-dialog notebook stack, .chord-dialog viewport, .chord-dialog box.chord-page {
  background-color: %(bg)s; background-image: none; color: %(fg)s; }
.chord-own, .chord-dialog, .chord-own menu, menubar.chord-menubar, tooltip, popover.chord-pop {
  font-family: %(font)s; font-size: 9pt; }
.chord-own label, .chord-dialog label { color: %(fg)s; }
.chord-own .dim-label, .chord-dialog .dim-label, .chord-dim { color: %(dim)s; }
.chord-own label:disabled, .chord-dialog label:disabled { color: %(dim)s; }
.chord-own separator, .chord-dialog separator { background-color: %(line)s; }

/* menu bar and menus */
menubar.chord-menubar { background-color: %(top1)s; background-image: none; border-bottom: 1px solid %(line)s;
  padding: 0; box-shadow: none; }
menubar.chord-menubar > menuitem { padding: 3px 9px; color: %(top_fg)s; }
menubar.chord-menubar > menuitem label { color: %(top_fg)s; }
menubar.chord-menubar > menuitem:hover { background-color: %(menu_hover)s; }
menubar.chord-menubar > menuitem:hover label { color: %(menu_hover_fg)s; }
.chord-own menu, menu.chord-menu, .chord-own .menu, .chord-own .context-menu, window.popup menu {
  background-color: %(menu)s; background-image: none; color: %(menu_fg)s; border: 1px solid %(line)s; padding: 3px 0; }
menu.chord-menu menuitem, .chord-own menu menuitem { padding: 4px 18px 4px 10px; color: %(menu_fg)s; }
menu.chord-menu menuitem label, .chord-own menu menuitem label, menu.chord-menu accelerator, .chord-own menu accelerator { color: %(menu_fg)s; }
menu.chord-menu accelerator, .chord-own menu accelerator { color: %(dim)s; }
menu.chord-menu menuitem:hover, .chord-own menu menuitem:hover { background-color: %(menu_hover)s; }
menu.chord-menu menuitem:hover label, .chord-own menu menuitem:hover label, menu.chord-menu menuitem:hover accelerator { color: %(menu_hover_fg)s; }
menu.chord-menu menuitem:disabled label, .chord-own menu menuitem:disabled label { color: %(dim)s; }
menu.chord-menu separator, .chord-own menu separator { background-color: %(line)s; margin: 3px 0; min-height: 1px; }
menu.chord-menu check, menu.chord-menu radio, .chord-own menu check, .chord-own menu radio {
  background-color: transparent; background-image: none; border: none; color: %(menu_fg)s; }
menu.chord-menu menuitem:hover check, menu.chord-menu menuitem:hover radio { color: %(menu_hover_fg)s; }
menu.chord-menu arrow { color: %(menu_fg)s; }

/* the top bar: transport, volume, status display, view buttons, search */
.chord-topbar { background-image: linear-gradient(to bottom, %(top1)s, %(top2)s); border-bottom: 1px solid %(line)s;
  padding: 6px 10px; }
.chord-topbar label { color: %(top_fg)s; }
button.chord-round { border-radius: 99px; min-width: 30px; min-height: 30px; padding: 2px;
  background-image: linear-gradient(to bottom, %(btn1)s, %(btn2)s); background-color: %(btn2)s; color: %(btn_fg)s;
  border: 1px solid %(btn_line)s; box-shadow: none; text-shadow: none; }
button.chord-round.big { min-width: 38px; min-height: 38px; }
button.chord-round:hover { background-image: linear-gradient(to bottom, %(btn1)s, %(btn1)s); }
button.chord-round:active { background-image: linear-gradient(to bottom, %(btn2)s, %(btn1)s); }
button.chord-round image, button.chord-flat image, button.chord-seg image { color: %(btn_fg)s; }
button.chord-seg { border-radius: 3px; padding: 2px 6px; min-height: 22px; min-width: 22px;
  background-image: linear-gradient(to bottom, %(btn1)s, %(btn2)s); background-color: %(btn2)s; color: %(btn_fg)s;
  border: 1px solid %(btn_line)s; box-shadow: none; text-shadow: none; }
button.chord-seg:checked, button.chord-seg.on { background-image: linear-gradient(to bottom, %(btn2)s, %(btn1)s);
  box-shadow: inset 0 1px 3px alpha(black, 0.35); }
button.chord-seg:checked image, button.chord-seg.on image { color: %(accent)s; }
button.chord-seg label { color: %(btn_fg)s; }
button.chord-flat { background: transparent; border: none; box-shadow: none; padding: 2px 4px; min-height: 20px; min-width: 20px; color: %(fg)s; }
button.chord-flat:hover { background-color: alpha(%(fg)s, 0.10); }
button.chord-flat label { color: %(fg)s; }
.chord-topbar scale trough, .chord-own scale trough { background-color: %(btn2)s; background-image: none; border: 1px solid %(btn_line)s;
  min-height: 4px; border-radius: 3px; }
.chord-topbar scale highlight, .chord-own scale highlight { background-color: %(accent)s; background-image: none; border: none; }
.chord-own scale slider { background-image: linear-gradient(to bottom, %(btn1)s, %(btn2)s); background-color: %(btn1)s;
  border: 1px solid %(btn_line)s; min-width: 13px; min-height: 13px; border-radius: 99px; margin: -6px; box-shadow: none; }
.chord-own scale marks, .chord-own scale value, .chord-own scale label { color: %(dim)s; }
.chord-lcd { background-image: linear-gradient(to bottom, %(lcd1)s, %(lcd2)s); background-color: %(lcd2)s;
  border: 1px solid %(lcd_line)s; border-radius: 5px; padding: 3px 10px; min-height: 46px;
  box-shadow: inset 0 1px 2px alpha(black, 0.18); }
.chord-lcd label { color: %(lcd_fg)s; }
.chord-lcd label.chord-lcd-sub, .chord-lcd label.chord-lcd-time { color: %(lcd_dim)s; font-size: 8.5pt; }
.chord-lcd label.chord-lcd-title { font-weight: bold; }
.chord-lcd label.chord-lcd-logo { font-size: 14pt; font-weight: bold; color: %(lcd_dim)s; }
.chord-lcd scale trough { background-color: %(lcd_trough)s; border: 1px solid %(lcd_line)s; min-height: 5px; border-radius: 0; }
.chord-lcd scale highlight { background-color: %(lcd_fill)s; border: none; border-radius: 0; }
.chord-lcd scale slider { background-image: none; background-color: %(lcd_fg)s; border: none; min-width: 7px; min-height: 9px;
  border-radius: 1px; margin: -3px; }
.chord-lcd button.chord-flat image { color: %(lcd_fg)s; }
.chord-lcd button.chord-flat:hover { background-color: alpha(%(lcd_fg)s, 0.12); }

/* entries everywhere */
.chord-own entry, .chord-dialog entry, .chord-own spinbutton, .chord-dialog spinbutton, .chord-own textview, .chord-own textview text,
.chord-dialog textview, .chord-dialog textview text, .chord-dialog spinbutton entry {
  background-color: %(entry)s; background-image: none; color: %(entry_fg)s; caret-color: %(entry_fg)s;
  border: 1px solid %(btn_line)s; box-shadow: none; text-shadow: none; }
.chord-own entry.chord-search { border-radius: 99px; padding: 0 8px; min-height: 22px; }
.chord-own entry image, .chord-dialog entry image { color: %(dim)s; }
.chord-own entry selection, .chord-dialog entry selection, .chord-own textview text selection, .chord-dialog textview text selection {
  background-color: %(accent)s; color: %(accent_fg)s; }
.chord-own entry:disabled, .chord-dialog entry:disabled { color: %(dim)s; }
.chord-dialog spinbutton button, .chord-own spinbutton button { background-color: %(btn1)s; background-image: none; color: %(btn_fg)s;
  border: none; border-left: 1px solid %(btn_line)s; box-shadow: none; }

/* source list */
.chord-source, .chord-source.view { background-color: %(src)s; color: %(src_fg)s; }
.chord-source.view:selected, .chord-source.view:selected:focus { background-image: linear-gradient(to bottom, %(src_sel1)s, %(src_sel2)s);
  background-color: %(src_sel2)s; color: %(sel_fg)s; }
.chord-art-pane { background-color: %(src)s; border-top: 1px solid %(line)s; }
.chord-art-pane label { color: %(src_head)s; }

/* song lists, browser, grids */
.chord-own treeview.view { background-color: %(list)s; color: %(list_fg)s; }
.chord-own treeview.view:selected, .chord-own treeview.view:selected:focus { background-color: %(sel)s; color: %(sel_fg)s; }
.chord-own treeview.view.chord-source:selected { background-color: %(src_sel2)s; }
.chord-own treeview.view header button { background-image: linear-gradient(to bottom, %(head1)s, %(head2)s);
  background-color: %(head2)s; color: %(head_fg)s; border: none; border-right: 1px solid %(line)s; border-bottom: 1px solid %(line)s;
  box-shadow: none; padding: 1px 6px; text-shadow: none; }
.chord-own treeview.view header button label { color: %(head_fg)s; }
.chord-own treeview.view header button arrow { color: %(head_fg)s; }
.chord-own treeview.view header button:hover { background-image: linear-gradient(to bottom, %(head1)s, %(head1)s); }
.chord-own treeview.view check, .chord-own treeview.view radio, .chord-own check, .chord-own radio, .chord-dialog check, .chord-dialog radio {
  background-color: %(entry)s; background-image: none; border: 1px solid %(btn_line)s; color: %(fg)s; border-radius: 2px; }
.chord-own treeview.view check:checked, .chord-own check:checked, .chord-dialog check:checked, .chord-own radio:checked, .chord-dialog radio:checked {
  background-color: %(accent)s; border-color: %(accent_dark)s; color: %(accent_fg)s; }
.chord-own checkbutton label, .chord-dialog checkbutton label, .chord-own radiobutton label, .chord-dialog radiobutton label { color: %(fg)s; }
.chord-own treeview.view.chord-browse:not(:selected) { background-color: %(browse)s; }
.chord-own iconview { background-color: %(grid)s; color: %(list_fg)s; }
.chord-own iconview:selected { background-color: %(sel)s; color: %(sel_fg)s; }
.chord-own .chord-browser { border-bottom: 1px solid %(line)s; }
.chord-own .chord-sectionbar { background-image: linear-gradient(to bottom, %(head1)s, %(head2)s); border-bottom: 1px solid %(line)s; padding: 3px 8px; }
.chord-own .chord-sectionbar label { color: %(head_fg)s; }
.chord-own .chord-heading { font-size: 13pt; font-weight: bold; color: %(fg)s; }
.chord-own .chord-card { background-color: %(list)s; border: 1px solid %(line)s; border-radius: 4px; padding: 6px; }
.chord-own .chord-card label { color: %(list_fg)s; }
.chord-own .chord-badge { background-color: %(badge)s; color: %(badge_fg)s; border-radius: 99px; padding: 0 6px; font-size: 8pt; font-weight: bold; }
.chord-own .chord-notes, .chord-own .chord-notes text { background-color: %(list)s; color: %(list_fg)s; }
.chord-own list, .chord-own list row, .chord-dialog list, .chord-dialog list row { background-color: %(list)s; color: %(list_fg)s; }
.chord-own list row:selected, .chord-dialog list row:selected { background-color: %(sel)s; color: %(sel_fg)s; }
.chord-own list row:selected label, .chord-dialog list row:selected label { color: %(sel_fg)s; }
.chord-own list row:hover:not(:selected) { background-color: %(hover)s; }
.chord-own flowbox, .chord-own flowboxchild { background-color: transparent; }
.chord-own flowboxchild:selected { background-color: %(sel_dim)s; }
.chord-own scrolledwindow, .chord-own viewport { background-color: transparent; border-color: %(line)s; }
.chord-own scrollbar, .chord-dialog scrollbar { background-color: transparent; border-color: transparent; }
.chord-own scrollbar slider, .chord-dialog scrollbar slider { background-color: %(scroll)s; border: none; min-width: 7px; min-height: 7px; }
.chord-own paned > separator { background-color: %(line)s; background-image: none; min-width: 1px; min-height: 1px; }

/* bottom bar */
.chord-bottombar { background-image: linear-gradient(to bottom, %(bottom1)s, %(bottom2)s); border-top: 1px solid %(line)s; padding: 3px 8px; }
.chord-bottombar label { color: %(top_fg)s; }

/* buttons in dialogs and panes */
.chord-dialog button:not(.chord-default):not(.chord-flat):not(.chord-seg):not(.chord-round),
.chord-own button.chord-button {
  background-image: linear-gradient(to bottom, %(btn1)s, %(btn2)s); background-color: %(btn2)s; color: %(btn_fg)s;
  border: 1px solid %(btn_line)s; box-shadow: none; text-shadow: none; border-radius: 4px; padding: 2px 12px; min-height: 22px; }
.chord-dialog button:not(.chord-default):not(.chord-flat):not(.chord-seg):not(.chord-round) label, .chord-own button.chord-button label { color: %(btn_fg)s; }
.chord-dialog button image, .chord-own button.chord-button image { color: %(btn_fg)s; }
button.chord-default, .chord-dialog button.suggested-action { background-image: linear-gradient(to bottom, %(src_sel1)s, %(src_sel2)s);
  background-color: %(accent)s; color: %(accent_fg)s; border: 1px solid %(accent_dark)s; border-radius: 4px; padding: 2px 14px; box-shadow: none; text-shadow: none; }
button.chord-default label, .chord-dialog button.suggested-action label { color: %(accent_fg)s; }
.chord-dialog button:disabled label, .chord-own button:disabled label { color: %(dim)s; }
.chord-own combobox button, .chord-dialog combobox button { background-image: linear-gradient(to bottom, %(btn1)s, %(btn2)s);
  background-color: %(btn2)s; color: %(btn_fg)s; border: 1px solid %(btn_line)s; box-shadow: none; text-shadow: none; padding: 1px 8px; }
.chord-own combobox button cellview, .chord-dialog combobox button cellview, .chord-own combobox button label, .chord-dialog combobox button label { color: %(btn_fg)s; }
.chord-own combobox arrow, .chord-dialog combobox arrow { color: %(btn_fg)s; }
.chord-dialog notebook, .chord-dialog notebook header { background-color: %(bg)s; border-color: %(line)s; }
.chord-dialog notebook tab { background-color: transparent; padding: 4px 12px; }
.chord-dialog notebook tab label { color: %(fg)s; }
.chord-dialog notebook tab:checked { box-shadow: inset 0 -2px %(accent)s; }
.chord-dialog frame > border, .chord-own frame > border { border-color: %(line)s; }
.chord-dialog headerbar, .chord-dialog .titlebar { background-color: %(top1)s; background-image: none; color: %(top_fg)s; border-color: %(line)s; box-shadow: none; }
.chord-dialog headerbar label { color: %(top_fg)s; }
.chord-dialog .chord-art { background-color: %(list)s; border: 1px solid %(line)s; }
.chord-dialog .chord-eq-scale trough { background-color: %(btn2)s; border: 1px solid %(btn_line)s; min-width: 4px; }
.chord-dialog .chord-eq-scale highlight { background-color: %(accent)s; }
.chord-dialog scale slider { background-image: linear-gradient(to bottom, %(btn1)s, %(btn2)s); background-color: %(btn1)s;
  border: 1px solid %(btn_line)s; min-width: 13px; min-height: 13px; border-radius: 99px; margin: -6px; box-shadow: none; }
.chord-dialog scale marks, .chord-dialog scale value { color: %(dim)s; }
.chord-dialog scale trough { background-color: %(btn2)s; background-image: none; border: 1px solid %(btn_line)s; }
.chord-dialog scale highlight { background-color: %(accent)s; background-image: none; }

/* pop-ups and tooltips */
popover.chord-pop, popover.chord-pop.background { background-color: %(menu)s; background-image: none; color: %(menu_fg)s; border-color: %(line)s; }
popover.chord-pop > contents { background-color: %(menu)s; }
popover.chord-pop label { color: %(menu_fg)s; }
popover.chord-pop list, popover.chord-pop list row, popover.chord-pop treeview.view { background-color: %(menu)s; color: %(menu_fg)s; }
popover.chord-pop list row:selected { background-color: %(sel)s; }
popover.chord-pop button { background-image: none; background-color: transparent; color: %(menu_fg)s; border: 1px solid transparent; box-shadow: none; text-shadow: none; }
popover.chord-pop button label, popover.chord-pop button image { color: %(menu_fg)s; }
popover.chord-pop button:hover { background-color: %(hover)s; }
tooltip, tooltip.background { background-color: %(tip)s; color: %(tip_fg)s; border: 1px solid %(line)s; border-radius: 0; box-shadow: none; }
tooltip label { color: %(tip_fg)s; padding: 2px 3px; }
tooltip * { background-color: transparent; }

.chord-mini { background-image: linear-gradient(to bottom, %(top1)s, %(top2)s); }
.chord-mini label { color: %(top_fg)s; }
.chord-vis, .chord-vis.background { background-color: %(vis)s; }
.chord-vis label { color: #e8e8e8; }
.chord-banner { background-color: %(sel_dim)s; padding: 4px 10px; border-bottom: 1px solid %(line)s; }
.chord-banner label { color: %(fg)s; }
"""


def css(dark):
    p = dict(DARK if dark else LIGHT)
    p["font"] = FONT
    return CSS % p


def colours(dark):
    return DARK if dark else LIGHT
