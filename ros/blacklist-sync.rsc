# 表同步（blacklist 明确被墙 IP 段 + 当前接入运营商 CT/CM）
# 手动执行: /import file-name=blacklist-sync.rsc
# 自动执行: 调度器 blacklist-sync 每日 06:30（VPS 06:00 生成之后）
# 2026-09-23: 加入 CT/CM；proxy-domain 随 ROS DNS 停用而退出，CN/CU/CC 无消费者不再同步
# 本文件以 VPS /srv/github-mirror/static/ros/ 为准（镜像分发），勿在 ROS 本地手改
/tool fetch url="http://192.168.40.1:18080/ros/blacklist.rsc" mode=http
/import file-name=blacklist.rsc
/tool fetch url="http://192.168.40.1:18080/ros/cn-telecom.rsc" mode=http
/import file-name=cn-telecom.rsc
/tool fetch url="http://192.168.40.1:18080/ros/cn-mobile.rsc" mode=http
/import file-name=cn-mobile.rsc
:log info "rules synced from VPS mirror: blacklist + ct + cm"
