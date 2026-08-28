# ROS 规则（ROS address-list 脚本）

本目录存放由 VPS 上的镜像管线（`ros/generator/`）从上游规则源生成的 RouterOS 可导入脚本。数据每日 06:00（VPS 时间）自动刷新，本仓库为其版本留档。

## 文件

| 文件 | 地址表 | 内容 |
|---|---|---|
| `cn.rsc` | `ROS_CN` | 中国大陆全部 CIDR（Loyalsoldier cncidr ∪ metowolf CN，已合并相邻网段） |
| `cn-telecom.rsc` | `ROS_CN_TELECOM` | 中国电信网段 |
| `cn-mobile.rsc` | `ROS_CN_MOBILE` | 中国移动网段 |
| `cn-unicom.rsc` | `ROS_CN_UNICOM` | 中国联通网段 |
| `cn-cernet.rsc` | `ROS_CN_CERNET` | 教育网（CERNET）网段 |
| `telegram.rsc` | `ROS_TELEGRAM` | Telegram 网段 |
| `blacklist.rsc` | `ROS_BLACKLIST` | 被墙 IP 服务合集（Telegram + Twitter），按需扩充 |
| `lan.rsc` | `ROS_LAN_LOCAL` | 内网/保留网段 |
| `ad_domains.domains.txt` | —（DNS 层） | 广告域名表（约 28 万条），供 OxiDNS 等 DNS 服务使用 |

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
# 或等每日 cron（0 6 * * *），日志在 /var/log/ros-rules-gen.log
```

生成器与源配置在 `ros/generator/`（`gen_rules.py`、`sources.json`、`repos.json`）。
新增规则源：编辑 `sources.json` 加入上游 raw 地址，重跑生成器即可。

## 上游致谢

- [metowolf/iplist](https://github.com/metowolf/iplist) — 运营商/国家 CIDR
- [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) — cncidr / telegramcidr / lancidr
- [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script) — Twitter IP 段、广告域名表

数据版权归上游项目所有，本仓库仅做格式转换与聚合，供个人网络使用。
