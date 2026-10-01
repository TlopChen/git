# _infra —— 服务端分发与调度

这里放**广州服务器上跑**的东西，不属于任何单条处理管线。

| 文件 | 作用 |
|---|---|
| `mirror.py` | GitHub raw 按需镜像服务，监听 `192.168.40.1:18080`；`/ros/<文件>` 直接发静态产物 |
| `repos.json` | 镜像允许拉取的仓库白名单（安全控制）；上游增减后要同步 |
| `publish.sh` | 把各管线 `output/` 与 `ros-side/*.rsc` 平铺发布到 `/srv/github-mirror/static/ros/` |
| `ros-rules-daily.sh` | 06:00 日更：拉仓库 → 生成 → 发布 → 提交推送 |
| `manual-refresh.sh` | 手工部分快速刷新：`rules`（离线重生成域名产物）/ `direct-ip`（复用 dns-only） |
| `manual-watch.sh` | 每分钟监视手工清单；有变化才触发 `manual-refresh`，无变化静默退出 |
| `ros-manual-sync.sh` | 旧的手工立即生效脚本（SSH 到 ROS 导入）；保留备用 |

## 手工清单自动触发（manual-watch）

```text
GitHub 网页改 input/manual/*（或直接改服务器上的文件）
        │  ≤1 分钟
        ▼
manual-watch.sh  ── 命中 ──▶  manual-refresh.sh rules|direct-ip
        │                          │ 生成 → publish.sh → 提交 → 推送
   无变化则静默退出                 ▼
                          /srv/github-mirror/static/ros/  ← ROS / OxiDNS 只管拉输出
```

- **两种改动来源都覆盖**：远端（`git fetch` 后比对 `HEAD..origin/main` 里被监视文件）
  与本地（比对被监视文件的 sha256 与上次成功处理后的基线）。
- **被监视文件**：
  `scripts/domain-rules/input/manual/{manual-blacklist,exclude-blacklist,manual-cn-domains}.txt`
  与 `scripts/direct-ip/{include-ipv4,exclude-ipv4}.txt`、`scripts/direct-ip/direct-domains.json`。
- **静默设计**：无变化时不写日志、不产生输出；失败后有 600 秒冷却，避免每分钟刷日志。
- **锁**：探测阶段短暂持 `/tmp/ros-rules.lock`，实际生成交给 `manual-refresh.sh`（它自己再取锁），
  与 06:00 日更、06:15 direct-ip 互斥。

部署：

```sh
# /etc/cron.d/manual-watch
* * * * * root /root/git/scripts/_infra/manual-watch.sh >/dev/null 2>&1
```

运维命令：

```sh
/root/git/scripts/_infra/manual-watch.sh --dry-run   # 只报告"将触发什么"，不动任何东西
/root/git/scripts/_infra/manual-watch.sh --init      # 写入当前基线（首次安装/恢复后调用）
tail -50 /var/log/manual-watch.log                   # 只在命中或失败时才有内容
cat /var/lib/manual-watch/state                      # 基线哈希 + 失败冷却时间戳
```

停用：注释掉 `/etc/cron.d/manual-watch` 那一行即可；`manual-refresh` 手动路径不受影响。

## 部署关系

- **代码**：本仓库是权威。服务器侧只保留 `mirror.py` 的部署副本（它必须和 `static/`、`repos/` 在一起），
  由 systemd `github-mirror.service` 启动。
- **产物**：生成器写到各模块 `output/`，`publish.sh` 复制到 `/srv/github-mirror/static/ros/`。
- **HTTP 路径**：`/ros/<文件名>` 与文件名保持不变，ROS 与 OxiDNS 端无需改动。

## 环境变量

| 变量 | 默认 | 用途 |
|---|---|---|
| `MIRROR_BIND` | `0.0.0.0` | mirror 监听地址 |
| `MIRROR_ROOT` | 脚本所在目录 | mirror 的数据根（`static/`、`repos/`） |
| `MIRROR_REPOS` | `<root>/repos.json` | 镜像白名单文件 |
| `MIRROR_CACHE` | `<root>/repos` | GitHub partial clone 缓存目录 |
| `MIRROR_PORT` | `18080` | 监听端口 |
| `RULES_OUT` | 模块 `output/` | 生成器输出目录（试跑用） |
| `RULES_UPSTREAM` | 模块 `input/upstream/` | 上游快照目录（试跑用） |
| `BIN_DEST` | `/srv/github-mirror/static/ros` | 二进制资产发布目录 |