/***********************************************************************************************

   LICENSE
   Copyright (C) 2018 openQCM
   This program is free software: you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.
   You should have received a copy of the GNU General Public License
   along with this program.  If not, see http://www.gnu.org/licenses/gpl-3.0.txt
  --------------------------------------------------------------------------------
   OPENQCM NEXT PM - Quartz Crystal Microbalance for Particulate Matter monitoring
   with dissipation monitoring, temperature control, pump and air flow measurement
   openQCM is the unique opensource quartz crystal microbalance
   http://openqcm.com/

   ELECTRONICS
     - board and firmware designed for TEENSY 4.0 dev board https://www.pjrc.com/store/teensy40.html
     - DDS/DAC Synthesizer AD9851
     - phase comparator AD8302
     - I2C digital potentiometer AD5251+
     - MTD415T - TEC driver Thorlabs
     info      https://www.thorlabs.com/thorproduct.cfm?partnumber=MTD415T
     datasheet https://www.thorlabs.com/drawings/b4052d6b3d0a3c51-05F7919E-E07A-065E-046B0AD9948EAEB5/MTD415T-DataSheet.pdf
     - Transistor to turn on the TEC THORLAB MTD415T: PIN 10 = HIGH
     - Teensy pin control to enable/disable TEC THORLAB MTD415T: PIN 11 = LOW
     - MCP9808 temperature sensor for ambient temperature monitoring
     - FAN added a cooling fan to optimize the termal control
     
     NEW in VER 0.2.0 - PM SENSOR VERSION:
     - SparkFun Qwiic Motor Driver (I2C: 0x5D) for pump control
     - FS3000 flow sensor (I2C: 0x28) for air velocity measurement
     - Gravimetric impactor functionality for atmospheric particulate monitoring

   HISTORY CHANGES
   --------------------------------------------------------------------------------
   version     0.2.0
   version tag // VER 0.2.0
   date        2025-01-20 
   
   NEW FEATURES FOR PM (Particulate Matter) MONITORING:
   - Added pump control via SparkFun Qwiic Motor Driver (I2C address 0x5D)
   - Added air flow measurement via FS3000 sensor (I2C address 0x28)
   - New serial commands for pump and flow control
   
   PUMP CONTROL COMMANDS:
   COMMAND     RESPONSE/ACTION
   B0          Stop pump
   B1          Start pump at speed 80 (~30%)
   B2          Start pump at speed 130 (~50%)
   B3          Start pump at speed 190 (~75%)
   B4          Start pump at speed 255 (100%)
   Bxxx        Set pump speed to xxx (30-255)
   B?          Returns current pump speed (0-255)
   
   FLOW SENSOR COMMANDS:
   COMMAND     RESPONSE
   G?          Returns current flow in m/s (float)
   Gr          Returns raw sensor value (0-3686)
   Gm          Returns average flow in m/s during pump operation
   Gs          Returns complete status: speed;flow;avg_flow;samples
   G0          Reset flow statistics
   
   MODIFIED SWEEP OUTPUT FORMAT (backward compatible):
   amplitude_0;phase_0
   amplitude_1;phase_1
   ...
   amplitude_n;phase_n
   temperature;status_control;error_register_bit;flow_m_s;pump_speed;termination_char
   
   Note: If pump/flow hardware not detected, flow_m_s and pump_speed will be 0
   
   --------------------------------------------------------------------------------
   version     0.1.5
   version tag // VER 0.1.5
   date        2022-11-14 
   - Change the way the MCP9808 error status is read by using error register 
   - Read MCP9808 TEC controller error register
   - Improved MTD415T startup, insert a delay and serial flush in setup()
   - Add error_register_bit to sweep output buffer
   - Turn the Fan ON if only if the temperature control is active 

   --------------------------------------------------------------------------------
   version 0.1.4
   - Change the sweep frequency step to 1 Hz
   - change the average to 500 samples
   - Read firmware version with 'F' command
   - Read TEC controller status with 'A?' command
   
   --------------------------------------------------------------------------------
   version  0.2.0
   date     2025-01-20
   author   marco - openQCM team / Novaetech S.r.l.
   --------------------------------------------------------------------------------

 ***********************************************************************************************/

/************************** LIBRARIES **************************/
#include <Wire.h>
// libraries included in /src folder
#include "src/Adafruit_MCP9808.h"
#include "src/ADC/ADC.h"
#include "src/ADC/ADC_util.h"

// VER 0.2.0 - PM sensor libraries
// These libraries need to be installed or included in /src folder
#include "SCMD.h"
#include "SCMD_config.h"
#include <SparkFun_FS3000_Arduino_Library.h>

/*************************** DEFINE ***************************/
// potentiometer AD5252 I2C address is 0x2C(44)
#define ADDRESS 0x2C
// potentiometer AD5252 default value
// VER 0.1.4 low pot value for compatibility with new electronic amplifier
#define POT_VALUE 180 //240
// reference clock
#define REFCLK 125000000

#define AVERAGING   1
#define RESOLUTION 12

// VER 0.1.5 define wait time for MTD415T startup
// wait for a second before MTD415T serial flush in setup
#define MTD415T_TIME_SEC_STARTUP  1000

// VER 0.2.0 define firmware version
#define FW_VERSION "0.2.2-PM"

// VER 0.2.0 - PUMP CONFIGURATION
#define PUMP_CHANNEL 0              // Motor driver channel A
#define PUMP_SPEED_MIN 30           // Minimum pump speed
#define PUMP_SPEED_MAX 255          // Maximum pump speed
#define MOTOR_DRIVER_ADDR 0x5D      // I2C address of motor driver

