#!/bin/sh
# Regenerates the PNG figures used in ../03-specification.md from mockup.html.
# Needs Google Chrome. Each line is: frame number, file name, width, height
# (width and height must match the frame's size in mockup.html).
set -eu
cd "$(dirname "$0")"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"

while read -r frame name width height; do
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --force-device-scale-factor=2 --window-size="$width,$height" \
    --screenshot="$name.png" "file://$PWD/mockup.html?f=$frame" >/dev/null 2>&1
  echo "wrote $name.png"
done <<'EOF'
00 00-pipeline 1280 330
01 01-first-arrival 1440 800
02 02-one-value-selected 1440 800
03 03-levels-of-detail 1440 850
04 04-documents 900 440
05 05-source-html-view 900 400
06 06-record-folded-and-unfolded 1320 640
07 07-a-judgement-call 1440 900
08 08-stops-without-a-highlight 1440 400
09 09-course-list-and-run-report 1320 650
EOF
