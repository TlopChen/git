# 直连 IPv4 维护管线

在广州节点运行：上游 Git 文件 → 本地原始快照 → 严格解析 CIDR → 国内并集 + 指定主机解析 + 手工添加 → 排除 → 无损聚合 → 纯 CIDR / ROS 地址表 → Git 留档与隧道内 HTTP 分发。

此目录的脚本、配置、手工表均以 `/root/git/scripts/direct-ip`（本仓库）为权威。旧 `/srv/github-mirror/gen_rules.py` 不生成或覆盖本目录产物。本管线不会登录或修改 AR/ROS，不自动接入现有 blacklist-sync。

## 目录结构（脚本 / input / output 分层）

与 `scripts/domain-rules` 保持同一约定：脚本和上游清单在仓库根，手工输入在 `input/manual`，上游原始快照在 `input/upstream`，产物在 `output`。

```text
scripts/direct-ip/
  gen_direct.py          生成器（标准库 + git + dig）
  asn_sources.py         RIPE RIS 整 ASN 快照
  update.sh              定时/手工运行入口（git 提交 raw/output）
  sources.json           上游清单单一入口（CN 三源 + direct_asns + resolvers）
  input/
    manual/              手写输入，入库；改动后由 manual-watch 触发重生成
      include-ipv4.txt     手工直连 CIDR
      exclude-ipv4.txt     手工排除 CIDR（优先于所有来源和手工添加）
      direct-domains.json  精确主机例外（国内 DNS 解析为 /32）
      pending-services.json 待采集/已处理服务的跟踪状态
    upstream/            上游原始快照（本地留档，抓取失败按年龄+哈希回退）
      <source>.txt/.json   gaoyifan/metowolf/misaka/steam 快照 + 来源 commit/sha256
      as53850-*.json       RIPE RIS 原始响应与元数据
  output/                生成产物（含报告）
  service-evidence/      单个服务的实测证据（如 sufun.json、girigiri.json）
  licenses/              上游许可
```

为什么快照和产物都入库：上游 GitHub/RIPE 抓取失败时，管线按 `input/upstream` 里的快照回退（72 小时内且校验通过）继续生成；即使某次推送/抓取全挂，`output/` 的历史版本仍在 Git 与 `/var/lib/direct-ip/releases` 里，能顶住一次故障。

## 来源选择

