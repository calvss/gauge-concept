import os
import spidev
import time
import signal
import threading
import math
import tkinter
import RPi.GPIO as GPIO

BUFFERSIZE = 20

coilTimeConstant = 0.002 # time each stepper coil is powered
spiReceiveRate = 0.05 # receive message every 0.1 seconds

lock = threading.Lock()
mainExit = threading.Event()
data = [0] * 10 # slave sends total of 10 integers

class SPIListenerClass(threading.Thread):
    # NOTE: 16-bit words are sent thru SPI one byte (8 bits) at a time

    def __init__(self):
        threading.Thread.__init__(self)
        self.exitFlag = threading.Event()

    def run(self):
        global data

        spi = spidev.SpiDev()
        spi.open(1,0)
        spi.max_speed_hz = 15200

        tNext = time.time()

        while not self.exitFlag.is_set():
            tNext = tNext + spiReceiveRate
            reply = spi.xfer(bytearray(BUFFERSIZE))

            # list operations aren't atomic!
            with lock:
                data = [((reply[byte + 1] << 8) | reply[byte]) for byte in range(0, BUFFERSIZE, 2)]

            # check if the stop word makes sense (0xAAAA)
            lastWord = data[-1] # list[-1] returns the last element of the list
            if lastWord != 0xAAAA:
                while lastWord != 0xAAAA:
                    print("syncing data")

                    # extract one byte and append it to lastWord
                    # mask lastWord to limit its length to 16 bits
                    lastWord = ((lastWord << 8) & 0xFFFF) | spi.xfer([0])[0]
                # after reading correct stop word, read a complete reply
                reply = spi.xfer(bytearray(BUFFERSIZE))
                with lock:
                    data = [((reply[byte + 1] << 8) | reply[byte]) for byte in range(0, BUFFERSIZE, 2)]

            print(data)
            while time.time() <= tNext:
                pass
        spi.close()

class StepperClass(threading.Thread):
    __gpioInitialized__ = False
    __classInstances__ = 0
    def __init__(self, pinA, pinB, pinC, pinD, timeConstant):
        threading.Thread.__init__(self)
        self.exitFlag = threading.Event()

        if not __gpioInitialized__:
            GPIO.setmode(GPIO.BCM)
            __gpioInitialized__ = True

        __classInstances__ += 1

        self.__pinA__ = pinA
        self.__pinB__ = pinB
        self.__pinC__ = pinC
        self.__pinD__ = pinD
        self.coilTimeConstant = timeConstant

    def run(self):
        GPIO.setup(self.__pinA__, GPIO.OUT)
        GPIO.setup(self.__pinB__, GPIO.OUT)
        GPIO.setup(self.__pinC__, GPIO.OUT)
        GPIO.setup(self.__pinD__, GPIO.OUT)

        currentPoint = 0

        #return needle to 0 at the start
        for __ in range(100):
            self.__stepCCW__();

        while not self.exitFlag.is_set():
            with lock:
                localCopyOfData = data[:]

            potValue = localCopyOfData[5]
            setPoint = math.floor((potValue/1023)*100)

            if currentPoint < setPoint:
                self.__stepCW__()
                currentPoint = currentPoint + 1
            elif currentPoint > setPoint:
                self.__stepCCW__()
                currentPoint = currentPoint - 1
            else:
                pass

        # decrement number of running stepperClasses
        __classInstances__ -= 1

        # if you're the last class, clean up after youtself
        if __classInstances__ == 0:
            GPIO.cleanup()

    def __stepCW__(self):

        GPIO.output(self.__pinA__, GPIO.HIGH)
        GPIO.output(self.__pinB__, GPIO.LOW)
        GPIO.output(self.__pinC__, GPIO.LOW)
        GPIO.output(self.__pinD__, GPIO.LOW)
        time.sleep(self.timeConstant)

        GPIO.output(self.__pinA__, GPIO.LOW)
        GPIO.output(self.__pinB__, GPIO.LOW)
        GPIO.output(self.__pinC__, GPIO.HIGH)
        GPIO.output(self.__pinD__, GPIO.LOW)
        time.sleep(self.timeConstant)

        GPIO.output(self.__pinA__, GPIO.LOW)
        GPIO.output(self.__pinB__, GPIO.HIGH)
        GPIO.output(self.__pinC__, GPIO.LOW)
        GPIO.output(self.__pinD__, GPIO.LOW)
        time.sleep(self.timeConstant)

        GPIO.output(self.__pinA__, GPIO.LOW)
        GPIO.output(self.__pinB__, GPIO.LOW)
        GPIO.output(self.__pinC__, GPIO.LOW)
        GPIO.output(self.__pinD__, GPIO.HIGH)
        time.sleep(self.timeConstant)

    def __stepCCW__(self):

        GPIO.output(self.__pinA__, GPIO.LOW)
        GPIO.output(self.__pinB__, GPIO.LOW)
        GPIO.output(self.__pinC__, GPIO.LOW)
        GPIO.output(self.__pinD__, GPIO.HIGH)
        time.sleep(self.timeConstant)

        GPIO.output(self.__pinA__, GPIO.LOW)
        GPIO.output(self.__pinB__, GPIO.HIGH)
        GPIO.output(self.__pinC__, GPIO.LOW)
        GPIO.output(self.__pinD__, GPIO.LOW)
        time.sleep(self.timeConstant)

        GPIO.output(self.__pinA__, GPIO.LOW)
        GPIO.output(self.__pinB__, GPIO.LOW)
        GPIO.output(self.__pinC__, GPIO.HIGH)
        GPIO.output(self.__pinD__, GPIO.LOW)
        time.sleep(self.timeConstant)

        GPIO.output(self.__pinA__, GPIO.HIGH)
        GPIO.output(self.__pinB__, GPIO.LOW)
        GPIO.output(self.__pinC__, GPIO.LOW)
        GPIO.output(self.__pinD__, GPIO.LOW)
        time.sleep(self.timeConstant)

