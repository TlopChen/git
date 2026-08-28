#telegram — 8 条, 2026-08-29 02:10:50 由 gen_rules.py 生成
# ROS 拉取: /tool fetch url="http://192.168.40.1:18080/ros/telegram.rsc" mode=http
#         /import file-name=telegram.rsc
/ip firewall address-list
remove [find list=ROS_TELEGRAM]
add list=ROS_TELEGRAM address=91.105.192.0/23
add list=ROS_TELEGRAM address=91.108.4.0/22
add list=ROS_TELEGRAM address=91.108.8.0/21
add list=ROS_TELEGRAM address=91.108.16.0/21
add list=ROS_TELEGRAM address=91.108.56.0/22
add list=ROS_TELEGRAM address=95.161.64.0/20
add list=ROS_TELEGRAM address=149.154.160.0/20
add list=ROS_TELEGRAM address=185.76.151.0/24
