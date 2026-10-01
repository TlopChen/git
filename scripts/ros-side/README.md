# ros-side —— ROS 本地脚本留档

这些是**在 ROS 设备上运行**的脚本，属于消费端。ROS 自带脚本能力，
拉取、校验、导入都由它自己完成；Git 这边只做留档与备份，不参与执行。

| 文件 | ROS 系统脚本 | 作用 |
|---|---|---|
| `ros-rules-entry.rsc` | `ros-rules-sync` | 六表同步入口：CT / CM / blacklist / DIRECT_IP / NOCM / NOCT |
| `sync.rsc` | —（入口下载后 import） | 六表同步的实际内容 |
| `manual-refresh.rsc` | `manual-refresh` | 手工改动按需联动：地址表 + OxiDNS 规则；**无定时、无哈希** |
| `blacklist-sync.rsc` | 兼容入口 | 转调 `ros-rules-sync` |

## 三个入口

| 场景 | 操作 |
|---|---|
| 日常（自动） | 06:30 scheduler 跑 `/system script run ros-rules-sync` |
| 手工改了地址表 | 广州 `manual-refresh direct-ip` → ROS `/system script run manual-refresh` |
| 手工改了域名 | 广州 `manual-refresh rules` → ROS `/system script run manual-refresh` |
| 只改地址、想跑得快 | ROS `/system script run ros-rules-sync`（约 2 分钟；不含 OxiDNS） |

`manual-refresh` 一次做两件事（约 2.5 分钟）：

1. `/system script run ros-rules-sync` —— 地址表（幂等，含 DIRECT_IP 手工段与 NOCM/NOCT 派生表）；
2. OxiDNS 三份规则 `proxy-domain.txt` / `cn-extra.txt` / `geosite.dat`：
   先用 `/tool fetch` 拉到临时文件并校验字节数，三份都通过才替换，然后重启容器重载（约 20 秒）。

> **为什么是重启容器**：OxiDNS 的规则重载只有它内部的任务链（`rules_download` → `rules_reload`，
> 每天 07:00 由 cron 插件触发）能执行，没有对外的手动触发口。容器设了 `start-on-boot=yes`、
> `restart-policy=always`，重启期间 DNS 约 1–8 秒不可用（2026-10-01 实测一次，8 秒内恢复）。

## 关键路径

| 项 | 值 |
|---|---|
| 内网镜像 | `http://192.168.40.1:18080/ros/` |
| OxiDNS 规则挂载 | ROS `oxidns-conf/rules` ⇄ 容器 `/etc/oxidns/rules` |
| 六表暂存 | ROS 文件根 `sync-stage-*` |
| OxiDNS 刷新临时文件 | ROS 文件根 `mr-*.tmp`（成功后被改名消耗，不留残留） |

## 部署方式（从零恢复）

```routeros
# 1) 用 SFTP 把 .rsc 传到 ROS 文件根，再用「文件内容」建系统脚本（避免嵌套字符串插值）
/system script add name="manual-refresh" \
    source=[/file get "manual-refresh.rsc" contents] \
    policy=ftp,read,write,test \
    comment="On-demand manual refresh: address lists + OxiDNS rules; no scheduler, no hashing"
/file remove "manual-refresh.rsc"

# 2) 唯一保留的定时任务（仅六表同步；manual-refresh 不制定时）
/system scheduler add name=ros-rules-sync start-time=06:30:00 interval=1d \
    on-event="/system script run ros-rules-sync"
```

回滚：`/system script remove manual-refresh`；六表同步与调度不受影响。

## 与广州的关系

```text
广州 scripts/_infra/publish.sh ──→ /srv/github-mirror/static/ros/<文件>
                                        │ HTTP :18080/ros/
                                        ▼
ROS  /system script run manual-refresh ──→ 地址表 /import + OxiDNS 规则重启重载
```

- 生成方：广州 `manual-refresh rules|direct-ip`（离线重生成手工部分）或 06:00/06:15 日更。
- 触发方：ROS 上按需 `/system script run manual-refresh`；**不在这里做**定时轮询、哈希校验。