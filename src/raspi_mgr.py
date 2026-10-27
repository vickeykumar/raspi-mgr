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
FAN_START_TEMP = 55.0
FAN_STOP_TEMP = 53.0       # hysteresis prevents rapid start/stop near 55°C
FAN_ON = False
ON = True
OFF = False
MIN_SPEED = 65.0           # minimum PWM duty while the fan is running (%)
PWM_FREQ = 200 #[Hz]
fanpwmHandle = None
WAIT_TIME = 5      # poll CPU temperature every 5 seconds
cpuTempOld=0
fanSpeedOld=0

# variable temperature and fan speeds
tempSteps = [55, 60, 65, 70]    # [°C]
speedSteps = [0, 50, 75, 100]   # [%]


def getCPUtemp():
        """Return CPU temperature in Celsius, or None if it cannot be read."""
        import subprocess

        try:
                result = subprocess.run(
                        ["/usr/bin/vcgencmd", "measure_temp"],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=3,
                )
                # Expected output: temp=41.3'C
                value = result.stdout.strip()
                if not value.startswith("temp=") or not value.endswith("'C"):
                        raise ValueError("unexpected vcgencmd output: %r" % value)
                return float(value[len("temp="):-2])
        except (OSError, subprocess.SubprocessError, ValueError) as e:
                print("ERROR: unable to read CPU temperature: %s" % e, flush=True)
                return None

def fan(mode=True):
        global FAN_PIN, FAN_ON, fanpwmHandle
        if fanpwmHandle:
            speed = 0
            if mode: speed=100
            fanpwmHandle.ChangeDutyCycle(speed)
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
        """Temperature-based PWM with a minimum running duty and fixed polling."""
        global FAN_ON, WAIT_TIME, fanSpeedOld, fanpwmHandle

        cpuTemp = getCPUtemp()
        loop_interval = WAIT_TIME

        if cpuTemp is None:
                # Fail safe: if temperature cannot be read, command full fan.
                fanSpeed = 100.0
        elif FAN_ON and cpuTemp > FAN_STOP_TEMP:
                # Once running, keep it running until it cools below stop temp.
                if cpuTemp < FAN_START_TEMP:
                        fanSpeed = MIN_SPEED
                else:
                        fanSpeed = float(
                                numpy.interp(cpuTemp, tempSteps, speedSteps)
                        )
                        # Avoid low-duty humming/stalling on a 2-wire fan.
                        fanSpeed = max(MIN_SPEED, fanSpeed)
        elif cpuTemp >= FAN_START_TEMP:
                fanSpeed = float(
                        numpy.interp(cpuTemp, tempSteps, speedSteps)
                )
                # A nonzero target must be at least the configured start duty.
                fanSpeed = max(MIN_SPEED, fanSpeed)
        else:
                fanSpeed = 0.0

        fanSpeed = max(0.0, min(100.0, fanSpeed))
        if fanpwmHandle is not None:
                fanpwmHandle.ChangeDutyCycle(fanSpeed)

        FAN_ON = fanSpeed > 0.0
        fanSpeedOld = fanSpeed

        tempText = "UNKNOWN" if cpuTemp is None else "%.1f" % cpuTemp
        print(
                "CPU Temp: %s loop_after:%ss fanspeed:%.1f FAN_ON:%s"
                % (tempText, loop_interval, fanSpeed, FAN_ON),
                flush=True,
        )

        # Keep monitoring frequent even when the CPU is hot.
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
        if args.ssh:
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