def signalHandler(sig, frame):
    SPIListener.exitFlag.set()
    Stepper.exitFlag.set()
    mainExit.set()

def deleteWindowHandler():
    os.kill(os.getpid(), signal.SIGINT)

def matrixMultiply(a, b):
    zip_b = zip(*b)
    zip_b = list(zip_b)
    return [[sum(ele_a*ele_b for ele_a, ele_b in zip(row_a, col_b)) for col_b in zip_b] for row_a in a]

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signalHandler)

    SPIListener = SPIListenerClass()
    SPIListener.start()

    Stepper = StepperClass(
        pinA = 2,
        pinB = 3,
        pinC = 4,
        pinD = 5,
        timeConstant = coilTimeConstant)
    Stepper.start()

    mainWindow = tkinter.Tk(className="gauge")
    mainWindow.protocol("WM_DELETE_WINDOW", deleteWindowHandler)
    canvas = tkinter.Canvas(mainWindow, width = 200, height = 200)
    canvas.pack()

    # square = [[50, 50], [100, 50], [100, 100]]
    # squareCentroid = [sum(column) / len(column) for column in list(zip(*square))]
    #
    # # convert points to vertical vectors with 1 at the end
    # squareAugmented = [[[coord] for coord in (*point, 1)] for point in square]
    #
    # translateToOrigin = [[1, 0, -squareCentroid[0]], [0, 1, -squareCentroid[1]], [0, 0, 1]]
    # rotationMatrix = [[math.cos(math.radians(10)), -math.sin(math.radians(10)), 0], [math.sin(math.radians(10)), math.cos(math.radians(10)), 0], [0, 0, 1]]
    # translateToCentroid = [[1, 0, squareCentroid[0]], [0, 1, squareCentroid[1]], [0, 0, 1]]
    #
    # affineMatrix = matrixMultiply(translateToCentroid, matrixMultiply(rotationMatrix, translateToOrigin))
    #
    # squareAugmentedRotated = [matrixMultiply(affineMatrix, vector) for vector in squareAugmented]
    #
    # squareRotated = [[coord[0] for coord in vector[:2]] for vector in squareAugmentedRotated]
    #
    # canvas.create_polygon(*square, fill="red")
    # canvas.create_polygon(*squareRotated, fill="blue")

    needleCoords = [[0, 200], [100, 190], [100, 210]]
    needleHinge = [100, 200]
    needleAngle = 0

    translateToOrigin = [[1, 0, -needleHinge[0]], [0, 1, -needleHinge[1]], [0, 0, 1]]
    translateToHinge = [[1, 0, needleHinge[0]], [0, 1, needleHinge[1]], [0, 0, 1]]
    rotateCW = [[math.cos(math.radians(1)), -math.sin(math.radians(1)), 0], [math.sin(math.radians(1)), math.cos(math.radians(1)), 0], [0, 0, 1]]
    rotateCCW = [[math.cos(math.radians(-1)), -math.sin(math.radians(-1)), 0], [math.sin(math.radians(-1)), math.cos(math.radians(-1)), 0], [0, 0, 1]]

    dial = canvas.create_arc(0, 200, 100, 200, start = 0, extent = 180, fill = "black")
    needle = canvas.create_polygon(*needleCoords, fill="red")

    while not mainExit.is_set():

        with lock:
            localCopyOfData = data[:]

        potValue = localCopyOfData[5]
        setPoint = math.floor((potValue/1023)*180)

        if needleAngle < setPoint:
            affineMatrix = matrixMultiply(translateToHinge, matrixMultiply(rotateCW, translateToOrigin))
            needleAugmented = [[[coord] for coord in (*point, 1)] for point in needleCoords]
            needleAugmented = [matrixMultiply(affineMatrix, vector) for vector in needleAugmented]
            needleCoords = [[coord[0] for coord in vector[:2]] for vector in needleAugmented]

            needleAngle = needleAngle + 1
        elif needleAngle > setPoint:
            affineMatrix = matrixMultiply(translateToHinge, matrixMultiply(rotateCCW, translateToOrigin))
            needleAugmented = [[[coord] for coord in (*point, 1)] for point in needleCoords]
            needleAugmented = [matrixMultiply(affineMatrix, vector) for vector in needleAugmented]
            needleCoords = [[coord[0] for coord in vector[:2]] for vector in needleAugmented]

            needleAngle = needleAngle - 1
        else:
            pass

        canvas.coords(needle, [coord for point in needleCoords for coord in point])

        mainWindow.update_idletasks()
        mainWindow.update()
