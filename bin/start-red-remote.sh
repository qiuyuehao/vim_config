#!/bin/sh
echo "adb support ip"
echo $#
if [ $# -eq 1 ];then
    adb connect $1
    if [ $? -eq 0 ];then
        echo "wifi connect success"
    else
        echo "wifi connect fail"
        exit
    fi
fi
adb shell chmod 777 /dev/tcm0

adb shell setenforce 0
adb shell setprop service.adb.tcp.port 5555
adb forward tcp:10001 tcp:10001

adb shell am force-stop com.synaptics.redremote

adb shell am start -a android.intent.action.MAIN -n com.synaptics.redremote/.SettingsActivity --activity-clear-task \
        -e "Use Sysfs" "false" \
        -e "Device Node" "/dev/tcm0" \
        -e "Attention Node" "/sys/bus/platform/devices/synaptics_tcm.0/attn"

adb shell am start -a android.intent.action.MAIN -n com.synaptics.redremote/.ActivityCDCIServer --activity-clear-task -e "StartServer" "true"
