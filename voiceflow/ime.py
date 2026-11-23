"""Caret-local push-to-talk for applications using the VoiceFlow IBus source."""
import tempfile
from collections import deque
from pathlib import Path

import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, Gio, IBus
from . import system
from .app import background

CTRL = {IBus.KEY_Control_L, IBus.KEY_Control_R}
SHIFT = {IBus.KEY_Shift_L, IBus.KEY_Shift_R}
MOD = IBus.ModifierType


SERVICE = "io.github.chandan_itian.VoiceFlowInput"
PATH = "/io/github/chandan_itian/VoiceFlowInput"
INTERFACE = Gio.DBusNodeInfo.new_for_xml(f"""<node><interface name="{SERVICE}">
    <method name="Begin"><arg type="b" direction="out"/></method>
    <method name="End"><arg type="b" direction="out"/></method>
    <method name="Cancel"><arg type="b" direction="out"/></method>
    <signal name="Level"><arg type="d"/></signal></interface></node>""")


class DictationEngine(IBus.EngineSimple):
    active = None
    shell_capture = False
    connection = None
    __gtype_name__ = "VoiceFlowDictationEngine"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.focused = False
        self.private = False
        self.held = False
        self.f8_down = False
        self.pending = 0
        self.session = None
        self.processing = False
        self.generation = 0

    def do_focus_in(self):
        self.focused = True
        DictationEngine.active = self
        self.get_surrounding_text()  # Subscribe before taking a caret snapshot.

    def do_focus_out(self):
        self.focused = False
        if DictationEngine.active is self:
            DictationEngine.active = None
        self.reset_capture()

    def do_reset(self):
        self.reset_capture()
        IBus.EngineSimple.do_reset(self)

    def do_disable(self):
        self.focused = False
        if DictationEngine.active is self:
            DictationEngine.active = None
        self.reset_capture()

    def do_set_content_type(self, purpose, hints):
        self.private = purpose in (IBus.InputPurpose.PASSWORD, IBus.InputPurpose.PIN)
        if self.private:
            self.reset_capture()

    def reset_capture(self):
        self.end_meter()
        self.generation += 1
        self.processing = self.held = self.f8_down = False
        if self.pending:
            GLib.source_remove(self.pending)
            self.pending = 0
        if self.session:
            proc, temp, *_ = self.session
            self.session = None
            proc.kill()
            proc.communicate()
            temp.cleanup()
            self.wave("")

    def caret_state(self):
        if self.client_capabilities & IBus.Capabilite.SURROUNDING_TEXT:
            text, cursor, anchor = self.get_surrounding_text()
            if text is not None:
                return (text.get_text(), cursor, anchor)
        return None

    def end_meter(self):
        if self.shell_capture:
            self.emit_level(-1.0)
            self.shell_capture = False

    def emit_level(self, level):
        self.connection.emit_signal(None, PATH, SERVICE, "Level", GLib.Variant("(d)", (level,)))

    def wave(self, value):
        self.update_preedit_text(IBus.Text.new_from_string(value), 0, bool(value))

    def report(self, message):
        self.update_auxiliary_text(IBus.Text.new_from_string(message), True)

    def do_process_key_event(self, key, code, state):
        modifier = key in CTRL or key in SHIFT
        release = bool(state & MOD.RELEASE_MASK)
        if key == IBus.KEY_F8 and self.focused and not self.private:
            if self.f8_down:
                if release:
                    self.f8_down = False
                    if self.session:
                        self.stop()
                return True
            if not release and not (state & (MOD.CONTROL_MASK | MOD.SHIFT_MASK | MOD.MOD1_MASK |
                                             MOD.MOD4_MASK | MOD.SUPER_MASK | MOD.MOD5_MASK)):
                if not self.processing and not self.held:
                    self.f8_down = True
                    self.start()
                return True
        if self.f8_down and not release:
            self.reset_capture()
        if modifier and release and self.held:
            self.held = False
            if self.pending:
                GLib.source_remove(self.pending)
                self.pending = 0
            if self.session:
                self.stop()
        elif not release and self.focused and not self.private:
            chord = (key in CTRL and state & MOD.SHIFT_MASK or key in SHIFT and state & MOD.CONTROL_MASK)
            extra = state & (MOD.MOD1_MASK | MOD.SUPER_MASK | MOD.MOD4_MASK | MOD.MOD5_MASK)
            if chord and not extra and not self.held and not self.processing:
                self.held = True
                self.pending = GLib.timeout_add(120, self.start)
            elif not modifier and (self.held or self.processing):
                self.reset_capture()
        return IBus.EngineSimple.do_process_key_event(self, key, code, state)

    def start(self):
        self.pending = 0
        self.hide_auxiliary_text()
        temp = tempfile.TemporaryDirectory(prefix="voiceflow-")
        levels = deque([0.0], maxlen=1)
        try:
            config = system.load()
            suffix = ".flac" if config["speech_provider"] == "Gemini" else ".m4a"
            path = Path(temp.name) / ("speech" + suffix)
            proc = system.record(path, meter=levels.append)
        except Exception as exc:
            temp.cleanup()
            self.report(str(exc))
            return False
        self.session = proc, temp, path, config
        bars = deque("▁" * 10, maxlen=10)
        def tick():
            if not self.session or self.session[0] is not proc:
                return False
            if proc.poll() is not None:
                self.stop()
                return False
            bars.append("▁▂▃▄▅▆▇█"[min(7, int(levels[-1] ** 0.5 * 18))])
            if self.shell_capture:
                self.emit_level(levels[-1])
            else:
                self.wave("".join(bars))
            return True
        if tick():
            GLib.timeout_add(65, tick)
        return False

    def stop(self):
        proc, temp, path, config = self.session
        self.session = None
        self.wave("")
        origin = self.origin if self.shell_capture else None
        self.end_meter()
        self.processing = True
        generation = self.generation
        def work():
            try:
                return system.process(config, path, proc)
            finally:
                temp.cleanup()
        def done(result, err):
            if self.generation != generation or not self.focused or self.private:
                return
            self.processing = False
            if origin is not None and self.caret_state() != origin:
                return
            if err:
                self.report(err)
            else:
                self.commit_text(IBus.Text.new_from_string(result[1]))
        background(work, done)


