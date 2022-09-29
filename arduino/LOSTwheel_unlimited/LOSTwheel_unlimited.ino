#include <Servo.h>
#include <Arduino.h>
#include <U8g2lib.h>
#include <U8x8lib.h>
#ifdef U8X8_HAVE_HW_SPI
#include <SPI.h>
#endif
#ifdef U8X8_HAVE_HW_I2C
#include <Wire.h>
#endif

int lockedpos = 120;  //servo position to lock
int openpos = 100; //servo position to unlock
Servo myservo; // servo
int hallsensor = 2; //hall sensor pin

volatile long count; //rotation count

U8X8_SSD1306_128X64_NONAME_SW_I2C u8x8(A5, A4);

unsigned long startupTime;
unsigned long previousTime;
unsigned long currentTime;
unsigned long printTime;

void setup()
{
  Serial.begin(9600);
  while (!Serial);

  count = 0;

  u8x8.begin();
  u8x8.setFlipMode(1);
  u8x8.setFont(u8x8_font_amstrad_cpc_extended_r);
  u8x8.setInverseFont(1);

  u8x8.setCursor(1, 3);
  u8x8.print("count");
  u8x8.setCursor(1, 6);
  u8x8.print("time (min)");
  u8x8.setInverseFont(0);

  attachInterrupt(digitalPinToInterrupt(hallsensor), sensor, FALLING); //attach interrupt
  pinMode(hallsensor, INPUT_PULLUP); //setup hall sensor
//  myservo.attach(9); //setup pin for servo
//  myservo.write(openpos); //default state is open

  previousTime = 0;
  startupTime = millis();
}

void loop() {
  // put your main code here, to run repeatedly:

  currentTime = millis() - startupTime;

  if (currentTime - previousTime >= 1000) {
    previousTime = currentTime;
    printTime = currentTime;

    update();

  }

}

void sensor() { //interrupt to measure rotations
  count++; //every time hall effect sensor goes off, add 1 to count

}

void update() { //function to update serial and screen

  noInterrupts();
  long countCopy = count;  //make a copy of count with interrupts turned off
  count = 0;
  interrupts();

  Serial.print(float(printTime / 1000.0));
  Serial.print(',');
  Serial.print(countCopy);
  Serial.print('\n');

  u8x8.clearLine(4);
  u8x8.setCursor(1, 4);
  u8x8.print(countCopy); // clicks
  
  u8x8.setCursor(1, 7);
  u8x8.print((printTime/1000/60)); //printing time

}
