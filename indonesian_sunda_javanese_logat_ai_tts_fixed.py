import asyncio
import re
import os
import sys
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
import edge_tts

# Pastikan Event Loop policy kompatibel untuk Windows 11
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = FastAPI(
    title="Indonesian, Sundanese & Javanese AI Text-to-Speech Generator",
    description="Aplikasi Text-to-Speech Bahasa Indonesia, Sunda, dan Jawa berbasis Edge TTS",
    version="1.0.1"
)

# Aktifkan CORS untuk akses fleksibel lokal
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Teks narasi yang akan diubah menjadi suara")
    language: str = Field(..., description="Indonesia, Sunda, Indonesia Logat Sunda eksperimental, atau Jawa")
    gender: str = Field(..., description="Pria atau Wanita")
    emotion: str = Field("Ceria", description="Ceria, Sedih, Puitis, Berwibawa, atau Seram")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Kecepatan bicara dari 0.5x sampai 2.0x")
    accent_strength: str = Field("Sedang", description="Kekuatan simulasi logat Sunda: Ringan, Sedang, atau Kental")

VOICE_MAP = {
    "Indonesia Standar": {
        "Pria": "id-ID-ArdiNeural",
        "Wanita": "id-ID-GadisNeural"
    },
    "Sunda": {
        "Pria": "su-ID-JajangNeural",
        "Wanita": "su-ID-TutiNeural"
    },
    "Indonesia Logat Sunda (eksperimental)": {
        "Pria": "id-ID-ArdiNeural",
        "Wanita": "id-ID-GadisNeural"
    },
    "Jawa Medok/Kental": {
        "Pria": "jv-ID-DimasNeural",
        "Wanita": "jv-ID-SitiNeural"
    },
    "Jawa Halus/Santai": {
        "Pria": "jv-ID-DimasNeural",
        "Wanita": "jv-ID-SitiNeural"
    }
}

EMOTION_SETTINGS = {
    "Ceria": {"pitch": "+8Hz", "rate_delta": 10},
    "Sedih": {"pitch": "-8Hz", "rate_delta": -15},
    "Puitis": {"pitch": "+3Hz", "rate_delta": -10},
    "Berwibawa": {"pitch": "-10Hz", "rate_delta": -5},
    "Seram": {"pitch": "-15Hz", "rate_delta": -20}
}

DIALECT_SETTINGS = {
    "Indonesia Standar": {"rate_delta": 0},
    "Sunda": {"rate_delta": 0},
    "Indonesia Logat Sunda (eksperimental)": {"rate_delta": -3},
    "Jawa Medok/Kental": {"rate_delta": 0},
    "Jawa Halus/Santai": {"rate_delta": -5}
}


# ---------------------------------------------------------------------------
# SIMULASI LOGAT SUNDA UNTUK TEKS INDONESIA
# ---------------------------------------------------------------------------
# Edge TTS tidak menyediakan voice khusus "Bahasa Indonesia + aksen Sunda".
# Mode ini tetap memakai voice Indonesia dan menambahkan pronunciation hints
# pada sejumlah kata. Ini pendekatan fonetik, bukan model suara yang dilatih
# khusus pada penutur Indonesia berlogat Sunda.

SUNDA_ACCENT_WORDS = {
    "film": "pilim",
    "fokus": "pokus",
    "foto": "poto",
    "fotografi": "potograpi",
    "fakta": "pakta",
    "fiksi": "piksi",
    "fisik": "pisik",
    "fitur": "pitur",
    "formal": "pormal",
    "format": "pormat",
    "favorit": "paporit",
    "festival": "pestipal",
    "video": "pideo",
    "vitamin": "pitamin",
    "versi": "persi",
    "visual": "pisual",
    "universitas": "unipersitas",
    "zona": "sona",
    "zaman": "saman",
    "izin": "isin",
    "rezeki": "reski",
    "informasi": "inpormasi",
}