def main():
    IBus.init()
    bus = IBus.Bus.new()
    if not bus.is_connected():
        raise SystemExit("IBus is unavailable")
    factory = IBus.Factory.new(bus.get_connection())
    factory.add_engine("voiceflow-zorin", DictationEngine.__gtype__)
    bus.request_name("org.freedesktop.IBus.VoiceFlow", 0)
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    DictationEngine.connection = connection
    def control(_, sender, path, interface, method, args, invocation):
        engine = DictationEngine.active
        ok = False
        if engine and engine.focused and not engine.private:
            if method == "Begin" and not (engine.session or engine.processing or engine.pending):
                engine.origin = engine.caret_state()
                if engine.origin and engine.origin[1] != engine.origin[2]:
                    invocation.return_value(GLib.Variant("(b)", (False,)))
                    return
                engine.shell_capture = True
                engine.start()
                ok = engine.session is not None
                if not ok:
                    engine.end_meter()
            elif engine.shell_capture and engine.session:
                if method == "End":
                    engine.stop()
                    ok = True
                elif method == "Cancel":
                    engine.reset_capture()
                    ok = True
        invocation.return_value(GLib.Variant("(b)", (ok,)))
    connection.register_object(PATH, INTERFACE.interfaces[0], control, None, None)
    Gio.bus_own_name_on_connection(connection, SERVICE, Gio.BusNameOwnerFlags.NONE, None, None)
    loop = GLib.MainLoop()
    bus.connect("disconnected", lambda *_: loop.quit())
    loop.run()
