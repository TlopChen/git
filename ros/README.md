# 分流规则集（代理域名表 + 国内 IP 段）

个人网络分流用的规则集，每日自动从上游开源规则源生成并留档。
**下游按 URL 直接拉取即可，无需本地生成。**

---

## 快速拉取

### OxiDNS（`domain_set` 文本）

```
https://raw.githubusercontent.com/TlopChen/git/main/ros/proxy-domain.oxi.txt
```

每行一条：

- `domain:example.com` —— 后缀域，匹配该域及其所有子域
- `full:host.example.com` —— 精确主机名，只匹配这一个

### RouterOS（可直接 `/import` 的脚本）

```
/tool fetch url="http://192.168.40.1:18080/ros/proxy-domain.rsc" mode=http
/import file-name=proxy-domain.rsc
```

该地址走 WireGuard 隧道的私有镜像；公网环境请从本仓库 raw 链接下载后导入。
脚本为 remove-then-add 幂等：重复导入不会产生重复条目，只会整表刷新。

### 通用纯域名列表

- `proxy-domain.domains.txt` —— 后缀域，一行一个裸域名
- `proxy-domain.exact.txt` —— 精确 FQDN，一行一个

适合 dnsmasq / unbound / AdGuard Home / sing-box / Clash 等自行转换。

---

## 文件清单

| 文件 | 消费端 | 内容 |
|---|---|---|
| `proxy-domain.oxi.txt` | OxiDNS `domain_set` | 代理域名（`domain:` / `full:` 前缀） |
| `proxy-domain.domains.txt` | 通用（中间产物） | 代理域名，后缀域，一行一个 |
| `proxy-domain.exact.txt` | 通用（中间产物） | 代理域名，精确 FQDN |
| `proxy-domain.rsc` | RouterOS | `/ip dns static type=FWD` 脚本（带 `match-subdomain` 语义与 blacklist 打标） |
| `cn.rsc` | RouterOS | 中国大陆全部 CIDR（已合并相邻网段） |
| `cn-telecom.rsc` / `cn-mobile.rsc` / `cn-unicom.rsc` / `cn-cernet.rsc` | RouterOS | 电信 / 移动 / 联通 / 教育网 网段 |
| `blacklist.rsc` | RouterOS | 被墙服务的基础 IP 段（Telegram / Twitter 等） |

设计上**不做广告域名表**——域名级拦截建议在消费端自行维护小精选表。

---

## 数据来源

| 上游源 | 用途 |
|---|---|
| `Loyalsoldier/clash-rules` → `gfw.txt` | 被墙域名 |
| `Loyalsoldier/clash-rules` → `proxy.txt` | `geolocation-!cn` 全量兜底 |
| `blackmatrix7/ios_rule_script` → `Proxy_Domain.txt` | 代理域名 |
| `blackmatrix7` → `OpenAI` / `Claude` / `Anthropic` / `Gemini` `.list` | AI 服务专项 |
| `Loyalsoldier/clash-rules` → `cncidr.txt` | 国内 IP |
| `metowolf/iplist` → `CN` / `isp/*.txt` | 国内 IP（含各运营商） |

本地修正层（在 `generator/` 下，**改动以本仓库这份为准**）：

- `manual-blacklist.txt` —— 手工强制入代理层的域名
- `exclude-blacklist.txt` —— 反向剔除名单（命中项及其所有子域一并排除）

 选取原则：只列**确信未被墙、且流量大或高频**的域名（微软系、苹果系、硬件驱动、常用开发工具、游戏 CDN、公共 CDN 等）。
 边界不清的一律不列——排除即走直连，若它其实被墙就会拿到污染结果。

---

## 生成规则（语义，勿破坏）

- **后缀域**：`DOMAIN-SUFFIX,x` / 裸域名 → 用 PSL 收敛到注册域 + 后缀去重 → OxiDNS `domain:` / RouterOS `match-subdomain=yes`
- **精确域**：`DOMAIN,x` → 不收敛 → OxiDNS `full:` / RouterOS `match-subdomain=no`

  ⚠️ **精确条目绝不会被放大成整域**：这是刻意保证的。历史上曾把某个精确 FQDN 概括成整域，
  导致该域下的国内子域被错误地走代理 DNS，出现解析异常。
- 剔除名单命中项**及其子域**全部排除；`manual` 与剔除后的自动层合并去重。
- 生成器有条数下限保护：上游拉取失败（条数异常少）时**拒绝生成**，避免产出空表覆盖。

---

## 关于 IP 段类规则（为什么不能只靠域名）

有些服务**不走 DNS**，最典型的是 **Telegram**：官方客户端把数据中心（DC）的 IP 硬编码在程序里，
当 DNS 解析失败或缓慢时直接回退到硬编码 IP，**完全绕过基于 DNS 的重定向**。
所以对这类服务，域名规则无效，必须用 IP 段兜底。

`blacklist.rsc` 专门承担这个职责，内容来自三类：

| 源 | 内容 |
|---|---|
| `Loyalsoldier/clash-rules` → `telegramcidr.txt` | Telegram 段（与官方 `core.telegram.org/resources/cidr.txt` 对齐；本仓库用 /21 合并官方拆分的 /22，另含 `95.161.64.0/20`） |
| `blackmatrix7` → `Twitter.list` | Twitter / X 段 |
| `sources.json` → `blacklist.extra_cidrs` | 手工补充（被干扰的公共 DNS `8.8.8.8` / `1.1.1.1` 等） |

**增删这类段**：编辑 `generator/sources.json` 里 `blacklist` 条目的 `sources` 或 `extra_cidrs`，
下次日更自动生效（源文件会同步留档到 `src/`，产物为 `blacklist.rsc`）。
判定某服务是否属于此类：看它客户端是否**直连硬编码 IP**——是则需要 IP 段，否则域名规则即可覆盖。

## 更新

- 每日 **06:00（VPS 时间）** 自动：拉上游 → 生成全部产物 → 提交本仓库
- 手动立即生成：`python3 generator/gen_rules.py`

产物路径对应关系：生成器输出到工作目录的 `static/ros/`，随后同步进本仓库的 `ros/`。

---

## 增删规则

改 `generator/` 下的清单文件（**以本仓库这份为准，不要改部署端的旧副本**）：

| 需求 | 改哪个 |
|---|---|
| 某域名要强制走代理 | `manual-blacklist.txt` 加一行 |
| 某域名要从代理层剔除（走直连） | `exclude-blacklist.txt` 加一行 |
| 增加/更换上游源 | `sources.json` 的 `sources` 数组 |
| 新增消费端格式 | 在 `gen_oxi.py` 旁加一个适配器，只读 `proxy-domain.domains.txt` / `.exact.txt` |

改完等日更自动生效，或手动重跑生成器。

---

## 致谢

- [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules)
- [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script)
- [metowolf/iplist](https://github.com/metowolf/iplist)
- [publicsuffix/list](https://github.com/publicsuffix/list)

数据版权归上游项目所有；本仓库仅做格式转换与聚合，供个人网络使用。
