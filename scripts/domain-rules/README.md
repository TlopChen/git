# domain-rules —— 域名 + CIDR 规则管线

上游开源规则源 → 处理脚本 → RouterOS / OxiDNS 可直接消费的产物。

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
```

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
| `cn.rsc` / `cn-telecom.rsc` / `cn-mobile.rsc` / `cn-unicom.rsc` / `cn-cernet.rsc` | RouterOS | 国内网段（合并后）与各运营商 |
| `blacklist.rsc` | RouterOS | 硬编码 IP 类服务兜底（Telegram / Twitter + 公共 DNS 等手工段） |
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

## 为什么还要 IP 段

Telegram 这类客户端把 DC IP 硬编码，DNS 解析失败时直接回退硬编码 IP，绕过 DNS 重定向，
因此必须用地址表兜底。增删这类段：改 `sources.json` 的 `blacklist.sources` / `extra_cidrs`。

## 手工维护

| 需求 | 改哪个 |
|---|---|
| 某域名强制走代理 | `input/manual/manual-blacklist.txt` 加一行 |
| 某域名从代理层剔除（走直连） | `input/manual/exclude-blacklist.txt` 加一行 |
| 国内域名表补充/纠正 | `input/manual/manual-cn-domains.txt`（`domain:` / `full:` 前缀） |
| 增删/更换上游源 | `sources.json` |

改完等 06:00 日更，或跑 `manual-refresh rules` 立即重生成手工部分（不拉上游）。