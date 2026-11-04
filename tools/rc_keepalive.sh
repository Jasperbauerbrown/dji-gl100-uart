#!/bin/sh
# rc_keepalive.sh - keep the GL100 (Spark RC) from auto-powering-off.
# Runs ON the RC (RAM only; gone after reboot). Start with:  sh /tmp/rc_keepalive.sh &
#
# The MCU's idle timer is fed by stick data that apsrv forwards over ttyATH0. Sticks are
# MLX90393 sensors -> /dev/input/event0/1, which accept write() (evdev injection). Every 30 s
# we inject a ~2.6 deg (~10%) X blip on event0. A real sample overwrites it within ~30 ms.
#
# WARNING: this is REAL stick input. Do not run with an aircraft linked/armed.
EV=/dev/input/event0
Z='\000\000\000\000\000\000\000\000'
# struct input_event (MIPS32 BE): timeval(8) type(2) code(2) value(4); EV_ABS/ABS_X=246 then EV_SYN
printf "$Z\000\003\000\000\000\000\000\366$Z\000\000\000\000\000\000\000\000" > /tmp/ka_inj.bin
while true; do
    i=0; while [ $i -lt 10 ]; do cat /tmp/ka_inj.bin > $EV; i=$((i+1)); done
    sleep 30
done
