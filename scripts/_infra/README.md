# _infra —— 服务端分发与调度

这里放**广州服务器上跑**的东西，不属于任何单条处理管线。

| 文件 | 作用 |
|---|---|
| `mirror.py` | GitHub raw 按需镜像服务，监听 `192.168.40.1:18080`；`/ros/<文件>` 直接发静态产物 |
| `repos.json` | 镜像允许拉取的仓库白名单（安全控制）；domain-rules 上游增减后要同步 |
| `publish.sh` | 把 domain-rules 的域名产物与 `ros-side/*.rsc` 平铺发布到 `/srv/github-mirror/static/ros/` |
| `ros-rules-daily.sh` | 06:00 域名日更：拉仓库 → 生成域名规则 → 发布 → 提交推送 |
| `manual-refresh.sh` | 手工部分快速刷新：`rules`（离线重生成域名产物）/ `ip-rules`（复用上游快照重生成 IP 地址表） |
| `manual-watch.sh` | 每分钟监视手工清单；有变化才触发 `manual-refresh`，无变化静默退出 |
| `ros-manual-sync.sh` | 旧的手工立即生效脚本（SSH 到 ROS 导入）；保留备用 |

## 两条管线的生成与发布

| 管线 | 定时入口 | 发布方式 |
|---|---|---|
| domain-rules（域名规则） | 06:00 `/usr/local/bin/ros-rules-daily.sh` | `publish.sh` 拷贝到 `/srv/github-mirror/static/ros/` |
| ip-rules（IPv4 地址表） | 06:15 `/etc/cron.d/ip-rules` → `/usr/local/bin/ip-rules-update full` | `gen_direct.py --publish-root /var/lib/ip-rules --static-dir /srv/github-mirror/static/ros`：releases/current 原子切换 + symlink |

ROS 与 OxiDNS 只拉 `http://192.168.40.1:18080/ros/<文件>`，不关心产物由哪条管线生成；文件名与路径保持不变。

## 手工清单自动触发（manual-watch）

```text
GitHub 网页改 input/manual/*（或直接改服务器上的文件）
        │  ≤1 分钟
        ▼
manual-watch.sh  ── 命中 ──▶  manual-refresh.sh rules|ip-rules
        │                          │ 生成 → 发布 → 提交 → 推送
   无变化则静默退出                 ▼
                          /srv/github-mirror/static/ros/  ← ROS / OxiDNS 只管拉输出
```

- **两种改动来源都覆盖**：远端（`git fetch` 后比对 `HEAD..origin/main` 里被监视文件）
  与本地（比对被监视文件的 sha256 与上次成功处理后的基线）。
- **被监视文件**：
  - `scripts/domain-rules/input/manual/{manual-blacklist,exclude-blacklist,manual-cn-domains}.txt` → 触发 `rules`
  - `scripts/ip-rules/input/manual/{include-ipv4,exclude-ipv4}.txt` → 触发 `ip-rules`
- **静默设计**：无变化时不写日志、不产生输出；失败后有 600 秒冷却，避免每分钟刷日志。
- **锁**：探测阶段短暂持 `/tmp/ros-rules.lock`，实际生成交给 `manual-refresh.sh`（它自己再取锁），
  与 06:00 域名日更、06:15 ip-rules 日更互斥。

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
- **产物**：域名产物由 `publish.sh` 发布；IP 地址表由 `ip-rules/update.sh` 以 release + symlink 方式发布
  （`/var/lib/ip-rules/current` → `static/ros/` 下的 symlink）。
- **HTTP 路径**：`/ros/<文件名>` 与文件名保持不变，ROS 与 OxiDNS 端无需改动。

## 环境变量

| 变量 | 默认 | 用途 |
|---|---|---|
| `MIRROR_BIND` | `0.0.0.0` | mirror 监听地址 |
| `MIRROR_ROOT` | 脚本所在目录 | mirror 的数据根（`static/`、`repos/`） |
| `MIRROR_REPOS` | `<root>/repos.json` | 镜像白名单文件 |
| `MIRROR_CACHE` | `<root>/repos` | GitHub partial clone 缓存目录 |
| `MIRROR_PORT` | `18080` | 监听端口 |
| `RULES_OUT` | 模块 `output/` | domain-rules 生成器输出目录（试跑用） |
| `RULES_UPSTREAM` | 模块 `input/upstream/` | domain-rules 上游快照目录（试跑用） |
| `BIN_DEST` | `/srv/github-mirror/static/ros` | 二进制资产发布目录 |

ip-rules 的可选参数见其 `README.md`（`--offline` / `--cache` / `--publish-root` / `--static-dir`）。
