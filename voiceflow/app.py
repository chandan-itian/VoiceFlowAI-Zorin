from collections import deque
import os
import sys
import tempfile
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

from . import cloud, system, __version__


def column(spacing=12):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)


def label(text):
    return Gtk.Label(label=text, xalign=0, wrap=True)


def button(title, callback):
    widget = Gtk.Button.new_with_label(title)
    widget.connect("clicked", callback)
    return widget


def combo(values, selected):
    widget = Gtk.ComboBoxText()
    for value in values:
        widget.append(value, value)
    widget.set_active_id(selected)
    return widget


def background(work, done):
    def run():
        try:
            result, failure = work(), None
        except Exception as exc:
            result, failure = None, str(exc)
        def deliver():
            done(result, failure)
            return False
        GLib.idle_add(deliver)
    threading.Thread(target=run, daemon=True).start()


def install_shortcuts():
    settings = Gio.Settings.new("org.gnome.desktop.input-sources")
    sources = settings.get_value("sources").unpack()
    source = ("ibus", "voiceflow-zorin")
    if source not in sources and not settings.set_value("sources", GLib.Variant("a(ss)", sources + [source])):
        raise RuntimeError("Enable VoiceFlow AI in Keyboard Settings → Input Sources.")
    Gio.Settings.sync()


def install_toggle():
    binding = "<Super><Shift>space"
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    if not Gio.SettingsSchemaSource.get_default().lookup(schema, True):
        raise RuntimeError("Use Keyboard Settings to bind Super + Shift + Space to voiceflow-zorin --toggle.")
    settings = Gio.Settings.new(schema)
    path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voiceflow-toggle/"
    item = Gio.Settings.new_with_path(schema + ".custom-keybinding", path)
    wm = Gio.Settings.new("org.gnome.desktop.wm.keybindings")
    previous = wm.get_strv("switch-input-source-backward")
    keep = [v for v in previous if Gtk.accelerator_parse(v) != Gtk.accelerator_parse(binding)]
    if previous != keep and not wm.set_strv("switch-input-source-backward", keep):
        raise RuntimeError("Keyboard Settings reserves this shortcut for the previous input source.")
    Gio.Settings.sync()
    for key, value in (("name", "VoiceFlow AI dictation"), ("command", "voiceflow-zorin --toggle"),
                       ("binding", binding)):
        if not item.set_string(key, value):
            raise RuntimeError("Keyboard shortcut settings are locked.")
    paths = list(settings.get_strv("custom-keybindings"))
    if path not in paths and not settings.set_strv("custom-keybindings", paths + [path]):
        raise RuntimeError("Unable to register the desktop shortcut.")
    Gio.Settings.sync()


class RecordingIndicator(Gtk.Window):
    def __init__(self):
        super().__init__(title="VoiceFlow recording")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_position(Gtk.WindowPosition.MOUSE)
        self.set_border_width(10)
        self.bars = deque("▁" * 14, maxlen=14)
        self.caption = Gtk.Label()
        self.add(self.caption)
        self.update_level(0)

    def update_level(self, level):
        self.bars.append("▁▂▃▄▅▆▇█"[min(7, int(level ** 0.5 * 18))])
        self.caption.set_markup('<span foreground="#35ae86">●</span>  <tt>' + "".join(self.bars) + "</tt>")