// VER 0.2.0 - FLOW SENSOR CONFIGURATION
#define FLOW_SENSOR_ADDR 0x28       // I2C address of FS3000
#define FLOW_UPDATE_INTERVAL 500    // Flow update interval (ms)


/*************************** VARIABLE DECLARATION ***************************/

// VER 0.1.4 change reduce the number of samples for averaging ADC
int AVERAGE_SAMPLE = 500;

// RGB LED
int RGB_RED_PIN   = 5;
int RGB_GREEN_PIN = 6;
int RGB_BLUE_PIN  = 7;

// current input frequency
long freq = 0;
// DDS Synthesizer AD9851 pin function for TEENSY 4.0
int WCLK = 3;
int DATA = 4;
int FQ_UD = 2;
// frequency tuning word
long FTW;
float temp_FTW; // temporary variable

// T40 pin ADC
const int readPin = A9;
const int readPin2 = A3;
// init  adc object
ADC *adc = new ADC();

// TODO VER 0.1.3
// wait for a while before change the frequency of the input signal
// to prevent distortion in the response signal
// ADC init variabl
boolean WAIT = false;
// ADC waiting delay microseconds
int WAIT_DELAY_US = 200;
// ADC averaging
boolean AVERAGING_BOOL = true;

// VER 0.1.4 change - reduce the number of samples for smoothing ADC
// init number of averaging
// VER 0.1.3 doubled number of samples for smoothing ADC
// int AVERAGE_SAMPLE = 4096; // TODO VER 0.1.3 increase to 8192

// teensy ADC averaging init
// int ADC_RESOLUTION = 13;

// init sweep param
long freq_start;
long freq_stop;
long freq_step;

// init output ad8302 measurement (cast to double)
double measure_phase = 0;
double measure_mag = 0;

// MTD415T variable declaration
// -----------------------------
// Status Signal input
// HIGH = Temperature within defined temperature window
// LOW  = Temperature outside programmed temperature window or an error occurred
int STATUS_TEC = 9;
// Transistor to turn on the TEC THORLAB MTD415T: PIN 10 = HIGH
int CTRL_SWITCH_PIN = 10;
// Teensy pin control to enable/disable TEC THORLAB MTD415T: PIN 11 = LOW
int ENABLE_PIN = 11;
// set boolean temperature control switch OFF
boolean CTRL_SWITCH = false;

// TODO embedded light on T40 delete ?
const int ledPin = 13;

// MCP9808 temperature sensor
// -----------------------------
// Create the MCP9808 temperature sensor object
Adafruit_MCP9808 tempsensor = Adafruit_MCP9808();
// init temperature variable
float temperature = 0;

// TODO DELETE
int _TIME = 100;

// VER 0.1.4
// variable current status control
// _STATUS_CONTROL = -1   > TEC controller is active and STATUS pin is low and current is null
// _STATUS_CONTROL =  0   > TEC controller is not active
// _STATUS_CONTROL =  1   > TEC controller is active and STATUS pin is low and current is not null
// _STATUS_CONTROL =  2   > TEC controller is active and STATUS pin is HIGH
int _STATUS_CONTROL = 0;

// VER 0.1.4
// FAN control pin
// T40 pin  8 = voltage control (output)
// T40 pin 12 = status control  (input)
int FAN_PIN = 8; // 12

// ===========================================================================
// VER 0.2.0 - PM SENSOR VARIABLES
// ===========================================================================

// Motor driver object for pump control
SCMD motorDriver;
// Flow sensor object
FS3000 flowSensor;

// Pump state variables
int pumpSpeed = 0;                  // Current pump speed (0-255)
boolean pumpActive = false;         // Pump status
unsigned long pumpStartTime = 0;    // Pump start timestamp
unsigned long pumpActiveTime = 0;   // Total pump active time

// Flow measurement variables
float flowCurrent = 0.0;            // Current flow in m/s
float flowAverage = 0.0;            // Average flow during pump operation
float flowMax = 0.0;                // Maximum flow recorded
float flowMin = 999.0;              // Minimum flow recorded
int flowSampleCount = 0;            // Number of flow samples
float flowSampleSum = 0.0;          // Sum of flow samples for averaging
unsigned long lastFlowUpdate = 0;   // Last flow update timestamp

// Hardware detection flags
boolean motorDriverOK = false;      // Motor driver detected and initialized
boolean flowSensorOK = false;       // Flow sensor detected and initialized


/*************************** FUNCTION ***************************/

/* AD9851 set frequency fucntion */
void SetFreq(long frequency)
{
  // set to 125 MHz internal clock
  temp_FTW = (frequency * pow(2, 32)) / REFCLK;
  FTW = long (temp_FTW);

  long pointer = 1;
  int pointer2 = 0b10000000;
  int lastByte = 0b10000000;

  /* 32 bit dds tuning word frequency instructions */
  for (int i = 0; i < 32; i++)
  {
    if ((FTW & pointer) > 0) digitalWrite(DATA, HIGH);
    else digitalWrite(DATA, LOW);
    digitalWrite(WCLK, HIGH);
    digitalWrite(WCLK, LOW);
    pointer = pointer << 1;
  }

  /* 8 bit dds phase and x6 multiplier refclock*/
  for (int i = 0; i < 8; i++)
  {
    //if ((lastByte & pointer2) > 0) digitalWrite(DATA, HIGH);
    //else digitalWrite(DATA, LOW);
    digitalWrite(DATA, LOW);
    digitalWrite(WCLK, HIGH);
    digitalWrite(WCLK, LOW);
    pointer2 = pointer2 >> 1;
  }

  digitalWrite(FQ_UD, HIGH);
  digitalWrite(FQ_UD, LOW);

  //FTW = 0;
}

