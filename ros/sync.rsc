# ROS 规则同步脚本（由 VPS gen_rules 管线维护，2026-08-29 版：7 张表）
# 手动更新: /import file-name=sync.rsc
# 自动更新: 调度器 ros-rules-sync 每日 06:30 执行（在 VPS 06:00 重新生成之后）
/tool fetch url="http://192.168.40.1:18080/ros/proxy-domain.rsc" mode=http
/import file-name=proxy-domain.rsc
/tool fetch url="http://192.168.40.1:18080/ros/cn.rsc" mode=http
/import file-name=cn.rsc
/tool fetch url="http://192.168.40.1:18080/ros/cn-telecom.rsc" mode=http
/import file-name=cn-telecom.rsc
/tool fetch url="http://192.168.40.1:18080/ros/cn-mobile.rsc" mode=http
/import file-name=cn-mobile.rsc
/tool fetch url="http://192.168.40.1:18080/ros/cn-unicom.rsc" mode=http
/import file-name=cn-unicom.rsc
/tool fetch url="http://192.168.40.1:18080/ros/cn-cernet.rsc" mode=http
/import file-name=cn-cernet.rsc
/tool fetch url="http://192.168.40.1:18080/ros/blacklist.rsc" mode=http
/import file-name=blacklist.rsc
:log info "ROS rules synced from VPS mirror"