def apply_sundanese_accent(text: str, strength: str = "Sedang") -> str:
    """Memberi petunjuk pengucapan untuk simulasi logat Sunda.

    Ringan : perubahan sangat sedikit.
    Sedang : rekomendasi untuk narasi.
    Kental : pronunciation hint lebih terasa.

    Bahasa dan makna kalimat tetap Indonesia.
    """
    strength = strength if strength in {"Ringan", "Sedang", "Kental"} else "Sedang"
    result = text

    for original, spoken in SUNDA_ACCENT_WORDS.items():
        result = re.sub(
            rf"(?<![\w]){re.escape(original)}(?![\w])",
            spoken,
            result,
            flags=re.IGNORECASE,
        )

    if strength == "Ringan":
        # Hilangkan beberapa perubahan yang lebih kuat.
        for original in ["festival", "universitas", "informasi", "visual", "rezeki"]:
            spoken = SUNDA_ACCENT_WORDS[original]
            result = re.sub(
                rf"(?<![\w]){re.escape(spoken)}(?![\w])",
                original,
                result,
                flags=re.IGNORECASE,
            )
    elif strength == "Kental":
        result = re.sub(r"(?i)\bfoto-foto\b", "poto-poto", result)
        result = re.sub(r"(?i)\bfokusnya\b", "pokusnya", result)

    return result

def calculate_tts_parameters(language: str, gender: str, emotion: str, user_speed: float):
    """Menghitung voice ID, rate, dan pitch berdasarkan konfigurasi pengguna."""
    lang_voices = VOICE_MAP.get(language, VOICE_MAP["Indonesia Standar"])
    voice = lang_voices.get(gender, lang_voices["Pria"])

    base_speed_pct = int((user_speed - 1.0) * 100)
    emotion_info = EMOTION_SETTINGS.get(emotion, EMOTION_SETTINGS["Ceria"])
    dialect_info = DIALECT_SETTINGS.get(language, DIALECT_SETTINGS["Indonesia Standar"])

    total_rate_pct = base_speed_pct + emotion_info["rate_delta"] + dialect_info["rate_delta"]
    rate_str = f"{total_rate_pct:+d}%"
    pitch_str = emotion_info["pitch"]

    # Experimental only: this still uses an Indonesian voice, so it is not
    # a true Sundanese accent. The effect is intentionally subtle.
    if language == "Indonesia Logat Sunda (eksperimental)":
        if emotion == "Ceria":
            pitch_str = "+6Hz"
        elif emotion == "Sedih":
            pitch_str = "-6Hz"
        elif emotion == "Puitis":
            pitch_str = "+2Hz"
        elif emotion == "Berwibawa":
            pitch_str = "-8Hz"
        elif emotion == "Seram":
            pitch_str = "-12Hz"

    return voice, rate_str, pitch_str

async def synthesize_edge_tts(text: str, voice: str, rate: str, pitch: str) -> bytes:
    """
    Menjalankan proses pembuatan audio menggunakan edge-tts
    dengan penanganan fallback jika parameter pitch ditolak oleh model suara tertentu.
    """
    # Percobaan 1: Menggunakan Rate & Pitch penuh
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
        audio_buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.extend(chunk["data"])
        if audio_buffer:
            return bytes(audio_buffer)
    except Exception:
        pass

    # Percobaan 2: Menggunakan Rate saja dengan Pitch netral (cocok untuk suara Jawa yang sensitif terhadap pitch)
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch="+0Hz")
        audio_buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.extend(chunk["data"])
        if audio_buffer:
            return bytes(audio_buffer)
    except Exception:
        pass

    # Percobaan 3: Menggunakan konfigurasi dasar tanpa modifikasi
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice)
        audio_buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.extend(chunk["data"])
        if audio_buffer:
            return bytes(audio_buffer)
    except Exception as e:
        raise RuntimeError(f"Gagal menghubungi server Edge TTS. Pastikan koneksi internet aktif. Error: {str(e)}")

    raise RuntimeError("Tidak ada data audio yang dihasilkan dari server TTS.")