// TODO DELETE BLINK
void my_blink() {
  digitalWrite(ledPin, HIGH);   // set the LED on
  delay(100);                  // wait for a second
  digitalWrite(ledPin, LOW);    // set the LED off
  delay(100);
}

// RGB LED function
// RGB light value 0,..., 255
void RGB_color(int red_light_value, int green_light_value, int blue_light_value)
{
  analogWrite(RGB_RED_PIN, 255 - red_light_value);
  analogWrite(RGB_GREEN_PIN, 255 - green_light_value);
  analogWrite(RGB_BLUE_PIN, 255 - blue_light_value);
}

// flush serial 1
void Serial_1_Flush() {
  while (Serial1.available() > 0) {
    String flush_buffer = Serial1.readStringUntil('\n');
    // DEBUG
    // Serial.print ("DEBUG: serial1 flush read buffer: ");
    // Serial.println(flush_buffer);
  }
}

// ===========================================================================
// VER 0.2.0 - PM SENSOR FUNCTIONS
// ===========================================================================

/**
 * Initialize motor driver for pump control
 * Returns true if successful, false otherwise
 */
boolean initMotorDriver() {
  motorDriver.settings.commInterface = I2C_MODE;
  motorDriver.settings.I2CAddress = MOTOR_DRIVER_ADDR;
  
  uint8_t attempts = 0;
  while (motorDriver.begin() != 0xA9 && attempts < 5) {
    delay(200);
    attempts++;
  }
  
  if (attempts >= 5) {
    return false;
  }
  
  // Wait for driver to be ready
  while (motorDriver.ready() == false);
  while (motorDriver.busy());
  motorDriver.enable();
  delay(100);
  
  return true;
}

/**
 * Initialize flow sensor
 * Returns true if successful, false otherwise
 */
boolean initFlowSensor() {
  if (flowSensor.begin() == false) {
    return false;
  }
  
  // Set range for FS3000-1005 (7.23 m/s max)
  flowSensor.setRange(AIRFLOW_RANGE_7_MPS);
  // For FS3000-1015 (15 m/s max), use:
  // flowSensor.setRange(AIRFLOW_RANGE_15_MPS);
  
  return true;
}

/**
 * Set pump speed
 * @param speed: 0 to stop, PUMP_SPEED_MIN to PUMP_SPEED_MAX for operation
 */
void setPumpSpeed(int speed) {
  if (!motorDriverOK) {
    return;
  }
  
  if (speed == 0) {
    // Stop pump with gradual deceleration
    if (pumpActive && pumpSpeed > 0) {
      for (int v = pumpSpeed; v >= 0; v -= 5) {
        motorDriver.setDrive(PUMP_CHANNEL, 0, v);
        delay(20);
      }
    }
    motorDriver.setDrive(PUMP_CHANNEL, 0, 0);
    pumpSpeed = 0;
    pumpActive = false;
    pumpActiveTime = 0;
    return;
  }
  
  // Clamp speed to valid range
  if (speed < PUMP_SPEED_MIN) {
    speed = PUMP_SPEED_MIN;
  }
  if (speed > PUMP_SPEED_MAX) {
    speed = PUMP_SPEED_MAX;
  }
  
  // Start pump or change speed
  boolean wasInactive = !pumpActive;
  
  motorDriver.setDrive(PUMP_CHANNEL, 0, speed);
  pumpSpeed = speed;
  pumpActive = true;
  
  // If just started, initialize timing and reset stats
  if (wasInactive) {
    pumpStartTime = millis();
    resetFlowStats();
  }
}

/**
 * Update flow measurement from sensor
 */
void updateFlowReading() {
  if (!flowSensorOK) {
    flowCurrent = 0.0;
    return;
  }
  
  flowCurrent = flowSensor.readMetersPerSecond();
  lastFlowUpdate = millis();
  
  // Update statistics only when pump is active
  if (pumpActive) {
    flowSampleCount++;
    flowSampleSum += flowCurrent;
    flowAverage = flowSampleSum / flowSampleCount;
    
    if (flowCurrent > flowMax) flowMax = flowCurrent;
    if (flowCurrent < flowMin && flowCurrent > 0) flowMin = flowCurrent;
  }
}

/**
 * Reset flow statistics
 */
void resetFlowStats() {
  flowMax = 0.0;
  flowMin = 999.0;
  flowSampleCount = 0;
  flowSampleSum = 0.0;
  flowAverage = 0.0;
}

/**
 * Get raw flow sensor value
 */
int getFlowRaw() {
  if (!flowSensorOK) {
    return 0;
  }
  return flowSensor.readRaw();
}

/**
 * Update pump active time
 */
void updatePumpTime() {
  if (pumpActive) {
    pumpActiveTime = millis() - pumpStartTime;
  }
}


