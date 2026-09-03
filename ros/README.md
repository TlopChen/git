# ROS 规则（ROS address-list 脚本）

本目录存放由 VPS 上的镜像管线（`ros/generator/`）从上游规则源生成的 RouterOS 可导入脚本。数据每日 06:00（VPS 时间）自动刷新，本仓库为其版本留档。

## 文件

| 文件 | 地址表 | 内容 |
|---|---|---|
| `cn.rsc` | `CN` | 中国大陆全部 CIDR（Loyalsoldier cncidr ∪ metowolf CN，已合并相邻网段） |
| `cn-telecom.rsc` | `CT` | 中国电信网段 |
| `cn-mobile.rsc` | `CM` | 中国移动网段 |
| `cn-unicom.rsc` | `CU` | 中国联通网段 |
| `cn-cernet.rsc` | `CC` | 教育网（CERNET）网段 |
| `blacklist.rsc` | `blacklist`（与域名分流共用） | 被墙 IP 服务合集（Telegram + Twitter + MikroTik），带 `ros-rules-auto` 标记，只清理自身不动 DNS 动态条目；导入时自动迁移旧列表 ROS_BLACKLIST |
| `proxy-domain.rsc` | `blacklist`（DNS 静态） | 代理侧域名 FWD 表（手工 blacklist + Loyalsoldier gfw.txt + blackmatrix7 Proxy/OpenAI/Claude/Anthropic/Gemini，PSL 收敛到注册域，零正则，match-subdomain 覆盖子域） |

注：不做 DNS 层广告域名表——ROS 的 DNS 性能有限，域名级拦截如以后有需要，用小规模精选表在 OxiDNS 上单独做。

## ROS 端用法

走 WireGuard 隧道拉取（无需公网开放端口）：

```
/tool fetch url="http://192.168.40.1:18080/ros/cn.rsc" mode=http
/import file-name=cn.rsc
```

定时自动化示例：

```
/system scheduler
add name=sync-rules interval=1d on-event="\
    /tool fetch url=\"http://192.168.40.1:18080/ros/cn.rsc\" mode=http;\
    /import file-name=cn.rsc"
```

脚本为 remove-then-add 幂等更新：重复导入不会产生重复条目，只会整表刷新。

## 重新生成（VPS 上）

```
python3 /srv/github-mirror/gen_rules.py        # 手动立即生成
# 或等每日 cron（0 6 * * *），日志在 /var/log/ros-rules-daily.log
```

生成器与源配置在 `ros/generator/`（`gen_rules.py`、`sources.json`、`repos.json`）。
新增规则源：编辑 `sources.json` 加入上游 raw 地址，重跑生成器即可。

## 上游致谢

- [metowolf/iplist](https://github.com/metowolf/iplist) — 运营商/国家 CIDR
- [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) — cncidr / telegramcidr / gfw
- [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) — Twitter IP 段、Proxy 域名、AI 域名（OpenAI/Claude/Anthropic/Gemini）

数据版权归上游项目所有，本仓库仅做格式转换与聚合，供个人网络使用。

## 关于 blacklist 域名表（无导入顺序问题）

`proxy-domain.rsc` 是 blacklist 域名表的**唯一来源**，每次导入整表重建，由两个手工文件 + 上游自动生成：

- **`ros/generator/manual-blacklist.txt`** —— 走代理黑名单（正向）。每行一个域名，`#` 注释。
  只保留上游没有、手工补充的域名（当前 247 条，已剔除与上游重复的冗余）。
  生成器打 `comment="ros-rules-manual"` 标记合入。
- **`ros/generator/exclude-blacklist.txt`** —— 反向剔除名单（负向）。这些域名（及其所有子域）
  从上游自动层剔除、按大陆直连，例如 bing.com、微软/苹果国内站、cloudfront.net（公共 CDN）、
  国内券商 `.cn` 站（富途/老虎/嘉信/长桥）。生成器给上游自动域名打 `comment="ros-rules-auto"`
  标记，被 exclude 命中的不会出现在产物里。

要增删域名：编辑 VPS 上对应的 `/srv/github-mirror/manual-blacklist.txt`（加代理）
或 `/srv/github-mirror/exclude-blacklist.txt`（减代理），下次日更（06:00）自动生效；
或手动跑 `python3 /srv/github-mirror/gen_rules.py` 立即重生成。
**不要再导入旧的手工 gfw.rsc**——它会清掉整表，与生成文件互相覆盖。
