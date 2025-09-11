# hk_pmt_pm
-----
# 실시간 환경 및 고전압(HV) 모니터링 및 제어 시스템
## 1. 프로젝트 개요

본 프로젝트는 아두이노에 연결된 다수의 DHT22 온/습도 센서와 CAEN HV 전원 공급 장치의 상태를 실시간으로 모니터링하고, 원격으로 제어하며, 모든 데이터를 장기간 CSV 파일로 기록하는 Python 기반 GUI 애플리케이션입니다.

실험 환경의 안정성을 지속적으로 확인하고, 필요시 즉각적으로 HV 채널을 제어할 수 있도록 설계되었습니다. 모든 설정은 `config.json` 파일을 통해 관리되므로, 코드 수정 없이 다양한 하드웨어 구성에 유연하게 대응할 수 있습니다.



## 2. 주요 기능

* **실시간 데이터 모니터링**:
    * 다중 DHT22 센서의 온도 및 습도 값을 1초 단위로 UI에 표시.
    * CAEN SMARTHV의 모든 채널의 전압(VMon) 및 전류(IMon) 값을 1초 단위로 UI에 표시.
* **데이터 시각화**:
    * `PyQtGraph`를 이용한 4분할 그래프 (온도, 습도, HV 전압, HV 전류).
    * 모든 센서와 HV 채널은 각각 다른 색상으로 그래프에 표시.
    * 그래프는 1분 단위로 데이터를 샘플링하여 장시간 변화 추이를 관찰하기 용이.
* **원격 HV 제어**:
    * 별도의 제어판(Control Panel) 창을 통해 개별 채널의 전압/전류 설정 및 ON/OFF 제어 가능.
    * GECO2020과 같은 공식 프로그램의 점유 없이 직접 장비 제어.
* **장기간 데이터 로깅**:
    * 1분마다 모든 센서 데이터를 메모리 버퍼에 수집.
    * 30분마다 버퍼의 데이터를 CSV 파일에 일괄 기록하여 I/O 부하 최소화.
    * 프로그램 종료 시 버퍼에 남은 데이터를 안전하게 저장.
* **유연한 설정 관리**:
    * `config.json` 파일을 통해 아두이노 포트, 센서 목록, HV 연결 방식(TCPIP/USB) 및 주소 등 모든 주요 설정을 관리.
* **안정적인 멀티스레딩**:
    * Arduino, CAEN HV 통신 및 GUI를 각각 별도의 스레드로 분리하여 장시간 안정적인 동작 보장.

## 3. 시스템 아키텍처

-   **`monitoring_app.py`**: PyQt5 기반의 메인 애플리케이션으로, GUI와 전체 로직을 담당합니다.
-   **`config.json`**: 모든 하드웨어 및 프로그램 설정을 담고 있는 중앙 설정 파일입니다.
-   **Arduino**: `multi_sensor_sketch.ino` 스케치가 업로드되어, DHT22 센서 데이터를 주기적으로 읽어 시리얼 통신으로 전송하는 데이터 수집 장치 역할을 합니다.
-   **CAEN HV Power Supply**: TCPIP 또는 USB를 통해 `caen_libs` 라이브러리로 연결되어 모니터링 및 제어됩니다.
-   ```bash
    pip install caen-libs
    ```
    https://www.caen.it/products/caen-hv-wrapper-library/

## 4. 사전 요구사항

-   Python 3.x
-   Arduino IDE
-   Rocky Linux 9 (또는 기타 리눅스 환경)
-   CAEN HV C/C++ Wrapper (https://www.caen.it/products/caen-hv-wrapper-library/)
-   CAEN HV Wrapper (python binding)
    ```bash
    pip install caen-libs
    ```
-   필수 Python 라이브러리:
    ```bash
    pip install pyqt5 pyqtgraph pyserial numpy 
    ```
-   (Rocky Linux 9 기준) OpenSSL 1.1.1 호환성 라이브러리:
    ```bash
    sudo dnf install openssl1.1
    ```

## 5. 설치 및 사용법

**1단계: 하드웨어 연결**
-   `config.json`의 `"sensors"` 목록에 맞게 DHT22 센서들을 아두이노의 디지털 핀에 연결합니다.

**2단계: 아두이노 스케치 업로드**
1.  Arduino IDE를 엽니다.
2.  `arduino_sketch/multi_sensor_sketch.ino` 파일을 엽니다.
3.  스케치 상단의 `DHT_PINS` 배열이 `config.json`의 센서 핀 구성과 일치하는지 확인합니다.
4.  아두이노 보드에 스케치를 업로드합니다.

**3단계: 설정 파일 구성 (`config.json`)**
1.  스크립트와 같은 위치에 `config.json` 파일이 있는지 확인합니다.
2.  `"arduino_settings"` 섹션에서 `"port"`를 자신의 환경에 맞는 아두이노 시리얼 포트 이름(예: `/dev/ttyUSB0`)으로 수정합니다.
3.  `"caen_hv_settings"` 섹션에서 `"link_type"`과 `"connection_argument"` (IP 주소 또는 USB 장치 번호)를 자신의 HV 장비에 맞게 수정합니다.

**4단계: 애플리케이션 실행**
-   터미널에서 아래 명령어를 실행하여 모니터링 프로그램을 시작합니다.
    ```bash
    python3 monitoring_app.py
    ```
<img width="1820" height="990" alt="image" src="https://github.com/user-attachments/assets/2c956fe7-0e90-4bbd-93f7-e6c6e0e981af" />
<img width="331" height="294" alt="image" src="https://github.com/user-attachments/assets/666f5163-f796-4e52-ad74-e372f81c6daa" /><img width="324" height="240" alt="image" src="https://github.com/user-attachments/assets/cf14d72b-5a18-4181-90a6-9ed27744e03d" />

<img width="1820" height="990" alt="image" src="https://github.com/user-attachments/assets/c5e77540-e3a3-48d9-8c94-afbbb61064a0" />

## 6. 파일 구조

````
├── monitoring_app.py       \# 메인 파이썬 스크립트
├── config.json             \# 모든 설정을 담은 파일
├── arduino_sketch/
│   └── multi_sensor_sketch.ino \# 아두이노에 업로드할 스케치
└── README.md               \# 프로젝트 설명 파일
````

-----

