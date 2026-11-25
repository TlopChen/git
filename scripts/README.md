# scripts —— 处理管线与配套

```
scripts/
├── domain-rules/    域名规则管线（OxiDNS domain_set / ROS FWD 域名表）
├── ip-rules/        纯 IPv4 地址表管线（直连 / CN / 运营商 / blacklist）
├── _infra/          服务端：GitHub 镜像服务、发布、定时入口
└── ros-side/        ROS 本地脚本留档（消费端；Git 只存不跑）
```

## 分层

| 层 | 目录 | 谁负责 | 说明 |
|---|---|---|---|
| 处理 | `domain-rules/`、`ip-rules/` | 本仓库 | 源输入 → 脚本 → 输出，是仓库主体 |
| 分发 | `_infra/` | 广州服务器 | 把产物发布到内网 HTTP 根，供 ROS/OxiDNS 取用 |
| 消费 | `ros-side/` | ROS 设备 | ROS 自带脚本能力负责拉取与导入，这里只留档 |

两条处理管线自 2026-11-26 起按数据类型独立：**域名归 domain-rules，IPv4 地址表归 ip-rules**，
各自 `input/` + `output/`，互不读取对方产物。

## 加一条新管线

1. 建目录：`scripts/<名字>/{README.md,sources.json,input/,output/}`；
2. `sources.json` 注册上游与表；
3. 写处理脚本，读写都相对模块目录（见 `domain-rules/store.py` 的取数约定、`ip-rules/gen_direct.py` 的快照约定）；
4. 定时调用：域名类加进 `_infra/ros-rules-daily.sh`；地址表类按需加独立 `/etc/cron.d/` 入口并共用 `/tmp/ros-rules.lock`；
5. 产物需要出现在 HTTP 根时：域名类加进 `_infra/publish.sh` 的发布清单，地址表类实现 release + symlink 发布
   （参考 `ip-rules/gen_direct.py` 的 `publish()`）。