HTML_CONTENT = """<!DOCTYPE html>
<html lang="id" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Indonesian, Sundanese & Javanese AI Text-to-Speech Generator</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Plus Jakarta Sans', 'sans-serif'],
                    },
                    colors: {
                        brand: {
                            500: '#6366f1',
                            600: '#4f46e5',
                            700: '#4338ca',
                        }
                    }
                }
            }
        }
    </script>
    <style>
        .glass-panel {
            background: rgba(30, 41, 59, 0.7);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .custom-scrollbar::-webkit-scrollbar {
            width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
            background: rgba(15, 23, 42, 0.6);
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
            background: rgba(99, 102, 241, 0.4);
            border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
            background: rgba(99, 102, 241, 0.7);
        }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 font-sans min-h-screen flex flex-col antialiased selection:bg-brand-500 selection:text-white">

    <!-- Header Navigation -->
    <header class="border-b border-slate-800/80 bg-slate-900/50 backdrop-blur-md sticky top-0 z-50">
        <div class="max-w-6xl mx-auto px-4 py-4 sm:px-6 lg:px-8 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="h-10 w-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
                    <i class="fa-solid fa-wand-magic-sparkles text-white text-lg"></i>
                </div>
                <div>
                    <h1 class="text-base sm:text-lg font-bold bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400">
                        Indonesian & Javanese AI TTS
                    </h1>
                    <p class="text-xs text-slate-400">FastAPI & Edge TTS Engine</p>
                </div>
            </div>
            <div class="flex items-center space-x-2">
                <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse mr-2"></span> Sistem Aktif
                </span>
            </div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="flex-1 max-w-6xl w-full mx-auto px-4 py-6 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-12 gap-6">

        <!-- Controls Column -->
        <div class="lg:col-span-5 space-y-5">
            <div class="glass-panel p-5 rounded-2xl space-y-5">
                
                <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                    <h2 class="text-sm font-semibold text-slate-200 tracking-wide uppercase flex items-center gap-2">
                        <i class="fa-solid fa-sliders text-indigo-400"></i> Pengaturan Suara
                    </h2>
                </div>

                <!-- Bahasa / Logat -->
                <div class="space-y-2">
                    <label class="text-xs font-medium text-slate-300 flex items-center justify-between">
                        <span>Bahasa / Logat</span>
                        <span class="text-slate-500 text-[10px]">Pilih bahasa / karakter pengucapan</span>
                    </label>
                    <div class="grid grid-cols-1 gap-2">
                        <label class="relative flex items-center p-3 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition-all">
                            <input type="radio" name="language" value="Indonesia Standar" checked class="sr-only peer">
                            <div class="w-4 h-4 rounded-full border border-slate-600 peer-checked:border-indigo-500 peer-checked:bg-indigo-500 flex items-center justify-center transition-all">
                                <div class="w-1.5 h-1.5 rounded-full bg-white opacity-0 peer-checked:opacity-100"></div>
                            </div>
                            <div class="ml-3 flex items-center space-x-2">
                                <span class="text-lg">🇮🇩</span>
                                <span class="text-sm font-medium text-slate-200 peer-checked:text-indigo-400">Indonesia Standar</span>
                            </div>
                        </label>

                        <label class="relative flex items-center p-3 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition-all">
                            <input type="radio" name="language" value="Sunda" class="sr-only peer">
                            <div class="w-4 h-4 rounded-full border border-slate-600 peer-checked:border-indigo-500 peer-checked:bg-indigo-500 flex items-center justify-center transition-all">
                                <div class="w-1.5 h-1.5 rounded-full bg-white opacity-0 peer-checked:opacity-100"></div>
                            </div>
                            <div class="ml-3 flex items-center space-x-2">
                                <span class="text-lg">🌿</span>
                                <div>
                                    <span class="text-sm font-medium text-slate-200">Sunda</span>
                                    <p class="text-[11px] text-slate-500">Bahasa Sunda · suara Jajang/Tuti</p>
                                </div>
                            </div>
                        </label>

                        <label class="relative flex items-center p-3 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition-all">
                            <input type="radio" name="language" value="Indonesia Logat Sunda (eksperimental)" class="sr-only peer">
                            <div class="w-4 h-4 rounded-full border border-slate-600 peer-checked:border-indigo-500 peer-checked:bg-indigo-500 flex items-center justify-center transition-all">
                                <div class="w-1.5 h-1.5 rounded-full bg-white opacity-0 peer-checked:opacity-100"></div>
                            </div>
                            <div class="ml-3 flex items-center space-x-2">
                                <span class="text-lg">🗣️</span>
                                <div>
                                    <span class="text-sm font-medium text-slate-200">Indonesia + Logat Sunda</span>
                                    <p class="text-[11px] text-slate-500">Simulasi fonetik Bahasa Indonesia berlogat Sunda</p>
                                </div>
                            </div>
                        </label>

                        <label class="relative flex items-center p-3 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition-all">
                            <input type="radio" name="language" value="Jawa Medok/Kental" class="sr-only peer">
                            <div class="w-4 h-4 rounded-full border border-slate-600 peer-checked:border-indigo-500 peer-checked:bg-indigo-500 flex items-center justify-center transition-all">
                                <div class="w-1.5 h-1.5 rounded-full bg-white opacity-0 peer-checked:opacity-100"></div>
                            </div>
                            <div class="ml-3 flex items-center space-x-2">
                                <span class="text-lg">🪵</span>
                                <div>
                                    <span class="text-sm font-medium text-slate-200">Jawa Medok / Kental</span>
                                    <p class="text-[11px] text-slate-500">Dialek ekspresif khas Jawa</p>
                                </div>
                            </div>
                        </label>

                        <label class="relative flex items-center p-3 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition-all">
                            <input type="radio" name="language" value="Jawa Halus/Santai" class="sr-only peer">
                            <div class="w-4 h-4 rounded-full border border-slate-600 peer-checked:border-indigo-500 peer-checked:bg-indigo-500 flex items-center justify-center transition-all">
                                <div class="w-1.5 h-1.5 rounded-full bg-white opacity-0 peer-checked:opacity-100"></div>
                            </div>
                            <div class="ml-3 flex items-center space-x-2">
                                <span class="text-lg">🌾</span>
                                <div>
                                    <span class="text-sm font-medium text-slate-200">Jawa Halus / Santai</span>
                                    <p class="text-[11px] text-slate-500">Nada santun & tenang</p>
                                </div>
                            </div>
                        </label>
                    </div>
                </div>

                <!-- Gender -->
                <div class="space-y-2">
                    <label class="text-xs font-medium text-slate-300">Jenis Kelamin / Narator</label>
                    <div class="grid grid-cols-2 gap-3">
                        <button type="button" onclick="selectGender('Pria')" id="btn-pria" class="gender-btn flex items-center justify-center space-x-2 py-2.5 px-4 rounded-xl bg-indigo-600 text-white font-medium text-sm transition-all border border-indigo-500 shadow-md shadow-indigo-600/20">
                            <i class="fa-solid fa-mars"></i>
                            <span>Pria</span>
                        </button>
                        <button type="button" onclick="selectGender('Wanita')" id="btn-wanita" class="gender-btn flex items-center justify-center space-x-2 py-2.5 px-4 rounded-xl bg-slate-900/80 text-slate-300 font-medium text-sm hover:bg-slate-800 transition-all border border-slate-800">
                            <i class="fa-solid fa-venus"></i>
                            <span>Wanita</span>
                        </button>
                    </div>
                </div>

                <!-- Emosi -->
                <div class="space-y-2">
                    <label class="text-xs font-medium text-slate-300">Intonasi & Emosi</label>
                    <div class="grid grid-cols-3 gap-2">
                        <button type="button" onclick="selectEmotion('Ceria')" id="emo-Ceria" class="emo-btn py-2 px-2 text-xs rounded-xl bg-slate-800 border border-indigo-500/50 text-indigo-300 font-medium text-center transition-all flex flex-col items-center gap-1">
                            <span>😊 Ceria</span>
                        </button>
                        <button type="button" onclick="selectEmotion('Sedih')" id="emo-Sedih" class="emo-btn py-2 px-2 text-xs rounded-xl bg-slate-900 border border-slate-800 text-slate-400 font-medium text-center hover:bg-slate-800 transition-all flex flex-col items-center gap-1">
                            <span>😢 Sedih</span>
                        </button>
                        <button type="button" onclick="selectEmotion('Puitis')" id="emo-Puitis" class="emo-btn py-2 px-2 text-xs rounded-xl bg-slate-900 border border-slate-800 text-slate-400 font-medium text-center hover:bg-slate-800 transition-all flex flex-col items-center gap-1">
                            <span>📜 Puitis</span>
                        </button>
                        <button type="button" onclick="selectEmotion('Berwibawa')" id="emo-Berwibawa" class="emo-btn py-2 px-2 text-xs rounded-xl bg-slate-900 border border-slate-800 text-slate-400 font-medium text-center hover:bg-slate-800 transition-all flex flex-col items-center gap-1">
                            <span>👑 Berwibawa</span>
                        </button>
                        <button type="button" onclick="selectEmotion('Seram')" id="emo-Seram" class="emo-btn py-2 px-2 text-xs rounded-xl bg-slate-900 border border-slate-800 text-slate-400 font-medium text-center hover:bg-slate-800 transition-all flex flex-col items-center gap-1 col-span-2">
                            <span>👻 Seram / Horor</span>
                        </button>
                    </div>
                </div>

                <!-- Kecepatan -->
                <div class="space-y-2 pt-1">
                    <div class="flex items-center justify-between">
                        <label class="text-xs font-medium text-slate-300">Kecepatan Bicara</label>
                        <span id="speed-val" class="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">1.0x</span>
                    </div>
                    <input type="range" id="speed-slider" min="0.5" max="2.0" step="0.1" value="1.0" oninput="updateSpeedDisplay(this.value)" class="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500">
                    <div class="flex justify-between text-[10px] text-slate-500 px-0.5">
                        <span>0.5x (Lambat)</span>
                        <span>1.0x (Normal)</span>
                        <span>2.0x (Cepat)</span>
                    </div>
                </div>

                <!-- Kekuatan Logat Sunda -->
                <div id="sunda-accent-control" class="space-y-2 pt-1 hidden">
                    <div class="flex items-center justify-between">
                        <label class="text-xs font-medium text-slate-300">Kekuatan Logat Sunda</label>
                        <span class="text-[10px] text-slate-500">Khusus Indonesia + Logat Sunda</span>
                    </div>
                    <select id="accent-strength" class="w-full p-2.5 rounded-xl bg-slate-900/80 border border-slate-800 text-slate-200 text-xs focus:outline-none focus:border-indigo-500">
                        <option value="Ringan">Ringan — paling halus</option>
                        <option value="Sedang" selected>Sedang — rekomendasi</option>
                        <option value="Kental">Kental — paling terasa</option>
                    </select>
                    <p class="text-[10px] text-slate-500 leading-relaxed">
                        Bahasa tetap Indonesia. Sistem memberi pronunciation hint pada kata tertentu agar karakter pengucapan lebih mendekati penutur berlogat Sunda.
                    </p>
                </div>

            </div>
        </div>

        <!-- Input & Player Column -->
        <div class="lg:col-span-7 space-y-5 flex flex-col">
            
            <div class="glass-panel p-5 rounded-2xl space-y-3 flex-1 flex flex-col">
                <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                    <h2 class="text-sm font-semibold text-slate-200 tracking-wide uppercase flex items-center gap-2">
                        <i class="fa-solid fa-pen-nib text-indigo-400"></i> Masukkan Narasi
                    </h2>
                    <div class="flex items-center space-x-2">
                        <button onclick="insertSample('id')" class="text-[11px] px-2 py-1 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition-all">
                            Contoh ID
                        </button>
                        <button onclick="insertSample('su')" class="text-[11px] px-2 py-1 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition-all">
                            Contoh Sunda
                        </button>
                        <button onclick="insertSample('jv')" class="text-[11px] px-2 py-1 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 transition-all">
                            Contoh Jawa
                        </button>
                        <button onclick="clearText()" class="text-[11px] px-2 py-1 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-all">
                            Hapus
                        </button>
                    </div>
                </div>

                <div class="relative flex-1 flex flex-col">
                    <textarea id="text-input" placeholder="Tuliskan teks narasi yang ingin disuarakan di sini..." class="w-full flex-1 p-4 rounded-xl bg-slate-900/80 border border-slate-800 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 resize-none custom-scrollbar text-sm leading-relaxed min-h-[200px]" oninput="updateCharCount()"></textarea>
                    
                    <div class="flex justify-between items-center text-[11px] text-slate-500 mt-2 px-1">
                        <span id="char-count">0 karakter</span>
                        <span>Mendukung hingga 5.000 karakter</span>
                    </div>
                </div>

                <button id="generate-btn" onclick="generateAudio()" class="w-full py-3.5 px-6 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-semibold text-sm shadow-lg shadow-indigo-600/30 hover:shadow-indigo-600/50 transition-all flex items-center justify-center space-x-2 active:scale-[0.99]">
                    <i class="fa-solid fa-play text-xs" id="btn-icon"></i>
                    <span id="btn-text">Generate Audio Speech</span>
                </button>
            </div>

            <!-- Pesan Error -->
            <div id="error-box" class="hidden p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-start space-x-3">
                <i class="fa-solid fa-circle-exclamation text-base mt-0.5"></i>
                <div class="flex-1">
                    <span class="font-semibold block mb-0.5">Terjadi Masalah</span>
                    <span id="error-message">Gagal menghubungi server.</span>
                </div>
            </div>

            <!-- Progress Bar -->
            <div id="progress-box" class="hidden glass-panel p-5 rounded-2xl space-y-3">
                <div class="flex items-center justify-between text-xs font-medium text-slate-300">
                    <span class="flex items-center gap-2">
                        <i class="fa-solid fa-spinner animate-spin text-indigo-400"></i>
                        Sedang mensintesis audio suara...
                    </span>
                    <span class="text-indigo-400">Memproses Edge TTS...</span>
                </div>
                <div class="w-full h-2 bg-slate-900 rounded-full overflow-hidden border border-slate-800">
                    <div class="h-full bg-gradient-to-r from-indigo-500 to-violet-500 w-full animate-pulse"></div>
                </div>
            </div>

            <!-- Player Hasil Audio -->
            <div id="audio-result-box" class="hidden glass-panel p-5 rounded-2xl space-y-4">
                <div class="flex items-center justify-between border-b border-slate-800 pb-3">
                    <div class="flex items-center space-x-2">
                        <div class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></div>
                        <h3 class="text-sm font-semibold text-slate-200">Hasil Audio Berhasil Dibuat</h3>
                    </div>
                    <span class="text-[11px] text-slate-400">Format MP3 (Stereo)</span>
                </div>

                <div class="bg-slate-900/90 p-3 rounded-xl border border-slate-800">
                    <audio id="audio-player" controls class="w-full h-10 accent-indigo-500">
                        Browser Anda tidak mendukung audio player.
                    </audio>
                </div>

                <div class="flex items-center gap-3">
                    <a id="download-btn" href="#" download="suara_ai.mp3" class="flex-1 py-2.5 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs text-center flex items-center justify-center space-x-2 shadow-md shadow-emerald-600/20 transition-all">
                        <i class="fa-solid fa-download"></i>
                        <span>Download Audio MP3</span>
                    </a>
                </div>
            </div>

        </div>
    </main>

    <footer class="border-t border-slate-800/80 py-4 mt-6 text-center text-xs text-slate-500">
        Indonesian & Javanese AI Text-to-Speech Generator &copy; 2026 - Edge TTS Local Backend
    </footer>

    <script>
        let selectedGender = "Pria";
        let selectedEmotion = "Ceria";
        let audioBlobUrl = null;

        function updateAccentControl() {
            const langRadio = document.querySelector('input[name="language"]:checked');
            const language = langRadio ? langRadio.value : "Indonesia Standar";
            const control = document.getElementById('sunda-accent-control');
            if (control) {
                control.classList.toggle('hidden', language !== "Indonesia Logat Sunda (eksperimental)");
            }
        }

        document.querySelectorAll('input[name="language"]').forEach(input => {
            input.addEventListener('change', updateAccentControl);
        });

        updateAccentControl();

        function selectGender(gender) {
            selectedGender = gender;
            document.querySelectorAll('.gender-btn').forEach(btn => {
                btn.classList.remove('bg-indigo-600', 'text-white', 'border-indigo-500', 'shadow-md', 'shadow-indigo-600/20');
                btn.classList.add('bg-slate-900/80', 'text-slate-300', 'border-slate-800');
            });

            const activeBtn = document.getElementById(gender === 'Pria' ? 'btn-pria' : 'btn-wanita');
            activeBtn.classList.remove('bg-slate-900/80', 'text-slate-300', 'border-slate-800');
            activeBtn.classList.add('bg-indigo-600', 'text-white', 'border-indigo-500', 'shadow-md', 'shadow-indigo-600/20');
        }

        function selectEmotion(emotion) {
            selectedEmotion = emotion;
            document.querySelectorAll('.emo-btn').forEach(btn => {
                btn.classList.remove('bg-slate-800', 'border-indigo-500/50', 'text-indigo-300');
                btn.classList.add('bg-slate-900', 'border-slate-800', 'text-slate-400');
            });

            const activeBtn = document.getElementById('emo-' + emotion);
            if (activeBtn) {
                activeBtn.classList.remove('bg-slate-900', 'border-slate-800', 'text-slate-400');
                activeBtn.classList.add('bg-slate-800', 'border-indigo-500/50', 'text-indigo-300');
            }
        }

        function updateSpeedDisplay(val) {
            document.getElementById('speed-val').innerText = parseFloat(val).toFixed(1) + 'x';
        }

        function updateCharCount() {
            const text = document.getElementById('text-input').value;
            document.getElementById('char-count').innerText = text.length + ' karakter';
        }

        function clearText() {
            document.getElementById('text-input').value = '';
            updateCharCount();
        }

        function insertSample(type) {
            const textInput = document.getElementById('text-input');
            if (type === 'id') {
                textInput.value = "Halo, selamat datang di aplikasi pengubah teks menjadi suara buatan lokal. Sistem ini menggunakan kecerdasan buatan untuk menghasilkan intonasi suara yang jernih dan alami.";
                document.querySelector('input[name="language"][value="Indonesia Standar"]').checked = true;
            } else if (type === 'su') {
                textInput.value = "Wilujeng sumping di aplikasi generator sora. Mugia aplikasi ieu tiasa ngabantosan anjeun nyieun narasi dina basa Sunda kalayan sora anu jelas tur alami.";
                document.querySelector('input[name="language"][value="Sunda"]').checked = true;
            } else if (type === 'jv') {
                textInput.value = "Sugeng rawuh wonten ing aplikasi generator swanten menika. Mugi-mugi aplikasi punika saget paring manfaat lan kemudahan kangge panjenengan sedaya.";
                document.querySelector('input[name="language"][value="Jawa Halus/Santai"]').checked = true;
            }
            updateCharCount();
        }

        function showError(msg) {
            const errorBox = document.getElementById('error-box');
            document.getElementById('error-message').innerText = msg;
            errorBox.classList.remove('hidden');
        }

        function hideError() {
            document.getElementById('error-box').classList.add('hidden');
        }

        async function generateAudio() {
            hideError();
            
            const text = document.getElementById('text-input').value.trim();
            if (!text) {
                showError("Silakan masukkan teks narasi terlebih dahulu.");
                return;
            }

            const langRadio = document.querySelector('input[name="language"]:checked');
            const language = langRadio ? langRadio.value : "Indonesia Standar";
            const speed = parseFloat(document.getElementById('speed-slider').value);

            const generateBtn = document.getElementById('generate-btn');
            const btnText = document.getElementById('btn-text');
            const btnIcon = document.getElementById('btn-icon');
            const progressBox = document.getElementById('progress-box');
            const audioResultBox = document.getElementById('audio-result-box');

            generateBtn.disabled = true;
            generateBtn.classList.add('opacity-75', 'cursor-not-allowed');
            btnText.innerText = "Memproses Suara...";
            btnIcon.className = "fa-solid fa-spinner animate-spin text-xs";
            progressBox.classList.remove('hidden');
            audioResultBox.classList.add('hidden');

            const payload = {
                text: text,
                language: language,
                gender: selectedGender,
                emotion: selectedEmotion,
                speed: speed,
                accent_strength: document.getElementById('accent-strength').value
            };

            try {
                const response = await fetch('/api/generate', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    let errDetail = "Gagal memproses audio.";
                    try {
                        const errJson = await response.json();
                        if (errJson.detail) errDetail = errJson.detail;
                    } catch(e) {}
                    throw new Error(errDetail);
                }

                const blob = await response.blob();
                
                if (audioBlobUrl) {
                    URL.revokeObjectURL(audioBlobUrl);
                }

                audioBlobUrl = URL.createObjectURL(blob);

                const audioPlayer = document.getElementById('audio-player');
                const downloadBtn = document.getElementById('download-btn');

                audioPlayer.src = audioBlobUrl;
                downloadBtn.href = audioBlobUrl;
                
                const safeName = language.replace(/[^a-zA-Z]/g, '_');
                downloadBtn.download = `TTS_${safeName}_${selectedGender}.mp3`;

                audioResultBox.classList.remove('hidden');
                audioPlayer.play().catch(() => {});

            } catch (err) {
                showError(err.message || "Terjadi masalah saat memproses audio.");
            } finally {
                generateBtn.disabled = false;
                generateBtn.classList.remove('opacity-75', 'cursor-not-allowed');
                btnText.innerText = "Generate Audio Speech";
                btnIcon.className = "fa-solid fa-play text-xs";
                progressBox.classList.add('hidden');
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Menyajikan antarmuka frontend HTML/CSS/JS"""
    return HTML_CONTENT

