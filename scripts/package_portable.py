#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 release 构建产物打包为 portable zip：
  <ProductName>_<version>_x64_portable.zip
内容布局（与 Tauri 安装包一致，exe 直接读取同目录 resources/）：
  <ProductName>.exe
  resources/python/   (src-python/ 脚本 + 内嵌 Python 运行时)
  resources/ps/      (来自 src-ps/)
内嵌运行时（首次打包自动构建并缓存到 release/_py_runtime/）：
  Python 3.12 embeddable 解释器 + requirements 依赖的 Windows wheels。
  state.rs 优先使用 resources/python/python.exe，目标机器无需安装 Python，
  CA 证书生成（device_proxy.py --gen-ca）等 Python 功能开箱即用。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_TAURI = os.path.join(ROOT, "src-tauri")
CONF = os.path.join(SRC_TAURI, "tauri.conf.json")
RELEASE_EXE = os.path.join(SRC_TAURI, "target", "release", "trae-work-assistant.exe")
OUT_DIR = os.path.join(ROOT, "release")

# ---- 内嵌 Python 运行时 ----
PY_EMBED_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
PY_PTH_NAME = "python312._pth"  # 文件名随 embeddable 大版本变化
PY_STDLIB_ZIP = "python312.zip"
# pip 交叉下载参数：目标平台 Windows x64 / CPython 3.12（在 Windows/Linux 主机上均可运行）
PIP_PLATFORM_ARGS = [
    "--platform", "win_amd64", "--only-binary=:all:",
    "--python-version", "312", "--implementation", "cp",
]
RUNTIME_REQS = ["cryptography>=42.0.0", "pywin32>=306"]
RUNTIME_CACHE = os.path.join(OUT_DIR, "_py_runtime")
# 无用大文件：CHM 帮助文档 / 目录签名清单，剔除以减小体积
RUNTIME_EXCLUDE_FILES = {"PyWin32.chm", "python.cat"}


def load_conf():
    with open(CONF, "r", encoding="utf-8") as f:
        return json.load(f)


def walk_copy(src, dst, skip_dirs=("__pycache__", ".git")):
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            s = os.path.join(root, name)
            rel = os.path.relpath(s, src)
            t = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(t), exist_ok=True)
            shutil.copy2(s, t)


def build_py_runtime(cache_dir):
    """构建内嵌 Python 运行时（幂等：缓存已存在则直接复用）。

    1. 下载 Windows x64 Python embeddable 并解压到 cache_dir
    2. pip 交叉下载 requirements 对应的 Windows wheels
    3. 解压 wheels 到 Lib/site-packages（跳过 *.data 安装期元数据）
    4. 重写 ._pth：启用 import site（pywin32.pth 依赖）并加入 site-packages 路径
    """
    if os.path.isfile(os.path.join(cache_dir, "python.exe")):
        print("复用内嵌运行时缓存:", cache_dir)
        return cache_dir
    print("构建内嵌 Python 运行时 ...")
    os.makedirs(cache_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="py_runtime_")
    try:
        # 1) embeddable 解释器
        embed_zip = os.path.join(tmp, "embed.zip")
        print("下载", PY_EMBED_URL)
        urllib.request.urlretrieve(PY_EMBED_URL, embed_zip)
        with zipfile.ZipFile(embed_zip) as z:
            z.extractall(cache_dir)

        # 2) 交叉下载 Windows wheels
        wheels_dir = os.path.join(tmp, "wheels")
        os.makedirs(wheels_dir)
        cmd = [sys.executable, "-m", "pip", "download", "-d", wheels_dir] \
            + PIP_PLATFORM_ARGS + RUNTIME_REQS
        print("运行:", " ".join(cmd))
        subprocess.run(cmd, check=True)

        # 3) 解压 wheels 到 Lib/site-packages
        sp = os.path.join(cache_dir, "Lib", "site-packages")
        os.makedirs(sp, exist_ok=True)
        for whl in os.listdir(wheels_dir):
            if not whl.endswith(".whl"):
                continue
            with zipfile.ZipFile(os.path.join(wheels_dir, whl)) as z:
                for name in z.namelist():
                    # <pkg>-<ver>.data/ 内是安装脚本等元数据，运行期不需要
                    if any(p.endswith(".data") for p in name.split("/")[:-1]):
                        continue
                    # wheel 内的帮助文档等排除文件（如 PyWin32.chm）
                    if os.path.basename(name) in RUNTIME_EXCLUDE_FILES:
                        continue
                    z.extract(name, sp)

        # 4) 重写 ._pth（默认模板不含 site-packages 且禁用 site）
        with open(os.path.join(cache_dir, PY_PTH_NAME), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(f"{PY_STDLIB_ZIP}\n.\nLib/site-packages\n\nimport site\n")

        # 5) 剔除帮助文档等无用文件
        for name in RUNTIME_EXCLUDE_FILES:
            p = os.path.join(cache_dir, name)
            if os.path.isfile(p):
                os.remove(p)
        print("内嵌运行时就绪:", cache_dir)
        return cache_dir
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    conf = load_conf()
    product = conf["productName"]
    version = conf["version"]
    resources = conf["bundle"]["resources"]
    # resources 形如 {"../src-python/": "python/", "../src-ps/": "ps/"}
    abs_res = {}
    for src_rel, dest in resources.items():
        src_abs = os.path.normpath(os.path.join(SRC_TAURI, src_rel))
        abs_res[src_abs] = dest.strip("/\\")

    if not os.path.isfile(RELEASE_EXE):
        print("ERROR: release exe 不存在:", RELEASE_EXE, file=sys.stderr)
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)
    zip_name = f"{product}_{version}_x64_portable.zip"
    zip_path = os.path.join(OUT_DIR, zip_name)

    tmp_root = os.path.join(OUT_DIR, "_portable_stage")
    if os.path.exists(tmp_root):
        shutil.rmtree(tmp_root)
    stage_app = os.path.join(tmp_root, product)
    os.makedirs(stage_app, exist_ok=True)

    # 1) exe 重命名为产品名
    shutil.copy2(RELEASE_EXE, os.path.join(stage_app, product + ".exe"))

    # 2) 资源按 Tauri 布局放入 resources/
    res_dir = os.path.join(stage_app, "resources")
    for src_abs, dest in abs_res.items():
        if not os.path.isdir(src_abs):
            print("WARN: 资源目录缺失:", src_abs, file=sys.stderr)
            continue
        target = os.path.join(res_dir, dest)
        walk_copy(src_abs, target)

    # 3) 内嵌 Python 运行时叠加到 resources/python/
    #    （state.rs 优先探测 resources/python/python.exe，命中后不再依赖系统 Python）
    py_target = os.path.join(res_dir, "python")
    if os.path.isdir(py_target):
        walk_copy(build_py_runtime(RUNTIME_CACHE), py_target)
    else:
        print("WARN: 未找到 resources/python，跳过运行时内嵌", file=sys.stderr)

    # 4) 打包（保留内部目录结构，顶层为产品名文件夹）
    print("正在打包:", zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(tmp_root):
            for name in files:
                fp = os.path.join(root, name)
                arc = os.path.relpath(fp, tmp_root)
                z.write(fp, arc)

    shutil.rmtree(tmp_root)
    size = os.path.getsize(zip_path)
    print(f"OK: {zip_path}  ({size/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()
