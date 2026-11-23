#!/bin/sh
set -eu
umask 022
cd "$(dirname "$0")/.."
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/DEBIAN" "$root/usr/lib/voiceflow-zorin/voiceflow" dist
chmod 755 "$root"
install -Dm755 packaging/voiceflow-zorin "$root/usr/bin/voiceflow-zorin"
install -m644 voiceflow/*.py "$root/usr/lib/voiceflow-zorin/voiceflow/"
install -Dm644 assets/voiceflow-zorin.png "$root/usr/share/icons/hicolor/512x512/apps/voiceflow-zorin.png"
install -Dm644 packaging/voiceflow-zorin.desktop "$root/usr/share/applications/voiceflow-zorin.desktop"
install -Dm644 LICENSE "$root/usr/share/doc/voiceflow-zorin/copyright"
cat > "$root/DEBIAN/control" <<'CONTROL'
Package: voiceflow-zorin
Version: 0.1.0
Section: sound
Priority: optional
Architecture: all
Maintainer: VoiceFlow AI contributors <chandan-itian@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-3.0, ffmpeg, libsecret-tools, xdotool, x11-utils
Recommends: gnome-keyring, gnome-settings-daemon-common
Description: Online desktop dictation with configurable transcription and refinement
 Record speech, transcribe via a cloud provider, and optionally refine the text.
CONTROL
dpkg-deb --root-owner-group --build "$root" dist/voiceflow-zorin_0.1.0_all.deb
