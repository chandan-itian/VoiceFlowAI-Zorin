import os
from unittest.mock import patch
from voiceflow.app import Preferences, VoiceFlow
from voiceflow import system

app = VoiceFlow()
assert app.register(None)
app.build_window()
app.window.show_all()
prefs = Preferences(app.window, app.config)
assert prefs.values() == system.DEFAULTS
prefs.stages["speech"][0].set_active_id("OpenAI")
assert prefs.values()["speech_model"] == "gpt-4o-transcribe"
assert prefs.values()["text_model"] == "llama-3.1-8b-instant"
prefs.destroy()
app.global_key = True
app.target = None
with patch.object(system, "paste", side_effect=AssertionError("Wayland attempted injection")), patch.dict(os.environ, XDG_SESSION_TYPE="wayland"):
    app.completed(("original", "Mujhe knowledge hai.", "Formatted"), None)
    assert "Copy result" in app.status.get_text()
app.quit()
print("PASS: GTK settings, independent model selection and Wayland copy flow")
