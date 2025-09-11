# 실시간 환경 및 고전압(HV) 모니터링 및 제어 시스템

## 1. 프로젝트 개요

본 프로젝트는 아두이노에 연결된 다수의 DHT22 온/습도 센서와 다양한 CAEN HV 전원 공급 장치(SMARTHV, SY4527/SY5527, N1470 등)의 상태를 실시간으로 모니터링하고, 원격으로 제어하며, 모든 데이터를 장기간 CSV 파일로 기록하는 Python 기반 GUI 애플리케이션입니다.
실험 환경의 안정성을 지속적으로 확인하고, 필요시 즉각적으로 HV 채널을 제어할 수 있도록 설계되었습니다. 모든 설정은 `config.json` 파일을 통해 관리되므로, 코드 수정 없이 다양한 하드웨어 구성에 유연하게 대응할 수 있습니다.

## 2. 주요 기능

* **다중 장비 지원**: `config.json` 설정을 통해 **SMARTHV**, **SY4527/SY5527**, **NIM/Desktop 모듈 (예: N1470)** 등 다양한 CAEN HV 시스템을 지원합니다.
* **실시간 데이터 모니터링**: 다중 DHT22 센서의 온도/습도 및 CAEN HV 채널의 전압/전류 값을 실시간으로 UI에 표시합니다.
* **데이터 시각화**: `PyQtGraph`를 이용한 4분할 그래프(온도, 습도, HV 전압, HV 전류)를 제공하며, 모든 센서와 채널은 개별 색상으로 표시됩니다.
* **원격 HV 제어**: 별도의 제어판(Control Panel) 창을 통해 개별 채널의 전압/전류 설정 및 ON/OFF 제어가 가능하여, GECO2020과 같은 공식 프로그램의 점유 없이 직접 장비를 제어할 수 있습니다.
* **장기간 데이터 로깅**: 1분마다 수집된 데이터를 메모리 버퍼에 저장 후, 30분 주기로 CSV 파일에 일괄 기록하여 시스템 부하를 최소화합니다.
* **유연한 설정 관리**: `config.json` 파일을 통해 아두이노 포트, 센서 목록, HV 연결 방식(TCPIP/USB) 및 주소 등 모든 주요 설정을 관리합니다.
* **안정적인 멀티스레딩**: Arduino, CAEN HV 통신 및 GUI를 각각 별도의 스레드로 분리하여 장시간 안정적인 동작을 보장합니다.

## 3. 시스템 아키텍처

-   **`monitoring_app.py`**: PyQt5 기반의 메인 애플리케이션으로, GUI와 전체 로직을 담당합니다.
-   **`N1470_monitoring_app.py`**: N1470과 같이 전류 파라미터 이름이 다른 모델을 위한 특화 버전 스크립트입니다.
-   **`hv_diagnostic.py`**: HV 장비에 연결하여 사용 가능한 파라미터 목록을 출력해주는 진단 도구입니다. 이를 통해 `monitoring_app.py` 코드의 파라미터 이름(`VMon`, `IMon` 등)을 검증하고 수정할 수 있습니다.
-   **`config.json`**: 모든 하드웨어 및 프로그램 설정을 담고 있는 중앙 설정 파일입니다.
-   **Arduino**: `multi_sensor_sketch.ino` 스케치가 업로드되어, DHT22 센서 데이터를 주기적으로 읽어 시리얼 통신으로 전송합니다.

## 4. 사전 요구사항

**설치 순서가 중요합니다.**

1.  **기본 프로그램 설치**
    -   Python 3.x
    -   Arduino IDE

