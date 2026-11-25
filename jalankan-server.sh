#!/bin/bash
# Pemasangan/pembaruan ketabonline-kurasi di server, sekali jalan (dijadwalkan sebagai root, mis. systemd-run).
# Salinan file ini ditaruh di /disk6/shamela/ketabonline/jalankan.sh.
#
#   1. repo dari bundle -> /disk6/shamela/ketabonline-kurasi, push ke Forgejo   (sebagai user biasa)
#   2. ekspor judul kitab_golden dari shamela-golden-pg -> golden.csv
#   3. docker compose build, pencocokan (alat cocok), GUI naik di jaringan jalurgateway
#
# Tidak mengunduh isi kitab dan tidak menyentuh stack "shamela". Log: $K/jalankan.log
set -uo pipefail

K=${KETAB_FOLDER:-/disk6/shamela/ketabonline}
REPO=${KETAB_REPO:-/disk6/shamela/ketabonline-kurasi}
U=${KETAB_USER:-syarwani}
REPO_ACUAN=/disk6/shamela/shamela-kurasi          # remote Forgejo diturunkan dari repo ini
BUNDLE=$K/ketabonline-kurasi.bundle
LOG=$K/jalankan.log
GAGAL=0

exec >>"$LOG" 2>&1
echo
echo "=================== mulai $(date '+%F %T')"
langkah() { echo "--- $(date '+%T') $*"; }
gagal() { echo "!!! GAGAL: $*"; GAGAL=$((GAGAL + 1)); }
sbg() { sudo -u "$U" -H env GIT_TERMINAL_PROMPT=0 "$@"; }

# 1. repo ---------------------------------------------------------------------------------------------
langkah "repo"
if [ ! -f "$BUNDLE" ]; then
  gagal "bundle $BUNDLE tidak ada"
elif [ ! -d "$REPO/.git" ]; then
  install -d -o "$U" -g "$(id -gn "$U")" "$REPO"     # folder kosong milik user biasa, lalu clone ke dalamnya
  sbg git clone -b main "$BUNDLE" "$REPO" || gagal "clone dari bundle"
else
  sbg git -C "$REPO" fetch "$BUNDLE" main && sbg git -C "$REPO" merge --ff-only FETCH_HEAD || gagal "perbarui dari bundle"
fi
if [ -d "$REPO/.git" ]; then
  ACUAN=$(sbg git -C "$REPO_ACUAN" remote get-url origin 2>/dev/null || true)
  if [ -n "$ACUAN" ]; then
    URL=$(printf '%s' "$ACUAN" | sed -E 's#shamela-kurasi(\.git)?/?$#ketabonline-kurasi\1#')
    echo "remote Forgejo: $URL"
    sbg git -C "$REPO" remote remove origin 2>/dev/null
    sbg git -C "$REPO" remote add origin "$URL"
    timeout 180 sudo -u "$U" -H env GIT_TERMINAL_PROMPT=0 git -C "$REPO" push -u origin main || gagal "push ke Forgejo"
  else
    gagal "remote origin $REPO_ACUAN tidak terbaca; push Forgejo dilewati"
  fi
  sbg git -C "$REPO" log --oneline -3
fi

# 2. golden.csv ---------------------------------------------------------------------------------------
langkah "ekspor kitab_golden"
if docker ps --format '{{.Names}}' | grep -qx shamela-golden-pg; then
  docker exec shamela-golden-pg psql -U golden -d golden -v ON_ERROR_STOP=1 -c \
    "\copy (SELECT golden_id, shamela_id, judul, pengarang, wafat_h, kategori, jumlah_halaman, dup_syamilah_id FROM kitab_golden ORDER BY golden_id) TO STDOUT WITH CSV HEADER" \
    > "$K/golden.csv.baru" && mv "$K/golden.csv.baru" "$K/golden.csv" && chown "$U": "$K/golden.csv" \
    && echo "golden.csv: $(($(wc -l < "$K/golden.csv") - 1)) kitab" || gagal "ekspor kitab_golden"
else
  gagal "container shamela-golden-pg tidak berjalan; pencocokan Golden memakai golden.csv lama bila ada"
fi

# 3. docker -------------------------------------------------------------------------------------------
if [ -f "$REPO/docker-compose.yml" ]; then
  cd "$REPO" || exit 1
  export KETAB_UID KETAB_GID
  KETAB_UID=$(id -u "$U"); KETAB_GID=$(id -g "$U")
  langkah "docker compose build"
  docker compose build || gagal "build image"
  langkah "pencocokan"
  docker compose run --rm alat cocok || gagal "pencocokan"
  langkah "GUI"
  docker compose up -d gui || gagal "menyalakan GUI"
  sleep 15
  docker ps --filter name=ketabonline-gui --format '{{.Names}} {{.Status}}'
  docker exec ketabonline-gui python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/sehat',timeout=5).read().decode())" \
    || gagal "GUI tidak menjawab /sehat"
else
  gagal "docker-compose.yml tidak ada di $REPO"
fi

echo "=================== selesai $(date '+%F %T'), kegagalan: $GAGAL"
[ "$GAGAL" -eq 0 ] && echo OK > "$K/jalankan.status" || echo "GAGAL $GAGAL" > "$K/jalankan.status"
chown "$U": "$K/jalankan.status" "$LOG" 2>/dev/null
exit 0
