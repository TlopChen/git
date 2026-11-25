# domain-rules —— 域名规则管线

上游开源域名规则源 → 处理脚本 → RouterOS / OxiDNS 可直接消费的产物。

本管线**只处理域名**。IPv4 地址表（CN/运营商/blacklist）自 2026-11-26 起在 `scripts/ip-rules` 生成，两条管线各自 IN/OUT、互不读取产物。

```text
input/upstream/   上游原始快照（未处理，带 _provenance.json 出处）
input/manual/     人工维护的输入（以本仓库为准，网页可直接改）
*.py              处理脚本
output/           产物（处理后，不手改）
```

## 命令

```sh
cd /root/git/scripts/domain-rules
python3 gen_rules.py                     # 全量（走本机镜像 :18080）
python3 gen_rules.py --offline           # 只用已验证快照，不联网
python3 gen_rules.py --only proxy-domain # 只重建一张表
python3 gen_oxi.py                       # proxy-domain → OxiDNS domain_set
python3 gen_cn.py                        # 国内域名表（GEN_CN_OFFLINE=1 可离线）
python3 fetch_bin.py                     # geosite.dat 等二进制（直接发 HTTP 目录）
````

## 来源清单：sources.json

加减上游**只改这里**：

```jsonc
"upstreams": { "owner/repo": {"branch": "master"} },
"tables": {
  "proxy-domain": { "type": "rosdns", "list": "blacklist",
                    "sources": ["owner/repo:path/in/repo", ...],
                    "manual": "input/manual/manual-blacklist.txt",
                    "exclude": "input/manual/exclude-blacklist.txt" }
},
"cn-domains": { "dnsmasq_source": "...", "sources": [...], "manual": "...", "min_rules": 5000 },
"binaries":   [ {"name": "geosite.dat", "url": "...", "min_bytes": 100000} ]
```

- 引用写法 `owner/repo:path`，分支从 `upstreams` 取；完整 URL 由脚本拼出。
- 新仓库还要加进 `../_infra/repos.json`（镜像白名单），否则取数会明确报错。
- 快照落在 `input/upstream/<owner>__<repo>/<path>`，出处记在同目录 `_provenance.json`。

## 产物与消费端

| 产物 | 消费端 | 内容 |
|---|---|---|
| `proxy-domain.oxi.txt` | OxiDNS `domain_set` | 代理域名（`domain:` 后缀 / `full:` 精确） |
| `cn-domains.oxi.txt` | OxiDNS `domain_set` | 国内域名表（「非国内即走远端」的反转判据） |
| `proxy-domain.domains.txt` / `.exact.txt` | 通用中间产物 | 裸后缀域 / 精确 FQDN，一行一个 |
| `proxy-domain.rsc` | RouterOS | `/ip dns static type=FWD`，带 match-subdomain 语义与 blacklist 打标 |
| `geosite.dat` | OxiDNS | 二进制，只发 HTTP，不进 Git |

RouterOS 取用：`http://192.168.40.1:18080/ros/<文件>`（内网隧道；公网请用仓库 raw 链接）。
`.rsc` 为 remove-then-add，重复导入幂等。

## 语义（勿破坏）

- **后缀域**：`DOMAIN-SUFFIX,x` / 裸域名 → PSL 收敛到注册域 + 后缀去重 →
  OxiDNS `domain:` / RouterOS `match-subdomain=yes`。
- **精确域**：`DOMAIN,x` → 不收敛 → OxiDNS `full:` / RouterOS `match-subdomain=no`。
  ⚠️ 精确条目**绝不会**被放大成整域（历史事故：`apm-misaka.biliapi.net` 被放大成 `biliapi.net`）。
- **排除名单**命中项及其子域整体剔除；手工层与自动层合并去重。
- 有条数下限保护：上游拉取异常时**拒绝生成**，不产出空表覆盖。

## 手工维护

| 需求 | 改哪个 |
|---|---|
| 某域名强制走代理 | `input/manual/manual-blacklist.txt` 加一行 |
| 某域名从代理层剔除（走直连） | `input/manual/exclude-blacklist.txt` 加一行 |
| 国内域名表补充/纠正 | `input/manual/manual-cn-domains.txt`（`domain:` / `full:` 前缀） |
| 增删/更换上游源 | `sources.json` |

改完等 06:00 日更，或跑 `manual-refresh rules` 立即重生成手工部分（不拉上游）。

## 与 ip-rules 的分工（2026-11-26 起）

| 管线 | 管什么 | 目录 |
|---|---|---|
| `domain-rules` | 域名（OxiDNS domain_set、RouterOS FWD 域名表） | `scripts/domain-rules/` |
| `ip-rules` | IPv4 地址表（直连表、CN/运营商表、blacklist 表） | `scripts/ip-rules/` |

- 原 `sources.json` 的 `cn`、`cn-telecom`、`cn-mobile`、`cn-unicom`、`cn-cernet`、`blacklist` 六张 CIDR 表（以及 `metowolf/iplist` 相关源）已迁到 `ip-rules`；本目录的 `output/` 不再有 `cn*.rsc` / `blacklist.rsc`。
- 相关程序逻辑（`parse_cidrs`、RIPE ASN 查询、CIDR 表 `.rsc` 渲染）一并迁走，本管线不再联网查询 ASN。
- 产物文件名/HTTP 路径不变，ROS 与 OxiDNS 消费端无需改。
- 两管线互不读取对方 `output/`：域名规则不依赖 IP 表，IP 表也不读 `blacklist.rsc` 文件（改用本次生成的 blacklist 地址集合）。
