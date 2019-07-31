#!/usr/bin/env python3
# coding: utf-8
# Author: VICKEY KUMAR
import asyncio,os
import math
import RPi.GPIO as GPIO
#import raspi_stub as GPIO 
GPIO.setmode (GPIO.BOARD)

FAN_PIN = 7
THRESHOLD_TEMP = 55
FAN_ON = False
ON = True
OFF = False


def getCPUtemp():
        temp = float(0)
        try:
                out = os.popen('/opt/vc/bin/vcgencmd measure_temp').readline()
                temp = float(out.replace("temp=","").replace("'C\n",""))
        except Exception as e:
                print("Exception while getting cpu temperature: ",str(e))
                pass
        return temp

def fan(mode=True):
        global FAN_PIN, FAN_ON
        GPIO.output(FAN_PIN, mode)
        FAN_ON = mode
        return()

def config():
        global FAN_PIN
        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)
        GPIO.setup(FAN_PIN,GPIO.OUT)
        fan(OFF)    #resetting fan

def fanManager(loop):
        global FAN_ON
        loop_interval = 60      #poll evry 60 sec for temperature
        cpuTemp = getCPUtemp()
        if cpuTemp>THRESHOLD_TEMP :
                if not FAN_ON: fan(ON)
                '''wait 60 sec for ev 5'C raise in temp for next polling'''
                loop_interval = 4*loop_interval*math.ceil((cpuTemp-THRESHOLD_TEMP)/5)
        else:
                if FAN_ON: fan(OFF)
        print("CPU Temp: %d loop_after:%s"%(cpuTemp, loop_interval), flush=True)
        loop.call_later(loop_interval, fanManager, loop)


def main():
        loop=0
        try:
                loop = asyncio.get_event_loop()
                config()
                # Schedule the first call to fanManager()
                loop.call_soon(fanManager, loop)

                # Blocking call interrupted by loop.stop()
                loop.run_forever()

        except KeyboardInterrupt:
                print("\nKeyboardInterrupt, cleaning up...")
                if loop: loop.stop()
                if loop: loop.close()
                GPIO.cleanup()
                pass

        except Exception as e:
                print("exeption: %s"%str(e), flush=True)
                if loop: loop.stop()
                if loop: loop.close()
                GPIO.cleanup()

        finally:
                if loop: loop.close()
                GPIO.cleanup()

if __name__ == "__main__":
        main()
