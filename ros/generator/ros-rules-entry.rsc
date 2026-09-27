{
 :if ([:len [/system script job find where script="ros-rules-sync"]] > 1) do={ :error "ros-rules-sync already running"; };
 :onerror err in={
  /tool fetch url="http://192.168.40.1:18080/ros/sync.rsc" dst-path="sync.rsc" output=file idle-timeout=30s;
  /import file-name=sync.rsc;
 } do={
  :log error ("ros-rules-sync entry FAILED: " . $err);
  :error $err;
 };
}