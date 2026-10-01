# ROS 侧唯一拉取入口：一次拉齐「ROS 要的六张地址表」+「OxiDNS 要的三份规则」。
# Canonical entry: /system script run ros-rules-sync（06:30 由 scheduler 触发）
# 手工立即生效: /system script run manual-refresh（本脚本 + 重启 oxidns 容器）
#
# 顺序：全部下载并校验 → 导入地址表并校验条数 → 三份 OxiDNS 规则改名替换。
# OxiDNS 自身不再联网：config.yaml 的 rules_download 已从任务链摘除，
# 每天 07:00 只做 reload_provider，因此断网也能重载本地规则。
{
    :if ([:len [/system script job find where script="ros-rules-sync"]] > 1) do={
        :error "ros-rules-sync already running";
    };
    :local base "http://192.168.40.1:18080/ros/";
    :local files {"cn-telecom.rsc";"cn-mobile.rsc";"blacklist.rsc";"direct-ipv4.rsc";"direct-ipv4-nocm.rsc";"direct-ipv4-noct.rsc"};
    :local stage "sync-stage-";
    :local rdir "oxidns-conf/rules/";
    :local step "download";
    :onerror err in={
        # ① 六张地址表：全部下载成功才继续
        :foreach name in=$files do={
            :set step ("fetch " . $name);
            /tool fetch url=($base . $name) dst-path=($stage . $name) output=file idle-timeout=30s;
            :local target ($stage . $name);
            :local size [/file get $target size];
            :local minimum 500;
            :if ($name="cn-telecom.rsc" || $name="cn-mobile.rsc" || $name="direct-ipv4.rsc" || $name="direct-ipv4-nocm.rsc" || $name="direct-ipv4-noct.rsc") do={ :set minimum 10000; };
            :if ($size < $minimum) do={ :error ("download too small: " . $name); };
        };

        # ② OxiDNS 三份规则：先落临时文件并校验字节数，任何一份不合格就整体中止
        :set step "fetch oxidns rules";
        /tool fetch url=($base . "proxy-domain.oxi.txt") dst-path="mr-proxy.tmp" output=file idle-timeout=30s;
        /tool fetch url=($base . "cn-domains.oxi.txt") dst-path="mr-cn.tmp" output=file idle-timeout=60s;
        /tool fetch url=($base . "geosite.dat") dst-path="mr-geo.tmp" output=file idle-timeout=120s;
        :local sp [/file get "mr-proxy.tmp" size];
        :local sc [/file get "mr-cn.tmp" size];
        :local sg [/file get "mr-geo.tmp" size];
        :if ($sp < 100000 || $sc < 500000 || $sg < 1000000) do={
            :error ("oxidns rules too small: " . $sp . "/" . $sc . "/" . $sg);
        };

        # ③ 导入地址表并校验条数
        :foreach name in=$files do={
            :set step ("import " . $name);
            /import file-name=($stage . $name);
        };
        :local ct [:len [/ip firewall address-list find where list="CT" and dynamic=no]];
        :local cm [:len [/ip firewall address-list find where list="CM" and dynamic=no]];
        :local bl [:len [/ip firewall address-list find where list="blacklist" and dynamic=no]];
        :local direct [:len [/ip firewall address-list find where list="DIRECT_IP" and dynamic=no]];
        :local nocm [:len [/ip firewall address-list find where list="DIRECT_IP_NOCM" and dynamic=no]];
        :local noct [:len [/ip firewall address-list find where list="DIRECT_IP_NOCT" and dynamic=no]];
        :set step "validate list counts";
        :if ($ct < 1000 || $cm < 500 || $bl < 10 || $direct < 1000 || $nocm < 1000 || $noct < 1000) do={ :error "unexpectedly short address list"; };

        # ④ 替换 OxiDNS 规则（挂载点 oxidns-conf/rules = 容器内 /etc/oxidns/rules）
        :set step "replace oxidns rules";
        :if ([:len [/file find where name=($rdir . "proxy-domain.txt")]] > 0) do={ /file remove ($rdir . "proxy-domain.txt"); };
        /file set "mr-proxy.tmp" name=($rdir . "proxy-domain.txt");
        :if ([:len [/file find where name=($rdir . "cn-extra.txt")]] > 0) do={ /file remove ($rdir . "cn-extra.txt"); };
        /file set "mr-cn.tmp" name=($rdir . "cn-extra.txt");
        :if ([:len [/file find where name=($rdir . "geosite.dat")]] > 0) do={ /file remove ($rdir . "geosite.dat"); };
        /file set "mr-geo.tmp" name=($rdir . "geosite.dat");

        :log info ("ros-rules-sync OK CT=" . $ct . " CM=" . $cm . " blacklist-static=" . $bl . " DIRECT_IP=" . $direct . " NOCM=" . $nocm . " NOCT=" . $noct . " oxidns=" . $sp . "/" . $sc . "/" . $sg);
    } do={
        :log error ("ros-rules-sync FAILED at " . $step . ": " . $err);
        :error ("ros-rules-sync failed at " . $step . ": " . $err);
    };
}