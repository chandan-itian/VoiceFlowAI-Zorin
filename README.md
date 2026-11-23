# VoiceFlow AI for Zorin OS

Online desktop dictation for Roman Hinglish, Hindi and English. Use one provider and model for speech recognition and another for text refinement. The default pairs Groq Whisper Large V3 with Llama 3.1 8B Instant. The desktop launcher uses the Android app’s five-bar logo.

## Preview

![VoiceFlow AI desktop window with an example Roman Hinglish result](docs/desktop-preview.png)

## Install

Download [the Debian installer from Releases](https://github.com/chandan-itian/VoiceFlowAI-Zorin/releases/latest). In the directory containing the downloaded package, run:

```sh
sudo apt install ./voiceflow-zorin_0.1.0_all.deb
```

Open **VoiceFlow AI** from the applications menu. The package targets Zorin OS 17 and 18 and their Ubuntu 22.04 and 24.04 bases. It uses Python 3, GTK 3, FFmpeg and the desktop Secret Service. No local AI model download is required.

## Dictate

1. Open **Settings → Providers**, choose a provider, enter your API key and click **Save key to desktop keyring**. **Test connection** checks the provider’s model list. A custom service without a model list can still accept dictation via a manually entered model ID.
2. Under **Dictation**, select the speech provider/model and optional refinement provider/model separately. Choose **Roman Hinglish** to keep Hindi in Latin letters and English in standard English spelling. Save settings.
3. Click **Start dictation**, speak, then **Stop and transcribe**. Compare the original transcript and formatted text in their tabs. Click **Copy result** to paste it elsewhere. Recording stops automatically after five minutes.
4. For use from another app, click **Register shortcuts in GNOME Settings** in the Providers tab. **Super + Shift + Space** starts or finishes dictation. **Super + Shift + Esc** cancels during capture. Within the VoiceFlow window, Esc also cancels. Keyboard Settings can bind custom shortcuts to `voiceflow-zorin --toggle` and `voiceflow-zorin --cancel` if the defaults conflict.
5. Closing the window hides the app so shortcuts continue working. **Quit** exits it.

On **X11**, shortcut dictation copies the result and can paste into the original window if it is still active. Recognized terminal windows use Ctrl+Shift+V. The app never sends Enter. On **Wayland**, the result window opens so you can click **Copy result** and paste it yourself. The shortcut works through the desktop’s keyboard settings. GNOME notifications report recording and processing while the app is in the background.

## Providers

| Provider | Audio | Refinement |
| --- | --- | --- |
| Groq | Whisper transcription API | Chat completions with configurable 429 fallback |
| OpenAI | Audio transcription API | Chat completions |
| Gemini | Native generateContent with FLAC audio | Native generateContent |
| OpenRouter | | Chat completions |
| Custom | OpenAI-compatible multipart /audio/transcriptions | OpenAI-compatible /chat/completions |

Model IDs and availability depend on the account. **Fetch** lists candidates and each model field accepts a manual ID. For a custom endpoint, include the API prefix, for example `https://host.example/v1`. HTTPS and loopback HTTP endpoints are supported. Custom keys are scoped to the exact base URL. If the key changes, save its replacement in Providers.

Groq formatting retries the same transcript on 429 using the configured fallback list. The default backups are GPT-OSS 20B and Llama 3.3 70B Versatile. Audio is uploaded once. If refinement fails, the original transcript is available. A transcription error is shown directly.

## Data handling

Your selected speech provider receives audio, and the selected refinement provider receives the transcript when refinement is enabled. Captures use 16 kHz mono AAC/M4A or FLAC for Gemini. Temporary recordings are removed on normal completion, failure and cancellation. Results stay in application memory until replaced or the app exits. The desktop clipboard and any clipboard manager follow the system’s retention settings. Credentials use Secret Service. Preferences live under `~/.config/voiceflow-zorin/`.

## Build and verify

```sh
./packaging/build-deb.sh
/usr/bin/python3 -m unittest discover -s tests -v
```

The CI workflow installs the package on both Ubuntu bases. Tests use controlled HTTP responses so they can exercise success and quota failures without a paid key. The X11 integration check uses PulseAudio, a keyring, a local HTTP endpoint and a separate GTK editor. The Wayland check runs the settings and result flow under a headless Weston compositor. These checks do not measure live provider accuracy, hardware microphone quality or Zorin Shell shortcut conflicts. [See verification runs](https://github.com/chandan-itian/VoiceFlowAI-Zorin/actions/workflows/verify.yml).
