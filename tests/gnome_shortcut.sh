#!/bin/bash
# Run under an isolated X11 and D-Bus session on Ubuntu Noble.
set -eu
export XDG_CONFIG_HOME=$(mktemp -d)
export XDG_CURRENT_DESKTOP=GNOME
export XDG_SESSION_TYPE=x11
export LIBGL_ALWAYS_SOFTWARE=1
gnome-shell --x11 --replace >"$XDG_RUNTIME_DIR/shell.log" 2>&1 &
shell_pid=$!
trap 'kill "$shell_pid" 2>/dev/null || true; tail -30 "$XDG_RUNTIME_DIR/shell.log"' EXIT
gdbus wait --session --timeout 45 org.gnome.Shell
/usr/libexec/gsd-media-keys >"$XDG_RUNTIME_DIR/media.log" 2>&1 &
gdbus wait --session --timeout 30 org.gnome.SettingsDaemon.MediaKeys
pulseaudio --start --exit-idle-time=-1
pactl load-module module-null-sink sink_name=voiceflow
pactl set-default-source voiceflow.monitor
/usr/bin/python3 -c 'from voiceflow.app import install_toggle; install_toggle()'
voiceflow-zorin >/tmp/voiceflow-gnome-app.log 2>&1 &
for i in $(seq 1 60); do xdotool search --onlyvisible --name '^VoiceFlow AI$' >/dev/null && break; sleep .2; done
xdotool key Super_L+Shift_L+space
for i in $(seq 1 60); do xdotool search --onlyvisible --name '^VoiceFlow recording$' >/dev/null && break; sleep .2; done
xdotool search --onlyvisible --name '^VoiceFlow recording$' >/dev/null
xdotool key Super_L+Shift_L+space
for i in $(seq 1 60); do xdotool search --onlyvisible --name '^VoiceFlow recording$' >/dev/null || break; sleep .2; done
if xdotool search --onlyvisible --name '^VoiceFlow recording$' >/dev/null; then exit 1; fi
echo 'PASS: GNOME Shell dispatched both keyboard shortcuts and the live meter opened and closed.'
