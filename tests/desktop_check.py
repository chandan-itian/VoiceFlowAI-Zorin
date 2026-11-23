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
            result = check()
            if result:
                return result
        except subprocess.SubprocessError:
            pass
        time.sleep(.15)
    raise AssertionError("Timed out waiting for " + str(check))


with tempfile.TemporaryDirectory() as tmp:
    os.environ["XDG_CONFIG_HOME"] = tmp
    raw, polished = "mujhe नॉलेज hai", "Mujhe knowledge hai."
    calls = []
    class API(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'<title>VF browser fixture</title><textarea autofocus oninput="document.title=this.value"></textarea>')

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
    others = []
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
        def dictate_into(window_name):
            def focus_ready_window():
                wid = run("xdotool", "search", "--onlyvisible", "--name", window_name).splitlines()[-1]
                run("xdotool", "windowactivate", "--sync", wid)
                # Writer can briefly unmap its document window while starting up.
                time.sleep(.4)
                return wid if run("xdotool", "getactivewindow") == wid else None
            wid = wait(focus_ready_window)
            run("voiceflow-zorin", "--toggle")
            wait(lambda: run("pactl", "list", "short", "source-outputs"))
            time.sleep(2.0)
            run("voiceflow-zorin", "--toggle")
            return wid

        if os.environ.get("VF_BROWSER"):
            page = config["custom_url"] + "/editor"
            others.append(subprocess.Popen([os.environ["VF_BROWSER"], "--no-first-run", "--disable-sync",
                "--user-data-dir=" + tmp + "/browser", "--new-window", page]))
            win = dictate_into("VF browser fixture")
            wait(lambda: polished in run("xdotool", "getwindowname", win))
            print("PASS: dictation inserted into browser textarea")

        if os.environ.get("VF_WRITER"):
            document = Path(tmp) / "VoiceFlow-Writer-check.txt"
            document.write_text("Start ")
            others.append(subprocess.Popen([os.environ["VF_WRITER"], "-env:UserInstallation=" +
                (Path(tmp) / "office").as_uri(), "--nologo", "--norestore", "--writer", str(document)],
                env=os.environ | {"SAL_USE_VCLPLUGIN": "gen"}))
            win = dictate_into("VoiceFlow-Writer-check")
            wait(lambda: len(calls) >= (6 if os.environ.get("VF_BROWSER") else 4))
            # Read back Writer's selected document text via the X11 selection.
            import gi
            gi.require_version("Gtk", "3.0")
            gi.require_version("Gdk", "3.0")
            from gi.repository import Gtk, Gdk
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            def inserted():
                run("xdotool", "key", "ctrl+a", "ctrl+c")
                value = clipboard.wait_for_text() or ""
                return polished in value and "Start" in value
            wait(inserted)
            print("PASS: dictation inserted into LibreOffice Writer")
        run("voiceflow-zorin","--quit")
        assert app.wait(timeout=5) == 0
    finally:
        for process in others:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        target.terminate()
        target.wait()
        if app.poll() is None:
            app.terminate()
            app.wait()
        api.shutdown()
        api.server_close()
