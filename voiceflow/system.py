import json
import os
import subprocess
import tempfile
from pathlib import Path
from .cloud import endpoint

DEFAULTS = dict(speech_provider="Groq", speech_model="whisper-large-v3",
                text_provider="Groq", text_model="llama-3.1-8b-instant", refine=True,
                language="Roman Hinglish", custom_url="", fallback=True,
                fallback_models="openai/gpt-oss-20b, llama-3.3-70b-versatile",
                prompt="Use natural punctuation and paragraph breaks.", auto_paste=True)


def config_path():
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "voiceflow-zorin/settings.json"


def load():
    try:
        return DEFAULTS | {k: v for k, v in json.loads(config_path().read_text()).items()
                           if k in DEFAULTS and type(v) is type(DEFAULTS[k])}
    except FileNotFoundError:
        return DEFAULTS.copy()


def save(config):
    path = config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
        try:
            json.dump({k: config[k] for k in DEFAULTS}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
            os.replace(f.name, path)
        finally:
            Path(f.name).unlink(missing_ok=True)


def credential(provider, config, value=None):
    base = endpoint(provider, config)
    args = ["secret-tool", "lookup"] if value is None else [
        "secret-tool", "store", "--label=VoiceFlow AI · " + provider]
    res = subprocess.run(args + ["application", "voiceflow-zorin", "endpoint", base],
                         input=value, text=True, capture_output=True, timeout=45)
    if res.returncode and (value is not None or res.stderr.strip()):
        raise RuntimeError("Cannot access the desktop keyring. Unlock it and try again.")
    key = res.stdout.strip()
    if value is None and not key and provider != "Custom":
        raise ValueError("Save an API key for " + provider + " in Settings.")
    return key


def record(path, source="default", test_source=False):
    source_args = ["-f", "pulse", "-i", source]
    if test_source:
        source_args = ["-re", "-f", "lavfi", "-i", source]
    codec = ["-c:a", "flac"] if str(path).endswith(".flac") else ["-c:a", "aac", "-b:a", "24k"]
    return subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *source_args,
                             "-t", "300", "-ac", "1", "-ar", "16000", *codec, str(path)],
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def finish(proc):
    try:
        _, err = proc.communicate(b"q\n" if proc.poll() is None else None, timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise RuntimeError("The microphone did not stop in time.")
    if proc.returncode:
        raise RuntimeError("Recording failed. Check the microphone in Sound Settings. " +
                           err.decode(errors="replace").strip()[-180:])


def x11_target():
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
        return None
    try:
        return subprocess.check_output(["xdotool", "getactivewindow"], text=True,
                                       stderr=subprocess.DEVNULL, timeout=2).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def paste(target):
    if not target or x11_target() != target:
        return False
    try:
        kind = subprocess.check_output(["xprop", "-id", target, "WM_CLASS"], text=True, timeout=2).lower()
        terminal = any(t in kind for t in ("terminal", "tilix", "kitty", "alacritty", "konsole", "wezterm"))
        return subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+shift+v" if terminal else "ctrl+v"],
                              timeout=2).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
