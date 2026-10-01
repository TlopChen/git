# manual-refresh —— 手工改动的按需联动（ROS 侧；不定时、不做哈希校验）
# 前置：广州执行 /usr/local/bin/manual-refresh rules|direct-ip 重生成并发布产物
# 用法：/system script run manual-refresh
# 行为：① 地址表复用六表同步；② OxiDNS 三份规则写入挂载目录后重启容器重载。
{
    :if ([:len [/system script job find where script="manual-refresh"]] > 1) do={
        :error "manual-refresh already running";
    };
    :local base "http://192.168.40.1:18080/ros/";
    :local step "address-lists";
    :onerror err in={
        # ① 地址表：复用既有六表同步（幂等；覆盖 DIRECT_IP 手工段与 NOCM/NOCT 派生表）
        /system script run ros-rules-sync;

        # ② OxiDNS 规则：先拉到文件根并校验大小，三份都齐了再替换，避免半截文件上线
        :set step "oxidns-fetch";
        /tool fetch url=($base . "proxy-domain.oxi.txt") dst-path="mr-proxy.tmp" output=file idle-timeout=30s;
        /tool fetch url=($base . "cn-domains.oxi.txt") dst-path="mr-cn.tmp" output=file idle-timeout=60s;
        /tool fetch url=($base . "geosite.dat") dst-path="mr-geo.tmp" output=file idle-timeout=120s;
        :local sp [/file get "mr-proxy.tmp" size];
        :local sc [/file get "mr-cn.tmp" size];
        :local sg [/file get "mr-geo.tmp" size];
        :if ($sp < 100000 || $sc < 500000 || $sg < 1000000) do={
            :error ("download too small: " . $sp . "/" . $sc . "/" . $sg);
        };

        # ③ 替换容器规则（挂载点 oxidns-conf/rules = 容器内 /etc/oxidns/rules）
        :set step "oxidns-replace";
        :if ([:len [/file find where name="oxidns-conf/rules/proxy-domain.txt"]] > 0) do={ /file remove "oxidns-conf/rules/proxy-domain.txt"; };
        /file set "mr-proxy.tmp" name="oxidns-conf/rules/proxy-domain.txt";
        :if ([:len [/file find where name="oxidns-conf/rules/cn-extra.txt"]] > 0) do={ /file remove "oxidns-conf/rules/cn-extra.txt"; };
        /file set "mr-cn.tmp" name="oxidns-conf/rules/cn-extra.txt";
        :if ([:len [/file find where name="oxidns-conf/rules/geosite.dat"]] > 0) do={ /file remove "oxidns-conf/rules/geosite.dat"; };
        /file set "mr-geo.tmp" name="oxidns-conf/rules/geosite.dat";

        # ④ 重载：OxiDNS 的 reload 只能由其内部任务链触发，这里整体重启容器
        :set step "oxidns-reload";
        /container stop oxidns;
        :delay 1s;
        /container start oxidns;

        # ⑤ 校验：容器在跑 + DNS 真能解析
        :set step "verify";
        :delay 8s;
        :local ip [:resolve "www.baidu.com"];
        :log info ("manual-refresh OK proxy=" . $sp . " cn=" . $sc . " geo=" . $sg . " dns=" . $ip);
    } do={
        :log error ("manual-refresh FAILED at " . $step . ": " . $err);
        :error ("manual-refresh failed at " . $step . ": " . $err);
    };
}