2.  **CAEN HV C/C++ Wrapper Library 설치 (필수)**
    -   [CAEN 공식 홈페이지](https://www.caen.it/products/caen-hv-wrapper-library/)에 접속하여 사용하는 운영체제(예: Linux 64bit)에 맞는 버전을 다운로드합니다.
    -   다운로드한 파일의 압축을 풀고, 내부의 `install.sh` 스크립트나 매뉴얼을 따라 시스템에 C/C++ 라이브러리를 설치합니다.

3.  **Python 라이브러리 설치**
    -   필수 라이브러리를 pip을 통해 설치합니다.
        ```bash
        pip install pyqt5 pyqtgraph pyserial numpy caen-libs
        ```

4.  **리눅스 시스템 라이브러리 설치**
    -   (Rocky Linux 9 기준) OpenSSL 1.1.1 호환성 라이브러리를 설치합니다.
        ```bash
        sudo dnf install openssl1.1
        ```

## 5. 설치 및 사용법

**1단계: 사용자 권한 설정 (최초 1회)**

리눅스에서 USB 시리얼 포트(`/dev/ttyUSB0` 등)에 접근하려면 사용자 계정을 `dialout` 그룹에 추가해야 합니다. 터미널에서 아래 명령어를 실행하고 **시스템을 재부팅하거나 로그아웃 후 다시 로그인**하세요.

```bash
sudo usermod -a -G dialout $USER
````

**2단계: 하드웨어 연결**

  - `config.json`의 `"sensors"` 목록에 맞게 DHT22 센서들을 아두이노의 디지털 핀에 연결합니다.

**3단계: 아두이노 스케치 업로드**

1.  Arduino IDE를 엽니다.
2.  `arduino_sketch/multi_sensor_sketch.ino` 파일을 엽니다.
3.  스케치 상단의 `DHT_PINS` 배열이 `config.json`의 센서 핀 구성과 일치하는지 확인 후 업로드합니다.

**4단계: 설정 파일 구성 (`config.json`)**

1.  사용할 장비에 맞는 `monitoring_app.py` 또는 `N1470_monitoring_app.py` 스크립트와 동일한 위치에 `config.json` 파일이 있는지 확인합니다.
2.  `"arduino_settings"` 섹션에서 `"port"`를 자신의 환경에 맞는 아두이노 시리얼 포트 이름으로 수정합니다.
3.  `"caen_hv_settings"` 섹션을 자신의 HV 장비에 맞게 수정합니다.
      - **`system_type`**: `SMARTHV`, `SY4527`, `SY5527`, `N1470` 등 장비 모델명을 정확히 기입합니다.
      - **`link_type`**: `TCPIP` 또는 `USB`
      - **`connection_argument`**:
          - `TCPIP` (SMARTHV, SY4527/5527): `"192.168.0.20"` (IP 주소만 입력)
          - `TCPIP` (NIM/Desktop, 예: N1470): `"192.168.0.250"` (`system_type`을 정확히 명시하면 LBus 주소는 라이브러리가 자동으로 인식하므로 생략 가능합니다.)
          - `USB`: `"0"` (장치 번호)

**5단계: (선택사항) HV 파라미터 진단**

만약 모니터링/제어 시 `Parameter not found` 오류가 발생하면, `hv_diagnostic.py`를 실행하여 장비가 실제로 사용하는 파라미터 이름을 확인하세요.

```bash
python3 hv_diagnostic.py
```

진단 결과에 나온 파라미터 목록을 참고하여 메인 스크립트(`CaenHvWorker` 클래스 내부)의 `get_ch_param` 또는 `set_ch_param`에 사용된 파라미터 이름(`VMon`, `IMon`, `VSet`, `ISet` 등)을 수정해야 할 수 있습니다.

**6단계: 애플리케이션 실행**

  - 터미널에서 아래 명령어를 실행하여 모니터링 프로그램을 시작합니다.
    ```bash
    python3 monitoring_app.py
    ```

## 6\. 파일 구조

```
.
├── N1470_LBus/
│   ├── monitoring_app_n1470.py # N1470 특화 버전 스크립트
│   └── config.json             # N1470용 설정 파일
├── monitoring_app.py           # SMARTHV, SY4527/5527용 메인 스크립트
├── hv_diagnostic.py            # HV 파라미터 진단 스크립트
├── config.json                 # 메인 스크립트용 설정 파일
├── arduino_sketch/
│   └── multi_sensor_sketch.ino # 아두이노에 업로드할 스케치
└── README.md                   # 프로젝트 설명 파일
```
