#!/usr/bin/env python3
"""上游取数层：把 sources.json 的引用变成「带出处」的本地快照。

约定
----
* sources.json 的 upstreams 注册仓库:  "owner/repo" -> {"branch": "...", ...}
* 引用写法: "owner/repo:path/in/repo"（path 相对仓库根，分支由注册表给出）
* 快照落盘: input/upstream/<owner>__<repo>/<path>
* 出处记录: input/upstream/<owner>__<repo>/_provenance.json
            {path: {url, branch, sha256, bytes, fetched_at}}
* 取数走本机 GitHub 镜像(:18080)；失败回退到已验证快照；offline 只用快照。

加减一个上游 = 在 sources.json 的 upstreams 注册仓库 + 在表的 sources 里引用它。
"""
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent          # scripts/domain-rules
REPO = BASE.parents[1]                          # /root/git
UP_DIR = Path(os.environ.get("RULES_UPSTREAM", BASE / "input" / "upstream"))
OUT_DIR = Path(os.environ.get("RULES_OUT", BASE / "output"))
MIRROR = os.environ.get("RULES_MIRROR", "http://192.168.40.1:18080/")
CONFIG = BASE / "sources.json"


def load():
    with open(CONFIG, encoding="utf-8") as fh:
        return json.load(fh)


def _whitelist():
    """镜像服务的仓库白名单；缺文件时不做检查（便于单测）。"""
    p = REPO / "scripts" / "_infra" / "repos.json"
    if not p.is_file():
        return None
    with open(p, encoding="utf-8") as fh:
        return set(json.load(fh))


def resolve(cfg, spec):
    """'owner/repo:path' -> (repo, branch, path, url)"""
    repo, sep, path = spec.partition(":")
    if not sep or not path:
        raise SystemExit("[config] 引用格式应为 owner/repo:path，收到 %r" % spec)
    up = cfg["upstreams"].get(repo)
    if up is None:
        raise SystemExit("[config] 上游未注册: %s（请加进 sources.json 的 upstreams）" % repo)
    white = _whitelist()
    if white is not None and repo not in white:
        raise SystemExit("[config] 上游 %s 不在 scripts/_infra/repos.json 白名单，"
                         "镜像会拒绝；请先加入白名单" % repo)
    branch = up["branch"]
    url = "https://raw.githubusercontent.com/%s/%s/%s" % (repo, branch, path)
    return repo, branch, path, url


def snapshot_path(cfg, spec):
    """引用对应的本地快照路径。"""
    repo, _, path, _ = resolve(cfg, spec)
    return UP_DIR / repo.replace("/", "__") / path


def abs_path(cfg, p):
    """配置里的相对路径按模块根解析（手工输入等）。"""
    p = Path(p)
    return p if p.is_absolute() else BASE / p


def _record(meta_path, path, url, branch, snapshot):
    data = {}
    if meta_path.is_file():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    raw = snapshot.read_bytes()
    data[path] = {
        "url": url,
        "branch": branch,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "fetched_at": time.strftime("%F %T%z"),
    }
    tmp = meta_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, meta_path)


def fetch(cfg, spec, offline=False, timeout=120):
    """取上游文本。成功则刷新快照与出处；失败回退快照。"""
    repo, branch, path, url = resolve(cfg, spec)
    snap = snapshot_path(cfg, spec)
    meta = snap.parent / "_provenance.json"

    if offline:
        if snap.is_file():
            return snap.read_text(encoding="utf-8")
        raise SystemExit("[offline] 没有本地快照: %s" % spec)

    err = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(MIRROR + url, timeout=timeout) as r:
                data = r.read()
            if not data:
                raise ValueError("empty body")
            text = data.decode("utf-8", "replace")
            snap.parent.mkdir(parents=True, exist_ok=True)
            tmp = snap.with_name(snap.name + ".tmp")
            with open(tmp, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            os.replace(tmp, snap)
            _record(meta, path, url, branch, snap)
            return text
        except Exception as e:
            err = e
            time.sleep(3)
    if snap.is_file():
        print("[warn] 拉取失败，回退已验证快照: %s (%s)" % (spec, err))
        return snap.read_text(encoding="utf-8")
    raise SystemExit("[fail] %s: %s" % (spec, err))