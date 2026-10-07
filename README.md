# 🎮 Twitch Plays Pokémon - Docker Edition

Ein vollständiges, containerisiertes **Twitch Plays Pokémon**-System mit Retro-Webinterface, Game Boy Emulator (PyBoy), Live-Videostreaming, Chat, Anarchie- vs. Demokratie-Modus sowie optionaler nativer Twitch IRC-Anbindung.

---

## 🌟 Features

* **📦 Vollständig Dockerisiert:** Läuft mit einem einzigen Befehl via `docker compose`.
* **🕹️ PyBoy Game Boy Emulator:** Unterstützt Pokémon Rot/Blau/Gelb, Gold/Silber/Kristall sowie alle `.gb` und `.gbc` ROMs.
* **📺 Ultra-Low-Latency Web-Stream:** Nativer MJPEG-Stream direkt im Browser mit pixelgenauem Rendering und optionalem CRT-Scanline-Filter.
* **⚖️ Anarchie vs. Demokratie System:**
  * **Anarchie:** Jeder Befehl wird sofort chronologisch in einer Warteschlange ausgeführt.
  * **Demokratie:** Die Community stimmt in Runden (z. B. 10 Sekunden) ab; der Befehl mit den meisten Stimmen gewinnt.
  * **Tug-of-War Bar:** Zuschauer können `anarchy` oder `democracy` abstimmen, um den Modus dynamisch umzuschalten.
* **⚡ Befehls-Multiplikatoren:** Unterstützt Tasten-Wiederholungen wie `a3`, `up2`, `right5` (bis zu 9x).
* **🎮 Drei Steuerungsarten:**
  1. **Web-Chat & Text:** Befehle wie `a`, `b`, `up`, `down`, `left`, `right`, `start`, `select`, `wait`.
  2. **Virtueller Game Boy Controller:** Klick- und Touch-Steuerung für Steuerkreuz und Tasten.
  3. **Tastatur-Shortcuts:** Pfeiltasten für Bewegung, `Z` = A, `X` = B, `Enter` = Start, `Shift` = Select.
* **💬 Integrierter Chat:** Besucher des Webinterfaces können direkt miteinander chatten und mitspielen.
* **🟣 Optionale Twitch-Anbindung:** Lies echte Twitch-Chat-Nachrichten deines Kanals live ein (funktioniert auch anonym ohne OAuth-Token).
* **💾 Save-State & Battery-Save:** Spielstände (`.sav`) und automatisierte Schnellspeicherpunkte (`autosave.state`) bleiben dauerhaft im gemounteten `saves/`-Ordner erhalten.
* **🛡️ Standby-Schutz:** Startet auch ohne ROM im interaktiven Standby-Modus mit Hinweisen, ohne abzustürzen!

---

## 🚀 Schnellstart

### 1. Repository-Ordner vorbereiten
Navigiere in den Projektordner:
```bash
cd /Users/fynnhicken/.gemini/antigravity/scratch/twitch-plays-pokemon
```

### 2. ROM einfügen (Optional)
Kopiere deine Pokémon ROM (z. B. `Pokemon - Red Version.gb`) in den Ordner `roms/`:
```bash
cp /pfad/zu/deiner/rom.gb ./roms/
```
*(Hinweis: Falls du noch keine ROM ablegst, startet der Container mit einem animierten Standby-Bildschirm).*

### 3. Starten

#### Option A: Mit Docker (Empfohlen)
```bash
docker compose up -d --build
```

#### Option B: Direkt lokal mit Python (ohne Docker)
Falls du Docker nicht installiert hast, kannst du das Projekt direkt starten:
```bash
./run.sh
```

