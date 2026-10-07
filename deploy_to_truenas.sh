#!/usr/bin/env bash
set -e

TRUENAS_HOST="192.168.0.14"
TRUENAS_USER="${1:-admin}"
KEY_PATH="/Users/fynnhicken/.gemini/antigravity/scratch/truenas_key"
PROJECT_DIR="/Users/fynnhicken/.gemini/antigravity/scratch/twitch-plays-pokemon"
REMOTE_DIR="~/twitch-plays-pokemon"

echo "=== 🚀 Deploye Twitch Plays Pokémon auf TrueNAS ($TRUENAS_USER@$TRUENAS_HOST) ==="

# 1. Test SSH Connection
echo "Teste SSH-Verbindung..."
if ! ssh -i "$KEY_PATH" -o ConnectTimeout=5 -o BatchMode=yes "$TRUENAS_USER@$TRUENAS_HOST" "echo 'SSH-Verbindung erfolgreich!'" ; then
    echo "❌ SSH-Verbindung fehlgeschlagen!"
    echo "Bitte stelle sicher, dass der SSH-Public-Key auf TrueNAS hinterlegt wurde."
    exit 1
fi

# 2. Prepare remote directory
echo "Erstelle Zielverzeichnis auf TrueNAS..."
ssh -i "$KEY_PATH" "$TRUENAS_USER@$TRUENAS_HOST" "mkdir -p $REMOTE_DIR"

# 3. Sync project files
echo "Kopiere Projektdateien (inklusive ROM)..."
scp -i "$KEY_PATH" -r "$PROJECT_DIR"/* "$TRUENAS_USER@$TRUENAS_HOST:$REMOTE_DIR/"

# 4. Start Docker Compose on TrueNAS
echo "Baue und starte Docker-Container auf TrueNAS..."
ssh -i "$KEY_PATH" "$TRUENAS_USER@$TRUENAS_HOST" "cd $REMOTE_DIR && docker compose up -d --build"

echo ""
echo "=========================================================="
echo "✅ Erfolgreich auf TrueNAS bereitgestellt!"
echo "👉 Webinterface erreichbar unter: http://$TRUENAS_HOST:8080"
echo "=========================================================="
