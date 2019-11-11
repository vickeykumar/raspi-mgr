#!/usr/bin/env python3
# coding: utf-8
# Author: VICKEY KUMAR
import asyncio,os
import signal
import math,numpy
import argparse
import RPi.GPIO as GPIO
#from raspi_stub import GPIO
GPIO.setmode (GPIO.BOARD)

CONFIG_FILE="/etc/raspi_mgr.config"
KEY_PAIR_FILE=""
SSH_FWD_IP=None
SSH_PORT=22
TUNNEL_PORT=22
TCP_FWD_IP=None
TCP_PORT=80
FWDNG_AGENT=None
FAN_PIN = 7
THRESHOLD_TEMP = 55
FAN_ON = False
ON = True
OFF = False
MIN_SPEED = 65 # minimum fan speed [%]
PWM_FREQ = 200 #[Hz]
fanpwmHandle = None
WAIT_TIME = 60     #poll evry 60 sec for temperature
cpuTempOld=0
fanSpeedOld=0

# variable temperature and fan speeds
tempSteps = [50, 55, 60, 70]    # [°C]
speedSteps = [0, 55, 75, 100]   # [%]


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
        global FAN_PIN, FAN_ON, fanpwmHandle
        if fanpwmHandle:
            fanpwmHandle.ChangeDutyCycle(0)
        else:
            GPIO.output(FAN_PIN, mode)
        FAN_ON = mode
        return()

def config():
        global FAN_PIN
        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)
        GPIO.setup(FAN_PIN,GPIO.OUT)
        fan(OFF)    #resetting fan

# Fan svc using PWM
def setupPwmConfig():
        global FAN_PIN, PWM_FREQ, fanpwmHandle
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(FAN_PIN, GPIO.OUT, initial=GPIO.LOW)
        fanpwmHandle=GPIO.PWM(FAN_PIN,PWM_FREQ)
        fanpwmHandle.start(0);

# Fan Manager Svc
def fanManagerSvc(loop):
        global FAN_ON
        loop_interval=WAIT_TIME
        cpuTemp = getCPUtemp()
        if cpuTemp>THRESHOLD_TEMP :
                if not FAN_ON: fan(ON)
                '''wait 60 sec for ev 5'C raise in temp for next polling'''
                loop_interval = 5*loop_interval*math.ceil((cpuTemp-THRESHOLD_TEMP)/5)
        else:
                if FAN_ON: fan(OFF)
        print("CPU Temp: %d loop_after:%s"%(cpuTemp, loop_interval), flush=True)
        loop.call_later(loop_interval, fanManagerSvc, loop)

# Fan manager PWM Svc
def fanManagerPwmSvc(loop):
        global FAN_ON, WAIT_TIME, fanSpeedOld, fanpwmHandle
        cpuTemp = getCPUtemp()
        fanSpeed = 0
        loop_interval=WAIT_TIME
        if(cpuTemp < tempSteps[0] or cpuTemp < THRESHOLD_TEMP):
                if FAN_ON: fan(OFF)
        elif(cpuTemp >= tempSteps[len(tempSteps)-1]):
                if not FAN_ON: fan(ON)
                fanSpeed = 100 # 100% speed
        else:
                fanSpeed = numpy.interp(cpuTemp, tempSteps, speedSteps)
                if (fanSpeedOld!=fanSpeed):
                    fanpwmHandle.ChangeDutyCycle(fanSpeed)
                    if not int(fanSpeed):
                        FAN_ON=False
                    else:
                        FAN_ON=True
                if (cpuTemp>THRESHOLD_TEMP): loop_interval = 5*loop_interval*math.ceil((cpuTemp-THRESHOLD_TEMP)/5)

        fanSpeedOld = fanSpeed
        print("CPU Temp: %d loop_after:%s fanspeed:%s FAN_ON:%s"%(cpuTemp, loop_interval, fanSpeed, FAN_ON), flush=True)
        loop.call_later(loop_interval, fanManagerPwmSvc, loop)


