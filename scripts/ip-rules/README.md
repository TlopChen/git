# ip-rules —— 纯 IPv4 地址表管线

上游 IP 源 → 本地原始快照 → 严格解析/规模校验 → 手工添加 → 手工排除 → IPv4 地址表（直连表 + CN/运营商表 + blacklist 表）→ Git 留档与隧道内 HTTP 分发。

本目录的脚本、配置、手工表均以 `/root/git/scripts/ip-rules`（本仓库）为权威。本管线**只处理 IP**：不解析域名、不访问 DNS、不读取 domain-rules 的产物，也不登录或修改 AR/ROS。

与 `scripts/domain-rules` 的分工（两管线独立）：

| 管线 | 输入 | 产物 | 消费端 |
|---|---|---|---|
| `domain-rules` | 域名规则源 + 手工域名表 | OxiDNS `domain_set`、RouterOS `/ip dns static` FWD | OxiDNS、RouterOS |
| `ip-rules` | IP/CIDR 源 + 手工 IP 表 | 直连地址表、CN/运营商地址表、blacklist 地址表 | RouterOS |

2026-11-26 之前 IP 表由 `domain-rules` 生成、域名解析混在直连管线里；现在两边各自 IN/OUT，互不依赖。

## 目录结构（IN/OUT）

```text
scripts/ip-rules/
  gen_direct.py          生成器（标准库 + git）
  asn_sources.py         RIPE RIS 整 ASN 快照
  update.sh              定时/手工运行入口（full | offline）
  sources.json           上游源与输出表定义（单一入口）
  input/
    manual/              手写 IP 表
      include-ipv4.txt     手工添加的直连 CIDR
      exclude-ipv4.txt     手工排除 CIDR（优先于所有来源和手工添加）
    upstream/            上游原始快照（非手写；抓取失败按 sha256 + 72h 回退）
      <source>.txt/.json   源快照 + 来源 repo/ref/commit/sha256/抓取时间
      as<asn>-response.json / as<asn>-meta.json  RIPE RIS 原始响应与元数据
  output/                IPv4 产物（扁平；发布到内网 mirror 时文件名不变）
  service-evidence/      单个服务的实测证据（sufun.json、girigiri.json）与 pending-services.json
  licenses/              上游许可
```

2026-11-26 由 `scripts/direct-ip` 改名并重构而来：旧的 `raw/`、`input/ip`、`input/domain`、`input/manual/`、`output/ip`、`output/domain` 均不再使用；发现旧布局时生成器会明确报错，避免迁移不完整时静默读空输入。

## 来源选择

