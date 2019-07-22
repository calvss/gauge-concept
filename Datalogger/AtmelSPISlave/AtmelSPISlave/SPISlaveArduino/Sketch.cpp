/*
    Author: Calvin Ng

    Date Created: 2019 July 01
*/

/*
    Inherited from code20180914_fix.ino by GR Licu

    Notes:

      Background Information
    Project data logger is the development of a single device capable of logging data
    into an SD Card. It's purpose is to increase convenience when testing. As of writing
    this, it's still a prototype.

      Instructions
    - Power supply: ~12V (can be the vehicles accesories or a battery)
    - The 'Record' switch. Start recording by turning it ON. Recording also has a
      maximum record time. For each recording session, a new log file is generated.
    - Led has warning pattern if SD Card is missing.
    - SD Card should not be removed while device is powered.


    Fuse Settings

    BODLEVEL = DISABLED
    RSTDISBL = [ ]
    DWEN = [ ]
    SPIEN = [X]
    WDTON = [ ]
    EESAVE = [ ]
    BOOTSZ = 2048W_3800
    BOOTRST = [ ]
    CKDIV8 = [X]
    CKOUT = [ ]
    SUT_CKSEL = EXTFSXTAL_258CK_14CK_4MS1
*/

#include<Arduino.h>
#include<TimerOne.h>
#include<SPISlave.h>

//---------------------------------- DEFINES

#define BUFFERSIZE 20

//---------------------------------- PIN ASSIGNMENTS

const uint8_t inTmpPin = A1;      // analog input, temperature
const uint8_t inCurPin = A2;      // analog input, current
const uint8_t inPowPin = A3;      // analog input, conn. power
const uint8_t inThrPin = A4;      // analog input, conn. throttle
const uint8_t inVltPin = A5;      // analog input, voltage
const uint8_t inFwdPin = 4;       // digital input, conn. forward
const uint8_t inRevPin = 5;       // digital input, conn. reverse
const uint8_t ledPin = 7;         // digital output, led

const uint8_t speedInterruptPin = 2; // interrupt input, conn. speed
const uint8_t speedInterrupt    = 0; // Interrupts for ATMEGA328: 0 --> pin 2, 1 --> pin 3

//---------------------------------- VARIABLES

const uint32_t timerInit = 50000; // timer period, should tick every 0.05 second

uint8_t buffer[BUFFERSIZE];

uint8_t blink = 0;// led state
uint32_t tic = 0;// used to measure time per sampling period

uint16_t dataTmp = 0; // Temperature
uint16_t dataCur = 0; // Battery Current
uint16_t dataPow = 0; // Power to Controller
uint16_t dataThr = 0; // Throttle Signal
uint16_t dataVlt = 0; // Battery Voltage
uint16_t dataSpd = 0; // Speed
uint16_t dataFwd = 0; // Forward Signal
uint16_t dataRev = 0; // Reverse Signal
uint16_t dataTic = 0; // Processing time


//---------------------------------- FUNCTION DECLARATIONS

// ISR functions
void timerIsr();
void speedIsr();

// Utility functions

inline void uint16to8Converter(uint8_t *out, uint16_t in);

//---------------------------------- SETUP
void setup()
{
    pinMode(ledPin, OUTPUT); // LED signal
    digitalWrite(ledPin, HIGH); // On start-up. turn ON to see whether microcontroller is working

    // Setup output pins
    pinMode(inFwdPin, INPUT); // forward signal
    pinMode(inRevPin, INPUT); // reverse signal
    pinMode(speedInterruptPin, INPUT_PULLUP); // speed interrupt signal
    attachInterrupt(speedInterrupt, speedIsr, RISING);

    delay(100);

    // Begin SPI slave mode
    SPISlave.begin();

    // initialize Timer
    Timer1.initialize(timerInit);
    Timer1.attachInterrupt(timerIsr);
}

void loop()
{
    digitalWrite(ledPin, blink);
    blink = !blink;
    // time data
	tic = millis() - tic;
    dataTic = (uint16_t) tic;
    tic = millis();

    // write sensor data to buffer array
    // buffer is 8 bits per element, so need to split each variable into nibbles
    uint16to8Converter(&(buffer[0]), dataTic);
    uint16to8Converter(&(buffer[2]), dataRev);
    uint16to8Converter(&(buffer[4]), dataFwd);
    uint16to8Converter(&(buffer[6]), dataSpd);
    dataSpd = 0;
    uint16to8Converter(&(buffer[8]), dataVlt);
    uint16to8Converter(&(buffer[10]), dataThr);
    uint16to8Converter(&(buffer[12]), dataPow);
    uint16to8Converter(&(buffer[14]), dataCur);
    uint16to8Converter(&(buffer[16]), dataTmp);
    buffer[18] = 0xAA;
    buffer[19] = 0xAA;

    // buffer[0] = (uint8_t) dataTic;
    // buffer[1] = (uint8_t) (dataTic >> 8);
    //
    // buffer[2] = (uint8_t) dataRev;
    // buffer[3] = (uint8_t) (dataRev >> 8);
    //
    // buffer[4] = (uint8_t) dataFwd;
    // buffer[5] = (uint8_t) (dataFwd >> 8);
    //
    // buffer[6] = (uint8_t) dataSpd;
    // buffer[7] = (uint8_t) (dataSpd >> 8);
    //
    // buffer[8] = (uint8_t) dataVlt;
    // buffer[9] = (uint8_t) (dataVlt >> 8);
    //
    // buffer[10] = (uint8_t) dataThr;
    // buffer[11] = (uint8_t) (dataThr >> 8);
    //
    // buffer[12] = (uint8_t) dataPow;
    // buffer[13] = (uint8_t) (dataPow >> 8);
    //
    // buffer[14] = (uint8_t) dataCur;
    // buffer[15] = (uint8_t) (dataCur >> 8);
    //
    // buffer[16] = (uint8_t) dataTmp;
    // buffer[17] = (uint8_t) (dataTmp >> 8);

    // Execution will block until buffer has been sent completely
    // unless interrupted by Timer1 or speedInterupt
    SPISlave.transferString(buffer, BUFFERSIZE);
}

//---------------------------------- TIMER ISR

void timerIsr()
{
    dataTmp = analogRead(inTmpPin); // temperature data
    dataCur = analogRead(inCurPin); // current data
    dataPow = analogRead(inPowPin); // power signal data
    dataThr = analogRead(inThrPin); // throttle data
    dataFwd = digitalRead(inFwdPin)*100; // forward signal data
    dataRev = digitalRead(inRevPin)*100; // reverse signal data
    dataVlt = analogRead(inVltPin); // voltage data
}

//---------------------------------- SPEED ISR

void speedIsr()
{
    // speed data
    dataSpd++;
}

//requires 'out' to be pointing to at least 2 contiguous bytes
inline void uint16to8Converter(uint8_t *out, uint16_t in)
{
    *out = (uint8_t) in;
    *(out+1) = (uint8_t) (in >> 8);
}
