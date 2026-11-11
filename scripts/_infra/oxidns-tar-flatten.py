#!/usr/bin/env python3
"""把 docker save 产出的 tar 里的 index.json 扁平化成"指向镜像 manifest"的形态。

背景（2026-11-11）：GitHub runner 用 containerd 镜像存储时，docker save 写出的 index.json
manifests[0].mediaType 是 application/vnd.oci.image.index.v1+json（嵌套镜像索引），
RouterOS 7.25.1 的容器导入只认 manifests[0] 直接指向 application/vnd.oci.image.manifest.v1+json，
否则报 "no config found in manifest"（tar 内容本身完整）。

用法: python3 oxidns-tar-flatten.py <oxidns-vX.Y.Z-linux-amd64.tar>
幂等：index.json 已是扁平结构时直接跳过。
"""
import io
import json
import sys
import tarfile


def main(path: str) -> int:
    with tarfile.open(path, "r") as t:
        members = t.getmembers()
        idx = json.load(t.extractfile("index.json"))
        m0 = idx["manifests"][0]
        if not m0["mediaType"].endswith("image.index.v1+json"):
            print("index.json already flat, skip")
            return 0
        inner_digest = m0["digest"].split(":", 1)[1]
        nested = json.loads(t.extractfile("blobs/sha256/" + inner_digest).read())
        pick = next((x for x in nested["manifests"]
                     if x.get("platform", {}).get("architecture") == "amd64"), None)
        if pick is None:
            raise SystemExit("nested index has no linux/amd64 manifest")
        new = {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [{
                "mediaType": pick["mediaType"],
                "digest": pick["digest"],
                "size": pick["size"],
            }],
        }
        if m0.get("annotations"):
            new["manifests"][0]["annotations"] = m0["annotations"]
        nb = json.dumps(new, separators=(",", ":")).encode()
        tmp = path + ".patched"
        with tarfile.open(tmp, "w") as out:
            for m in members:
                if m.name == "index.json":
                    continue
                out.addfile(m, t.extractfile(m) if m.isfile() else None)
            ti = tarfile.TarInfo("index.json")
            ti.size = len(nb)
            ti.mode = 0o644
            ti.mtime = members[0].mtime
            out.addfile(ti, io.BytesIO(nb))
    import os
    os.replace(tmp, path)
    print("index.json flattened ->", new["manifests"][0]["digest"])
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
