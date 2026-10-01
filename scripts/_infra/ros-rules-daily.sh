#!/bin/bash
# ROS 规则日更：拉仓库 → 用仓库里的脚本生成 → 发布到内网 mirror → 留档并推送。
# 代码权威 = 本仓库 /root/git；手工数据权威 = scripts/domain-rules/input/manual/。
set -u
REPO=/root/git
R="$REPO/scripts/domain-rules"
echo "=== $(date '+%F %T') 开始 ==="

cd "$REPO" || exit 1
if git pull --rebase --autostash --quiet; then
    echo "已拉取远端: $(git log --oneline -1)"
else
    echo "[warn] git pull 失败，本次用本地版本；此时 push 会因远端领先而失败，不会盖掉网页改动"
fi

# 生成：脚本在仓库里，上游快照写 input/upstream，产物写 output/
if ! /usr/bin/python3 "$R/gen_rules.py"; then
    echo "生成失败，本次跳过提交（保留旧产物）"
    exit 1
fi
/usr/bin/python3 "$R/gen_oxi.py"   || echo "[warn] gen_oxi failed"
/usr/bin/python3 "$R/gen_cn.py"    || echo "[warn] gen_cn failed"
/usr/bin/python3 "$R/fetch_bin.py" || echo "[warn] fetch_bin failed"

# 发布到内网 HTTP 目录（ROS 从这里按 /ros/<文件> 取用）
"$REPO/scripts/_infra/publish.sh"

cd "$REPO" || exit 1
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