| 源 | 输入 | 用途 |
|---|---|---|
| [gaoyifan/china-operator-ip](https://github.com/gaoyifan/china-operator-ip) | `ip-lists:china.txt` | 直连底表：国内 BGP/运营商分类和项目兜底，日更 |
| [misakaio/chnroutes2](https://github.com/misakaio/chnroutes2) | `master:chnroutes.txt` | 直连底表：BGP 收集器聚合补充，小时更 |
| [metowolf/iplist](https://github.com/metowolf/iplist) | `master:data/special/china.txt` | 直连底表：中国内地地理库补充；内地专用表，不是厂商全球 ASN |
| [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) | `release:cncidr.txt` | `cn.rsc`（ROS 表 CN） |
| [metowolf/iplist](https://github.com/metowolf/iplist) | `master:data/country/CN.txt` | `cn.rsc`（ROS 表 CN） |
| [metowolf/iplist](https://github.com/metowolf/iplist) | `master:data/isp/chinatelecom.txt` 等 | `cn-telecom.rsc` / `cn-mobile.rsc` / `cn-unicom.rsc` / `cn-cernet.rsc`（CT/CM/CU/CC） |
| [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) | `release:telegramcidr.txt` | `blacklist.rsc`：Telegram DC 段 |
| [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) | `master:rule/Surge/Twitter/Twitter.list` 的 IP-CIDR | `blacklist.rsc`：Twitter 硬编码段 |
| AS51894（RIPE RIS） | `stat.ripe.net` announced-prefixes | `blacklist.rsc`：Mikrotikls 公告段 |
| AS53850（RIPE RIS） | 同上 | 直连表的整 ASN 例外（速方云） |

直连底表采用三源并集，倾向减少漏直连；任一源的误分类也可能进入结果，不代表每个 IP 均经本地宽带实测。`direct-ipv4-report.json` 列出各源覆盖和独有地址量，误判用 `input/manual/exclude-ipv4.txt` 纠正。不叠加实际同源的包装列表；不按整个云厂商/CDN 的全球 ASN 放行。

加减上游、调整表或 ASN **只改 `sources.json`**（本管线用已配置的 GitHub SSH 直取需要的文件，不经过 `_infra` 的 mirror 白名单）。原始文件、commit、SHA256、抓取时间保存在 `input/upstream/`；缓存目录 `/var/cache/ip-rules-upstreams`。

## 权威顺序与手工维护

生成时按固定层次组装（代码 `assemble()`，报告 `precedence` 同名输出）：

1. **上游源（权威底表）**：`sources.json` 的 CN 三源并集；单源条数与覆盖量有上下限校验。
2. **手工层**：`input/manual/include-ipv4.txt` 的手工 CIDR + `direct_asns` 整 ASN 公告。手工是"在源之上加例外"，不会删除源里的条目。
3. **排除层（优先于前两层）**：`input/manual/exclude-ipv4.txt` + `blacklist.rsc` 对应地址集合（强制代理语义）。被排除层吃掉的手工/源条目会写进报告 `manual_conflicts`，不静默失效。
4. **派生兜底表**：`DIRECT_IP_NOCM`（减移动网段）/ `DIRECT_IP_NOCT`（减电信网段），只用于两条家宽线路各自承载"不属于对端运营商"的前缀，不是新的权威来源。

独立地址表（`tables`）与直连表分开组装：`cn`、各运营商表由各自来源整表重建；`blacklist` 表参与直连表的排除层，但自身仍按"清静态、保留动态"整表重建（与 OxiDNS 动态注入共存）。

维护要点：

- `input/manual/include-ipv4.txt`：纯 IPv4/CIDR，一行一条，可以有 ``#` 注释；回滚就是删对应行。
- `input/manual/exclude-ipv4.txt`：从最终集合做地址差集，支持从大网段排除单个 `/32`。
- 现有 `blacklist` 表（Telegram / Twitter / AS51894 / 公共 DNS 等）的地址自动加入排除集合，高于直连源和手工添加；冲突列在报告的 `manual_conflicts`。
- 增删/更换上游源、表、ASN：改 `sources.json`。
- GiriGiri：`input/manual/include-ipv4.txt` 收录 15 条 holder `/24`（见文末），域名判国内在 `domain-rules/input/manual/manual-cn-domains.txt`，两边各自独立维护。
- 原 Steam 国内 CDN 域名解析（`steam-cn` 源）已移除：纯 IP 管线不再做域名解析，Steam 下载所需 IP 多数已在国内 BGP 段；若发现漏覆盖，把实测 IP 加进 `include-ipv4.txt`。

## 输出与分发

| 输出 | 内容 | ROS 表名 |
|---|---|---|
| `output/direct-ipv4.txt` | 完整可用直连集合，纯 CIDR 无注释 | — |
| `output/direct-cn-ipv4.txt` | 直连底表（CN 三源并集）减去排除 | — |
| `output/direct-manual-ipv4.txt` | 手工层（include + direct_asns） | — |
| `output/direct-extra-ipv4.txt` | 手工层中超出直连底表与排除集合的部分 | — |
| `output/direct-excluded-ipv4.txt` | 本次排除集合 | — |
| `output/direct-ipv4.rsc` | 直连表增量更新（保留手工/其它条目） | **DIRECT_IP** |
| `output/direct-ipv4-nocm.rsc` | `DIRECT_IP` 减 `cn-mobile`（CM）地址 | **DIRECT_IP_NOCM** |
| `output/direct-ipv4-noct.rsc` | `DIRECT_IP` 减 `cn-telecom`（CT）地址 | **DIRECT_IP_NOCT** |
| `output/direct-as<asn>-ipv4.txt` | 整 ASN 例外专表（如 `direct-as53850-ipv4.txt`） | — |
| `output/direct-ipv4-report.json` | 规模、各层贡献、源贡献、与 CT/CM 的覆盖差异、表统计、警告 | — |
| `output/cn.rsc` | 国内地址表合并 | **CN** |
| `output/cn-telecom.rsc` | 电信 | **CT** |
| `output/cn-mobile.rsc` | 移动 | **CM** |
| `output/cn-unicom.rsc` | 联通 | **CU** |
| `output/cn-cernet.rsc` | 教育网 | **CC** |
| `output/blacklist.rsc` | 强制代理兜底（Telegram/Twitter/AS51894/公共 DNS），清静态保留动态 | **blacklist** |

例如内网下载地址：`http://192.168.40.1:18080/ros/direct-ipv4.txt`、`http://192.168.40.1:18080/ros/direct-ipv4.rsc`、`http://192.168.40.1:18080/ros/cn-telecom.rsc`、`http://192.168.40.1:18080/ros/blacklist.rsc`。

- 直连表（DIRECT_IP*）是**增量更新**：先添加缺失地址、更新本管线拥有的记录标记，全部成功后再清理旧的 `ip-rules-auto:` 记录；不清空整表，不删除手工条目，重复导入可复用现有地址。`/32` 在 ROS 地址表中按主机表示匹配。需串行导入。
- CN/运营商/blacklist 表按整表重建：先 `remove` 旧条目（blacklist 清静态保留动态），再全量 `add`。与 2026-11-26 前 `domain-rules` 生成的格式与语义一致，ROS 侧无需改脚本。
- 内网 HTTP 文件通过 `/var/lib/ip-rules/current` 指向完整 release，校验后原子切换；历史版本保留在 `releases/`。文件名与路径保持不变（约定：ROS 走 `/ros/<文件>`）。
- ROS 侧 `ros-rules-sync` 06:30 拉六张地址表（`cn-telecom`、`cn-mobile`、`blacklist`、`direct-ipv4`、`direct-ipv4-nocm`、`direct-ipv4-noct`）并导入，见 `scripts/ros-side/README.md`。`cn.rsc`/`cn-unicom.rsc`/`cn-cernet.rsc` 仍照常发布。

## 运行与故障

依赖 Python 3 标准库、git、flock，复用广州现有 GitHub SSH 主机认证。不依赖 dig/DNS。

`sh
# 全量源 + ASN（每日北京时间 06:15）
/usr/local/bin/ip-rules-update full
# 复用已验证的本地快照，只按手工表重生成（手工改动走这条）
/usr/local/bin/ip-rules-update offline
# 单元测试（含目录分层、表生成、权威顺序、排除优先的回归）
cd /root/git/scripts/ip-rules && python3 -m unittest -v test_direct test_asn
````

计划任务在 `/etc/cron.d/ip-rules`（06:15 的 full；手工改动由 `scripts/_infra/manual-watch.sh` 每分钟检测后触发 offline）。日志 `/var/log/ip-rules.log`。与域名日更共用 `/tmp/ros-rules.lock`，避免并发提交。`update.sh` 只提交本目录 `input/upstream` 与 `output`，工作区有未提交修改时停止（手工表改动要先提交），Git 冲突时停止，不强推；上次 push 失败且已有本地提交时下次重试。

规模校验：CN 源单源至少 1000 条、覆盖量 1 亿–6.5 亿地址；表源按各自 `min_prefixes/max_prefixes`；直连合并结果 1000–30000 条、1 亿–6.5 亿地址；相对上一次发布变化超过 15%（地址量）或 50%（条数）时拒绝发布并保留旧 release。源抓取失败可使用 72 小时以内的已验证快照，超过则停止发布；直连源上游分支超过 14 天未更新视为抓取失败。警告写入报告和日志，不静默冒充更新成功。

不要为绕过变化阈值盲目清除上次结果。先核对上游差异和排除表。回退时可原子调整 `current` 为之前的 release；改规则和脚本应通过正常 Git 提交回退。禁用本任务只需注释 `/etc/cron.d/ip-rules` 的任务。

## 数据归属

上游保留各自版权与许可，来源链接及快照 commit 可追溯；许可文本见 `licenses/`。misaka LICENSE 为 CC BY-SA 4.0（其旧 README 链接仍指 2.0），含其数据的聚合衍生产物采用 CC BY-SA 4.0：https://creativecommons.org/licenses/by-sa/4.0/ 。对上游数据的改动为筛选、规范化、合并、地址差集及 ROS 格式转换。gaoyifan 与 V2Ray 的 MIT 许可随附；metowolf 源未找到根目录 LICENSE，保留来源署名与原始数据，不声称重新许可该源。

## AS53850 整 ASN 直连（2026-09-27 用户明确授权）

`sources.json` 的 `direct_asns: [53850]` 按天跟随 RIPE RIS 公告数据，包含该 ASN 的全部可观测 IPv4 起源前缀，不局限于速方云业务。与一般云/CDN 不整 ASN 放行的默认规则不同，这是用户指定的例外。

数据源：https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS53850&min_peers_seeing=1 。查询近 24 小时，按响应 `query_endtime` 过滤时间线，只取快照端点仍可见的前缀，避免直接混入两周历史中已撤销条目。RIS 有采集延迟，不代表实时全球完整路由；快照时间写入报告，超过 48 小时拒绝使用。抓取失败可回用完整性通过且快照仍未过期的缓存，失败不覆盖旧发布。

`input/upstream/as53850-response.json` 保留全部 API 响应（含 IPv6），`input/upstream/as53850-meta.json` 保留来源、时间和 SHA256；`output/direct-as53850-ipv4.txt` 为无损聚合后的 ASN 专表，最终并入 `direct-ipv4.txt` 和 ROS `DIRECT_IP`。现有 blacklist/手工排除仍优先，IPv6 尚未导入。

## GiriGiri 动漫站（2026-11-26 用户授权，速方云式）

对象：`ani.girigirilove.com` 播放页及其视频/CDN。作为对比，速方云案例见 `service-evidence/sufun.json`（先钉 `192.154.104.0/21`，后改为整 AS53850 自动维护）。

现场观测（2026-11-25/26，详见 `service-evidence/girigiri.json`）：

- 播放链路域名都在 `*.girigirilove.com` / `*.girigirilove.net`：`ani`（前端）、`m3u8`（接口）、`ana`（MP4 视频）、`danmu`（弹幕）、`jpg`（图片）。
- 后端是自建反代池：池 A 静态 7 IP；池 B 按运营商 GeoDNS，并集 24 IP（洛杉矶 19 + 莫斯科 5，7 个 ASN），**无大陆节点**。
- 站方按 IP 地区屏蔽 US/JP/EU；家庭当前经隧道看视频属于"可播但绕路 + 占隧道流量"。

处理（纯 IP 侧）：

1. `input/manual/include-ipv4.txt` 收录 15 条 holder `/24`（见该文件末段注释），覆盖 24 个已观测节点并容忍换机器/IP 漂移；这是"公告段覆盖"，与速方云先前的 `/21` 同性质。副作用是同 `/24` 邻居地址也会直连（廉价 VPS 段，影响可忽略）；要最小面可改回逐个 `/32`。
2. `input/manual/exclude-ipv4.txt` 保持干净；blacklist 表自动排除仍优先。
3. 域名层面（让 OxiDNS 判国内、停止 `ros_blacklist` 注入）在 `domain-rules/input/manual/manual-cn-domains.txt` 的 `girigirilove.com` / `girigirilove.net`，属于域名管线，不在本目录。

2026-11-26 改造前的 `input/domain/direct-domains.json`（6 个精确主机用国内 DNS 解析出 /32 自动跟随）已移除：纯 IP 管线不再解析域名。现有 15 条 `/24` 已覆盖观测到的节点；CDN 换新段时手工补 `/24` 或 `/32`。

回滚：删除 `include-ipv4.txt` 对应段 → `/usr/local/bin/manual-refresh ip-rules`；域名规则回滚在 domain-rules 侧。

## 2026-11-26 重构说明（direct-ip → ip-rules）

- 目录改名 `scripts/direct-ip` → `scripts/ip-rules`（用户指定），服务端入口改为 `/usr/local/bin/ip-rules-update`、`/etc/cron.d/ip-rules`、发布根 `/var/lib/ip-rules`。
- **纯 IP 化**：删除 `input/domain/`、`input/upstream/steam-cn.*`、`direct-domains.json`、DNS 解析（`resolvers`）、`direct-domains-resolved.json`、`steam-cn` 源；`output` 改为扁平。
- **从 domain-rules 迁入 IP 表**：`cn`、`cn-telecom`、`cn-mobile`、`cn-unicom`、`cn-cernet`、`blacklist` 六张表及产物（原 `gen_rules.py` 的 CIDR 表逻辑）改由本管线生成；`domain-rules` 只保留域名规则。产物文件名/表名/路径不变，ROS 与 OxiDNS 无需改。
- 直连表的排除层不再读 `domain-rules/output/blacklist.rsc` 文件，而是用本管线本次生成的 blacklist 地址集合，两管线完全解耦。
- 升级时服务端需一次性迁移 `/srv/github-mirror/static/ros/` 里旧的普通文件（`cn*.rsc`、`blacklist.rsc`）为 `/var/lib/ip-rules/current` 的 symlink，并删除旧的 `direct-domains-resolved.json` 链接；ROS 端脚本不改。
