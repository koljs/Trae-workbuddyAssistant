#!/usr/bin/env bash
# v2.6.2 Windows 交叉编译一键构建（环境重置后可重复执行）
# 产物：release/Trae Work 助手_2.6.2_x64-setup.exe + _portable.zip
set -euo pipefail

export PATH=/root/.pyenv/shims:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.cargo/bin

echo "=== [1/6] 安装 cargo-xwin ==="
if ! command -v cargo-xwin &>/dev/null; then
    cargo install cargo-xwin 2>&1 | tail -2
fi

echo "=== [2/6] 添加 Windows 目标 ==="
rustup target add x86_64-pc-windows-msvc 2>&1 | tail -2

echo "=== [3/6] 安装系统依赖（nsis + libayatana） ==="
if ! command -v makensis &>/dev/null; then
    apt-get update -qq
    apt-get install -y -qq nsis libayatana-appindicator3-dev 2>&1 | tail -2
fi

echo "=== [4/6] 前端构建 ==="
cd /workspace
npm install --silent 2>&1 | tail -1
npm run build 2>&1 | tail -1

echo "=== [5/6] Tauri 交叉编译 + NSIS 打包 ==="
cd /workspace/src-tauri
eval "$(cargo xwin env --target x86_64-pc-windows-msvc)"
../node_modules/.bin/tauri build --target x86_64-pc-windows-msvc 2>&1 | tail -3

echo "=== [6/6] 拷贝产物 + 便携包 ==="
cd /workspace
mkdir -p release
cp "src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/Trae Work 助手_2.6.2_x64-setup.exe" release/
mkdir -p src-tauri/target/release
cp src-tauri/target/x86_64-pc-windows-msvc/release/trae-work-assistant.exe src-tauri/target/release/
python3 scripts/package_portable.py 2>&1 | tail -2

echo ""
echo "=== 构建完成 ==="
ls -lh release/*.exe release/*.zip
