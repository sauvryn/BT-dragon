#!/system/bin/sh
# Runs ON the Echo Dot (dot-wifi.bat / dot-wifi.command copy it there). Adds one Wi-Fi network from /data/local/tmp/wifi.txt
# (line 1 = network name, line 2 = password), then reports what happened.
F=/data/local/tmp/wifi.txt
SSID=$(sed -n 1p $F | tr -d '\r')
PASS=$(sed -n 2p $F | tr -d '\r')
rm -f $F
[ -n "$SSID" ] || { echo "ERROR: no network name in wifi.txt"; exit 1; }

# find the way to talk to the running wpa_supplicant
W="wpa_cli -i wlan0"
$W ping 2>/dev/null | grep -q PONG || W="wpa_cli -i wlan0 -p /data/misc/wifi/sockets"
$W ping 2>/dev/null | grep -q PONG || W="wpa_cli -p /data/misc/wifi/sockets"
echo "control: $W"
$W ping 2>&1

echo "===== existing networks"
$W list_networks 2>&1
echo "===== adding"
N=$($W add_network 2>&1 | tail -n 1)
echo "network id: $N"
$W set_network $N ssid "\"$SSID\"" 2>&1
$W set_network $N psk "\"$PASS\"" 2>&1
$W set_network $N key_mgmt WPA-PSK 2>&1
$W enable_network $N 2>&1
$W select_network $N 2>&1
$W save_config 2>&1
echo "===== waiting 25 seconds to connect"
sleep 25
$W status 2>&1 | grep -v -i "psk\|passphrase"
echo "===== address"
ip addr show wlan0 2>&1 | grep -E "inet |state"
echo "===== adb over wifi"
getprop service.adb.tcp.port
(netstat -ltn 2>/dev/null || netstat -l 2>/dev/null) | grep -E ":5555" || echo "nothing listening on 5555 yet"
echo "===== saved config (password hidden)"
sed 's/psk=.*/psk=HIDDEN/' /data/misc/wifi/wpa_supplicant.conf
