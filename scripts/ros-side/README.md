# ros-side —— ROS 本地脚本留档

这些是**在 ROS 设备上运行**的脚本，属于消费端。ROS 自带脚本能力，
拉取、校验、导入都由它自己完成；Git 这边只做留档与备份，不参与执行。

| 文件 | 作用 |
|---|---|
| `ros-rules-entry.rsc` | `ros-rules-sync` 入口：下载 `sync.rsc` 并 import，防重复运行 |
| `sync.rsc` | 六表同步脚本：CT / CM / blacklist / DIRECT_IP / NOCM / NOCT |
| `blacklist-sync.rsc` | 兼容入口，转调 `ros-rules-sync` |

## 与广州的关系

```text
广州 publish.sh ──→ /srv/github-mirror/static/ros/<文件>
                         │  HTTP :18080/ros/
                         ▼
ROS   /tool fetch sync.rsc ──→ /import ──→ 六表
```

- 发布方：`scripts/_infra/publish.sh` 会把本目录的 `*.rsc` 一起发布到 HTTP 根。
- 触发方：ROS 上按需 `/system script run ros-rules-sync`，或 06:30 自然调度。
- **不在这里做**定时轮询、哈希校验或自动跳转；ROS 侧保持按需触发。