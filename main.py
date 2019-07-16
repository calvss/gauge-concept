import os
import spidev
import time
import signal
import multiprocessing
import math
import tkinter
import RPi.GPIO as GPIO
import csv
from collections import deque

BUFFERSIZE = 20

coilTimeConstant = 0.002 # time each stepper coil is powered
spiReceiveRate = 0.1 # receive message every 0.1 seconds
stepperLoopRate = 0.01 # step motors every 0.01 seconds

labelHeaderSize = 10
labelDataSize = 14

pulseToSpd = 0.5171692
pulseToKm = pulseToSpd*2/36000

startupTime = time.time()

def SPIListenerFunction(dataQueue):

    # dataQueue message format:
    #   [0] tic
    #   [1] rev
    #   [2] fwd
    #   [3] spd
    #   [4] vlt
    #   [5] thr
    #   [6] pow
    #   [7] cur
    #   [8] tmp
    #   [9] STOP WORD (0xAAAA)
    #   [10] timestamp

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
        #print(data[-1])

        dataQueue.put(data)

        while time.time() <= tNext:
            pass
    spi.close()

def stepperFunction(dataQueue, pinA, pinB, pinC, pinD, timeConstant):
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pinA, GPIO.OUT)
    GPIO.setup(pinB, GPIO.OUT)
    GPIO.setup(pinC, GPIO.OUT)
    GPIO.setup(pinD, GPIO.OUT)

    setPoint = 0;
    currentPoint = 0

    def __stepCW__():

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

    def __stepCCW__():

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

    for __ in range(180):
        __stepCCW__();

    tNext = time.time()

    while not mainExit.is_set():
        tNext += stepperLoopRate
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

        while time.time() <= tNext:
            time.sleep(stepperLoopRate)
    GPIO.cleanup()

def dataManagerFunction(speedGaugeQueue, ampGaugeQueue, processedData, SPIData, logData):
    previousTime = startupTime

    odoCount = float(0.0)
    speedData = deque(maxlen = 10)

    while not mainExit.is_set():
        ## TODO: calculate data and convert to proper units
        if not SPIData.empty():
            rawData = SPIData.get_nowait()
            data = rawData
            # Timestamps attached to each message
            # time in seconds
            currentTime = rawData[-1]
            timeElapsed = currentTime - previousTime
            previousTime = currentTime

            rawThrottle = rawData[5]

            # throttle signal is from 0V-4.7V, dividered between 1k and 100k
            # datalogger ADC maps 0V-5V to 0-1023
            throttlePct = clamp((((rawThrottle/1023) * 5) / 4), 0, 1)

            # speed calculation
            speedCount = rawData[3]
            speedData.append(speedCount)

            speedSum = 0
            for item in speedData:
                speedSum += item
            speedAverage = speedSum/len(speedData)

            speed = speedAverage * pulseToSpd # kph
            odoCount += speedCount * pulseToKm # km

            # current calculation
            rawCurrent = rawData[7]
            current = ((rawCurrent/204.6)*(1.001)-(327/204.6))*(200/1.25)

            # volts calculation
            rawVolt = rawData[4]
            volt = rawVolt*0.404 - 20.582

            #pow calculation
            rawPow = rawData[6]
            pow = rawPow*(0.158371)

            data[3] = speed
            data[4] = volt
            data[5] = throttlePct
            data[6] = pow
            data[7] = current

            # 106 steps in the dial
            speedPos = math.floor((speed / 80)*109)
            ampPos = 109 - math.floor((current/220)*109)
            # print(current, ampPos)

            try:
                speedGaugeQueue.put_nowait(speedPos)
                ampGaugeQueue.put_nowait(ampPos)
            except:
                pass

            try:
                processedData.put_nowait(data)
            except:
                pass

            try:
                logData.put(rawData, block = True, timeout = 0.1)
            except:
                print("slow SD card")

def fileWriterFunction(dataQueue):
    timeCreated = time.asctime().replace(" ", ".").replace(":", ".")
    dir = "/home/pi/gauge/Pot Gauge/"
    with open(dir + timeCreated + ".txt", 'w+') as logFile:
        writer = csv.writer(logFile, dialect = 'excel')
        logFile.write("temp, current, pow, throttle, volt, speed, fwd, rev, tic, timestamp\r\n")
        while not mainExit.is_set():
            data = []
            while not dataQueue.empty():
                data.append(dataQueue.get_nowait())

            for log in data:
                # [-3::-1] means "everything except the last 2 items, in reverse order"
                # last 2 items are stopword and timestamp
                # [-1] is the last item
                row = log[-3::-1] + [log[-1]]
                writer.writerow(row)


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

