import os
import spidev
import time
import signal
import multiprocessing
import math
import tkinter
import RPi.GPIO as GPIO

BUFFERSIZE = 20

coilTimeConstant = 0.002 # time each stepper coil is powered
spiReceiveRate = 0.1 # receive message every 0.1 seconds

def SPIListenerFunction(dataQueue):
    spi = spidev.SpiDev()
    spi.open(1, 0)
    spi.max_speed_hz = 15200

    tNext = time.time()

    while not mainExit.is_set():
        tNext += spiReceiveRate

        reply = spi.xfer(bytearray(BUFFERSIZE))

        # convert two 8-bit nibbles into one 16-bit word
        data = [((reply[byte + 1] << 8) | reply[byte]) for byte in range(0, BUFFERSIZE, 2)]

        # check if the stop word makes sense (0xAAAA)
        lastWord = data[-1] # list[-1] returns the last element of the list
        if lastWord != 0xAAAA:
            while lastWord != 0xAAAA:
                print("syncing data")

                # extract one 8-bit byte and append it to lastWord
                # mask lastWord to limit its length to 16 bits
                lastWord = ((lastWord << 8) & 0xFFFF) | spi.xfer([0])[0]
            # after reading correct stop word, read a complete reply
            reply = spi.xfer(bytearray(BUFFERSIZE))
            data = [((reply[byte + 1] << 8) | reply[byte]) for byte in range(0, BUFFERSIZE, 2)]

        data.append(time.time())
        print(data[-1])

        dataQueue.put(data)

        while time.time() <= tNext:
            pass
    spi.close()

def stepperFunction(dataQueue, pinA, pinB, pinC, pinD, timeConstant):
    GPIO.setup(pinA, GPIO.OUT)
    GPIO.setup(pinB, GPIO.OUT)
    GPIO.setup(pinC, GPIO.OUT)
    GPIO.setup(pinD, GPIO.OUT)

    currentPoint = 0

    for __ in range(180):
        self.__stepCCW__();

    while not mainExit.is_set():
        if not dataQueue.empty():
            setPoint = dataQueue.get()

        if currentPoint < setPoint:
            __stepCW__()
            currentPoint += 1
        elif currentPoint > setPoint:
            __stepCCW__()
            currentPoint -= 1
        else:
            pass

    def __stepCW__(self):

        GPIO.output(pinB, GPIO.LOW)
        GPIO.output(pinA, GPIO.HIGH)
        GPIO.output(pinC, GPIO.LOW)
        GPIO.output(pinD, GPIO.LOW)
        time.sleep(timeConstant)

        GPIO.output(pinA, GPIO.LOW)
        GPIO.output(pinB, GPIO.LOW)
        GPIO.output(pinC, GPIO.HIGH)
        GPIO.output(pinD, GPIO.LOW)
        time.sleep(timeConstant)

        GPIO.output(pinA, GPIO.LOW)
        GPIO.output(pinB, GPIO.HIGH)
        GPIO.output(pinC, GPIO.LOW)
        GPIO.output(pinD, GPIO.LOW)
        time.sleep(timeConstant)

        GPIO.output(pinA, GPIO.LOW)
        GPIO.output(pinB, GPIO.LOW)
        GPIO.output(pinC, GPIO.LOW)
        GPIO.output(pinD, GPIO.HIGH)
        time.sleep(timeConstant)

    def __stepCCW__(self):

        GPIO.output(pinA, GPIO.LOW)
        GPIO.output(pinB, GPIO.LOW)
        GPIO.output(pinC, GPIO.LOW)
        GPIO.output(pinD, GPIO.HIGH)
        time.sleep(timeConstant)

        GPIO.output(pinA, GPIO.LOW)
        GPIO.output(pinB, GPIO.HIGH)
        GPIO.output(pinC, GPIO.LOW)
        GPIO.output(pinD, GPIO.LOW)
        time.sleep(timeConstant)

        GPIO.output(pinA, GPIO.LOW)
        GPIO.output(pinB, GPIO.LOW)
        GPIO.output(pinC, GPIO.HIGH)
        GPIO.output(pinD, GPIO.LOW)
        time.sleep(timeConstant)

        GPIO.output(pinA, GPIO.HIGH)
        GPIO.output(pinB, GPIO.LOW)
        GPIO.output(pinC, GPIO.LOW)
        GPIO.output(pinD, GPIO.LOW)
        time.sleep(timeConstant)

