# Verification for 0.2.0

The IBus integration check starts a real input context, presses Ctrl and Shift, observes composing text at the caret, releases the keys, and verifies a single transcript commit using a local HTTP provider. It also exercises cancellation by another key and by focus loss. A codec test measures nonzero live levels from a generated tone while encoding the upload. GTK tests cover testing a newly entered key before saving. HTTP tests check the Groq request path, authorization header, and redacted 403 response. These tests run with synthetic audio and test credentials.

# Verification for 0.1.0

The Debian package was built and extracted on a Debian Linux host. Its launcher and packaged Python modules ran in isolated desktop sessions. The following checks completed against this build.

| Check | Result |
| --- | --- |
| Audio encoding | FFprobe identified FFmpeg output as AAC, 16 kHz, one channel. |
| Transcription and formatting | A local HTTP server received the audio multipart upload, then the transcript in a separate chat request. Original and formatted text were retained separately. |
| Groq fallback | Simulated 429 responses advanced through the configured models in order. A 401 stopped retries. |
| Gemini and custom profiles | Tested native Gemini audio payload and model listing, custom base URL routing and rejection of unsecured non-loopback HTTP. |
| Provider failure and preferences | Empty/truncated refinement was rejected. GTK recovered the original on refinement failure and skipped the formatter when disabled. |
| Secrets | The packaged application stored and retrieved a test key through an isolated Secret Service keyring. Preferences excluded credentials. |
| Desktop controls | A second CLI invocation reached the existing GTK application through D-Bus. Cancelling a capture produced zero HTTP requests. |
| X11 text insertion | PulseAudio capture from a virtual source completed the dictation path. Result text appeared in a separate GTK editor, Chromium textarea and LibreOffice Writer document. |
| Wayland | GTK opened under headless Weston, changed the speech model independently of the refinement model and presented the result for manual copy. |
| Logo | The installed 512-pixel PNG was converted from the Android launcher artwork. |

The network tests used controlled responses, not paid accounts. On-device microphone quality, cloud model quality, actual Zorin Shell shortcut conflicts and manual clipboard transfer on physical Wayland hardware remain unmeasured. The GitHub workflow covers Ubuntu 22.04 and 24.04 once pushed to a repository with Actions enabled.
