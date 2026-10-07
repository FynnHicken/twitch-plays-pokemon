#!/usr/bin/env bash
set -e

# Change to script directory
cd "$(dirname "$0")"

echo "=== 🎮 Twitch Plays Pokémon (Lokaler Start ohne Docker) ==="

# Check python3
if ! command -v python3 &> /dev/null; then
    echo "Fehler: python3 wurde nicht gefunden."
    exit 1
fi

# Create virtualenv if not exists
if [ ! -d "venv" ]; then
    echo "Erstelle Python Virtual Environment (venv)..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install requirements
echo "Installiere / Aktualisiere Abhängigkeiten..."
pip install --upgrade pip
pip install -r requirements.txt

# Start application
echo "Starte Twitch Plays Pokémon auf http://localhost:8080 ..."
python -m src.main
