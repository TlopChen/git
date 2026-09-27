# 直连 IPv4 维护管线

在广州节点运行：上游 Git 文件 → 本地原始快照 → 严格解析 CIDR → 国内并集 + 指定主机解析 + 手工添加 → 排除 → 无损聚合 → 纯 CIDR / ROS 地址表 → Git 留档与隧道内 HTTP 分发。

此目录的脚本、配置、手工表均以 `/root/git/ros/direct-ip`（本仓库）为权威。旧 `/srv/github-mirror/gen_rules.py` 不生成或覆盖本目录产物。本管线不会登录或修改 AR/ROS，不自动接入现有 blacklist-sync。

## 来源选择

| 源 | 输入 | 用途 |
|---|---|---|
| [gaoyifan/china-operator-ip](https://github.com/gaoyifan/china-operator-ip) | `ip-lists:china.txt` | 国内 BGP/运营商分类和项目提供的兜底，日更 |
| [misakaio/chnroutes2](https://github.com/misakaio/chnroutes2) | `master:chnroutes.txt` | BGP 收集器聚合补充，小时更 |
| [metowolf/iplist](https://github.com/metowolf/iplist/blob/master/docs/china.md) | `master:data/special/china.txt` | 中国内地地理库补充；采用内地专用表，不是厂商全球 ASN |
| [v2ray/domain-list-community](https://github.com/v2ray/domain-list-community/blob/master/data/steam) | `master:data/steam` 中 `@cn` 条目 | Steam 国内下载/CDN 主机，包括阿里、网宿、白山、新流云等 |

国内采用三源并集，倾向减少漏直连；任意一个源的误分类也可能进入结果，不代表每个 IP 均经本地宽带实测。`direct-ipv4-report.json` 列出各源覆盖和独有地址量，误判用 `exclude-ipv4.txt` 纠正。未选长期少更新的 17mon 作为默认运行源；不叠加多个实际同源的包装列表。

云厂家/CDN 的国内部署地址通过上述 CN 集合覆盖，不将阿里云、腾讯云、Cloudflare、Akamai 等整个全球 ASN 放行。需要直连的海外主机逐个写进 `direct-domains.json`，或把已核验网段写入 `include-ipv4.txt`。

原始文件、来源 commit、SHA256、抓取时间保存在 `raw/`。广州访问 GitHub raw HTTPS 不稳定，因此用已配置的 GitHub SSH 只取需要的文件；缓存放 `/var/cache/direct-ip-upstreams`。下载内容严格作为数据，不执行上游脚本。

## 手工维护与优先级

- `include-ipv4.txt`：纯 IPv4/CIDR，一行一条，可以有 `#` 注释。
- `exclude-ipv4.txt`：从最终集合做地址差集，支持从大网段排除单个 `/32`。
- `direct-domains.json`：精确主机名及原因，双国内 DNS（223.5.5.5、119.29.29.29）查询 A 记录取并集，只生成 `/32`。当前手工主机表为空。速方云在下载期间已实测目标 `192.154.108.234:50000`，据 RIPE 最长匹配加入 `192.154.104.0/21`（AS53850/GorillaServers），见 `service-evidence/sufun.json`。只收录该公告段，不放行整个托管商 ASN；前缀内其他 IP 尚未实测。`pending-services.json` 保留跟踪状态，新增节点继续采集。
- 现有 `blacklist.rsc` 的静态 IPv4 强制代理地址自动加入排除集合；排除高于 CN、DNS 例外和手工添加。冲突会列在解析报告的 `excluded_addresses`。
- Steam 源仅取 `@cn`；`full` 和后缀语义保存在域名报告中。对后缀条目只解析列出的主机本身，**并不枚举其所有子域名**。不对全球 `steamcontent.com`、Steam 社区做全域放行。

DNS 例外每 10 分钟刷新，使用广州所见的两家国内 DNS 结果，可能与家庭客户端命中的 CDN 节点不同；这不是全量 CDN IP 清单，也不是与客户端 DNS 同步的首包保证。未来接入 AR 时，国内底表提供静态覆盖；域名新增地址仍需考虑更新窗口。当前仅生成 IPv4，与现有未启用 IPv6 的导入策略一致。

## 输出与分发

| 输出 | 内容 |
|---|---|
| `output/direct-ipv4.txt` | 完整可用直连集合，纯 CIDR 无注释 |
| `output/direct-cn-ipv4.txt` | 国内三源并集减去排除 |
| `output/direct-extra-ipv4.txt` | DNS/手工直连中超出国内集合的部分 |
| `output/direct-excluded-ipv4.txt` | 本次排除集合 |
| `output/direct-ipv4.rsc` | `/ip firewall address-list`，表名 **DIRECT_IP** |
| `output/direct-domains-resolved.json` | 精确主机、原始匹配语义、各 DNS 返回、失败/缓存状态、排除冲突 |
| `output/direct-ipv4-report.json` | 规模、源贡献、与现有 CT/CM 的地址覆盖差异、警告 |

例如内网下载地址：`http://192.168.40.1:18080/ros/direct-ipv4.txt`、`http://192.168.40.1:18080/ros/direct-ipv4.rsc`。本次不执行 ROS 导入。文件是地址表而不是 `/ip route` 静态路由，未来还需要单独配置 BGP 宣告及 AR/ROS 选路。

ROS 脚本先添加缺失地址、更新本管线拥有的记录标记，全部成功后再清理旧的 `direct-ip-auto:` 记录；不清空整表，不删除手工条目，重复导入可复用现有地址。`/32` 在 ROS 地址表中按主机表示匹配。需串行导入；本次仅做结构检查，未在生产 ROS 上执行验证。

HTTP 文件通过 `/var/lib/direct-ip/current` 指向完整 release，校验后原子切换。多文件下载请核对报告/源版本；单次下载得到完整文件，多个 HTTP 请求跨更新边界仍可能看到不同版本。历史版本保留在 `releases/`（按内容去重），Git 保留原始源和产物历史。

## 运行与故障

依赖 Python 3 标准库、git、dig、flock，复用广州现有工具和 GitHub SSH 主机认证，不复制认证材料。

```sh
# 全量源与 DNS（每日北京时间 06:15）
/usr/local/bin/direct-ip-update full
# 复用已验证的本地 IP 源，仅刷新 DNS（每 10 分钟）
/usr/local/bin/direct-ip-update dns
# 单元测试
cd /root/git/ros/direct-ip && python3 -m unittest -v test_direct
```

计划任务在 `/etc/cron.d/direct-ip`，日志 `/var/log/direct-ip.log`；DNS 刷新在每小时 05/15/25/35/45/55 分，跳过 05:55 和 06:05，给现有 06:00 规则任务留窗口。与旧任务共用 `/tmp/ros-rules.lock`，避免并发提交。`update.sh` 只提交本目录 raw/output，已有未提交修改时停止，Git 冲突时停止，不强推；上次 push 失败且已有本地提交时下次重试。旧日更的通配符备份还可能将分发目录的 `direct-ipv4.rsc` 复制到 `ros/` 顶层；本目录 output 才是本管线的权威产物。

CIDR 源单源至少 1000 条、整体至少 1000 条，校验公网地址、默认路由/私网、覆盖量和异常增减。源抓取失败可使用 72 小时以内的已验证原始快照，超过则停止发布；IPv4 上游分支超过 14 天未更新时视为抓取失败。必需域名解析失败可保留 24 小时内最近成功结果，过期停止；非必需 Steam 主机过期会剔除并报告。警告写入报告和日志，不静默冒充更新成功。

不要为绕过变化阈值盲目清除上次结果。先核对上游差异和排除表。回退时可原子调整 `current` 为之前的 release；改规则和脚本应通过正常 Git 提交回退。禁用本任务只需注释 `/etc/cron.d/direct-ip` 两条任务，不影响旧管线。

## 数据归属

上游保留各自版权与许可，来源链接及快照 commit 可追溯；许可文本见 `licenses/`。misaka LICENSE 为 CC BY-SA 4.0（其旧 README 链接仍指 2.0），含其数据的聚合衍生产物采用 CC BY-SA 4.0：https://creativecommons.org/licenses/by-sa/4.0/ 。对上游数据的改动为筛选、规范化、合并、地址差集及 ROS 格式转换。gaoyifan 与 V2Ray 的 MIT 许可随附；metowolf 源未找到根目录 LICENSE，保留来源署名与原始数据，不声称重新许可该源。