### 4. Öffnen im Browser
Rufe im Browser auf:
👉 **[http://localhost:8080](http://localhost:8080)**

---

## 🎮 Steuerung & Befehle

Im Web-Chat oder im Twitch-Chat können folgende Befehle eingegeben werden:

| Befehl | Alternative | Funktion |
| :--- | :--- | :--- |
| `a` | `a1` bis `a9` | A-Knopf (Interagieren, Bestätigen) |
| `b` | `b1` bis `b9` | B-Knopf (Abbrechen, Menü zurück) |
| `up` | `u`, `oben`, `up2`... | Nach oben bewegen |
| `down` | `d`, `unten`, `down2`... | Nach unten bewegen |
| `left` | `l`, `links`, `left2`... | Nach links bewegen |
| `right` | `r`, `rechts`, `right2`... | Nach rechts bewegen |
| `start` | `start` | Start-Menü öffnen |
| `select` | `select` | Select-Taste |
| `wait` | `wait` | Kurz warten / Emulation laufen lassen |
| `anarchy` | - | Stimme für Anarchie-Modus |
| `democracy` | - | Stimme für Demokratie-Modus |

### Tastatur-Shortcuts im Webinterface:
* **Pfeiltasten** (▲ / ▼ / ◀ / ▶): Steuerkreuz
* **Z**: A-Knopf
* **X**: B-Knopf
* **Enter**: Start
* **Shift**: Select

---

## ⚙️ Konfiguration (`.env`)

Du kannst eine `.env`-Datei anlegen oder `docker-compose.yml` bearbeiten:

```ini
# Webserver Port
PORT=8080

# Bildwiederholrate des Streams
FPS=30

# Start-Modus: anarchy oder democracy
DEFAULT_MODE=anarchy

# Sekunden pro Abstimmung im Demokratie-Modus
DEMOCRACY_INTERVAL=10

# Automatisches Speicherintervall in Sekunden
AUTO_SAVE_INTERVAL=60

# --- Twitch IRC Integration (Optional) ---
# Trage deinen Kanal ein, um echten Twitch-Chat einzubinden:
TWITCH_CHANNEL=mein_twitch_kanal

# Optional (nur nötig, falls der Bot im Twitch-Chat schreiben soll):
# TWITCH_TOKEN=oauth:dein_token
```

---

## 🛠️ REST API & Endpunkte

Das System stellt eine REST-Schnittstelle bereit:

* **`GET /stream`** – Live MJPEG Video Stream
* **`GET /health`** – Healthcheck für Docker und Überwachung
* **`GET /api/status`** – Aktueller Spielstatus, FPS, Stimmenverteilung und History
* **`POST /api/save`** – Erzwingt sofortige Speicherung des Spielstands
* **`POST /api/input`** – Befehl per JSON senden:
  ```json
  {
    "command": "a",
    "user": "DiscordBot"
  }
  ```
* **`WS /ws`** – Bidirektionaler WebSocket für Live-Chat, Steuerung und UI-Sync

---

## 📁 Projektstruktur

```
twitch-plays-pokemon/
├── Dockerfile              # Container-Build mit Python 3.11 und SDL2
├── docker-compose.yml      # Service-Definition und Volume-Mounts
├── requirements.txt        # PyBoy, FastAPI, Pillow, Websockets
├── .env.example            # Vorlage für Umgebungsvariablen
├── README.md               # Dokumentation
├── roms/                   # Ordner für deine .gb / .gbc ROMs
│   └── README.md
├── saves/                  # Persistente Speicherstände (.sav & .state)
├── src/
│   ├── config.py           # Pydantic-Konfiguration
│   ├── emulator.py         # PyBoy Manager & Frame Capture
│   ├── game_mode.py        # Anarchie / Demokratie Logik & Multiplikatoren
│   ├── twitch_bot.py       # Asynchroner Twitch IRC Bot
│   └── main.py             # FastAPI App, WebSocket Hub & Background Tasks
└── static/
    ├── index.html          # Game Boy Retro Web UI
    ├── style.css           # Pixel-Design & CRT-Scanlines
    └── app.js              # WebSocket-Handler, Audio-Beeps & Controller
```

---

## 🛑 Container stoppen

```bash
docker compose down
```
Dein Spielstand im Ordner `saves/` bleibt dabei vollständig erhalten!
