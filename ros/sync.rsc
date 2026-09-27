# Four address lists only: CT, CM, blacklist, DIRECT_IP.
# Canonical entry: /system script run ros-rules-sync
# Daily scheduler: 06:30 Asia/Shanghai, after Guangzhou 06:00/06:15 generation.
{
    :if ([:len [/system script job find where script="ros-rules-sync"]] > 1) do={
        :error "ros-rules-sync already running";
    };
    :local base "http://192.168.40.1:18080/ros/";
    :local files {"cn-telecom.rsc";"cn-mobile.rsc";"blacklist.rsc";"direct-ipv4.rsc"};
    :local stage "sync-stage-";
    :local step "download";
    :onerror err in={
        # No imports until all four fetches complete successfully.
        :foreach name in=$files do={
            :set step ("fetch " . $name);
            /tool fetch url=($base . $name) dst-path=($stage . $name) output=file idle-timeout=30s;
            :local target ($stage . $name);
            :local size [/file get $target size];
            :local minimum 500;
            :if ($name="cn-telecom.rsc" || $name="cn-mobile.rsc" || $name="direct-ipv4.rsc") do={ :set minimum 10000; };
            :if ($size < $minimum) do={ :error ("download too small: " . $name); };
        };
        :foreach name in=$files do={
            :set step ("import " . $name);
            /import file-name=($stage . $name);
        };
        :local ct [:len [/ip firewall address-list find where list="CT" and dynamic=no]];
        :local cm [:len [/ip firewall address-list find where list="CM" and dynamic=no]];
        :local bl [:len [/ip firewall address-list find where list="blacklist" and dynamic=no]];
        :local direct [:len [/ip firewall address-list find where list="DIRECT_IP" and dynamic=no]];
        :set step "validate list counts";
        :if ($ct < 1000 || $cm < 500 || $bl < 10 || $direct < 1000) do={ :error "unexpectedly short address list"; };
        :log info ("ros-rules-sync OK CT=" . $ct . " CM=" . $cm . " blacklist-static=" . $bl . " DIRECT_IP=" . $direct);
    } do={
        :log error ("ros-rules-sync FAILED at " . $step . ": " . $err);
        :error ("ros-rules-sync failed at " . $step . ": " . $err);
    };
}
