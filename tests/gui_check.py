import os
from unittest.mock import Mock, patch
from voiceflow.app import Preferences, VoiceFlow, RecordingIndicator, install_toggle
from gi.repository import Gio, Gtk
from voiceflow import system

# Keep CI changes to desktop bindings inside this test process.
os.environ["GSETTINGS_BACKEND"] = "memory"
install_toggle()
install_toggle()
schema = "org.gnome.settings-daemon.plugins.media-keys"
path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/voiceflow-toggle/"
assert Gio.Settings.new(schema).get_strv("custom-keybindings").count(path) == 1
item = Gio.Settings.new_with_path(schema + ".custom-keybinding", path)
assert item.get_string("command") == "voiceflow-zorin --toggle"
binding = Gtk.accelerator_parse(item.get_string("binding"))
assert all(Gtk.accelerator_parse(v) != binding for v in
           Gio.Settings.new("org.gnome.desktop.wm.keybindings").get_strv("switch-input-source-backward"))
indicator = RecordingIndicator()
indicator.show_all()
indicator.update_level(.5)
assert indicator.get_mapped() and "█" in indicator.caption.get_text()
indicator.destroy()

app = VoiceFlow()
assert app.register(None)
app.build_window()
app.window.show_all()
prefs = Preferences(app.window, app.config)
assert prefs.values() == system.DEFAULTS
prefs.stages["speech"][0].set_active_id("OpenAI")
assert prefs.values()["speech_model"] == "gpt-4o-transcribe"
assert prefs.values()["text_model"] == "llama-3.1-8b-instant"
prefs.secret.set_text("new-test-key")
with patch("voiceflow.app.background", lambda work, done: done(work(), None)), \
     patch("voiceflow.system.credential", side_effect=AssertionError("Used old key")), \
     patch("voiceflow.cloud.check_connection", return_value="Connected") as fetch:
    prefs.test_connection(None)
    assert fetch.call_args.args[-1] == "new-test-key"
    assert "Connected" in prefs.message.get_text()
prefs.destroy()
app.global_key = True
app.target = None
with patch.object(system, "paste", side_effect=AssertionError("Wayland attempted injection")), patch.dict(os.environ, XDG_SESSION_TYPE="wayland"):
    app.completed(("original", "Mujhe knowledge hai.", "Formatted"), None)
    assert "Copy result" in app.status.get_text()
# An unavailable formatter must preserve the original transcript inside the UI.
app.global_key = False
app.config = system.DEFAULTS.copy()
app.capture_config = app.config.copy()
app.proc = Mock()
app.path = "/unused.wav"
def execute(work, done):
    done(work(), None)
with patch("voiceflow.app.background", execute), patch("voiceflow.system.finish"), \
     patch("voiceflow.system.credential", return_value="test"), \
     patch("voiceflow.cloud.transcribe", return_value="meeting kal hai"), \
     patch("voiceflow.cloud.refine", side_effect=RuntimeError("provider unavailable")):
    app.stop()
buf = app.views["output"].get_buffer()
assert buf.get_text(*buf.get_bounds(), True) == "meeting kal hai"
assert "Using original transcript" in app.status.get_text()
app.config["refine"] = False
app.capture_config = app.config.copy()
app.proc = Mock()
with patch("voiceflow.app.background", execute), patch("voiceflow.system.finish"), \
     patch("voiceflow.system.credential", return_value="test"), \
     patch("voiceflow.cloud.transcribe", return_value="raw only"), \
     patch("voiceflow.cloud.refine", side_effect=AssertionError("formatter called while disabled")):
    app.stop()
assert buf.get_text(*buf.get_bounds(), True) == "raw only"
app.quit()
print("PASS: GTK settings, independent model selection and Wayland copy flow")
