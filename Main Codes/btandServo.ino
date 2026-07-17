#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include "BluetoothSerial.h"

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();
BluetoothSerial BT;

#define SERVO_FREQ 50 

// Current positions
int currF = 0, currR = 0, currB = 0;
// Memory of last received targets to prevent jitter
int lastF = -1, lastR = -1, lastB = -1; 

int angleToTicks(int angle, int maxAngle, int maxTicks) {
  return map(angle, 0, maxAngle, 150, maxTicks);
}

void moveSmoothly(int targetF, int targetR, int targetB, int stepDelay) {
  targetB = constrain(targetB, 0, 90);
  targetF = constrain(targetF, 0, 60);
  targetR = constrain(targetR, 0, 60);

  Serial.printf("Executing Move: F:%d R:%d B:%d\n", targetF, targetR, targetB);

  while (currF != targetF || currR != targetR || currB != targetB) {
    if (currF < targetF) currF++; else if (currF > targetF) currF--;
    if (currR < targetR) currR++; else if (currR > targetR) currR--;
    if (currB < targetB) currB++; else if (currB > targetB) currB--;

    pwm.setPWM(0, 0, angleToTicks(currR, 60, 350));
    pwm.setPWM(1, 0, angleToTicks(currF, 60, 350));
    pwm.setPWM(2, 0, angleToTicks(currB, 90, 450));

    delay(stepDelay); 
  }
}

void setup() {
  Serial.begin(115200);
  pwm.begin();
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(SERVO_FREQ);
  
  BT.begin("ESP32_Arm_Controller"); 
  Serial.println("System Ready. Filtering duplicate signals...");

  moveSmoothly(0, 0, 0, 20); 
}

void loop() {
  if (BT.available()) {
    String receivedData = BT.readStringUntil('\n');
    receivedData.trim();

    if (receivedData.length() > 0) {
      int comma1 = receivedData.indexOf(',');
      int comma2 = receivedData.indexOf(',', comma1 + 1);

      if (comma1 > 0 && comma2 > 0) {
        int nextF = receivedData.substring(0, comma1).toInt();
        int nextR = receivedData.substring(comma1 + 1, comma2).toInt();
        int nextB = receivedData.substring(comma2 + 1).toInt();

        // --- THE JITTER FIX ---
        // Only move if the NEW values are different from the LAST values
        if (nextF != lastF || nextR != lastR || nextB != lastB) {
          moveSmoothly(nextF, nextR, nextB, 15);
          
          // Update memory so we don't move again for the same data
          lastF = nextF;
          lastR = nextR;
          lastB = nextB;
        } else {
          // Optional: Debug message to see if filter is working
          // Serial.println("Duplicate data ignored.");
        }
      }
    }
  }
}