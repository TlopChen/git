#!/bin/bash
# 手工清单变更监视（每分钟一次；无变化时静默退出，不写日志）
#
# 覆盖两种改动来源：
#   ① 远端：GitHub 网页改的 —— git fetch 后比较 HEAD..origin/main 里被监视文件是否变化
#   ② 本地：服务器上直接改的 —— 比较被监视文件的 sha256 与「上次成功处理后的基线」
# 命中才调用 manual-refresh（自带 /tmp/ros-rules.lock、发布、提交推送）。
#
# 用法: manual-watch.sh [--dry-run]
set -u
REPO=/root/git
R="$REPO/scripts"
STATE=/var/lib/manual-watch/state
LOG=/var/log/manual-watch.log
COOLDOWN=600          # 同一模式失败后，多少秒内不重试（避免每分钟刷日志）

RULES_FILES=( "$R/domain-rules/input/manual/manual-blacklist.txt"
              "$R/domain-rules/input/manual/exclude-blacklist.txt"
              "$R/domain-rules/input/manual/manual-cn-domains.txt" )
DI_FILES=( "$R/direct-ip/include-ipv4.txt"
           "$R/direct-ip/exclude-ipv4.txt"
           "$R/direct-ip/direct-domains.json" )

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
INIT=0
[ "${1:-}" = "--init" ] && INIT=1

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*" >>"$LOG"; }
hash_set() { sha256sum "$@" 2>/dev/null | sha256sum | cut -c1-32; }
state_get() { sed -n "s/^$1 //p" "$STATE" 2>/dev/null | head -1; }
state_put() {
    local k="$1" v="${2:-}" t
    t=$(mktemp)
    grep -v "^$k " "$STATE" >"$t" 2>/dev/null || true
    [ -n "$v" ] && echo "$k $v" >>"$t"
    mv "$t" "$STATE"
}
age_of() { local ts; ts=$(state_get "$1"); if [ -n "$ts" ]; then echo $(( $(date +%s) - ts )); else echo 999999; fi; }
log_throttled() { local k="$1"; shift; [ "$(age_of "log-$k")" -ge "$COOLDOWN" ] && { log "$*"; state_put "log-$k" "$(date +%s)"; }; }

mkdir -p "$(dirname "$STATE")"
touch "$STATE" "$LOG"
cd "$REPO" || exit 1

cd "$REPO" || exit 1

if [ "$INIT" = 1 ]; then
    state_put rules "$(hash_set "${RULES_FILES[@]}")"
    state_put direct-ip "$(hash_set "${DI_FILES[@]}")"
    echo "已写入基线 $STATE:"; cat "$STATE"
    exit 0
fi

modes=""

# ---------- ① 远端变化（短暂持主锁，避免与日更/direct-ip 的 pull 抢）----------
exec 9>/tmp/ros-rules.lock
if flock -n -w 5 9; then
    if GIT_TERMINAL_PROMPT=0 timeout 45 git fetch -q origin main 2>>"$LOG"; then
        behind=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
        if [ "${behind:-0}" -gt 0 ]; then
            up=$(git diff --name-only HEAD origin/main -- "${RULES_FILES[@]}" "${DI_FILES[@]}" 2>/dev/null || true)
            grep -q 'domain-rules/input/manual/' <<<"$up" && modes="$modes rules"
            grep -q '^scripts/direct-ip/'        <<<"$up" && modes="$modes direct-ip"
        fi
    else
        log_throttled fetch "[warn] git fetch 失败，本轮只做本地检测"
    fi
    flock -u 9
else
    [ "$DRY" = 1 ] && echo "主锁被占（日更/direct-ip 正在跑），本轮跳过"
    exit 0
fi
exec 9>&-

# ---------- ② 本地变化 ----------
[ "$(hash_set "${RULES_FILES[@]}")" != "$(state_get rules)" ]     && modes="$modes rules"
[ "$(hash_set "${DI_FILES[@]}")"    != "$(state_get direct-ip)" ] && modes="$modes direct-ip"

modes=$(printf '%s\n' $modes | awk '!x[$0]++' | tr '\n' ' ')
modes=${modes% }

if [ -z "$modes" ]; then
    [ "$DRY" = 1 ] && echo "无变化"
    exit 0
fi
if [ "$DRY" = 1 ]; then
    echo "将触发:$modes"
    exit 0
fi

log "检测到手工清单变化 →$modes"
for m in $modes; do
    if [ "$(age_of "fail-$m")" -lt "$COOLDOWN" ]; then
        log_throttled "skip-$m" "[warn] $m 上次失败，冷却中，暂不重试"
        continue
    fi
    if "$R/_infra/manual-refresh.sh" "$m" >>"$LOG" 2>&1; then
        log "manual-refresh $m 完成"
        if [ "$m" = rules ]; then
            state_put rules "$(hash_set "${RULES_FILES[@]}")"
        else
            state_put direct-ip "$(hash_set "${DI_FILES[@]}")"
        fi
        state_put "fail-$m" ""
    else
        log "[error] manual-refresh $m 失败（${COOLDOWN}s 内不重试）"
        state_put "fail-$m" "$(date +%s)"
    fi
done
exit 0