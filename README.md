# TlopChen/git

个人网络的规则生成仓库。**主体是脚本**：上游源输入 → 脚本处理 → 输出产物。
ROS / AR / OxiDNS 只是产物的消费端，不在这里定义。

```text
/root/git
├── README.md
└── scripts/
    ├── domain-rules/     域名 + CIDR 规则管线
    ├── direct-ip/        直连 IPv4 管线
    ├── _infra/           服务端分发与调度（mirror / cron / 发布脚本）
    └── ros-side/         ROS 本地脚本留档（消费端；Git 只存不跑）
```

## 模块索引

| 管线 | 源输入（未处理） | 处理脚本 | 产物（处理后） | 消费端 |
|---|---|---|---|---|
| domain-rules | `scripts/domain-rules/input/` | `gen_rules.py` `gen_cn.py` `gen_oxi.py` `fetch_bin.py` | `scripts/domain-rules/output/` | RouterOS、OxiDNS |
| direct-ip | `scripts/direct-ip/raw/` + 模块根手工表 | `gen_direct.py` `asn_sources.py` | `scripts/direct-ip/output/` | RouterOS |

每个模块的详细契约见各自目录下的 `README.md`。

## 日常运行

| 时间（北京时间） | 入口 | 动作 |
|---|---|---|
| 06:00 | `scripts/_infra/ros-rules-daily.sh` | 拉仓库 → 生成 → 发布到内网 HTTP → 提交推送 |
| 06:15 | `scripts/direct-ip/update.sh full` | 刷新直连表并原子发布 |
| 06:30 | ROS `/system script run ros-rules-sync` | ROS 自己拉六表并导入（不在这里） |
| 手动 | `manual-refresh rules` / `direct-ip` | 只重生成手工部分，不拉上游 |

手工改动生效路径：广州 `manual-refresh` 重生成产物 → ROS 上按需跑一次 `ros-rules-sync`。
ROS 侧不定时轮询、不做哈希校验。

## 约定

1. **一个管线一个目录**，固定结构：`README.md` / `sources.json` / `input/` / `output/`。
2. **加减上游只改 `sources.json`**（新仓库另需加进 `scripts/_infra/repos.json` 白名单），
   解析逻辑不写死来源。
3. `input/upstream/` 是上游快照，附 `_provenance.json`（url / branch / sha256 / 抓取时间）；
   `input/manual/` 是人维护的输入，以本仓库为准。
4. `output/` 是产物，不手改；由 `scripts/_infra/publish.sh` 平铺发布到内网 HTTP 根。
5. ROS 走 `http://192.168.40.1:18080/ros/<文件>`，该路径与文件名保持不变。

## 公开拉取地址（raw）

```
https://raw.githubusercontent.com/TlopChen/git/main/scripts/domain-rules/output/proxy-domain.oxi.txt
https://raw.githubusercontent.com/TlopChen/git/main/scripts/domain-rules/output/cn-domains.oxi.txt
```

2026-10-01 目录整理前的路径为 `ros/...`，现已迁移。