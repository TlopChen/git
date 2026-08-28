#blacklist — 17 条, 2026-08-29 02:20:27 由 gen_rules.py 生成
# ROS 拉取: /tool fetch url="http://192.168.40.1:18080/ros/blacklist.rsc" mode=http
#         /import file-name=blacklist.rsc
/ip firewall address-list
remove [find list=ROS_BLACKLIST]
add list=ROS_BLACKLIST address=69.195.160.0/19
add list=ROS_BLACKLIST address=91.105.192.0/23
add list=ROS_BLACKLIST address=91.108.4.0/22
add list=ROS_BLACKLIST address=91.108.8.0/21
add list=ROS_BLACKLIST address=91.108.16.0/21
add list=ROS_BLACKLIST address=91.108.56.0/22
add list=ROS_BLACKLIST address=95.161.64.0/20
add list=ROS_BLACKLIST address=149.154.160.0/20
add list=ROS_BLACKLIST address=159.148.147.0/24
add list=ROS_BLACKLIST address=159.148.172.0/24
add list=ROS_BLACKLIST address=185.76.151.0/24
add list=ROS_BLACKLIST address=192.133.76.0/22
add list=ROS_BLACKLIST address=199.59.148.0/22
add list=ROS_BLACKLIST address=199.96.56.0/21
add list=ROS_BLACKLIST address=202.160.128.0/22
add list=ROS_BLACKLIST address=209.237.192.0/19
add list=ROS_BLACKLIST address=2a02:610:7501::/48