| 源 | 输入 | 用途 |
|---|---|---|
| [gaoyifan/china-operator-ip](https://github.com/gaoyifan/china-operator-ip) | `ip-lists:china.txt` | 国内 BGP/运营商分类和项目提供的兜底，日更 |
| [misakaio/chnroutes2](https://github.com/misakaio/chnroutes2) | `master:chnroutes.txt` | BGP 收集器聚合补充，小时更 |
| [metowolf/iplist](https://github.com/metowolf/iplist/blob/master/docs/china.md) | `master:data/special/china.txt` | 中国内地地理库补充；采用内地专用表，不是厂商全球 ASN |
| [v2ray/domain-list-community](https://github.com/v2ray/domain-list-community/blob/master/data/steam) | `master:data/steam` 中 `@cn` 条目 | Steam 国内下载/CDN 主机，包括阿里、网宿、白山、新流云等 |

国内采用三源并集，倾向减少漏直连；任意一个源的误分类也可能进入结果，不代表每个 IP 均经本地宽带实测。`direct-ipv4-report.json` 列出各源覆盖和独有地址量，误判用 `exclude-ipv4.txt` 纠正。未选长期少更新的 17mon 作为默认运行源；不叠加多个实际同源的包装列表。

云厂家/CDN 的国内部署地址通过上述 CN 集合覆盖，不将阿里云、腾讯云、Cloudflare、Akamai 等整个全球 ASN 放行。需要直连的海外主机逐个写进 `input/manual/direct-domains.json`，或把已核验网段写入 `input/manual/include-ipv4.txt`。

原始文件、来源 commit、SHA256、抓取时间保存在 `input/upstream/`。广州访问 GitHub raw HTTPS 不稳定，因此用已配置的 GitHub SSH 只取需要的文件；缓存放 `/var/cache/direct-ip-upstreams`。下载内容严格作为数据，不执行上游脚本。

## 权威顺序与手工维护

生成时按固定层次组装（代码里 `assemble()`，报告 `precedence` 字段同名输出）：

1. **上游源（权威底表）**：`sources.json` 的 CN 三源并集；单源条数与覆盖量有上下限校验。
2. **手工层**：`input/manual/include-ipv4.txt` 的手工 CIDR + `sources.json` 的 `direct_asns` 整 ASN 公告 + `input/manual/direct-domains.json` 的精确主机解析（/32）。手工是"在源之上加例外"，不会删除源里的条目。
3. **排除层（优先于前两层）**：`input/manual/exclude-ipv4.txt` + 现有 `blacklist.rsc` 的静态 IPv4（强制代理语义）。被排除层吃掉的手工/源条目会写进报告 `manual_conflicts`，不静默失效。
4. **派生兜底表**：`DIRECT_IP_NOCM`（减移动网段）/ `DIRECT_IP_NOCT`（减电信网段），只用于两条家宽线路各自承载"不属于对端运营商"的前缀，不是新的权威来源。

维护要点：

- `include-ipv4.txt`：纯 IPv4/CIDR，一行一条，可以有 `#` 注释；回滚就是删对应行。
- `exclude-ipv4.txt`：从最终集合做地址差集，支持从大网段排除单个 `/32`。
- `direct-domains.json`：精确主机名及原因，双国内 DNS（223.5.5.5、119.29.29.29）查询 A 记录取并集，只生成 `/32`；只解析列出的主机本身，不枚举子域。当前收录 GiriGiri 的 6 个主机（见文末）。
- 现有 `blacklist.rsc` 的静态 IPv4 强制代理地址自动加入排除集合；排除高于 CN、DNS 例外和手工添加。冲突会列在解析报告的 `excluded_addresses` 与总报告的 `manual_conflicts`。
- Steam 源仅取 `@cn`；`full` 和后缀语义保存在域名报告中。不对全球 `steamcontent.com`、Steam 社区做全域放行。上游 `@cn` 里已废弃的主机用 `sources.json` 的 `exclude_hosts` 剔除（当前 6 个网宿/品云旧域：csgo.wmsj.cn、dota2.wmsj.cn、st.dl.pinyuncloud.com、steampowered.com.8686c.com、steamstatic.com.8686c.com、wmsjsteam.com），避免每日解析告警。
- 速方云：`sources.json` 的 `direct_asns: [53850]` 按天跟随 RIPE RIS 公告，包含该 ASN 全部可观测 IPv4 起源前缀，不局限于速方云业务（用户明确指定的例外）。

DNS 例外随每日 full 刷新一次（2026-09-27 起不再做每 10 分钟检测），使用广州所见的两家国内 DNS 结果，可能与家庭客户端命中的 CDN 节点不同；这不是全量 CDN IP 清单，也不是与客户端 DNS 同步的首包保证。域名新增地址仍需考虑更新窗口。当前仅生成 IPv4，与现有未启用 IPv6 的导入策略一致。

## 输出与分发

| 输出 | 内容 |
|---|---|
| `output/direct-ipv4.txt` | 完整可用直连集合，纯 CIDR 无注释 |
| `output/direct-cn-ipv4.txt` | 国内三源并集减去排除 |
| `output/direct-manual-ipv4.txt` | 手工层（include + direct_asns + direct-domains 解析）减去排除 |
| `output/direct-extra-ipv4.txt` | 手工/域名中超出国内集合的部分 |
| `output/direct-excluded-ipv4.txt` | 本次排除集合 |
| `output/direct-ipv4.rsc` | `/ip firewall address-list`，表名 **DIRECT_IP** |
| `output/direct-ipv4-nocm.rsc` | 同上，表名 **DIRECT_IP_NOCM**：`DIRECT_IP` 减 `cn-mobile.rsc`（CM）地址，电信线路专用 |
| `output/direct-ipv4-noct.rsc` | 同上，表名 **DIRECT_IP_NOCT**：`DIRECT_IP` 减 `cn-telecom.rsc`（CT）地址，移动线路专用 |
| `output/direct-domains-resolved.json` | 精确主机、原始匹配语义、各 DNS 返回、失败/缓存状态、排除冲突 |
| `output/direct-ipv4-report.json` | 规模、各层贡献（`precedence`/`manual_*`）、源贡献、与 CT/CM 的覆盖差异、警告 |

例如内网下载地址：`http://192.168.40.1:18080/ros/direct-ipv4.txt`、`http://192.168.40.1:18080/ros/direct-ipv4.rsc`、`http://192.168.40.1:18080/ros/direct-ipv4-nocm.rsc`、`http://192.168.40.1:18080/ros/direct-ipv4-noct.rsc`。本管线不执行 ROS 导入。按运营商拆分的派生表（NOCM/NOCT）每日随 `direct-ipv4.rsc` 重算，差集依据是分发目录里当日最新的 `cn-telecom.rsc`/`cn-mobile.rsc`。文件是地址表而不是 `/ip route` 静态路由，选路由 BGP 自环注入 + AR 侧策略决定。

ROS 脚本先添加缺失地址、更新本管线拥有的记录标记，全部成功后再清理旧的 `direct-ip-auto:` 记录；不清空整表，不删除手工条目，重复导入可复用现有地址。`/32` 在 ROS 地址表中按主机表示匹配。需串行导入。

HTTP 文件通过 `/var/lib/direct-ip/current` 指向完整 release，校验后原子切换。多文件下载请核对报告/源版本；单次下载得到完整文件，多个 HTTP 请求跨更新边界仍可能看到不同版本。历史版本保留在 `releases/`（按内容去重），Git 保留原始源和产物历史。

## 运行与故障

依赖 Python 3 标准库、git、dig、flock，复用广州现有工具和 GitHub SSH 主机认证，不复制认证材料。

```sh
# 全量源与 DNS（每日北京时间 06:15）
/usr/local/bin/direct-ip-update full
# 复用已验证的本地 IP 源，仅刷新 DNS（手工表变更走这条）
/usr/local/bin/direct-ip-update dns
# 单元测试（含目录分层、权威顺序、排除优先的回归）
cd /root/git/scripts/direct-ip && python3 -m unittest -v test_direct test_asn
```

计划任务在 `/etc/cron.d/direct-ip`（06:15 的 full；手工改动由 `scripts/_infra/manual-watch.sh` 每分钟检测后触发 dns 模式），日志 `/var/log/direct-ip.log`。与旧任务共用 `/tmp/ros-rules.lock`，避免并发提交。`update.sh` 只提交本目录 `input/upstream` 与 `output`，已有未提交修改时停止（手工表改动要先提交），Git 冲突时停止，不强推；上次 push 失败且已有本地提交时下次重试。

CIDR 源单源至少 1000 条、整体至少 1000 条，校验公网地址、默认路由/私网、覆盖量和异常增减。源抓取失败可使用 72 小时以内的已验证原始快照，超过则停止发布；IPv4 上游分支超过 14 天未更新时视为抓取失败。必需域名解析失败可保留 24 小时内最近成功结果，过期停止；非必需 Steam 主机过期会剔除并报告。警告写入报告和日志，不静默冒充更新成功。

不要为绕过变化阈值盲目清除上次结果。先核对上游差异和排除表。回退时可原子调整 `current` 为之前的 release；改规则和脚本应通过正常 Git 提交回退。禁用本任务只需注释 `/etc/cron.d/direct-ip` 的任务，不影响旧管线。

## 数据归属

上游保留各自版权与许可，来源链接及快照 commit 可追溯；许可文本见 `licenses/`。misaka LICENSE 为 CC BY-SA 4.0（其旧 README 链接仍指 2.0），含其数据的聚合衍生产物采用 CC BY-SA 4.0：https://creativecommons.org/licenses/by-sa/4.0/ 。对上游数据的改动为筛选、规范化、合并、地址差集及 ROS 格式转换。gaoyifan 与 V2Ray 的 MIT 许可随附；metowolf 源未找到根目录 LICENSE，保留来源署名与原始数据，不声称重新许可该源。

## AS53850 整 ASN 直连（2026-09-27 用户明确授权）

`sources.json` 的 `direct_asns: [53850]` 按天跟随 RIPE RIS 公告数据，包含该 ASN 的全部可观测 IPv4 起源前缀，不局限于速方云业务。与一般云/CDN不整ASN放行的默认规则不同，这是用户指定的例外。

数据源：https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS53850&min_peers_seeing=1 。查询近24小时，按响应 `query_endtime` 过滤时间线，只取快照端点仍可见的前缀，避免直接混入两周历史中已撤销条目。RIS有采集延迟，不代表实时全球完整路由；快照时间写入报告，超过48小时拒绝使用。抓取失败可回用完整性通过且快照仍未过期的缓存，失败不覆盖旧发布。

`input/upstream/as53850-response.json` 保留全部API响应（含IPv6），`input/upstream/as53850-meta.json` 保留来源、时间和SHA256；`output/direct-as53850-ipv4.txt` 为无损聚合后的ASN专表，最终并入 `direct-ipv4.txt` 和 ROS `DIRECT_IP`。现有blacklist/手工排除仍优先，IPv6尚未导入。原来的手工 `/21` 已删除，未来撤销该网段可正常随ASN源收敛。

## GiriGiri 动漫站（2026-11-26 用户授权，速方云式）

对象：`ani.girigirilove.com` 播放页及其视频/CDN。作为对比，速方云案例见 `service-evidence/sufun.json`（先钉 `192.154.104.0/21`，后改为整 AS53850 自动维护）。

现场观测（2026-11-25/26，详见 `service-evidence/girigiri.json`）：

- 播放链路域名都在 `*.girigirilove.com` / `*.girigirilove.net`：`ani`（前端）、`m3u8`（接口）、`ana`（MP4 视频）、`danmu`（弹幕）、`jpg`（图片）。
- 后端是自建反代池：池 A `g2014c9.cdn.girigirilove.com` 静态 7 IP；池 B `gcacac7.cdn.girigirilove.net` 按运营商 GeoDNS，并集 24 IP（洛杉矶 19 + 莫斯科 5，7 个 ASN），**无大陆节点**。
- 站方按 IP 地区屏蔽 US/JP/EU：无扩展浏览器从日本出口打开播放页会 302 到 `502.girigirilove.com`；家庭当前经隧道看视频属于"可播但绕路 + 占隧道流量"。
- 视频单集约 176 MB / 24 分钟（≈1 Mbps）；家宽经隧道实测 0.15-0.81 MB/s，CN 直连参照 0.08-2.3 MB/s。

处理（速方云式：holder 网段覆盖 + 精确主机跟随）：

1. `input/manual/include-ipv4.txt` 收录 15 条 holder `/24`（见该文件末段注释），覆盖 24 个已观测节点并容忍换机器/IP 漂移；这是"公告段覆盖"，与速方云先前的 `/21` 同性质。副作用是同 `/24` 邻居地址也会直连（廉价 VPS 段，影响可忽略）；要最小面可改回逐个 `/32`。
2. `input/manual/direct-domains.json` 收录 6 个精确主机，每日用国内 DNS 解析结果补 `/32`，跟随 CDN 新增 IP。
3. `scripts/domain-rules/input/manual/manual-cn-domains.txt` 收录 `domain:girigirilove.com`、`domain:girigirilove.net`，让 OxiDNS 判国内、停止 `ros_blacklist` 注入；否则 OxiDNS 动态注入的 `/32` 会压过本表继续走隧道。
4. 生效后需在 ROS 删除这些 IP 的历史动态 `/32`（comment 前缀 `oxi`），或等 `fixed_ttl` 24 小时自然过期。

回滚：删除第 1、2 步对应条目 → `/usr/local/bin/manual-refresh direct-ip`；删除第 3 步两行 → `/usr/local/bin/manual-refresh rules`。域名回到日本分支后 blacklist 会重新注入，路由自动回隧道。
