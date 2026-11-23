"""Drive an actual IBus input context through press, release, waveform and commit."""
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import gi
gi.require_version("IBus", "1.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, IBus
from voiceflow import system

IBus.init()
bus = IBus.Bus.new()
assert bus.is_connected()
ctx = bus.create_input_context("voiceflow-test-editor")
caps = IBus.Capabilite
ctx.set_capabilities(caps.PREEDIT_TEXT | caps.FOCUS | caps.AUXILIARY_TEXT)
waves, commits, errors, calls = [], [], [], []
ctx.connect("update-preedit-text", lambda _, text, pos, visible: waves.append(text.get_text() if visible else ""))
ctx.connect("commit-text", lambda _, text: commits.append(text.get_text()))
ctx.connect("update-auxiliary-text", lambda _, text, visible: errors.append(text.get_text()) if visible else None)
ctx.focus_in()
assert bus.set_global_engine("voiceflow-zorin"), [e.get_name() for e in bus.list_engines()][:12]
ctx.set_engine("voiceflow-zorin")


def until(check, timeout=10):
    end = time.monotonic() + timeout
    loop = GLib.MainContext.default()
    while time.monotonic() < end:
        while loop.pending():
            loop.iteration(False)
        if check():
            return
        time.sleep(.01)
    raise AssertionError(f"IBus timeout: waves={waves[-3:]}, commits={commits}, errors={errors}, calls={calls}")


class Provider(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        assert b"ftyp" in body
        calls.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"text": "Mujhe knowledge hai."}).encode())


server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
threading.Thread(target=server.serve_forever, daemon=True).start()
system.save(system.DEFAULTS | {"speech_provider": "Custom", "refine": False,
                               "custom_url": f"http://127.0.0.1:{server.server_port}"})
until(lambda: ctx.get_engine() and ctx.get_engine().get_name() == "voiceflow-zorin")
mod = IBus.ModifierType
def press():
    ctx.process_key_event(IBus.KEY_Control_L, 29, 0)
    ctx.process_key_event(IBus.KEY_Shift_L, 42, mod.CONTROL_MASK)

def release():
    ctx.process_key_event(IBus.KEY_Shift_L, 42, mod.CONTROL_MASK | mod.SHIFT_MASK | mod.RELEASE_MASK)
    ctx.process_key_event(IBus.KEY_Control_L, 29, mod.CONTROL_MASK | mod.RELEASE_MASK)

press()
ctx.process_key_event(IBus.KEY_C, 46, mod.CONTROL_MASK | mod.SHIFT_MASK)
release()
time.sleep(.25)
press()
until(lambda: len([w for w in waves if w]) >= 10)
release()
until(lambda: commits)
assert waves[-1] == "" and commits == ["Mujhe knowledge hai."] and calls == ["/audio/transcriptions"]
# The editor changing focus while the microphone is open discards that capture.
waves.clear()
press()
until(lambda: any(waves))
ctx.focus_out()
time.sleep(.3)
release()
assert len(calls) == len(commits) == 1
win = Gtk.Window(title="VoiceFlow hold test")
entry = Gtk.Entry()
win.add(entry)
win.show_all()
entry.grab_focus()
def send_keys():
    time.sleep(.6)
    subprocess.run(["xdotool","keydown","ctrl","keydown","shift"],check=True)
    time.sleep(1.7)
    subprocess.run(["xdotool","keyup","shift","keyup","ctrl"],check=True)
threading.Thread(target=send_keys,daemon=True).start()
until(lambda: entry.get_text() == "Mujhe knowledge hai.", 12)
print("PASS: X11 keydown/keyup to real GTK editor:", entry.get_text())

server.shutdown()
print("PASS: modifier hold and release, third-key cancellation, caret preedit and single text commit over IBus")