class Preferences(Gtk.Dialog):
    def __init__(self, parent, config):
        super().__init__(title=f"Settings · VoiceFlow {__version__}", transient_for=parent, modal=True)
        self.add_button("Close", Gtk.ResponseType.CANCEL)
        self.add_button("Save settings", Gtk.ResponseType.OK)
        self.set_default_size(560, 550)
        self.config = config.copy()
        self.stages = {}
        pages = Gtk.Notebook()
        self.get_content_area().add(pages)
        routing, accounts = column(), column()
        for page, name in ((routing, "Dictation"), (accounts, "Providers")):
            page.set_border_width(16)
            pages.append_page(page, label(name))
        self.url = Gtk.Entry(text=config["custom_url"], placeholder_text="https://server.example/v1")
        self.message = label("")
        for stage, title, index in (("speech", "Voice to text", 1), ("text", "Text refinement", 2)):
            routing.add(label(title))
            row = Gtk.Box(spacing=8)
            routing.add(row)
            providers = [p for p in cloud.PROVIDERS if p != "OpenRouter" or stage == "text"]
            prov = combo(providers, config[stage + "_provider"])
            model = Gtk.ComboBoxText.new_with_entry()
            row.add(prov)
            row.pack_start(model, True, True, 0)
            self.stages[stage] = prov, model

            def populate(widget, field=model, idx=index):
                field.remove_all()
                values = cloud.PROVIDERS[widget.get_active_id()][idx]
                for v in values:
                    field.append_text(v)
                field.get_child().set_text(values[0] if values else "")
            prov.connect("changed", populate)
            populate(prov)
            model.get_child().set_text(config[stage + "_model"])
            row.add(button("Fetch", lambda _, s=stage: self.fetch(s)))

        self.lang = combo(cloud.LANGUAGES, config["language"])
        routing.add(label("Output language"))
        routing.add(self.lang)
        self.toggles = {}
        for key, title in (("refine", "Refine the transcript"), ("auto_paste", "Paste into the original X11 window"),
                           ("fallback", "Try fallback models when a Groq model is unavailable or rate-limited")):
            switch = Gtk.CheckButton.new_with_label(title)
            switch.set_active(config[key])
            routing.add(switch)
            self.toggles[key] = switch
        self.fallbacks = Gtk.Entry(text=config["fallback_models"])
        routing.add(label("Fallback models, in order"))
        routing.add(self.fallbacks)
        self.prompt = Gtk.Entry(text=config["prompt"])
        routing.add(label("Additional formatting instructions"))
        routing.add(self.prompt)

        accounts.add(label("Custom OpenAI-compatible base URL"))
        accounts.add(self.url)
        self.who = combo(cloud.PROVIDERS, config["speech_provider"])
        accounts.add(label("API key storage"))
        accounts.add(self.who)
        self.secret = Gtk.Entry(visibility=False, placeholder_text="New API key")
        self.who.connect("changed", lambda *_: self.secret.set_text(""))
        accounts.add(self.secret)
        accounts.add(button("Save key to desktop keyring", self.save_key))
        accounts.add(label("For configured Groq models, Test connection sends a short built-in sample and uses API quota."))
        accounts.add(button("Test connection", self.test_connection))
        accounts.add(label("Global shortcuts"))
        accounts.add(label("Select the VoiceFlow AI input source, then hold Ctrl + Shift to speak. Release either key to insert."))
        accounts.add(button("Enable VoiceFlow AI input source", self.shortcuts))
        accounts.add(label("The toggle shortcut replaces GNOME’s previous input source shortcut. Super + Space still switches sources."))
        accounts.add(button("Enable Super + Shift + Space dictation", self.enable_toggle))
        self.get_content_area().pack_start(self.message, False, True, 8)
        self.show_all()

    def enable_toggle(self, _):
        try:
            install_toggle()
            self.message.set_text("Super + Shift + Space starts or finishes recording.")
        except Exception as exc:
            self.message.set_text(str(exc))

    def credentials_config(self):
        return self.config | {"custom_url": self.url.get_text().strip()}

    def save_key(self, _):
        provider, config, value = self.who.get_active_id(), self.credentials_config(), self.secret.get_text().strip()
        if not value:
            self.message.set_text("Enter a key first.")
            return
        def saved(_, err):
            if self.who.get_active_id() == provider and self.secret.get_text().strip() == value and not err:
                self.secret.set_text("")
            self.message.set_text(err or "API key saved.")
        background(lambda: system.credential(provider, config, value), saved)

    def test_connection(self, _):
        provider, config = self.who.get_active_id(), self.values(validate=False)
        entered = self.secret.get_text().strip()
        self.message.set_text(f"Checking {provider}…")
        background(lambda: cloud.check_connection(provider, config, entered or system.credential(provider, config)),
                   lambda result, err: self.message.set_text(err or result))

    def fetch(self, stage):
        prov, model = self.stages[stage]
        provider, config = prov.get_active_id(), self.credentials_config()
        self.message.set_text("Fetching models…")
        def done(values, err):
            if err:
                self.message.set_text(err)
                return
            if prov.get_active_id() != provider:
                return
            prev = model.get_child().get_text()
            if provider != "Custom":
                if stage == "speech" and provider != "Gemini":
                    values = [v for v in values if "whisper" in v or "transcribe" in v]
                elif stage == "text":
                    values = [v for v in values if not any(w in v for w in ("whisper", "transcribe", "embedding", "tts"))]
            model.remove_all()
            for v in values:
                model.append_text(v)
            model.get_child().set_text(prev)
            self.message.set_text("Choose a listed model or type a supported ID.")
        background(lambda: cloud.fetch_models(provider, config, system.credential(provider, config)), done)

    def shortcuts(self, _):
        try:
            install_shortcuts()
            self.message.set_text("Use Super + Space to select VoiceFlow AI. If missing, sign out and back in.")
        except Exception as exc:
            self.message.set_text(str(exc))

    def values(self, validate=True):
        result = self.credentials_config()
        result.update({key: widget.get_active() for key, widget in self.toggles.items()})
        for stage, (prov, model) in self.stages.items():
            result[stage + "_provider"] = prov.get_active_id()
            result[stage + "_model"] = model.get_child().get_text().strip()
            if validate and (stage == "speech" or result["refine"]):
                cloud.endpoint(prov.get_active_id(), result)
                if not result[stage + "_model"]:
                    raise ValueError("Enter a model ID for the selected provider.")
        return result | {"language": self.lang.get_active_id(), "prompt": self.prompt.get_text(),
                         "fallback_models": self.fallbacks.get_text()}


