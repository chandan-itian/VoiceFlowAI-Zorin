"""Caret-local push-to-talk for applications using the VoiceFlow IBus source."""
import tempfile
from collections import deque
from pathlib import Path

import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus
from . import system
from .app import background

CTRL = {IBus.KEY_Control_L, IBus.KEY_Control_R}
SHIFT = {IBus.KEY_Shift_L, IBus.KEY_Shift_R}
MOD = IBus.ModifierType


class DictationEngine(IBus.EngineSimple):
    __gtype_name__ = "VoiceFlowDictationEngine"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.focused = False
        self.private = False
        self.held = False
        self.pending = 0
        self.session = None
        self.processing = False
        self.generation = 0

    def do_focus_in(self):
        self.focused = True

    def do_focus_out(self):
        self.focused = False
        self.reset_capture()

    def do_reset(self):
        self.reset_capture()
        IBus.EngineSimple.do_reset(self)

    def do_disable(self):
        self.focused = False
        self.reset_capture()

    def do_set_content_type(self, purpose, hints):
        self.private = purpose in (IBus.InputPurpose.PASSWORD, IBus.InputPurpose.PIN)
        if self.private:
            self.reset_capture()

    def reset_capture(self):
        self.generation += 1
        self.processing = self.held = False
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

    def wave(self, value):
        self.update_preedit_text(IBus.Text.new_from_string(value), 0, bool(value))

    def report(self, message):
        self.update_auxiliary_text(IBus.Text.new_from_string(message), True)

    def do_process_key_event(self, key, code, state):
        modifier = key in CTRL or key in SHIFT
        release = bool(state & MOD.RELEASE_MASK)
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
            self.wave("".join(bars))
            return True
        if tick():
            GLib.timeout_add(65, tick)
        return False

    def stop(self):
        proc, temp, path, config = self.session
        self.session = None
        self.wave("")
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
    loop = GLib.MainLoop()
    bus.connect("disconnected", lambda *_: loop.quit())
    loop.run()