/*************************** SETUP ***************************/
void setup()
{
  // Initialise I2C communication as Master
  Wire.begin();
  // Initialise serial communication, set baud rate = 9600
  Serial.begin(115200);
  // DEBUG_0.1.1a
  Serial.setTimeout(250);

  // set potentiometer value
  // Start I2C transmission
  Wire.beginTransmission(ADDRESS);
  // Send instruction for POT channel-0
  Wire.write(0x01);
  // Input resistance value, 0x80(128)
  Wire.write(POT_VALUE);
  // Stop I2C transmission
  Wire.endTransmission();

  // AD9851 set pin mode
  pinMode(WCLK, OUTPUT);
  pinMode(DATA, OUTPUT);
  pinMode(FQ_UD, OUTPUT);

  // AD9851 enter serial mode
  digitalWrite(WCLK, HIGH);
  digitalWrite(WCLK, LOW);
  digitalWrite(FQ_UD, HIGH);
  digitalWrite(FQ_UD, LOW);

  // ----------------------------------------------------------
  // TEENSY 4.0 ADC SETTING
  // ----------------------------------------------------------

  // T40 init ADC pin
  pinMode(readPin, INPUT);
  pinMode(readPin2, INPUT);

  // ADC0 setting
  adc->setAveraging(AVERAGING); // set number of averages
  adc->setResolution(RESOLUTION); // set bits of resolution
  // it can be any of the ADC_CONVERSION_SPEED enum: VERY_LOW_SPEED, LOW_SPEED, MED_SPEED, HIGH_SPEED_16BITS, HIGH_SPEED or VERY_HIGH_SPEED
  // see the documentation for more information
  // additionally the conversion speed can also be ADACK_2_4, ADACK_4_0, ADACK_5_2 and ADACK_6_2,
  // where the numbers are the frequency of the ADC clock in MHz and are independent on the bus speed.
  adc->setConversionSpeed(ADC_CONVERSION_SPEED::HIGH_SPEED); // VER 0.1.4 change the conversion speed to HIGH_SPEED
  // it can be any of the ADC_MED_SPEED enum: VERY_LOW_SPEED, LOW_SPEED, MED_SPEED, HIGH_SPEED or VERY_HIGH_SPEED
  adc->setSamplingSpeed(ADC_SAMPLING_SPEED::HIGH_SPEED); // VER 0.1.4 change the conversion speed to HIGH_SPEED

  // ADC1 setting
  adc->setAveraging(AVERAGING, ADC_1); // set number of averages
  adc->setResolution(RESOLUTION, ADC_1); // set bits of resolution
  adc->setConversionSpeed(ADC_CONVERSION_SPEED::HIGH_SPEED, ADC_1); // change the conversion speed to HIGH_SPEED
  adc->setSamplingSpeed(ADC_SAMPLING_SPEED::HIGH_SPEED, ADC_1); // change the sampling speed to HIGH_SPEED

  // start adc read synchronized continuous
  adc->startSynchronizedContinuous(readPin, readPin2);

  // VER 0.1.5 TODO delete MCP9808 temperature sensor init
  // begin MCP9808 sensor temperature sensor
  tempsensor.begin();

  // ----------------------------------------------------------
  // MTD415T TEC CONTROLLER SETUP
  // ----------------------------------------------------------

  // init status signal pin
  pinMode(STATUS_TEC, INPUT);
  // init control switch power on/off
  pinMode(CTRL_SWITCH_PIN, OUTPUT);
  // init enable pin
  pinMode(ENABLE_PIN, OUTPUT);
  // Turn ON MTD415T TEC by default
  digitalWrite(CTRL_SWITCH_PIN, HIGH);
  // Disable temperature control TEC by default (LOW active)
  digitalWrite(ENABLE_PIN, HIGH);

  // begin T40 UART Serial1
  Serial1.begin(115200);
  // DEBUG_0.1.1a
  Serial1.setTimeout(250);

  // VER 0.1.5
  // wait for MTD415T at startup
  delay(MTD415T_TIME_SEC_STARTUP);
  // flush serial 1 at startup, clear the serial1 at startup
  Serial_1_Flush();

  // RGB LED SETUP
  pinMode(RGB_RED_PIN, OUTPUT);
  pinMode(RGB_GREEN_PIN, OUTPUT);
  pinMode(RGB_BLUE_PIN, OUTPUT);

  // shine on you crazy diamond, exposed to the light openqcm (0, 142, 192)
  RGB_color(255, 255, 255);

  // VER 0.1.4
  // FAN pwm control init
  pinMode(FAN_PIN, OUTPUT);

  // T40 PWM and Tone code info https://www.pjrc.com/teensy/td_pulse.html
  // setting PWM frequency output
  // analogWriteFrequency(FAN_PIN, 25000);
  // setting PWM resolution analogWrite value 0 to 4095, or 4096 for high
  // analogWriteResolution(12);

  // setting PWM output ( tested: minimum 40 to maximum 255 )
  // VER 0.1.5 turn off the fan if the temperature control is disabled
  analogWrite(FAN_PIN, 0);

  // ----------------------------------------------------------
  // VER 0.2.0 - PM SENSOR INITIALIZATION
  // ----------------------------------------------------------
  
  // Initialize motor driver for pump
  motorDriverOK = initMotorDriver();
  
  // Initialize flow sensor
  flowSensorOK = initFlowSensor();
  
  // Small delay for sensor stabilization
  delay(100);
}

/*************************** GLOBAL VARIABLE INIT ***************************/
int message = 0;
// boolean debug = true;
long pre_time = 0;
long last_time = 0;

int byteAtPort = 0;

// MTD415T string test init
// init first setting if temperature module
boolean TEMPERATURE_BOOLEAN = true;
// init read string
String MTD415T_READ_STRING = "";

// VER 0.1.5 init read string error register
String MTD415T_READ_STRING_ERROR = "";

// PROGRAM
String TEMPERATURE_SET = "T20000\n";
String TEMPERATURE_GET = "Te?\n";
String P_SET = "P1000\n";
String P_GET = "";

