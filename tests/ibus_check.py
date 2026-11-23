"""Drive an actual IBus input context through press, release, waveform and commit."""
import os
import json
import subprocess
import threading
import time
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import gi
gi.require_version("IBus", "1.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gio, Gtk, IBus
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


browser_ready = threading.Event()
browser_values = []

class Provider(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"""<input type=search id=q value='Before  after' autofocus>
        <script>const q=document.querySelector('input'); q.focus(); q.setSelectionRange(7,7);
        const t=setInterval(()=>{if(document.hasFocus() && document.activeElement===q){
          clearInterval(t);fetch('/ready',{method:'POST',body:'ok'});}},100);
        q.oninput=()=>fetch('/value',{method:'POST',body:q.value});</script>""")

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if self.path in ("/ready", "/value"):
            if self.path == "/ready":
                browser_ready.set()
            else:
                browser_values.append(body.decode())
            self.send_response(204)
            self.end_headers()
            return
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

# Feed the virtual PulseAudio sink so the test waits for captured audio,
# including on runners where the monitor source initially starts suspended.
tone = subprocess.Popen(["ffmpeg", "-nostdin", "-loglevel", "error", "-re", "-f", "lavfi",
                         "-i", "sine=frequency=440", "-t", "30", "-f", "pulse", "VoiceFlow test"])
press()
ctx.process_key_event(IBus.KEY_C, 46, mod.CONTROL_MASK | mod.SHIFT_MASK)
release()
time.sleep(.25)
press()
until(lambda: sum(any(bar in w for bar in "▂▃▄▅▆▇█") for w in waves) >= 5)
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
entry.set_text("Before  after")
win.add(entry)
win.show_all()
entry.grab_focus()
entry.set_position(7)
def send_keys():
    time.sleep(.6)
    if os.environ.get("VF_CONTROL_BUS"):
        for method in ("Begin", "End"):
            result = control_bus.call_sync("io.github.chandan_itian.VoiceFlowInput",
                "/io/github/chandan_itian/VoiceFlowInput", "io.github.chandan_itian.VoiceFlowInput",
                method, None, None, Gio.DBusCallFlags.NONE, 2000, None)
            assert result.unpack() == (True,)
            if method == "Begin":
                time.sleep(1.7)
    else:
        keys = os.environ.get("VF_HOLD_KEYS", "F8").split()
        if count == 2:
            keys.reverse()
        subprocess.run(["xdotool", *[part for k in keys for part in ("keydown", k)]], check=True)
        time.sleep(1.7)
        subprocess.run(["xdotool", *[part for k in reversed(keys) for part in ("keyup", k)]], check=True)
if os.environ.get("VF_CONTROL_BUS"):
    # Stand in for Shell on the isolated Weston test bus.
    control_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    Gio.bus_own_name_on_connection(control_bus, "org.gnome.Shell", Gio.BusNameOwnerFlags.NONE, None, None)
for count in (1, 2):
    threading.Thread(target=send_keys, daemon=True).start()
    until(lambda: entry.get_text() == "Before " + "Mujhe knowledge hai." * count + " after", 12)
print("PASS: repeated commits into GTK editor:", entry.get_text())

if os.environ.get("VF_WAYLAND_BROWSER"):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        chrome = subprocess.Popen([os.environ["VF_WAYLAND_BROWSER"], "--ozone-platform=wayland",
            "--enable-wayland-ime", "--wayland-text-input-version=3", "--disable-gpu", "--no-first-run",
            "--user-data-dir=" + profile, f"http://127.0.0.1:{server.server_port}/editor"])
        try:
            until(browser_ready.is_set, 20)
            threading.Thread(target=send_keys, daemon=True).start()
            until(lambda: "Before Mujhe knowledge hai. after" in browser_values, 15)
            print("PASS: Wayland Chromium search field retained surrounding text")
        finally:
            chrome.terminate()
            chrome.wait(timeout=10)

tone.terminate()
tone.wait(timeout=5)
server.shutdown()
print("PASS: modifier hold and release, third-key cancellation, caret preedit and single text commit over IBus")