class VoiceFlow(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.chandan_itian.VoiceFlowAI",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        for flag in ("toggle", "cancel", "quit"):
            self.add_main_option(flag, 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, flag.capitalize(), None)
        self.window = None
        self.phase = "idle"
        self.proc = None
        self.temp = None
        self.dlg = None
        self.indicator = None
        self.target = None
        self.config = system.load()

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()

    def do_command_line(self, cmd):
        options = cmd.get_options_dict()
        self.build_window()
        if options.contains("quit"):
            if self.phase in ("processing", "stopping"):
                cmd.printerr("Dictation is finishing. Try again shortly.\n")
                return 1
            self.cancel()
            self.quit()
        elif options.contains("cancel"):
            self.cancel()
        elif options.contains("toggle"):
            self.toggle(global_key=True)
        else:
            self.window.present()
        return 0

    def build_window(self):
        if self.window:
            return
        self.window = Gtk.ApplicationWindow(application=self, title="VoiceFlow AI")
        self.window.set_default_size(560, 510)
        self.window.set_icon_name("voiceflow-zorin")
        self.window.connect("delete-event", lambda win, *_: (win.hide(), True)[1])
        self.window.connect("key-press-event", self.keypress)
        header = Gtk.HeaderBar(title="VoiceFlow AI", show_close_button=True)
        header.pack_end(button("Settings", self.preferences))
        self.window.set_titlebar(header)
        header.show_all()
        body = column(12)
        body.set_border_width(22)
        self.window.add(body)
        self.status = label("Ready to dictate")
        self.engine = label("")
        body.add(self.status)
        body.add(self.engine)
        actions = Gtk.Box(spacing=8)
        self.record_btn = button("Start dictation", lambda _: self.toggle())
        self.record_btn.get_style_context().add_class("suggested-action")
        self.cancel_btn = button("Cancel", lambda _: self.cancel())
        actions.add(self.record_btn)
        actions.add(self.cancel_btn)
        body.add(actions)
        tabs = Gtk.Notebook()
        self.views = {}
        for key, name in (("output", "Formatted text"), ("raw", "Original transcript")):
            view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, editable=False, left_margin=12, right_margin=12)
            scroll = Gtk.ScrolledWindow()
            scroll.add(view)
            tabs.append_page(scroll, label(name))
            self.views[key] = view
        body.pack_start(tabs, True, True, 0)
        footer = Gtk.Box(spacing=8)
        footer.add(button("Copy result", self.copy_result))
        footer.pack_end(button("Quit", self.quit_clicked), False, False, 0)
        body.add(footer)
        body.show_all()
        self.refresh()

    def quit_clicked(self, _):
        if self.phase in ("processing", "stopping"):
            self.status.set_text("Finish the current dictation before quitting.")
            return
        self.cancel()
        self.quit()

    def keypress(self, _, event):
        if event.keyval == Gdk.KEY_Escape:
            self.cancel()
            return True
        return False

    def refresh(self):
        self.engine.set_text(self.config["speech_provider"] + " · " + self.config["speech_model"])
        self.record_btn.set_label("Stop and transcribe" if self.phase == "recording" else "Start dictation")
        self.record_btn.set_sensitive(self.phase in ("idle", "recording"))
        self.cancel_btn.set_sensitive(self.phase == "recording")

    def preferences(self, _):
        if self.phase != "idle" or self.dlg:
            return
        self.dlg = Preferences(self.window, self.config)
        while self.dlg.run() == Gtk.ResponseType.OK:
            try:
                config = self.dlg.values()
                system.save(config)
                self.config = config
                break
            except Exception as exc:
                self.dlg.message.set_text(str(exc))
        self.dlg.destroy()
        self.dlg = None
        self.refresh()

    def notice(self, text):
        self.status.set_text(text)
        if not self.window.is_active():
            notice = Gio.Notification.new("VoiceFlow AI")
            notice.set_body(text)
            self.send_notification("dictation", notice)

    def toggle(self, global_key=False):
        if self.phase == "recording":
            self.stop()
            return
        if self.phase != "idle":
            return
        # A shortcut can be tried inside the modal settings dialog. Keep its
        # result in the main window instead of pasting into a settings field.
        if self.dlg and self.dlg.is_active():
            global_key = False
        self.target = system.x11_target() if global_key else None
        self.global_key = global_key
        self.temp = tempfile.TemporaryDirectory(prefix="voiceflow-")
        self.capture_config = self.config.copy()
        suffix = ".flac" if self.config["speech_provider"] == "Gemini" else ".m4a"
        self.path = Path(self.temp.name) / ("recording" + suffix)
        try:
            self.level = deque([0.0], maxlen=1)
            self.proc = system.record(self.path, meter=self.level.append)
        except Exception as exc:
            self.clear()
            self.notice(str(exc))
            return
        self.phase = "recording"
        self.notice("Recording · use the shortcut again to finish")
        self.refresh()
        self.indicator = RecordingIndicator()
        if not global_key:
            self.indicator.set_transient_for(self.dlg or self.window)
        self.indicator.show_all()
        GLib.timeout_add(75, self.monitor, self.proc)

    def monitor(self, proc):
        if self.proc is not proc or self.phase != "recording":
            return False
        if proc.poll() is None:
            if self.indicator:
                self.indicator.update_level(self.level[-1])
            return True
        self.stop()
        return False

    def cancel(self):
        if self.phase != "recording":
            return
        proc = self.proc
        proc.kill()
        proc.communicate()
        self.clear()
        self.notice("Recording cancelled")

    def hide_indicator(self):
        if self.indicator:
            self.indicator.destroy()
            self.indicator = None

    def clear(self):
        self.hide_indicator()
        if self.temp:
            self.temp.cleanup()
        self.proc = self.temp = None
        self.phase = "idle"
        self.refresh()

    def stop(self):
        self.hide_indicator()
        self.phase = "stopping"
        self.notice("Transcribing…")
        self.refresh()
        config, path, proc = self.capture_config, self.path, self.proc
        background(lambda: system.process(config, path, proc), self.completed)

    def completed(self, result, failure):
        self.clear()
        if failure:
            self.notice(failure)
            return
        raw, output, note = result
        self.views["raw"].get_buffer().set_text(raw)
        self.views["output"].get_buffer().set_text(output)
        if self.global_key and (os.environ.get("XDG_SESSION_TYPE") == "wayland" or os.environ.get("WAYLAND_DISPLAY")):
            self.window.present()
            where = "Result ready · click Copy result, then paste in your app"
        elif self.global_key:
            self.clipboard(output)
            inserted = self.config["auto_paste"] and system.paste(self.target)
            where = "Pasted into original window" if inserted else "Copied · paste into your text field"
        else:
            where = "Result ready"
        self.notice(" · ".join(filter(None, (where, note))))

    @staticmethod
    def clipboard(text):
        clip = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clip.set_text(text, -1)
        clip.store()

    def copy_result(self, _):
        buf = self.views["output"].get_buffer()
        text = buf.get_text(*buf.get_bounds(), True)
        if text:
            self.clipboard(text)
            self.notice("Result copied")


def main():
    return VoiceFlow().run(sys.argv)
