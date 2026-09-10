#!/bin/bash
# 手工清单「立即生效」：在 GitHub 网页改完 manual-blacklist.txt 后，跑本脚本一次完成
#   拉取仓库 → 重新生成规则 → 提交推送 GitHub → 下发家里 ROS 并 import
# 用法: /usr/local/bin/ros-manual-sync.sh   （日志: /var/log/ros-manual-sync.log）
# 注意: 本脚本随公开仓库留档，故不含任何口令；ROS 口令放 /root/.ros_sync_pass (权限 600)
set -u

PASSFILE=/root/.ros_sync_pass
ROS_HOST=192.168.40.2
ROS_PORT=52222
ROS_USER=Tlop
RULES_URL=http://192.168.40.1:18080/ros/proxy-domain.rsc
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15"

echo "=== $(date '+%F %T') 手工清单同步开始 ==="

cd /root/git || exit 1

# 1) 拉取远端（把网页上的改动拿下来）
if ! git pull --rebase --autostash --quiet; then
    echo "[abort] git pull 失败，请先处理 /root/git 仓库状态再重试"
    exit 1
fi
echo "已拉取远端: $(git log --oneline -1)"
echo "--- 仓库手工清单尾部（确认网页改动已进来） ---"
tail -5 /root/git/ros/generator/manual-blacklist.txt

# 2) 重新生成（gen_rules.py 的 manual/exclude 直接读仓库那份）
if ! /usr/bin/python3 /srv/github-mirror/gen_rules.py; then
    echo "[abort] 生成失败，不提交也不下发"
    exit 1
fi
head -1 /srv/github-mirror/static/ros/proxy-domain.rsc

# 3) 留档提交推送（失败则不下发，避免 GitHub 与 ROS 版本不一致）
cp /srv/github-mirror/static/ros/*.rsc /root/git/ros/
cd /root/git || exit 1
git add -A
if git diff --cached --quiet; then
    echo "产物无变化，跳过提交"
else
    if git commit --quiet -m "手工清单同步 $(date +%F)（proxy-domain 重生成）" && git push origin main; then
        echo "已提交并推送: $(git log --oneline -1)"
    else
        echo "[abort] 提交或推送失败，已跳过 ROS 下发"
        exit 1
    fi
fi

# 4) 下发家里 ROS：fetch + import（ROS 配置即持久，无需 save）
if [ ! -f "$PASSFILE" ]; then
    echo "[abort] 缺少 $PASSFILE（家里 ROS 口令，权限 600），无法下发"
    exit 1
fi
export SSHPASS="$(cat $PASSFILE)"
echo "--- 下发家里 ROS $ROS_HOST ---"
sshpass -e ssh -p $ROS_PORT $SSH_OPTS $ROS_USER@$ROS_HOST     "/tool fetch url=$RULES_URL mode=http; /import file-name=proxy-domain.rsc" 2>&1 | tail -6

# 5) 校验
echo "--- ROS 侧校验 ---"
sshpass -e ssh -p $ROS_PORT $SSH_OPTS $ROS_USER@$ROS_HOST     ':put ("blacklist 总数: " . [:len [/ip dns static find where address-list=blacklist]]); :put ("手工条目: " . [:len [/ip dns static find where comment=ros-rules-manual]]); :put ("上游条目: " . [:len [/ip dns static find where comment=ros-rules-auto]])' 2>&1

echo "=== 完成 ==="
