# _infra —— 服务端分发与调度

这里放**广州服务器上跑**的东西，不属于任何单条处理管线。

| 文件 | 作用 |
|---|---|
| `mirror.py` | GitHub raw 按需镜像服务，监听 `192.168.40.1:18080`；`/ros/<文件>` 直接发静态产物 |
| `repos.json` | 镜像允许拉取的仓库白名单（安全控制）；上游增减后要同步 |
| `publish.sh` | 把各管线 `output/` 与 `ros-side/*.rsc` 平铺发布到 `/srv/github-mirror/static/ros/` |
| `ros-rules-daily.sh` | 06:00 日更：拉仓库 → 生成 → 发布 → 提交推送 |
| `manual-refresh.sh` | 手工部分快速刷新：`rules`（离线重生成域名产物）/ `direct-ip`（复用 dns-only） |
| `ros-manual-sync.sh` | 旧的手工立即生效脚本（SSH 到 ROS 导入）；保留备用 |

## 部署关系

- **代码**：本仓库是权威。服务器侧只保留 `mirror.py` 的部署副本（它必须和 `static/`、`repos/` 在一起），
  由 systemd `github-mirror.service` 启动。
- **产物**：生成器写到各模块 `output/`，`publish.sh` 复制到 `/srv/github-mirror/static/ros/`。
- **HTTP 路径**：`/ros/<文件名>` 与文件名保持不变，ROS 与 OxiDNS 端无需改动。

## 环境变量

| 变量 | 默认 | 用途 |
|---|---|---|
| `MIRROR_BIND` | `0.0.0.0` | mirror 监听地址 |
| `RULES_OUT` | 模块 `output/` | 生成器输出目录（试跑用） |
| `RULES_UPSTREAM` | 模块 `input/upstream/` | 上游快照目录（试跑用） |
| `BIN_DEST` | `/srv/github-mirror/static/ros` | 二进制资产发布目录 |