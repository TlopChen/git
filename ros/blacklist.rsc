#blacklist — 23 条, 2026-09-12 06:00:43 由 gen_rules.py 生成
# ROS 拉取: /tool fetch url="http://192.168.40.1:18080/ros/blacklist.rsc" mode=http
#         /import file-name=blacklist.rsc
/ip firewall address-list
remove [find where list="blacklist" && dynamic=no]
remove [find list=ROS_BLACKLIST]
remove [find where list="blacklist" and address="1.0.0.1"]
add list=blacklist address=1.0.0.1/32 comment="ros-rules-auto"
remove [find where list="blacklist" and address="1.1.1.1"]
add list=blacklist address=1.1.1.1/32 comment="ros-rules-auto"
remove [find where list="blacklist" and address="5.28.192.0/18"]
add list=blacklist address=5.28.192.0/18 comment="ros-rules-auto"
remove [find where list="blacklist" and address="8.8.4.4"]
add list=blacklist address=8.8.4.4/32 comment="ros-rules-auto"
remove [find where list="blacklist" and address="8.8.8.8"]
add list=blacklist address=8.8.8.8/32 comment="ros-rules-auto"
remove [find where list="blacklist" and address="69.195.160.0/19"]
add list=blacklist address=69.195.160.0/19 comment="ros-rules-auto"
remove [find where list="blacklist" and address="91.105.192.0/23"]
add list=blacklist address=91.105.192.0/23 comment="ros-rules-auto"
remove [find where list="blacklist" and address="91.108.4.0/22"]
add list=blacklist address=91.108.4.0/22 comment="ros-rules-auto"
remove [find where list="blacklist" and address="91.108.8.0/21"]
add list=blacklist address=91.108.8.0/21 comment="ros-rules-auto"
remove [find where list="blacklist" and address="91.108.16.0/21"]
add list=blacklist address=91.108.16.0/21 comment="ros-rules-auto"
remove [find where list="blacklist" and address="91.108.56.0/22"]
add list=blacklist address=91.108.56.0/22 comment="ros-rules-auto"
remove [find where list="blacklist" and address="95.161.64.0/20"]
add list=blacklist address=95.161.64.0/20 comment="ros-rules-auto"
remove [find where list="blacklist" and address="109.239.140.0/24"]
add list=blacklist address=109.239.140.0/24 comment="ros-rules-auto"
remove [find where list="blacklist" and address="149.154.160.0/20"]
add list=blacklist address=149.154.160.0/20 comment="ros-rules-auto"
remove [find where list="blacklist" and address="159.148.147.0/24"]
add list=blacklist address=159.148.147.0/24 comment="ros-rules-auto"
remove [find where list="blacklist" and address="159.148.172.0/24"]
add list=blacklist address=159.148.172.0/24 comment="ros-rules-auto"
remove [find where list="blacklist" and address="185.76.151.0/24"]
add list=blacklist address=185.76.151.0/24 comment="ros-rules-auto"
remove [find where list="blacklist" and address="192.133.76.0/22"]
add list=blacklist address=192.133.76.0/22 comment="ros-rules-auto"
remove [find where list="blacklist" and address="199.59.148.0/22"]
add list=blacklist address=199.59.148.0/22 comment="ros-rules-auto"
remove [find where list="blacklist" and address="199.96.56.0/21"]
add list=blacklist address=199.96.56.0/21 comment="ros-rules-auto"
remove [find where list="blacklist" and address="202.160.128.0/22"]
add list=blacklist address=202.160.128.0/22 comment="ros-rules-auto"
remove [find where list="blacklist" and address="209.237.192.0/19"]
add list=blacklist address=209.237.192.0/19 comment="ros-rules-auto"
# （1 条 IPv6 网段未导入：内网未启用 IPv6，ipv6=true 可开启）
