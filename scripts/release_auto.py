# -*- coding: utf-8 -*-
"""
一劳永逸发布脚本：release_auto.py
用法：python release_auto.py <VERSION> [body.txt]
  VERSION  目标版本号，如 1.0.33
  body.txt 可选，Release 正文文件（UTF-8）
前置：APK 已上传到仓库 apk/liuliu-fucai-<VERSION>.apk（构建后 push 一次即可）
流程：从仓库下载 APK -> 创建 Release -> 上传 APK asset -> 更新 version.json（仓库+asset）
不依赖任何本地文件，任何环境只要有 GH_TOKEN 即可发布。
"""
import sys
import json
import base64
import os
import urllib.request

VERSION = sys.argv[1] if len(sys.argv) > 1 else ""
if not VERSION:
    print("用法: python release_auto.py <VERSION> [body.txt]")
    sys.exit(1)
BODY = open(sys.argv[2], encoding="utf-8").read() if len(sys.argv) > 2 else ("liuliu-fucai v" + VERSION)
token = os.environ.get("GH_TOKEN", "")
if not token:
    print("缺少环境变量 GH_TOKEN")
    sys.exit(1)
REPO = "raowanxin/liuliu-fucai"
APK_NAME = "liuliu-fucai-" + VERSION + ".apk"


def api(url, method="GET", body=None, raw=False, ctype="application/json; charset=utf-8"):
    data = None if body is None else (body if raw else json.dumps(body).encode("utf-8"))
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "liuliu-fucai")
    req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            text = resp.read().decode("utf-8")
            return text if raw else (json.loads(text) if text else {})
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        raise RuntimeError("HTTP %s %s: %s" % (e.code, url, err[:400]))


# 1) 从仓库 apk/ 取 APK（一劳永逸的基石：APK 只认仓库里的）
print("STEP1 从仓库取 APK:", APK_NAME)
try:
    meta = api("https://api.github.com/repos/%s/contents/apk/%s" % (REPO, APK_NAME))
except RuntimeError as e:
    print("仓库中不存在该 APK，请先构建并上传到仓库 apk/ 目录。")
    print(e)
    sys.exit(1)
apk_bytes = base64.b64decode(meta["content"])

# 2) 创建 Release
print("STEP2 创建 Release v" + VERSION)
try:
    rel = api("https://api.github.com/repos/%s/releases" % REPO, "POST", {
        "tag_name": "v" + VERSION,
        "name": "liuliu-fucai v" + VERSION,
        "body": BODY,
        "draft": False,
        "prerelease": False,
    })
except RuntimeError as e:
    if "already_exists" in str(e) or "422" in str(e):
        print("Release 已存在，尝试复用 tag")
        rel = api("https://api.github.com/repos/%s/releases/tags/v%s" % (REPO, VERSION))
    else:
        raise
rid = rel["id"]
print("RELEASE_ID", rid)


def upload_asset(rid, fname, content):
    enc = urllib.request.quote(fname)
    url = ("https://uploads.github.com/repos/%s/releases/%s/assets?name=%s" % (REPO, rid, enc))
    req = urllib.request.Request(url, data=content, method="POST")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "liuliu-fucai")
    req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    print("ASSET", fname, data.get("size", 0))
    return data


# 3) 上传 APK asset
print("STEP3 上传 APK asset")
upload_asset(rid, APK_NAME, apk_bytes)

# 4) 更新 version.json（仓库 + release asset）
vj = json.dumps({"latest": VERSION, "apk": APK_NAME}).encode("utf-8")
print("STEP4 更新 version.json:", vj.decode("utf-8"))
upload_asset(rid, "version.json", vj)
try:
    old = api("https://api.github.com/repos/%s/contents/version.json" % REPO)
    sha = old.get("sha")
except Exception:
    sha = None
    print("警告: 仓库 version.json 不存在，将新建")
b = {"message": "version.json latest=" + VERSION, "content": base64.b64encode(vj).decode("ascii")}
if sha:
    b["sha"] = sha
api("https://api.github.com/repos/%s/contents/version.json" % REPO, "PUT", b)
print("DONE v" + VERSION)
