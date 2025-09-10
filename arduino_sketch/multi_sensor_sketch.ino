/**
 * @file multi_sensor_sketch.ino
 * @brief Reads data from multiple DHT22 sensors and sends it over serial.
 * @details This sketch is designed to work with the Python monitoring application.
 * It reads temperature and humidity from an array of DHT22 sensors
 * and prints the data in a machine-readable format for parsing.
 * * Data Format (Success): "SENSOR:[index],TEMP:[value],HUMI:[value]"
 * Data Format (Failure): "SENSOR:[index],ERROR:Failed to read from sensor"
 * * @author Jiyoung Choi (Chonnam Nat'l Univ.), with assistance from Gemini
 * @version 1.0
 * @date 2025-09-11
 */

#include "DHT.h"

// ========================================================================
// [ 중요 / IMPORTANT ]
// 이 배열을 Python의 'config.json' 파일에 정의된 센서 목록과
// 반드시 일치시켜야 합니다. 센서의 순서(인덱스)와 개수가 중요합니다.
// 예: config.json의 첫 번째 센서는 DHT_PINS[0]에 해당합니다.
//
// This array MUST match the "sensors" list defined in the 'config.json'
// file used by the Python application. The order and number of sensors
// are critical for correct data parsing.
// ========================================================================
const int DHT_PINS[] = {2, 3, 4, 5}; 

// 배열의 크기로부터 센서의 총 개수를 자동으로 계산합니다.
const int NUM_SENSORS = sizeof(DHT_PINS) / sizeof(int);

// 사용할 센서 타입을 DHT22로 정의합니다.
#define DHTTYPE DHT22

// DHT 객체를 가리키는 포인터 배열을 선언합니다.
// (객체를 직접 생성하면 컴파일 오류가 발생하므로 포인터를 사용합니다.)
DHT *dht_sensors[NUM_SENSORS];

/**
 * @brief 초기 설정을 수행합니다. 시리얼 통신을 시작하고 모든 센서를 초기화합니다.
 */
void setup() {
  // 9600 bps로 시리얼 통신을 시작합니다.
  Serial.begin(9600);
  Serial.println("Multi-DHT22 Sensor System Initialized");

  // DHT_PINS 배열을 순회하며 각 핀에 연결된 센서를 초기화합니다.
  for (int i = 0; i < NUM_SENSORS; i++) {
    // 'new' 키워드를 사용해 각 센서 객체를 동적으로 생성하고,
    // 생성된 객체의 메모리 주소를 포인터 배열에 할당합니다.
    dht_sensors[i] = new DHT(DHT_PINS[i], DHTTYPE);
    // 포인터를 통해 해당 객체의 begin() 함수를 호출하여 센서를 시작합니다.
    dht_sensors[i]->begin();
    delay(100); // 다음 센서 초기화 전 안정화를 위한 짧은 지연
  }
}

/**
 * @brief 메인 루프. 2초마다 모든 센서의 데이터를 읽어 시리얼 포트로 전송합니다.
 */
void loop() {
  // 2초 동안 대기합니다. (DHT22 센서의 최소 샘플링 주기는 2초입니다.)
  delay(2000); 

  // 모든 센서를 순회하며 데이터를 읽고 전송합니다.
  for (int i = 0; i < NUM_SENSORS; i++) {
    // 포인터를 통해 습도와 온도 값을 읽어옵니다.
    float h = dht_sensors[i]->readHumidity();
    float t = dht_sensors[i]->readTemperature();

    // 센서 읽기에 실패했는지 확인합니다. (isnan: is Not a Number)
    if (isnan(h) || isnan(t)) {
      // 실패 시, Python 스크립트가 인식할 수 있는 오류 메시지를 전송합니다.
      Serial.print("SENSOR:");
      Serial.print(i);
      Serial.println(",ERROR:Failed to read from sensor");
    } else {
      // 성공 시, 파싱하기 쉬운 형식으로 데이터를 전송합니다.
      Serial.print("SENSOR:");
      Serial.print(i);
      Serial.print(",TEMP:");
      Serial.print(t);
      Serial.print(",HUMI:");
      Serial.println(h);
    }
  }
}
