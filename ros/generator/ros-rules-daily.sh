#!/bin/bash
# ROS 规则日更：生成 → 同步到 Git 仓库 → 归档推送（有变化才提交）
set -u
echo "=== $(date '+%F %T') 开始 ==="

if ! /usr/bin/python3 /srv/github-mirror/gen_rules.py; then
    echo "生成失败，本次跳过提交（保留旧文件）"
    exit 1
fi

# 同步生成结果到 Git 仓库（否则 git add -A 看不到 static 下的变化）
cp /srv/github-mirror/static/ros/*.rsc /root/git/ros/
cp /srv/github-mirror/manual-blacklist.txt /root/git/ros/generator/manual-blacklist.txt

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
