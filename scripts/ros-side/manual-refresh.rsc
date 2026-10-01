# manual-refresh —— 手工改动的按需联动（ROS 侧；不定时、不做哈希校验）
# 前置：广州执行 /usr/local/bin/manual-refresh rules|direct-ip 重生成并发布产物
# 用法：/system script run manual-refresh
# 行为：跑一次 ros-rules-sync（拉齐六张地址表 + OxiDNS 三份规则），
#       再重启 oxidns 容器让规则立即生效（不等 07:00 的 reload）。
{
    :if ([:len [/system script job find where script="manual-refresh"]] > 1) do={
        :error "manual-refresh already running";
    };
    :local step "sync";
    :onerror err in={
        /system script run ros-rules-sync;
        :set step "oxidns-reload";
        /container stop oxidns;
        :delay 1s;
        /container start oxidns;
        :set step "verify";
        :delay 8s;
        :local ip [:resolve "www.baidu.com"];
        :log info ("manual-refresh OK dns=" . $ip);
    } do={
        :log error ("manual-refresh FAILED at " . $step . ": " . $err);
        :error ("manual-refresh failed at " . $step . ": " . $err);
    };
}