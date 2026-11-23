import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const name = 'io.github.chandan_itian.VoiceFlowInput';
const path = '/io/github/chandan_itian/VoiceFlowInput';
const binding = 'voiceflow-control-super';

export default class VoiceFlowShortcut extends Extension {
    enable() {
        this.pill = new St.BoxLayout({reactive: false, visible: false,
            style: 'background-color: #080808; border: 1px solid #666; border-radius: 32px; padding: 9px 20px; spacing: 4px;'});
        this.bars = Array.from({length: 11}, () => {
            const bar = new St.Widget({width: 4, height: 4, y_align: Clutter.ActorAlign.CENTER,
                style: 'background-color: white; border-radius: 2px;'});
            this.pill.add_child(bar);
            return bar;
        });
        Main.layoutManager.addChrome(this.pill, {affectsInputRegion: false});
        this.subscription = Gio.DBus.session.signal_subscribe(name, name, 'Level', path, null,
            Gio.DBusSignalFlags.NONE, (_c, _s, _p, _i, _n, args) => {
                if (!this.timer) return;
                const [level] = args.deepUnpack();
                if (level < 0) { this.finish(); return; }
                this.history.unshift(Math.min(1, Math.sqrt(level) * 3));
                this.history.pop();
                this.bars.forEach((bar, i) => {
                    const d = Math.abs(i - 5);
                    bar.height = 4 + Math.round((1 - d / 7) * this.history[d] * 24);
                });
                const m = Main.layoutManager.focusMonitor ?? Main.layoutManager.primaryMonitor;
                this.pill.set_position(Math.round(m.x + (m.width - 126) / 2), m.y + m.height - 84);
                this.pill.height = 48;
                this.pill.show();
            });
        Main.wm.addKeybinding(binding, this.getSettings(), Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
            Shell.ActionMode.NORMAL, () => this.begin());
    }
    send(method, callback = null) {
        Gio.DBus.session.call(name, path, name, method, null, null, Gio.DBusCallFlags.NO_AUTO_START,
            2000, null, (bus, result) => {
                let ok = false;
                try { ok = bus.call_finish(result).deepUnpack()[0]; } catch (_) {}
                callback?.(ok);
            });
    }
    begin() {
        if (this.timer) return;
        this.history = Array(6).fill(0);
        const token = this.timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 20, () => {
            const mask = global.get_pointer()[2];
            if ((mask & Clutter.ModifierType.CONTROL_MASK) &&
                (mask & (Clutter.ModifierType.MOD4_MASK | Clutter.ModifierType.SUPER_MASK)))
                return GLib.SOURCE_CONTINUE;
            this.finish();
            return GLib.SOURCE_REMOVE;
        });
        this.send('Begin', ok => {
            if (!ok && this.timer === token) {
                this.finish();
                Main.notify('VoiceFlow', 'Select the VoiceFlow AI input source and focus an editable field.');
            }
        });
    }
    finish() {
        if (this.timer) {
            GLib.Source.remove(this.timer);
            this.timer = 0;
            this.send('End');
        }
        this.pill.hide();
    }
    disable() {
        Main.wm.removeKeybinding(binding);
        if (this.timer) { GLib.Source.remove(this.timer); this.timer = 0; this.send('Cancel'); }
        Gio.DBus.session.signal_unsubscribe(this.subscription);
        Main.layoutManager.removeChrome(this.pill);
        this.pill.destroy();
    }
}