def clamp(n, minn, maxn):
    return max(min(maxn, n), minn)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, exitHandler)

    mainExit = multiprocessing.Event()
    SPIData = multiprocessing.Queue(maxsize = 2)
    speedGaugeQueue = multiprocessing.Queue(maxsize = 2)
    ampGaugeQueue = multiprocessing.Queue(maxsize = 2)
    processedData = multiprocessing.Queue(maxsize = 2)
    logData = multiprocessing.Queue(maxsize = 15)

    SPIListener = multiprocessing.Process(
        target = SPIListenerFunction,
        kwargs = {'dataQueue': SPIData}
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

    dataManager = multiprocessing.Process(
        target = dataManagerFunction,
        kwargs = {
            'speedGaugeQueue': speedGaugeQueue,
            'ampGaugeQueue': ampGaugeQueue,
            'processedData': processedData,
            'SPIData': SPIData,
            'logData': logData
        }
    )
    dataManager.start()

    fileWriter = multiprocessing.Process(
        target = fileWriterFunction,
        kwargs = {
            'dataQueue': logData
        }
    )
    fileWriter.start()

    mainWindow = tkinter.Tk(className="gauge")
    mainWindow.attributes("-fullscreen", True)
    mainWindow.config(cursor="none")
    mainWindow.protocol("WM_DELETE_WINDOW", deleteWindowHandler)
    gauge = tkinter.Canvas(mainWindow, width = 120, height = 60)
    gauge.grid(row = 0, column = 0, columnspan = 2)

    tkinter.Label(mainWindow, text="Time", font=("Courier", labelHeaderSize)).grid(row = 2, column = 0)
    tkinter.Label(mainWindow, text="Volt", font=("Courier", labelHeaderSize)).grid(row = 2, column = 1)
    tkinter.Label(mainWindow, text="Amp", font=("Courier", labelHeaderSize)).grid(row = 2, column = 2)
    tkinter.Label(mainWindow, text="Throttle", font=("Courier", labelHeaderSize)).grid(row = 2, column = 3)

    timeLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    voltLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    ampLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    throttleLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    timeLabel.grid(row = 3, column = 0)
    voltLabel.grid(row = 3, column = 1)
    ampLabel.grid(row = 3, column = 2)
    throttleLabel.grid(row = 3, column = 3)

    tkinter.Label(mainWindow, text="Speed", font=("Courier", labelHeaderSize)).grid(row = 4, column = 0)
    tkinter.Label(mainWindow, text="Distance", font=("Courier", labelHeaderSize)).grid(row = 4, column = 1)
    tkinter.Label(mainWindow, text="FWD", font=("Courier", labelHeaderSize)).grid(row = 4, column = 2)
    tkinter.Label(mainWindow, text="REV", font=("Courier", labelHeaderSize)).grid(row = 4, column = 3)

    speedLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    distanceLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    fwdLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    revLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    speedLabel.grid(row = 5, column = 0)
    distanceLabel.grid(row = 5, column = 1)
    fwdLabel.grid(row = 5, column = 2)
    revLabel.grid(row = 5, column = 3)

    tkinter.Label(mainWindow, text="Power", font=("Courier", labelHeaderSize)).grid(row = 6, column = 0)
    tkinter.Label(mainWindow, text="MCPow", font=("Courier", labelHeaderSize)).grid(row = 6, column = 1)
    tkinter.Label(mainWindow, text="Tic", font=("Courier", labelHeaderSize)).grid(row = 6, column = 2)

    powerLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    mcpowLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    ticLabel = tkinter.Label(mainWindow, text=".", font=("Courier", labelDataSize))
    powerLabel.grid(row = 7, column = 0)
    mcpowLabel.grid(row = 7, column = 1)
    ticLabel.grid(row = 7, column = 2)

    mainWindow.update_idletasks()
    mainWindow.update()

    needleCoords = [[gauge.winfo_rootx(), gauge.winfo_rooty() + gauge.winfo_height()], [gauge.winfo_rootx() + gauge.winfo_width()/2, gauge.winfo_rooty() + gauge.winfo_height() - 5], [gauge.winfo_rootx() + gauge.winfo_width()/2, gauge.winfo_rooty() + gauge.winfo_height() + 5]]
    needleHinge = [gauge.winfo_rootx() + gauge.winfo_width()/2, gauge.winfo_rooty() + gauge.winfo_height()]
    needleAngle = 0

    dial = gauge.create_arc(gauge.winfo_rootx(), gauge.winfo_rooty() + (gauge.winfo_height() - gauge.winfo_width()/2), gauge.winfo_rootx() + gauge.winfo_width(), gauge.winfo_rooty() + gauge.winfo_height() + gauge.winfo_width()/2, start = 0, extent = 180, fill = "black")

    translateToOrigin = [[1, 0, -needleHinge[0]], [0, 1, -needleHinge[1]], [0, 0, 1]]
    translateToHinge = [[1, 0, needleHinge[0]], [0, 1, needleHinge[1]], [0, 0, 1]]
    rotateCW = [[math.cos(math.radians(1)), -math.sin(math.radians(1)), 0], [math.sin(math.radians(1)), math.cos(math.radians(1)), 0], [0, 0, 1]]
    rotateCCW = [[math.cos(math.radians(-1)), -math.sin(math.radians(-1)), 0], [math.sin(math.radians(-1)), math.cos(math.radians(-1)), 0], [0, 0, 1]]

    needle = gauge.create_polygon(*needleCoords, fill="red")

    while not mainExit.is_set():
        if not processedData.empty():
            print(time.time())
            data = processedData.get()

        timeLabel.config(text=str(time.time() - startupTime)[:4])
        voltLabel.config(text=str(data[4])[:4])
        ampLabel.config(text=str(data[7])[:4])
        throttleLabel.config(text=str(data[5]*100)[:3] + "%")
        speedLabel.config(text=str(data[3])[:4])
        distanceLabel.config(text="0")
        fwdLabel.config(text=str(data[2])[:4])
        revLabel.config(text=str(data[1])[:4])
        powerLabel.config(text="0")
        mcpowLabel.config(text=str(data[6])[:4])
        ticLabel.config(text=str(data[0])[:4].rjust(4))

        throttlePct = data[5]

        setPoint = math.floor(throttlePct*180)

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

        gauge.coords(needle, [coord for point in needleCoords for coord in point])

        mainWindow.update_idletasks()
        mainWindow.update()
