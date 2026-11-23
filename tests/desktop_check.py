"""Exercise the installed application across real D-Bus, PulseAudio and X11."""
import json
import os
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from voiceflow import system


def run(*args):
    return subprocess.check_output(args, text=True, timeout=12).strip()


def wait(check):
    end = time.monotonic() + 18
    while time.monotonic() < end:
        try:
            if check():
                return
        except subprocess.SubprocessError:
            pass
        time.sleep(.15)
    raise AssertionError("Timed out waiting for " + str(check))


with tempfile.TemporaryDirectory() as tmp:
    os.environ["XDG_CONFIG_HOME"] = tmp
    raw, polished = "mujhe नॉलेज hai", "Mujhe knowledge hai."
    calls = []
    class API(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            calls.append((self.path, body))
            if self.path.endswith("transcriptions"):
                value = {"text": raw}
            else:
                value = {"choices":[{"message":{"content":polished}}]}
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())
    api = ThreadingHTTPServer(("127.0.0.1", 0), API)
    Thread(target=api.serve_forever, daemon=True).start()
    config = system.DEFAULTS | {"speech_provider":"Custom","text_provider":"Custom",
                                "custom_url":"http://127.0.0.1:" + str(api.server_port)}
    system.save(config)
    system.credential("Custom", config, "local-test-only")
    assert system.credential("Custom", config) == "local-test-only"
    target_file = Path(tmp) / "received.txt"
    target = subprocess.Popen([sys.executable, "-c", """
import sys,gi
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
w=Gtk.Window(title="VoiceFlow test editor")
e=Gtk.Entry()
e.connect('changed',lambda entry: Path(sys.argv[1]).write_text(entry.get_text()))
w.add(e)
w.show_all()
e.grab_focus()
Gtk.main()
""", str(target_file)])
    app = subprocess.Popen(["voiceflow-zorin"])
    try:
        wait(lambda: run("xdotool","search","--onlyvisible","--name","^VoiceFlow AI$"))
        editor = run("xdotool","search","--name","^VoiceFlow test editor$").splitlines()[0]
        run("xdotool","windowactivate","--sync",editor)
        run("voiceflow-zorin","--toggle")
        time.sleep(1)
        run("voiceflow-zorin","--cancel")
        assert not calls
        run("voiceflow-zorin","--toggle")
        time.sleep(1.2)
        run("voiceflow-zorin","--toggle")
        wait(lambda: target_file.exists() and target_file.read_text() == polished)
        assert [p for p,_ in calls] == ["/audio/transcriptions","/chat/completions"]
        assert b"ftyp" in calls[0][1]
        assert json.loads(calls[1][1])["messages"][1]["content"] == raw
        print("PASS: packaged app, keyring, cancel, PulseAudio capture, M4A upload, refinement and X11 insertion")
        run("voiceflow-zorin","--quit")
        assert app.wait(timeout=5) == 0
    finally:
        target.terminate()
        target.wait()
        if app.poll() is None:
            app.terminate()
            app.wait()
        api.shutdown()
        api.server_close()