def shutdown(signal, loop):
        """Cleanup tasks tied to the service's shutdown."""
        print("raspi-mgr: caught signal: ",signal,flush=True)
        GPIO.cleanup()
        loop.stop()

def parseArgs():
        parser = argparse.ArgumentParser()
        parser.add_argument('--ssh', action='store_true')
        parser.add_argument('--pwm', action='store_true')
        args = parser.parse_args()
        return args

def startsshSvc(args):
        global SSH_FWD_IP, SSH_PORT, TUNNEL_PORT, TCP_FWD_IP, TCP_PORT, FWDNG_AGENT, KEY_PAIR_FILE
        if args.ssh and FWDNG_AGENT and (SSH_FWD_IP or TCP_FWD_IP) :
            key_option = "-i %s"%KEY_PAIR_FILE if KEY_PAIR_FILE else ""
            tunnel_option = "-p %s"%TUNNEL_PORT if TUNNEL_PORT!=22 else ""
            ssh_option = "-R %s:%s:localhost:22"%(SSH_FWD_IP, SSH_PORT) if SSH_FWD_IP else ""
            tcp_option = "-R %s:%s:localhost:80"%(TCP_FWD_IP, TCP_PORT) if TCP_FWD_IP else ""
            print("starting autossh service with options:%s %s %s"%(key_option,ssh_option,tcp_option), flush=True)
            os.system('''export AUTOSSH_DEBUG=1; export AUTOSSH_POLL=60; autossh %s -M 0 -v -f %s %s %s %s -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o ExitOnForwardFailure=yes'''%(key_option,tunnel_option,ssh_option,tcp_option,FWDNG_AGENT))
        else:
            print("skipping ssh forwarding service, please check config or arguments",flush=True)

def startFanManagerSvc(args, loop):
        if args.pwm:
            print("starting pwm Fan mgr service:", flush=True)
            setupPwmConfig()
            loop.call_soon(fanManagerPwmSvc, loop)
        else:
            print("starting Fan mgr service:", flush=True)
            loop.call_soon(fanManagerSvc, loop)


def parseconfigfile():
        global CONFIG_FILE, SSH_FWD_IP, SSH_PORT, TUNNEL_PORT, TCP_FWD_IP, TCP_PORT, FWDNG_AGENT, KEY_PAIR_FILE
        try:
            f=open(CONFIG_FILE,"r")
            lines=f.readlines()
            f.close()
            lines = [l.strip() for l in lines]
            lines = [l.split("=") for l in lines if not l.startswith("#")]
            configMap = dict([l for l in lines if len(l)==2])
            SSH_FWD_IP = configMap["SSH_FWD_IP"] if "SSH_FWD_IP" in configMap else None
            SSH_PORT = configMap["SSH_PORT"] if "SSH_PORT" in configMap else 22
            TUNNEL_PORT = configMap["TUNNEL_PORT"] if "TUNNEL_PORT" in configMap else 22 		
            TCP_FWD_IP= configMap["TCP_FWD_IP"] if "TCP_FWD_IP" in configMap else None
            TCP_PORT= configMap["TCP_PORT"] if "TCP_PORT" in configMap else 80
            FWDNG_AGENT= configMap["FWDNG_AGENT"] if "FWDNG_AGENT" in configMap else None
            KEY_PAIR_FILE= configMap["KEY_PAIR_FILE"] if "KEY_PAIR_FILE" in configMap else None 

        except Exception as e:
            print("Failed to parse config file, Exception:%s"%str(e), flush=True)
            return False
        return True

def main():
        loop=0
        args = parseArgs()
        parseconfigfile()
        try:
                startsshSvc(args)
                loop = asyncio.get_event_loop()
                config()
                signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)
                for s in signals:
                        loop.add_signal_handler(s, shutdown, s, loop)
                # Schedule the first call to fanManager()
                startFanManagerSvc(args, loop)

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
