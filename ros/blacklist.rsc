#blacklist — 17 条, 2026-08-29 04:24:16 由 gen_rules.py 生成
# ROS 拉取: /tool fetch url="http://192.168.40.1:18080/ros/blacklist.rsc" mode=http
#         /import file-name=blacklist.rsc
/ip firewall address-list
remove [find where list="blacklist" && comment="ros-rules-auto"]
remove [find list=ROS_BLACKLIST]
add list=blacklist address=69.195.160.0/19 comment="ros-rules-auto"
add list=blacklist address=91.105.192.0/23 comment="ros-rules-auto"
add list=blacklist address=91.108.4.0/22 comment="ros-rules-auto"
add list=blacklist address=91.108.8.0/21 comment="ros-rules-auto"
add list=blacklist address=91.108.16.0/21 comment="ros-rules-auto"
add list=blacklist address=91.108.56.0/22 comment="ros-rules-auto"
add list=blacklist address=95.161.64.0/20 comment="ros-rules-auto"
add list=blacklist address=149.154.160.0/20 comment="ros-rules-auto"
add list=blacklist address=159.148.147.0/24 comment="ros-rules-auto"
add list=blacklist address=159.148.172.0/24 comment="ros-rules-auto"
add list=blacklist address=185.76.151.0/24 comment="ros-rules-auto"
add list=blacklist address=192.133.76.0/22 comment="ros-rules-auto"
add list=blacklist address=199.59.148.0/22 comment="ros-rules-auto"
add list=blacklist address=199.96.56.0/21 comment="ros-rules-auto"
add list=blacklist address=202.160.128.0/22 comment="ros-rules-auto"
add list=blacklist address=209.237.192.0/19 comment="ros-rules-auto"
add list=blacklist address=2a02:610:7501::/48 comment="ros-rules-auto"
