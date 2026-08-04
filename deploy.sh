#!/bin/bash
# Cube Radar 一键部署脚本
# 用法: ./deploy.sh [window]
#   window: 7d / 30d / 60d / 180d（默认 7d）
#
# 功能：生成最新报告 → 复制为 index.html → 推送到 GitHub Pages

set -e

WINDOW=${1:-7d}
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPORTS_DIR="$ROOT_DIR/reports"

cd "$ROOT_DIR"

echo "📊 生成 [$WINDOW] 报告..."
python3 __main__.py report --window "$WINDOW" 2>&1 | grep -v "NotOpenSSLWarning" | grep -v "warnings.warn"

echo "📋 复制最新报告为 index.html..."
cd "$REPORTS_DIR"
LATEST=$(ls -t report-${WINDOW}-*.html 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
    echo "❌ 没找到 report-${WINDOW}-*.html 文件"
    exit 1
fi
rm -f index.html
cp "$LATEST" index.html
echo "   ✓ index.html ← $LATEST"

echo "🚀 推送到 GitHub..."
git add .
git commit -m "update report: $(date '+%Y-%m-%d %H:%M') [$WINDOW]" 2>&1 | grep -E "main|file" | head -3
git push

echo ""
echo "✅ 部署完成！"
echo "   公网地址: https://caoqianyun.github.io/cube-radar/"
echo "   （GitHub Pages 会在 1-2 分钟内更新）"
