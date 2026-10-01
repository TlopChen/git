# ros-side —— ROS 本地脚本留档

这些是**在 ROS 设备上运行**的脚本，属于消费端。ROS 是**唯一的拉取方**：
一次把「ROS 要的六张地址表」和「OxiDNS 要的三份规则」都拉下来，地址表 `/import`，
OxiDNS 规则写进它的挂载目录；**OxiDNS 自己不再联网**。

| 文件 | ROS 系统脚本 | 作用 |
|---|---|---|
| `ros-rules-entry.rsc` | `ros-rules-sync` | 入口：下载并 import `sync.rsc`，防重复运行 |
| `sync.rsc` | —（入口下载后 import） | **统一拉取脚本**：六张地址表 + OxiDNS 三份规则 |
| `manual-refresh.rsc` | `manual-refresh` | 手工按需联动：跑一次 `ros-rules-sync` + 重启容器立即重载 |
| `blacklist-sync.rsc` | 兼容入口 | 转调 `ros-rules-sync` |

## 拉什么、放哪里

| 源（内网镜像 `/ros/`） | 目标 | 消费者 |
|---|---|---|
| `cn-telecom.rsc`、`cn-mobile.rsc`、`blacklist.rsc`、`direct-ipv4.rsc`、`direct-ipv4-nocm.rsc`、`direct-ipv4-noct.rsc` | 先落 `sync-stage-*`，校验大小后 `/import` | RouterOS 地址表 |
| `proxy-domain.oxi.txt` | `oxidns-conf/rules/proxy-domain.txt` | OxiDNS |
| `cn-domains.oxi.txt` | `oxidns-conf/rules/cn-extra.txt` | OxiDNS |
| `geosite.dat` | `oxidns-conf/rules/geosite.dat` | OxiDNS |

OxiDNS 三份先下到临时文件（`mr-*.tmp`）并校验字节数，**三份都合格**才改名替换——避免半截文件上线。
地址表导入并校验条数之后才做替换；任一环节失败则整体中止，不产生半截状态。

## OxiDNS 侧：已改成只读本地

`/etc/oxidns/config.yaml` 原来的任务链是 `rules_download → rules_reload`（每天 07:00 触发）。
现在已把 `rules_download` 从任务链里摘除，只保留 `rules_reload`：

- OxiDNS **只读本地文件**，启动与重载都不需要网络 → 隧道或镜像不可用时不影响它；
- 规则新鲜度由 ROS 侧拉取决定：06:30 `ros-rules-sync` 放好文件，07:00 reload 生效；
- 想立即生效就跑 `manual-refresh`（多一步重启容器）。

- 配置备份：`oxidns-conf/rules/config-backup-2026-10-01-before-localonly.yaml`
- 回滚：把备份拷回容器 `/etc/oxidns/config.yaml` 后重启容器

## 入口

| 场景 | 操作 |
|---|---|
| 日常（自动） | 06:30 `/system script run ros-rules-sync` 拉齐九份；07:00 OxiDNS 本地 reload |
| 手工改完立即生效 | `/system script run manual-refresh`（约 3 分钟；含 1–8 秒 DNS 中断） |

## 关键路径

| 项 | 值 |
|---|---|
| 内网镜像 | `http://192.168.40.1:18080/ros/` |
| OxiDNS 规则挂载 | ROS `oxidns-conf/rules` ⇄ 容器 `/etc/oxidns/rules` |
| 地址表暂存 | ROS 文件根 `sync-stage-*` |
| OxiDNS 临时文件 | ROS 文件根 `mr-*.tmp`（成功后改名消耗，不留残留） |

## 部署方式（从零恢复）

```text
# 1) 用 SFTP 把 .rsc 传到 ROS 文件根，再用「文件内容」建系统脚本（避免嵌套字符串插值）
/system script add name="manual-refresh" \
    source=[/file get "manual-refresh.rsc" contents] \
    policy=ftp,read,write,test \
    comment="On-demand manual refresh: pull all outputs + reload oxidns"
/file remove "manual-refresh.rsc"

# 2) 六表入口（同样用文件内容建脚本）
/system script add name="ros-rules-sync" \
    source=[/file get "ros-rules-entry.rsc" contents] policy=ftp,read,write,test

# 3) 唯一保留的定时任务（manual-refresh 不制定时）
/system scheduler add name=ros-rules-sync start-time=06:30:00 interval=1d \
    on-event="/system script run ros-rules-sync"
```

回滚：`/system script remove manual-refresh`；六表同步与 06:30 调度不受影响。

## 与广州的关系

```text
广州 scripts/_infra/publish.sh ──▶ /srv/github-mirror/static/ros/<文件>
                                        │ HTTP :18080/ros/
                                        ▼
ROS  ros-rules-sync ──▶ 地址表 /import ＋ OxiDNS 三份本地文件
                                        │
                       07:00 reload（本地，不联网）或 manual-refresh 重启容器立即生效
```

- 生成方：广州 06:00 日更 / 06:15 direct-ip / 手工清单变更触发（manual-watch）。
- 触发方：ROS 上按需 `/system script run manual-refresh`；**不在这里做**定时轮询、哈希校验。