@app.post("/api/generate")
async def generate_speech(payload: TTSRequest):
    """
    Endpoint POST /api/generate.
    Mode Indonesia + Logat Sunda memakai voice Indonesia lalu memberi
    pronunciation hint agar karakter pengucapannya lebih mendekati
    penutur Indonesia berlogat Sunda.
    """
    clean_text = payload.text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Teks narasi tidak boleh kosong.")

    voice, rate_str, pitch_str = calculate_tts_parameters(
        language=payload.language,
        gender=payload.gender,
        emotion=payload.emotion,
        user_speed=payload.speed
    )

    speech_text = clean_text
    if payload.language == "Indonesia Logat Sunda (eksperimental)":
        speech_text = apply_sundanese_accent(
            clean_text,
            payload.accent_strength
        )

    try:
        audio_bytes = await synthesize_edge_tts(
            text=speech_text,
            voice=voice,
            rate=rate_str,
            pitch=pitch_str
        )

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "attachment; filename=suara_ai.mp3",
                "Cache-Control": "no-cache"
            }
        )

    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Terjadi kesalahan internal server: {str(e)}"
        )

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    print("==================================================================")
    print(" 🎙️ Indonesian & Javanese AI Text-to-Speech Generator")
    print(" Server berjalan di: http://127.0.0.1:8000")
    print(" Buka tautan di atas pada browser Anda.")
    print(" Tekan Ctrl + C untuk menghentikan server.")
    print("==================================================================")
    
    # Jalankan instance aplikasi FastAPI langsung tanpa reload string
    uvicorn.run(app, host="127.0.0.1", port=8000)
