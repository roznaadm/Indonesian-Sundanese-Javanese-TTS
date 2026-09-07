# 🇮🇩 Indonesian, Sundanese & Javanese AI TTS

A lightweight **Text-to-Speech (TTS) web application** built with **FastAPI** and **Edge TTS** for Indonesian, Sundanese, and Javanese voice generation.

The project is designed for local use and provides a simple browser interface for generating MP3 narration without building a separate frontend application.

## ✨ Features

- 🇮🇩 **Indonesian Standard** — male and female voices
- 🌿 **Sundanese** — native Sundanese voices
- 🗣️ **Indonesian + Sundanese Accent (Experimental)** — Indonesian voice with phonetic pronunciation hints intended to approximate Sundanese-influenced pronunciation
- 🪵 **Javanese Medok / Strong** — Javanese voice option
- 🌾 **Javanese Polite / Relaxed** — slower and softer Javanese style
- 🎭 Emotion / intonation presets:
  - 😊 Cheerful
  - 😢 Sad
  - 📜 Poetic
  - 👑 Authoritative
  - 👻 Horror
- ⚡ Adjustable speaking speed from **0.5x to 2.0x**
- 🎚️ Sundanese accent strength:
  - Light
  - Medium
  - Strong
- 🔊 Browser audio preview
- ⬇️ Download generated speech as MP3
- 🌐 REST API endpoint at `/api/generate`
- 🪟 Windows-compatible event-loop configuration
- 🛡️ Automatic TTS fallback when a voice rejects pitch/rate parameters

## 🎙️ Available Voices

| Mode | Male | Female |
|---|---|---|
| Indonesian Standard | `id-ID-ArdiNeural` | `id-ID-GadisNeural` |
| Sundanese | `su-ID-JajangNeural` | `su-ID-TutiNeural` |
| Indonesian + Sundanese Accent | `id-ID-ArdiNeural` | `id-ID-GadisNeural` |
| Javanese | `jv-ID-DimasNeural` | `jv-ID-SitiNeural` |

## ⚠️ About the Sundanese Accent Mode

The **Indonesia + Logat Sunda** mode is experimental.

It does **not** use a voice model specifically trained to speak Indonesian with a Sundanese accent. Instead, the application keeps an Indonesian Edge TTS voice and applies selected pronunciation hints to the input text, together with small speech parameter adjustments.

For example, selected words can receive pronunciation hints such as:

```text
film      → pilim
fokus     → pokus
foto      → poto
video     → pideo
versi     → persi
zaman     → saman
izin      → isin
```

For a genuinely natural Sundanese-accented Indonesian voice, a dedicated voice model trained on Indonesian speech from Sundanese speakers would be preferable.

## 🖥️ Requirements

- Windows 10/11, Linux, or macOS
- Python **3.9+**
- Internet connection for Edge TTS

## 📦 Installation

Clone the repository:

```bash
git clone https://github.com/roznaadm/Indonesian-Sundanese-Javanese-TTS.git
cd Indonesian-Sundanese-Javanese-TTS
```

Create a virtual environment (recommended):

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install fastapi uvicorn edge-tts pydantic
```

## 🚀 Run the Application

Start the server:

```bash
python indonesian_sunda_javanese_logat_ai_tts_fixed.py
```

Then open:

```text
http://127.0.0.1:8000
```

The application will display the TTS interface directly in your browser.

## 🔌 API Usage

The main endpoint is:

```text
POST /api/generate
```

Example request:

```json
{
  "text": "Halo, selamat datang di aplikasi TTS Indonesia.",
  "language": "Indonesia Standar",
  "gender": "Pria",
  "emotion": "Ceria",
  "speed": 1.0,
  "accent_strength": "Sedang"
}
```

The endpoint returns generated audio with MIME type:

```text
audio/mpeg
```

### Example using Python

```python
import requests

payload = {
    "text": "Halo, selamat datang di aplikasi TTS.",
    "language": "Indonesia Standar",
    "gender": "Pria",
    "emotion": "Ceria",
    "speed": 1.0,
    "accent_strength": "Sedang"
}

response = requests.post(
    "http://127.0.0.1:8000/api/generate",
    json=payload
)

response.raise_for_status()

with open("output.mp3", "wb") as f:
    f.write(response.content)
```

Install the API client dependency if needed:

```bash
pip install requests
```

## 🧩 Project Structure

```text
Indonesian-Sundanese-Javanese-TTS/
│
├── indonesian_sunda_javanese_logat_ai_tts_fixed.py
└── README.md
```

## 🛠️ Technology Stack

- **Python**
- **FastAPI** — backend API
- **Uvicorn** — ASGI server
- **Edge TTS** — speech synthesis
- **Pydantic** — request validation
- **HTML / JavaScript / Tailwind CSS** — browser interface

## 📋 Input Limits

The API accepts up to **5,000 characters per request**.

Speaking speed is limited to:

```text
0.5x → 2.0x
```

## 🔒 Privacy

This application is intended to run locally, but the speech synthesis itself uses **Edge TTS**, so text sent to the Edge TTS service is processed through Microsoft's online speech service. Do not submit sensitive or confidential text unless you are comfortable with that processing model.

## 💡 Future Improvements

Possible future versions can add:

- Better Indonesian Sundanese-accent modeling
- More Indonesian regional accents
- Batch TXT-to-MP3 generation
- WAV output
- Voice presets
- Sentence-by-sentence generation
- Automatic subtitle generation
- Audio normalization
- Background music mixing
- Docker support
- API authentication
- Optional offline TTS models

## ⭐ Contributing

Issues, suggestions, and pull requests are welcome.

If this project is useful to you, consider giving the repository a ⭐ on GitHub.

## 📄 License

No license file has been added yet. Until a license is explicitly added to the repository, the source code should not be assumed to be freely redistributable.
