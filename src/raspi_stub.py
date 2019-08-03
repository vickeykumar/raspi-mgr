# implements RPi.GPIO stubs for testing
BOARD=True
OUT=True

class GPIO:
    BOARD = True
    OUT = True
    LOW = False
    def setmode(x):
        print("GPIO.setmode: ",x)
        pass

    def setwarnings(x):
        print("GPIO.setwarning: ",x)
        pass

    def setup(x, y, initial=False):
        print("GPIO.setup:",x,y,initial)
        pass
    
    def output(FAN_PIN, mode):
        print("GPIO.output: ",FAN_PIN, mode)
        pass

    def cleanup():
        print("GPIO.cleanup:")
        pass

    def PWM(x, y):
        print("GPIO.PWM: ",x,y)
        self = GPIO()
        return self

    def start(self, x):
        print("GPIO.start: ",self,x)
        pass
    
    def ChangeDutyCycle(self, x):
        print("GPIO.change duty: ",self, x)
        pass
