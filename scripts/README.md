# scripts —— 处理管线与配套

```
scripts/
├── domain-rules/    域名 + CIDR 规则管线（源输入 → 脚本 → 输出）
├── direct-ip/       直连 IPv4 管线
├── _infra/          服务端：GitHub 镜像服务、发布、定时入口
└── ros-side/        ROS 本地脚本留档（消费端；Git 只存不跑）
```

## 分层

| 层 | 目录 | 谁负责 | 说明 |
|---|---|---|---|
| 处理 | `domain-rules/`、`direct-ip/` | 本仓库 | 源输入 → 脚本 → 输出，是仓库主体 |
| 分发 | `_infra/` | 广州服务器 | 把产物发布到内网 HTTP 根，供 ROS/OxiDNS 取用 |
| 消费 | `ros-side/` | ROS 设备 | ROS 自带脚本能力负责拉取与导入，这里只留档 |

## 加一条新管线

1. 建目录：`scripts/<名字>/{README.md,sources.json,input/,output/}`；
2. `sources.json` 注册上游与表；
3. 写处理脚本，读写都相对模块目录（见 `domain-rules/store.py` 的取数约定）；
4. 在 `scripts/_infra/ros-rules-daily.sh` 里加一行调用；
5. 产物需要在 HTTP 出现时，加到 `scripts/_infra/publish.sh` 的发布清单。