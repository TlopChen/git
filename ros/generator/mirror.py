#!/usr/bin/env python3
"""按需 GitHub raw 镜像服务。

请求格式: /https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<路径>
简写格式: /<owner>/<repo>/<branch>/<路径>

只在被请求时通过 SSH 协议（git@github.com）从 GitHub 拉取该文件，
partial clone 不下载整仓；本地缓存 TTL 内直接命中，过期自动刷新，
刷新失败时回源旧文件。允许的仓库在 repos.json 中配置。
"""
import json
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.join(BASE, "repos")
TTL = 6 * 3600        # 缓存有效时长（秒）
GIT_TIMEOUT = 90      # 单次 git 操作超时（秒）
PORT = 18080

ALLOWED = json.load(open(os.path.join(BASE, "repos.json")))
_locks = {}
_locks_guard = threading.Lock()

CONTENT_TYPES = {
    ".list": "text/plain; charset=utf-8",
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".module": "text/plain; charset=utf-8",
    ".snippet": "text/plain; charset=utf-8",
    ".conf": "text/plain; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".sh": "text/x-shellscript; charset=utf-8",
    ".py": "text/x-python; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".png": "image/png",
}


def repo_lock(key):
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, timeout=GIT_TIMEOUT)


    def materialize(owner, repo, branch, rel):
        """确保 worktree 里存在 rel 指向的文件且尽量新鲜，返回本地路径。

        不走 worktree/index（空索引下 checkout pathspec 会匹配失败），
        直接 rev-parse 拿 blob OID 再 cat-file 懒加载内容，严格只取该文件。
        """
        key = f"{owner}__{repo}"
        wd = os.path.join(REPO_DIR, key)
        with repo_lock(key):
            target = os.path.join(wd, rel)
            if (os.path.isfile(target) and os.path.getsize(target) > 0
                    and time.time() - os.path.getmtime(target) < TTL):
                return target
            if not os.path.isdir(os.path.join(wd, ".git")):
                git("clone", "--quiet", "--depth", "1", "--filter=blob:none",
                    "--no-checkout", f"git@github.com:{owner}/{repo}.git", wd)
            git("fetch", "--quiet", "--depth", "1", "origin", branch, cwd=wd)
            oid = subprocess.run(
                ["git", "rev-parse", f"FETCH_HEAD:{rel}"], cwd=wd, check=True,
                capture_output=True, timeout=GIT_TIMEOUT, text=True).stdout.strip()
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                with open(target, "wb") as fh:
                    subprocess.run(["git", "cat-file", "blob", oid], cwd=wd,
                                   check=True, stdout=fh, timeout=GIT_TIMEOUT)
            except Exception:
                # 失败时清掉被截断的空文件，防止 0 字节缓存被 TTL 投毒
                try:
                    os.remove(target)
                except OSError:
                    pass
                raise
            if os.path.getsize(target) == 0:
                os.remove(target)
                raise RuntimeError(f"upstream blob is empty: {owner}/{repo}@{branch}:{rel}")
            os.utime(target, None)
            return target


class Handler(BaseHTTPRequestHandler):
    def send_body(self, code, body, ctype="application/json; charset=utf-8",
                  extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            self._handle()
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                self.send_body(500, json.dumps({"error": str(e)}).encode())
            except Exception:
                pass

    def _handle(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/health"):
            body = json.dumps({
                "ok": True,
                "repos": ALLOWED,
                "usage": "/https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>",
            }).encode()
            return self.send_body(200, body)

        # ROS 规则静态目录：/ros/<文件名>（由 gen_rules.py 生成）
        if path.startswith("/ros/"):
            name = path[len("/ros/"):]
            if not name or "/" in name or ".." in name:
                return self.send_body(400, b'{"error": "bad file name"}')
            f = os.path.join(BASE, "static", "ros", name)
            if not os.path.isfile(f):
                return self.send_body(404, b'{"error": "no such generated rule"}')
            with open(f, "rb") as fh:
                data = fh.read()
            return self.send_body(200, data, ctype="text/plain; charset=utf-8",
                                  extra={"Cache-Control": "no-cache"})

        raw = path.lstrip("/")
        prefix = "https://raw.githubusercontent.com/"
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
        parts = raw.split("/")
        if len(parts) < 4:
            return self.send_body(400, b'{"error": "need /<owner>/<repo>/<branch>/<path>"}')
        owner, repo, branch = parts[0], parts[1], parts[2]
        rel = "/".join(parts[3:])
        if f"{owner}/{repo}" not in ALLOWED:
            return self.send_body(403, b'{"error": "repo not allowed, edit repos.json"}')
        if any(s in ("", ".", "..") or s.lower() == ".git" for s in rel.split("/")):
            return self.send_body(400, b'{"error": "bad path"}')

        target = os.path.join(REPO_DIR, f"{owner}__{repo}", rel)
        try:
            materialize(owner, repo, branch, rel)
            cache = "FRESH"
        except subprocess.CalledProcessError:
            if not os.path.isfile(target):
                return self.send_body(404, b'{"error": "not found in repo (check branch/path)"}')
            cache = "STALE"
        except Exception:
            if not os.path.isfile(target):
                return self.send_body(502, b'{"error": "upstream fetch failed"}')
            cache = "STALE"

        with open(target, "rb") as fh:
            data = fh.read()
        ext = os.path.splitext(target)[1].lower()
        self.send_body(200, data,
                       ctype=CONTENT_TYPES.get(ext, "application/octet-stream"),
                       extra={"Cache-Control": "public, max-age=3600",
                              "X-Cache": cache})

    def log_message(self, fmt, *args):
        print(time.strftime("%F %T"), self.address_string(), fmt % args, flush=True)


if __name__ == "__main__":
    os.makedirs(REPO_DIR, exist_ok=True)
    print(f"serving on :{PORT}, allowed repos: {ALLOWED}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
