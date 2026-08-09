#!/usr/bin/env bash
# demo_up.sh — bringt die SnapPlan-Demo idempotent online:
#   1) FastAPI-Backend auf Port 8001 (falls nicht schon oben)
#   2) cloudflared-Quick-Tunnel -> öffentliche HTTPS-URL
#   3) Vercel-Env NEXT_PUBLIC_SNAPGRID_API_URL = Tunnel-URL (alle Targets, sauber neu gesetzt)
#   4) Production-Deployment aus GitHub main -> snapplan.tech
#   5) wartet auf READY und testet /health + Extraktion durch den Tunnel
#
# Aufruf:  bash demo_up.sh
# Voraussetzung: in diesem Terminal eingeloggt bei `vercel` (Token unter
#   ~/Library/Application Support/com.vercel.cli/auth.json). Backend-.env enthält SNAPGRID_ANTHROPIC_API_KEY.
#
# WICHTIG: Dieses Skript-Terminal MUSS während der Demo offen bleiben — Backend und
# Tunnel laufen als Kindprozesse. Schließt du es, gehen beide aus.
set -euo pipefail

REPO="/Users/clarence/Desktop/SnapPlan"
BACKEND="$REPO/backend"
PORT=8001
PROJ="prj_YJlaTHmlM4yKhr3mDCQWDJbFC9uZ"
TEAM="team_YvGNhIXh1XyoaGEJTPNjUivN"
REPOID=1133562193
AUTH="$HOME/Library/Application Support/com.vercel.cli/auth.json"
TOKEN="$(python3 -c "import json;print(json.load(open('$AUTH'))['token'])")"

api() { curl -s -m 30 -H "Authorization: Bearer $TOKEN" "$@"; }

echo "==> 1/5  Backend auf Port $PORT"
if curl -s -m 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo "    Backend läuft bereits."
else
  ( cd "$BACKEND" && nohup venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" \
      > /tmp/snapplan_backend.log 2>&1 & )
  for i in $(seq 1 30); do
    curl -s -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break; sleep 1
  done
  echo "    Backend gestartet."
fi

echo "==> 2/5  cloudflared-Tunnel"
pkill -f "cloudflared tunnel --url http://127.0.0.1:$PORT" 2>/dev/null || true
sleep 1
nohup cloudflared tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate > /tmp/cloudflared.log 2>&1 &
TUNNEL=""
for i in $(seq 1 40); do
  TUNNEL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | head -1 || true)"
  [ -n "$TUNNEL" ] && break; sleep 1
done
[ -z "$TUNNEL" ] && { echo "    FEHLER: keine Tunnel-URL"; exit 1; }
echo "    Tunnel: $TUNNEL"

echo "==> 3/5  Vercel-Env setzen (alte SNAPGRID-Einträge entfernen, neu anlegen)"
api "https://api.vercel.com/v9/projects/$PROJ/env?teamId=$TEAM" \
 | python3 -c "import json,sys;[print(e['id']) for e in json.load(sys.stdin).get('envs',[]) if e.get('key')=='NEXT_PUBLIC_SNAPGRID_API_URL']" \
 | while read -r id; do api -X DELETE "https://api.vercel.com/v9/projects/$PROJ/env/$id?teamId=$TEAM" -o /dev/null; done
api -X POST "https://api.vercel.com/v10/projects/$PROJ/env?teamId=$TEAM" \
  -H "Content-Type: application/json" \
  -d "{\"key\":\"NEXT_PUBLIC_SNAPGRID_API_URL\",\"value\":\"$TUNNEL\",\"type\":\"encrypted\",\"target\":[\"production\",\"preview\",\"development\"]}" \
  -o /dev/null
echo "    Env gesetzt."

echo "==> 4/5  Production-Deployment aus GitHub main"
DPL="$(api -X POST "https://api.vercel.com/v13/deployments?teamId=$TEAM&forceNew=1" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"snap-plan-final\",\"project\":\"$PROJ\",\"target\":\"production\",\"gitSource\":{\"type\":\"github\",\"repoId\":$REPOID,\"ref\":\"main\"}}" \
  | python3 -c "import json,sys;print(json.load(sys.stdin).get('id',''))")"
[ -z "$DPL" ] && { echo "    FEHLER: Deployment nicht gestartet"; exit 1; }
echo "    Deployment: $DPL  (Build läuft ~60-90s)"
for i in $(seq 1 60); do
  ST="$(api "https://api.vercel.com/v13/deployments/$DPL?teamId=$TEAM" | python3 -c "import json,sys;print(json.load(sys.stdin).get('readyState','?'))")"
  printf "\r    readyState=%s   " "$ST"
  case "$ST" in READY) echo; break;; ERROR|CANCELED) echo; echo "    BUILD FEHLGESCHLAGEN"; exit 1;; esac
  sleep 5
done

echo "==> 5/5  Test durch den Tunnel"
IP="$(dig +short @1.1.1.1 "${TUNNEL#https://}" | head -1)"
curl -s -m 15 --resolve "${TUNNEL#https://}:443:$IP" "$TUNNEL/health" -w "  (HTTP %{http_code})\n"
echo
echo "FERTIG. Live: https://snapplan.tech   |  Backend-URL: $TUNNEL"
echo "Dieses Terminal offen lassen!  Logs: /tmp/snapplan_backend.log  /tmp/cloudflared.log"
