#!/bin/bash
# Cube Radar 一键启动
cd "$(dirname "$0")"

pkill -f "http.server 8765" 2>/dev/null
sleep 0.5

echo "🔍 采集最新数据 + 生成 7 天报告..."
python3 __main__.py all --window 7d
LATEST=$(ls -t reports/report-*.html 2>/dev/null | head -1)
if [ -n "$LATEST" ]; then
    cp "$LATEST" reports/index.html
    echo "✅ 报告已生成"
fi

cd reports
python3 -m http.server 8765 &
sleep 1

open "http://127.0.0.1:8765/index.html"