def exitHandler(sig, frame):
    mainExit.set()

def deleteWindowHandler():
    # when window close button is clicked, send SIGINT to yourself
    # this lets the exitHandler function kill the threads properly
    os.kill(os.getpid(), signal.SIGINT)

def matrixMultiply(a, b):
    zip_b = zip(*b)
    zip_b = list(zip_b)
    return [[sum(ele_a*ele_b for ele_a, ele_b in zip(row_a, col_b)) for col_b in zip_b] for row_a in a]

if __name__ == "__main__":
    signal.signal(signal.SIGINT, exitHandler)
    GPIO.setmode(GPIO.BCM)

    mainExit = multiprocessing.Event()
    SPIQueue = multiprocessing.Queue(maxsize = 2)
    speedGaugeQueue = multiprocessing.Queue(maxsize = 2)
    ampGaugeQueue = multiprocessing.Queue(maxsize = 2)

    SPIListener = multiprocessing.Process(
        target = SPIListenerFunction,
        kwargs = {'dataQueue': SPIQueue}
    )
    SPIListener.start()

    speedGauge = multiprocessing.Process(
        target = stepperFunction,
        kwargs = {
            'dataQueue': speedGaugeQueue,
            'pinA': 2,
            'pinB': 3,
            'pinC': 4,
            'pinD': 5,
            'timeConstant': coilTimeConstant
        }
    )
    speedGauge.start()

    ampGauge = multiprocessing.Process(
        target = stepperFunction,
        kwargs = {
            'dataQueue': ampGaugeQueue,
            'pinA': 22,
            'pinB': 23,
            'pinC': 24,
            'pinD': 27,
            'timeConstant': coilTimeConstant
        }
    )
    ampGauge.start()

    mainWindow = tkinter.Tk(className="gauge")
    mainWindow.attributes("-fullscreen", True)
    mainWindow.config(cursor="none")
    mainWindow.protocol("WM_DELETE_WINDOW", deleteWindowHandler)
    canvas = tkinter.Canvas(mainWindow, width = 320, height = 240)
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

    needleCoords = [[0, 240], [160, 230], [160, 250]]
    needleHinge = [160, 240]
    needleAngle = 0

    translateToOrigin = [[1, 0, -needleHinge[0]], [0, 1, -needleHinge[1]], [0, 0, 1]]
    translateToHinge = [[1, 0, needleHinge[0]], [0, 1, needleHinge[1]], [0, 0, 1]]
    rotateCW = [[math.cos(math.radians(1)), -math.sin(math.radians(1)), 0], [math.sin(math.radians(1)), math.cos(math.radians(1)), 0], [0, 0, 1]]
    rotateCCW = [[math.cos(math.radians(-1)), -math.sin(math.radians(-1)), 0], [math.sin(math.radians(-1)), math.cos(math.radians(-1)), 0], [0, 0, 1]]

    dial = canvas.create_arc(0, 80, 320, 400, start = 0, extent = 180, fill = "black")
    needle = canvas.create_polygon(*needleCoords, fill="red")

    while not mainExit.is_set():
        if not dataQueue.empty():
            data = dataQueue.get()

        potValue = data[5]
        setPoint = math.floor((potValue/1023)*180)

        speedPos = math.floor((potValue/1023)*100)
        ampPos = 100 - math.floor((potValue/1023)*100)

        speedGaugeQueue.put(speedPos)
        ampGaugeQueue.put(ampPos)

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

    GPIO.cleanup()
