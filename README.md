# TlopChen/git

个人网络的规则生成仓库。**主体是脚本**：上游源输入 → 脚本处理 → 输出产物。
ROS / AR / OxiDNS 只是产物的消费端，不在这里定义。

```text
/root/git
├── README.md
├── .github/workflows/    oxidns-image：GitHub Actions 打包 OxiDNS 镜像
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
| oxidns-image | 上游 `svenshi/oxidns` 镜像 | `.github/workflows/oxidns-image.yml` + `scripts/_infra/oxidns-image-sync.sh` | `/ros/oxidns-image.json` + `/ros/oxidns-v*.tar` | RouterOS（`/system script run oxidns-upgrade`） |

每个模块的详细契约见各自目录下的 `README.md`。

## 日常运行

| 时间（北京时间） | 入口 | 动作 |
|---|---|---|
| 06:00 | `scripts/_infra/ros-rules-daily.sh` | 拉仓库 → 生成 → 发布到内网 HTTP → 提交推送 |
| 06:15 | `scripts/direct-ip/update.sh full` | 刷新直连表并原子发布 |
| 06:20 | `scripts/_infra/oxidns-image-sync.sh` | 把 `oxidns-images` 分支里的 OxiDNS 镜像 tar 发布到内网 HTTP |
| 06:30 | ROS `/system script run ros-rules-sync` | ROS 自己拉六表并导入（不在这里） |
| 手动 | `manual-refresh rules` / `direct-ip` | 只重生成手工部分，不拉上游 |

手工改动生效路径：广州 `manual-refresh` 重生成产物 → ROS 上按需跑一次 `ros-rules-sync`。
ROS 侧不定时轮询、不做哈希校验。

## OxiDNS 镜像管线（oxidns-image）

- **打包放 GitHub Actions，广州只做分发**：广州对 Docker Hub 的解析被投毒/被墙（`auth.docker.io` 超时、`registry-1.docker.io` 解析到 Facebook IPv6 段），拉不动镜像；Actions runner 自带 docker + 干净外网。
- **触发**：① Actions 页面 Run workflow（填 OxiDNS tag）；② 本地 `git push` 一个形如 `oxidns-image-v1.6.1` 的 tag（无需任何令牌，tag 名即版本号）。
- **产物**：workflow 用 `docker save` 生成 docker-archive tar + sha256，推到 `oxidns-images` 分支（`oxidns/manifest.json` + 最近 3 个版本）。
- **分发**：广州 06:20 的 `scripts/_infra/oxidns-image-sync.sh` 用专用浅克隆 `/srv/oxidns-images` 拉该分支 → 校验 sha256/size → 原子发布到 HTTP 根（`oxidns-image.json` + tar）；不碰 `/root/git`，避免和日更管线抢 .git 锁。
- **消费**：ROS 上按需 `/system script run oxidns-upgrade`（幂等：manifest 的 file 与当前容器的 `file=` 相同则什么都不做）；有新版才下载 tar → `set file=` → `repull` → 重启 → 验证解析。容器运行配置常驻挂载目录（`cmd` 指向 `/etc/oxidns/rules/config.yaml`），所以 `repull` 不会覆盖配置。
- **回滚**：`/container set oxidns file=oxidns-v<旧版本>-linux-amd64.tar` + `/container/repull oxidns` + `/container start oxidns`（旧 tar 仍在内网 HTTP 上）。

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