#!/bin/bash
# ROS 规则日更：拉仓库(含 GitHub 网页改的手工清单) → 生成 → 留档 → 提交推送（有变化才提交）
# 数据文件 manual-blacklist.txt / exclude-blacklist.txt 以 GitHub 仓库为准（网页可直接改）；
# 脚本与配置 gen_rules.py/sources.json/repos.json/mirror.py/本脚本 以 /srv/github-mirror 为准。
set -u
echo "=== $(date '+%F %T') 开始 ==="

# 1) 先拉远端：网页改完 manual-blacklist.txt，跑一次日更或 ros-manual-sync.sh 即生效
cd /root/git || exit 1
if git pull --rebase --autostash --quiet; then
    echo "已拉取远端: $(git log --oneline -1)"
else
    echo "[warn] git pull 失败，本次用本地版本；此时 push 会因远端领先而失败，不会盖掉网页改动"
fi

# 2) /srv 是脚本与配置的权威，回灌到 Git 仓库留档（数据文件不在此列）
for f in gen_rules.py sources.json repos.json mirror.py ros-rules-daily.sh ros-manual-sync.sh; do
    if [ -f "/srv/github-mirror/$f" ]; then
        cp "/srv/github-mirror/$f" "/root/git/ros/generator/$f"
    fi
done

# 3) 生成（gen_rules.py 的 manual/exclude 直接读 /root/git/ros/generator/ 下的仓库文件）
if ! /usr/bin/python3 /srv/github-mirror/gen_rules.py; then
    echo "生成失败，本次跳过提交（保留旧文件）"
    exit 1
fi

# 4) 同步生成结果到 Git 仓库（否则 git add -A 看不到 static 下的变化）
cp /srv/github-mirror/static/ros/*.rsc /root/git/ros/

cd /root/git || exit 1
git add -A
if git diff --cached --quiet; then
    echo "上游无变化，不提交"
else
    if git commit -m "规则日更 $(date +%F)" --quiet && git push origin main; then
        echo "已提交并推送: $(git log --oneline -1)"
    else
        echo "推送失败（可能网络抖动），下次运行会重试提交"
    fi
fi
echo "=== 完成 ==="
