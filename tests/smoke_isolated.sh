#!/bin/bash
# Prueba cada endpoint aislado, en orden; se detiene en el primero que falla.
B=${B:-http://localhost:8077}
step(){ name=$1; want=$2; shift 2; code=$(curl -sS -o /tmp/r.out -w '%{http_code}' -m 300 "$@"); body=$(head -c 160 /tmp/r.out | tr -d '\n'); 
  if [ "$code" = "$want" ]; then echo "OK   $code $name  ${body:0:120}"; else echo "FAIL $code (esperaba $want) $name  $body"; exit 1; fi; }
j(){ python3 -c "import json;print(json.load(open('/tmp/r.out'))$1)"; }
step "GET /api/options" 200 $B/api/options
step "GET /api/motion_status" 200 $B/api/motion_status
step "POST /api/character" 200 -X POST -H 'Content-Type: application/json' -d '{"description":"mujer joven pelo rojo","seed":1234}' $B/api/character
IMG=$(j "['image_url']")
step "GET /api/img (Pollinations)" 200 "$B$IMG"; file /tmp/r.out | cut -c1-60
cp /tmp/r.out /tmp/char.png
step "POST /api/upload" 200 -F file=@/tmp/char.png $B/api/upload
UID_=$(j "['image_id']")
step "GET /api/upload/{uid}" 200 $B/api/upload/$UID_
step "POST /api/video (engine=static)" 200 -X POST -H 'Content-Type: application/json' -d "{\"image_id\":\"$UID_\",\"scene_prompt\":\"prueba aislada devin\",\"engine\":\"static\",\"voice\":\"none\"}" $B/api/video
VID=$(j "['video_id']")
for i in $(seq 1 30); do sleep 3; curl -s $B/api/video/$VID/status > /tmp/s.out; grep -q processing /tmp/s.out || break; done
step "GET /api/video/{vid}/status" 200 $B/api/video/$VID/status
step "GET /api/video/{vid}/final.mp4" 200 -L $B/api/video/$VID/final.mp4; file /tmp/r.out | cut -c1-70
step "GET /api/video/{vid}/preview.png" 200 $B/api/video/$VID/preview.png
step "GET /api/feed (lista)" 200 $B/api/feed; python3 -c "import json;v=json.load(open('/tmp/r.out'))['videos'];print('     feed tiene',len(v),'videos; nuevo incluido:', any(x['video_id']=='$VID' for x in v))"
step "GET /api/video/{vid} (obtener)" 200 $B/api/video/$VID
step "PUT /api/video/{vid} (actualizar)" 200 -X PUT -H 'Content-Type: application/json' -d '{"scene":"escena editada"}' $B/api/video/$VID
step "GET /api/video/{vid} tras PUT" 200 $B/api/video/$VID; grep -q "escena editada" /tmp/r.out && echo "     update persistido" || { echo "FAIL update no persistió"; exit 1; }
step "PUT scene vacía -> 400" 400 -X PUT -H 'Content-Type: application/json' -d '{"scene":" "}' $B/api/video/$VID
step "DELETE /api/video/{vid}" 200 -X DELETE $B/api/video/$VID
step "GET /api/video/{vid} tras DELETE -> 404" 404 $B/api/video/$VID
step "DELETE id inexistente -> 404" 404 -X DELETE $B/api/video/0000000000
echo "TODO OK"
