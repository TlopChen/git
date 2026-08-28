#lan — 14 条, 2026-08-29 02:10:50 由 gen_rules.py 生成
# ROS 拉取: /tool fetch url="http://192.168.40.1:18080/ros/lan.rsc" mode=http
#         /import file-name=lan.rsc
/ip firewall address-list
remove [find list=ROS_LAN_LOCAL]
add list=ROS_LAN_LOCAL address=0.0.0.0/8
add list=ROS_LAN_LOCAL address=10.0.0.0/8
add list=ROS_LAN_LOCAL address=100.64.0.0/10
add list=ROS_LAN_LOCAL address=127.0.0.0/8
add list=ROS_LAN_LOCAL address=169.254.0.0/16
add list=ROS_LAN_LOCAL address=172.16.0.0/12
add list=ROS_LAN_LOCAL address=192.0.0.0/24
add list=ROS_LAN_LOCAL address=192.0.2.0/24
add list=ROS_LAN_LOCAL address=192.88.99.0/24
add list=ROS_LAN_LOCAL address=192.168.0.0/16
add list=ROS_LAN_LOCAL address=198.18.0.0/15
add list=ROS_LAN_LOCAL address=198.51.100.0/24
add list=ROS_LAN_LOCAL address=203.0.113.0/24
add list=ROS_LAN_LOCAL address=224.0.0.0/3