String TEMPERATURE_SET_READ = "T?";
String TEMPERATURE_READ = "Te?";

String message_str = "";
String readStr = "";

// T40 init ADC
double value = 0;
double value2 = 0;
long time_start = 0;

ADC::Sync_result result;

unsigned long MAIN_COUNTER = 0;

// TODO delete temporary debug var
boolean DBG_TEMP = false;
String my_string = "";
String read_message_TEMP = "";

/*************************** LOOP ***************************/
void loop()
{
  // ----------------------------------------------------------
  // READ enable pin and set the control status boolean
  // ----------------------------------------------------------
  int read_enable_pin = 0;
  read_enable_pin = digitalRead(ENABLE_PIN);
  // LOW = enable temperarture control
  if (read_enable_pin == 0) {
    // set boolean
    CTRL_SWITCH = true;
  }
  // HIGH = disable temperature control
  if (read_enable_pin == 1) {
    // set boolean
    CTRL_SWITCH = false;
  }

  // ----------------------------------------------------------
  // READ the MTD415T STATUS PIN
  // only if the temperature control is active and the sweep is moving
  // ----------------------------------------------------------
  // set read status tec variable
  int read_status_tec = 0;
  read_status_tec = digitalRead(STATUS_TEC);

  // ----------------------------------------------------------
  // TEMPERATURE CONTROL ACTIVE CHECK and ROUTINE
  // ----------------------------------------------------------
  if (CTRL_SWITCH == true) {
    // HIGH status = OK, temperature setpoint ok
    if (read_status_tec == 1) {
      // Status Signal High = temperature within defined temperature window
      RGB_color(0, 142, 192);
      _STATUS_CONTROL = 2;

      // VER 0.1.5 send temperature amd register status request 
      // also in status: temperatue control active, temperature setpoint ok 
      
      // SEND TEMPERATURE COMMAND MTD415T
      // -----------------------------------------------------
      Serial1.println(TEMPERATURE_GET);
      delay(10);
      /////////////////////////////////////////////////////////////////////////////
      // READ STRING at UART1 SERIAL
      if (Serial1.available()) {
        // read message from MTD415T
        MTD415T_READ_STRING = Serial1.readStringUntil('\n');
        // DEBUG
        // Serial.print("DEBUG MTD415T_READ_STRING "); Serial.println(MTD415T_READ_STRING);
      }
      /////////////////////////////////////////////////////////////////////////////

      // SEND ERROR CONTROL COMMAND MTD415T
      // -----------------------------------------------------
      // TODO check the way the message is read from MTD415T
      // as for temperature above
      Serial_1_Flush();
      Serial1.println("E?");
      delay(10);
      /////////////////////////////////////////////////////////////////////////////
      // READ STRING at UART1 SERIAL
      // read message from MTD415T
      // TODO check if the string is null before
      MTD415T_READ_STRING_ERROR = Serial1.readStringUntil('\n');
      // DEBUG
      // Serial.print("DEBUG MTD415T_READ_STRING_ERROR "); Serial.println(MTD415T_READ_STRING_ERROR);
      /////////////////////////////////////////////////////////////////////////////
      delay(10);

    }
    // LOW status = Temperature outside programmed temperature window or an error occurred
    else if (read_status_tec == 0) {
      // clear the serial
      Serial1.clear();
      delay(10);
      // check the current
      Serial1.println("A?");
      int actual_TEC_current = 0;
      // Serial1.clear();
      delay(10);
      // read the actual temperature current
      if (Serial1.available()) {
        actual_TEC_current = Serial1.readStringUntil('\n').toInt();
        // DEBUG
        // Serial.print("DEBUG ACTUAL TEC CURRENT "); Serial.println(actual_TEC_current );
      }
      delay(10);
      // clear the serial
      Serial1.clear();

      // SEND TEMPERATURE COMMAND MTD415T
      // -----------------------------------------------------
      Serial1.println(TEMPERATURE_GET);
      delay(10);
      /////////////////////////////////////////////////////////////////////////////
      // READ STRING at UART1 SERIAL
      if (Serial1.available()) {
        // read message from MTD415T
        MTD415T_READ_STRING = Serial1.readStringUntil('\n');
        // DEBUG
        // Serial.print("DEBUG MTD415T_READ_STRING "); Serial.println(MTD415T_READ_STRING);
      }
      /////////////////////////////////////////////////////////////////////////////

      // SEND ERROR CONTROL COMMAND MTD415T
      // -----------------------------------------------------
      // TODO check the way the message is read from MTD415T
      // as for temperature above
      Serial_1_Flush();
      // send error
      Serial1.println("E?");
      delay(10);
      /////////////////////////////////////////////////////////////////////////////
      // READ STRING at UART1 SERIAL
      // read message from MTD415T
      // TODO check if the string is null before
      MTD415T_READ_STRING_ERROR = Serial1.readStringUntil('\n');
      // DEBUG
      // Serial.print("DEBUG MTD415T_READ_STRING_ERROR "); Serial.println(MTD415T_READ_STRING_ERROR);
      /////////////////////////////////////////////////////////////////////////////
      delay(10);

      // -----------------------------------------------------
      // TODO ask for the temperature again ?
      // -----------------------------------------------------

      // -----------------------------------------------
      // CHECK THE STATUS OF THE TEC MODULE
      // -----------------------------------------------

      // if the error message is zero TEC status is OK
      if (MTD415T_READ_STRING_ERROR.toInt() == 0) {
        // You don't have to put on the red light
        RGB_color(255, 125, 10);
        _STATUS_CONTROL = 1;
      }
      // if the error message is not zero the TEC status is ERROR
      else if (MTD415T_READ_STRING_ERROR.toInt() != 0) {
        // You HAVE to put on the red light
        RGB_color(255, 0, 0);
        // status contrl error
        _STATUS_CONTROL = -1;
      }
    }
  }

  // VER 0.1.5
  // ----------------------------------------------------------
  // TEMPERATURE CONTROL NOT ACTIVE CHECK THE ERROR REGISTER
  // ----------------------------------------------------------
  else if (CTRL_SWITCH == false) {

    // SEND TEMPERATURE COMMAND MTD415T
    // -----------------------------------------------------
    Serial1.println(TEMPERATURE_GET);
    delay(10);
    /////////////////////////////////////////////////////////////////////////////
    // READ STRING at UART1 SERIAL
    if (Serial1.available()) {
      // read message from MTD415T
      MTD415T_READ_STRING = Serial1.readStringUntil('\n');
      // DEBUG
      // Serial.print("DEBUG MTD415T_READ_STRING "); Serial.println(MTD415T_READ_STRING);
    }
    /////////////////////////////////////////////////////////////////////////////

    // SEND ERROR CONTROL COMMAND MTD415T
    // -----------------------------------------------------
    // TODO check the way the message is read from MTD415T
    // as for temperature above
    Serial_1_Flush();
    Serial1.println("E?");
    delay(10);
    /////////////////////////////////////////////////////////////////////////////
    // READ STRING at UART1 SERIAL
    // read message from MTD415T
    // TODO check if the string is null before
    MTD415T_READ_STRING_ERROR = Serial1.readStringUntil('\n');
    // DEBUG
    // Serial.print("DEBUG MTD415T_READ_STRING_ERROR "); Serial.println(MTD415T_READ_STRING_ERROR);
    /////////////////////////////////////////////////////////////////////////////
    delay(10);
  }

  // ----------------------------------------------------------
  // VER 0.2.0 - UPDATE PUMP AND FLOW STATUS
  // ----------------------------------------------------------
  // Update pump active time
  updatePumpTime();
  
  // Periodically update flow reading (non-blocking)
  if (millis() - lastFlowUpdate > FLOW_UPDATE_INTERVAL) {
    updateFlowReading();
  }

  // ----------------------------------------------
  // READ BYTE at SERIAL PORT
  // ----------------------------------------------
  if ( (byteAtPort = Serial.available()) > 0 ) {

    // TODO
    // reset the case switch variable
    // message = 0;

    // read string message at serial port
    message_str = Serial.readStringUntil('\n');
    // convert string to byte artay
    char buf[byteAtPort];
    message_str.toCharArray(buf, sizeof(buf));

    // DECODE MESSAGE at SERIAL PORT check first byte
    // list of char decoding message
    // 'T', 'C', 'P', 'I', 'D', 'X', 'A', 'L', 'E'
    // VER 0.2.0: Added 'B' (Blower/pump) and 'G' (Gas flow)
    // ----------------------------------------------

    // TEMPERATURE SETTING
    // ----------------------------------------------
    // VER 0.2.1 - Fixed: removed debug strings, return only numeric values
    if (buf[0] == 'T') {
      // send message to Peltier Module
      Serial1.println(message_str);
      delay(10);  // Wait for MTD415L response
      // set temperature query (T?)
      if (message_str == TEMPERATURE_SET_READ) {
        // Return only the numeric value (mK)
        Serial.println(Serial1.readStringUntil('\n'));
      }
      // read actual temperature (Te?)
      else if (message_str == TEMPERATURE_READ) {
        // Return only the numeric value (mK)
        Serial.println(Serial1.readStringUntil('\n'));
      }
      else {
        // Setting temperature (Txxxxx) - no response needed
        Serial1.readStringUntil('\n');
      }
    }

    // PID SETTING
    // ----------------------------------------------
    // cycling time
    else if ( buf[0] == 'C' ) {
      // send message to Peltier Module
      Serial1.println(message_str);
      // read message
      read_message_TEMP = Serial1.readStringUntil('\n');
      if (DBG_TEMP) Serial.println(read_message_TEMP );
      if ( buf[1] == '?') Serial.println(read_message_TEMP );
    }
    // P Share
    else if ( buf[0] == 'P' ) {
      // send message to Peltier Module
      Serial1.println(message_str);
      // read message
      read_message_TEMP = Serial1.readStringUntil('\n');
      if (DBG_TEMP) Serial.println(read_message_TEMP );
      if ( buf[1] == '?') Serial.println(read_message_TEMP );
    }
    // I Share
    else if ( buf[0] == 'I' ) {
      // send message to Peltier Module
      Serial1.println(message_str);
      // read message
      read_message_TEMP = Serial1.readStringUntil('\n');
      if (DBG_TEMP) Serial.println(read_message_TEMP );
      if ( buf[1] == '?') Serial.println(read_message_TEMP );
    }
    // D Share
    else if ( buf[0]  == 'D' ) {
      // send message to Peltier Module
      Serial1.println(message_str);
      // read message
      read_message_TEMP = Serial1.readStringUntil('\n');
      if (DBG_TEMP) Serial.println(read_message_TEMP );
      if ( buf[1] == '?') Serial.println(read_message_TEMP );
    }

    // TURN TEC ON/OFF command
    // TURN ON
    else if (buf[0]  == 'X' ) {
      // Serial.println("TURN THE TEC ...");
      if ( buf[1] == '1') {
        // ENABLE  the TEC default (LOW active)
        digitalWrite(ENABLE_PIN, LOW);
        // set boolean control true
        CTRL_SWITCH = true;
        // change led color
        RGB_color(0, 142, 192);
        // VER 0.1.5 turn Fan ON
        analogWrite(FAN_PIN, 255);

      }
      // TURN OFF
      if ( buf[1] == '0') {
        // DISABLE the TEC default (LOW active)
        digitalWrite(ENABLE_PIN, HIGH);
        // set boolean control false
        CTRL_SWITCH = false;
        // VER 0.1.5 turn Fan OFF
        analogWrite(FAN_PIN, 0);

        // not in measure mode
        if (message == 0) {
          // turn white, inactive
          RGB_color(255, 255, 255);
        }
        // measure mode
        else if (message == 1) {
          // turn yellow
          RGB_color(255, 255, 0);
        }
      }
    }

    // VER 0.1.4
    // Reads the actual TEC current in mA
    else if (buf[0]  == 'A' ) {
      // long _time_pre = micros();
      Serial1.println("A?");
      delay(10);
      // echo write what you read
      Serial.println(Serial1.readStringUntil('\n'));
      // Serial.println ((micros() - _time_pre));
    }

    // Set the TEC current limit in mA (value range x: 200 to 1500 [mA])
    else if (buf[0]  == 'L' ) {
      // send message to Peltier Module
      Serial1.println(message_str);
      // read message
      read_message_TEMP = Serial1.readStringUntil('\n');
    }

    // VER 0.1.4
    // READ the current firmware version
    // character 'F'
    else if (buf[0] == 'F') {
      Serial.println(FW_VERSION);
    }

    // VER 0.1.5
    // Reads the error register
    else if (buf[0]  == 'E' ) {
      // flush serial1
      Serial_1_Flush();
      // send command
      Serial1.println("E?");
      delay(10);
      // echo write what you read
      Serial.println(Serial1.readStringUntil('\n'));
    }

    // ===========================================================================
    // VER 0.2.0 - PUMP CONTROL COMMANDS (character 'B' for Blower)
    // ===========================================================================
    else if (buf[0] == 'B') {
      // B? - Read current pump speed
      if (buf[1] == '?') {
        Serial.println(pumpSpeed);
      }
      // B0 - Stop pump
      else if (buf[1] == '0' && byteAtPort <= 3) {
        setPumpSpeed(0);
        Serial.println("0");  // Confirm stopped
      }
      // B1 - Preset speed 1 (~30%)
      else if (buf[1] == '1' && byteAtPort <= 3) {
        setPumpSpeed(80);
        Serial.println(pumpSpeed);
      }
      // B2 - Preset speed 2 (~50%)
      else if (buf[1] == '2' && byteAtPort <= 3) {
        setPumpSpeed(130);
        Serial.println(pumpSpeed);
      }
      // B3 - Preset speed 3 (~75%)
      else if (buf[1] == '3' && byteAtPort <= 3) {
        setPumpSpeed(190);
        Serial.println(pumpSpeed);
      }
      // B4 - Preset speed 4 (100%)
      else if (buf[1] == '4' && byteAtPort <= 3) {
        setPumpSpeed(255);
        Serial.println(pumpSpeed);
      }
      // Bxxx - Custom speed (30-255)
      else {
        // Parse numeric value after 'B'
        String speedStr = message_str.substring(1);
        int customSpeed = speedStr.toInt();
        if (customSpeed >= 0 && customSpeed <= 255) {
          setPumpSpeed(customSpeed);
          Serial.println(pumpSpeed);
        }
        else {
          Serial.println("ERR");  // Invalid speed
        }
      }
    }

    // ===========================================================================
    // VER 0.2.0 - FLOW SENSOR COMMANDS (character 'G' for Gas flow)
    // ===========================================================================
    else if (buf[0] == 'G') {
      // G? - Read current flow in m/s
      if (buf[1] == '?') {
        updateFlowReading();
        Serial.println(flowCurrent, 3);  // 3 decimal places
      }
      // Gr - Read raw sensor value
      else if (buf[1] == 'r' || buf[1] == 'R') {
        Serial.println(getFlowRaw());
      }
      // Gm - Read average flow
      else if (buf[1] == 'm' || buf[1] == 'M') {
        Serial.println(flowAverage, 3);
      }
      // Gs - Read complete status: speed;flow;avg_flow;samples;min;max;time_ms
      else if (buf[1] == 's' || buf[1] == 'S') {
        updateFlowReading();
        Serial.print(pumpSpeed);
        Serial.print(";");
        Serial.print(flowCurrent, 3);
        Serial.print(";");
        Serial.print(flowAverage, 3);
        Serial.print(";");
        Serial.print(flowSampleCount);
        Serial.print(";");
        Serial.print(flowMin < 999.0 ? flowMin : 0.0, 3);
        Serial.print(";");
        Serial.print(flowMax, 3);
        Serial.print(";");
        Serial.println(pumpActiveTime);
      }
      // G0 - Reset flow statistics
      else if (buf[1] == '0') {
        resetFlowStats();
        Serial.println("OK");
      }
      // Gh - Hardware status: motorOK;flowOK
      else if (buf[1] == 'h' || buf[1] == 'H') {
        Serial.print(motorDriverOK ? "1" : "0");
        Serial.print(";");
        Serial.println(flowSensorOK ? "1" : "0");
      }
    }

    // GET SWEEP FREQUENCY PARAMETERS (sweep has ';', MTD415T commands do not)
    // ----------------------------------------------
    else if (message_str.indexOf(';') >= 0) {
      // init
      char *p = buf;
      char *str;
      int nn = 0;

      // DECODE MESSAGE
      while ((str = strtok_r(p, ";", &p)) != NULL) {
        // frequency start
        if (nn == 0) {
          freq_start = atol(str);
          nn = 1;
        }
        // frequency stop
        else if (nn == 1) {
          freq_stop = atol(str);
          nn = 2;
        }
        // frequency step
        else if (nn == 2) {
          freq_step = atol(str);
          nn = 0;
          message = 1;
        }
      }
    }

    // VER 0.2.2 - MTD415T PASSTHROUGH
    // ----------------------------------------------
    // Any other single command (m?, u?, c, n?, ta?, tb?, ...) is forwarded
    // directly to the MTD415T. Enables diagnostic access to the TEC chip
    // via Serial Monitor or GUI console for debugging.
    else {
      Serial_1_Flush();
      Serial1.println(message_str);
      delay(10);
      if (Serial1.available()) {
        Serial.println(Serial1.readStringUntil('\n'));
      }
    }

    // VER 0.1.5 TODO
    // check if message is not decoded
    // Serial.println(message_str);

    // DUMMY DO NOTHING
    if (message == 0) {
      // nothing to do here, a dummy state
    }

    // START FREQUENCY SWEEP LOOP
    // ----------------------------------------------
    if (message == 1) {
      // start sweep
      long count = 0;
      pre_time = millis();
      // start sweep cycle measurement
      for (count = freq_start; count <= freq_stop; count = count + freq_step)
      {
        // set AD9851 DDS current frequency
        SetFreq(count);

        // ADC measure and averaging
        if (AVERAGING_BOOL == true) {
          for (int i = 0; i < AVERAGE_SAMPLE; i++) {
            result = adc->readSynchronizedContinuous();
            value += (uint16_t)result.result_adc0;
            value2 += (uint16_t)result.result_adc1;
          }
          // averaging (cast to double)
          value2 = 1.0 * value2 / AVERAGE_SAMPLE;
          value = 1.0 * value / AVERAGE_SAMPLE;

          // serial print data bit-amplitude and bit-phase values
          Serial.print(value);
          Serial.print(";");
          Serial.print(value2);
          Serial.println();
        }
      }

      // SEND TEMPERATURE COMMAND MTD415T
      // -----------------------------------------------------
      Serial1.println(TEMPERATURE_GET);

      /////////////////////////////////////////////////////////////////////////////
      // READ STRING at UART1 SERIAL
      if (Serial1.available()) {
        // read message from MTD415T
        MTD415T_READ_STRING = Serial1.readStringUntil('\n');
        // Serial.print("DEBUG MTD415T_READ_STRING "); Serial.println(MTD415T_READ_STRING);
      }
      /////////////////////////////////////////////////////////////////////////////

      // VER 0.2.0 - Update flow reading before sending sweep result
      updateFlowReading();

      // CHECK if TEMPERATURE CTRL is ACTIVE
      // NO temperature ctrl
      if (CTRL_SWITCH == false) {

        // we're all live in a yellow submarine
        // color yellow
        RGB_color(255, 255, 0);

        // print thermistor temperature
        Serial.print(MTD415T_READ_STRING.toFloat() / 1000.0);
        Serial.print(";");

        // VER 0.1.4
        // print TEC status boolean control variable
        Serial.print(0);
        // semicolon
        Serial.print(";");

        // VER 0.1.5 print the value of the error message
        Serial.print(MTD415T_READ_STRING_ERROR.toInt());
        Serial.print(";");

        // VER 0.2.0 - Add flow and pump data
        Serial.print(flowCurrent, 3);
        Serial.print(";");
        Serial.print(pumpSpeed);
        Serial.print(";");

        // print termination char EOM
        Serial.print("s");
      }

      // OK temperature ctrl
      else if (CTRL_SWITCH == true) {
        // print thermistor temperature
        Serial.print(MTD415T_READ_STRING.toFloat() / 1000.0);
        Serial.print(";");

        // READ STATUS TEC PIN
        if (digitalRead(STATUS_TEC) == 1) {
          // Status Signal (High = temperature within defined temperature window
          RGB_color(0, 142, 192);
          // VER 0.1.4
          // print TEC status boolean control variable
          Serial.print(_STATUS_CONTROL);
          // semicolon
          Serial.print(";");

        }

        // Low = Temperature outside programmed temperature window or an ERROR occurred
        else if (digitalRead(STATUS_TEC) == 0) {

          // TODO the test control status variable can switch to 1 randomly
          if (_STATUS_CONTROL == 1)  RGB_color(255, 125, 10);
          if (_STATUS_CONTROL == -1) RGB_color(255, 0, 0);

          // VER 0.1.4
          // print TEC status boolean control variable
          // check the current outide the loop
          Serial.print(_STATUS_CONTROL);
          // semicolon
          Serial.print(";");
        }

        // VER 0.1.5 print the value of the error message
        Serial.print(MTD415T_READ_STRING_ERROR.toInt());
        Serial.print(";");

        // VER 0.2.0 - Add flow and pump data
        Serial.print(flowCurrent, 3);
        Serial.print(";");
        Serial.print(pumpSpeed);
        Serial.print(";");

        // print termination char EOM
        Serial.print("s");
      }

      // check time elapsed
      // Serial.println(millis()-pre_time);
      // Serial.println();

      // TODO
      // VER 0.1.3
      // reset the case switch variable
      message = 0;
    }
  }
}
