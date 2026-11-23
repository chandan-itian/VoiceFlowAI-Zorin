#!/bin/bash
# Xvfb supplies a virtual monitor and keyboard to nested Mutter. GTK is Wayland-only.
set -eu
export XDG_CONFIG_HOME=$(mktemp -d)
export XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_TYPE=wayland LIBGL_ALWAYS_SOFTWARE=1
dbus-update-activation-environment XDG_CONFIG_HOME DISPLAY XAUTHORITY XDG_RUNTIME_DIR XDG_CURRENT_DESKTOP XDG_SESSION_TYPE
gsettings set org.gnome.shell welcome-dialog-last-shown-version '999'
gsettings set org.gnome.shell enabled-extensions "['voiceflow-ptt@chandan-itian.github.io']"
gnome-shell --nested --wayland --wayland-display=voiceflow-test >"$XDG_RUNTIME_DIR/shell.log" 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true; tail -55 "$XDG_RUNTIME_DIR/shell.log"' EXIT
gdbus wait --session --timeout 40 org.gnome.Shell
for i in $(seq 1 100); do grep -q 'GNOME Shell started' "$XDG_RUNTIME_DIR/shell.log" && break; sleep .2; done
export WAYLAND_DISPLAY=voiceflow-test GDK_BACKEND=wayland GTK_IM_MODULE=ibus
gnome-extensions info voiceflow-ptt@chandan-itian.github.io
gnome-extensions list --active | grep voiceflow-ptt
pulseaudio --start --exit-idle-time=-1
pactl load-module module-null-sink sink_name=voiceflow
pactl set-default-sink voiceflow
pactl set-default-source voiceflow.monitor
eval "$(printf test | gnome-keyring-daemon --unlock --components=secrets)"
gsettings set org.gnome.desktop.input-sources sources "[('ibus', 'voiceflow-zorin')]"
xdotool key Escape
VF_WAYLAND_BROWSER=google-chrome VF_HOLD_KEYS="ctrl Super_L" /usr/bin/python3 tests/ibus_check.py
