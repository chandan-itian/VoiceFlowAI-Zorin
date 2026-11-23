#!/bin/sh
set -eu
umask 022
cd "$(dirname "$0")/.."
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/DEBIAN" "$root/usr/lib/voiceflow-zorin/voiceflow" dist
chmod 755 "$root"
install -Dm755 packaging/voiceflow-zorin "$root/usr/bin/voiceflow-zorin"
install -Dm755 packaging/voiceflow-ibus "$root/usr/lib/voiceflow-zorin/voiceflow-ibus"
install -Dm644 packaging/voiceflow.xml "$root/usr/share/ibus/component/voiceflow.xml"
install -m644 voiceflow/*.py voiceflow/connection-test.m4a "$root/usr/lib/voiceflow-zorin/voiceflow/"
install -Dm644 assets/voiceflow-zorin.png "$root/usr/share/icons/hicolor/512x512/apps/voiceflow-zorin.png"
install -Dm644 packaging/voiceflow-zorin.desktop "$root/usr/share/applications/io.github.chandan_itian.VoiceFlowAI.desktop"
install -Dm644 LICENSE "$root/usr/share/doc/voiceflow-zorin/copyright"
extension="$root/usr/share/gnome-shell/extensions/voiceflow-ptt@chandan-itian.github.io"
mkdir -p "$extension/schemas"
install -m644 shell/extension.js shell/metadata.json "$extension/"
install -m644 shell/schemas/*.xml "$extension/schemas/"
glib-compile-schemas --strict "$extension/schemas"
cat > "$root/DEBIAN/control" <<'CONTROL'
Package: voiceflow-zorin
Version: 0.2.4
Section: sound
Priority: optional
Architecture: all
Maintainer: VoiceFlow AI contributors <chandan-itian@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-gi, ibus, ibus-gtk3, gir1.2-ibus-1.0, gir1.2-gtk-3.0, ffmpeg, libsecret-tools, xdotool, x11-utils, gnome-settings-daemon-common
Recommends: gnome-keyring
Description: Online desktop dictation with configurable transcription and refinement
 Record speech, transcribe via a cloud provider, and optionally refine the text.
CONTROL
dpkg-deb --root-owner-group --build "$root" dist/voiceflow-zorin_0.2.4_all.deb
