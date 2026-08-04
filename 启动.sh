#!/bin/bash
# Cube Radar 一键启动脚本
# 双击此文件即可启动服务器并打开浏览器

cd "$(dirname "$0")"

# 杀掉可能存在的旧服务器（避免端口冲突）
pkill -f "http.server 8765" 2>/dev/null
sleep 0.5

# 生成最新报告（如果数据库存在）
if [ -f "data/radar.db" ]; then
    echo "📊 生成最新报告..."
    python3 __main__.py report --window 7d > /dev/null 2>&1
    # 复制最新报告为 index.html
    LATEST=$(ls -t reports/report-*.html 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        cp "$LATEST" reports/index.html
    fi
fi

# 启动本地服务器（后台运行）
echo "🚀 启动本地服务器..."
cd reports
nohup python3 -m http.server 8765 > /tmp/cube-radar-server.log 2>&1 &
SERVER_PID=$!
sleep 1

# 验证服务器是否启动成功
if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/index.html | grep -q "200"; then
    echo "✅ 服务器已启动: http://127.0.0.1:8765"
    echo "🌐 正在打开浏览器..."
    open "http://127.0.0.1:8765/index.html"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Cube Radar 正在运行中"
    echo "  浏览器地址: http://127.0.0.1:8765"
    echo "  关闭服务器: 关闭此终端窗口"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    # 保持终端窗口打开
    echo "按 Ctrl+C 关闭服务器"
    wait $SERVER_PID
else
    echo "❌ 服务器启动失败，请检查日志: /tmp/cube-radar-server.log"
    read -p "按回车键退出..."
fi
