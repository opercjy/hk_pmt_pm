# 실시간 환경 및 고전압(HV) 모니터링 시스템 v2.2

## 1\. 프로젝트 개요

본 프로젝트는 실험실 환경의 물리적 조건(온/습도)과 CAEN 고전압(HV) 장비의 상태를 실시간으로 통합 모니터링하고 원격으로 제어하기 위한 Python 기반 GUI 애플리케이션입니다.

v2.2는 전문적인 Python 패키지 구조를 적용하여 **모듈성과 확장성을 극대화**했습니다. 모든 설정은 `.json` 설정 파일을 통해 관리되므로, 코드 수정 없이 다양한 하드웨어 구성에 유연하게 대응할 수 있도록 설계되었습니다.

## 2\. 핵심 기능

  * **전문적인 패키지 구조**: GUI, 백그라운드 작업 관리, 실제 하드웨어 통신 로직이 명확하게 분리되어 있습니다.
  * **동적 하드웨어 지원**: `config.json` 설정 변경만으로 `SMARTHV`, `N1470` 등 다양한 CAEN 장비와 포트가 다른 Arduino 보드를 완벽하게 지원합니다.
  * **안정적인 멀티스레딩**: 모든 하드웨어 통신은 별도의 스레드에서 처리되어 GUI의 응답성을 보장하며 장시간 안정적으로 동작합니다.
  * **실시간 시각화**: `PyQtGraph`를 이용해 모든 센서 및 HV 채널 데이터를 실시간 그래프로 시각화합니다.
  * **원격 HV 제어**: GUI 제어판을 통해 각 HV 채널의 전압/전류 설정 및 전원 ON/OFF를 원격으로 제어할 수 있습니다.
  * **사용자 편의 도구**: `find_arduino_port.py`, `hv_diagnostic.py`와 같은 유틸리티를 제공하여 설정 및 진단 과정을 간소화합니다.

## 3\. 시스템 아키텍처 (논리 제어 흐름)

```
[하드웨어] <------> [workers/ (패키지)] <------> [worker_manager.py] <------> [monitoring_app.py (GUI)]
 (Arduino,         (caen.py, arduino.py 등)        (백그라운드 작업 총괄)          (최종 사용자 인터페이스)
 CAEN HV)           (하드웨어 통신 전문가)
```

  * **`config.json`**: 프로젝트의 모든 동작 방식을 정의하는 중앙 설정 파일입니다.
  * **`workers/`**: 실제 하드웨어와 통신하는 `ArduinoWorker`, `CaenHvWorker`를 포함하는 전문가 패키지입니다.
  * **`worker_manager.py`**: 모든 워커들의 생명주기를 관리하고 GUI와의 통신을 중계하는 총괄 관리자입니다.
  * **`monitoring_app.py`**: 사용자에게 보여지는 최종 GUI 애플리케이션입니다.

## 4\. 사전 요구사항

  * Python 3.x
  * Arduino IDE
  * [CAEN HV C/C++ Wrapper Library](https://www.caen.it/products/caen-hv-wrapper-library/): **반드시 먼저 설치**해야 합니다.

## 5\. 설치 및 사용법

**1단계: 사용자 권한 설정 (리눅스 최초 1회)**

```bash
sudo usermod -a -G dialout $USER
```

> **중요**: 명령어 실행 후 반드시 **재부팅** 또는 **재로그인**해야 합니다.

**2단계: Python 라이브러리 설치**

```bash
pip install -r requirements.txt
```

**3단계: 아두이노 설정**

1.  `arduino_sketch/multi_sensor_sketch.ino` 파일을 Arduino IDE로 열어 보드에 업로드합니다.
2.  `python3 find_arduino_port.py`를 실행하여 아두이노 포트 이름(예: `/dev/ttyACM0`)을 확인합니다.

**4단계: `config.json` 설정**

1.  `config.json` 또는 `config_n1470.json` 파일을 복사하여 `my_config.json`과 같이 나만의 설정 파일을 만듭니다.
2.  3단계에서 찾은 포트 이름을 `arduino_settings`의 `port` 값에 입력합니다.
3.  `caen_hv_settings` 섹션을 사용하는 HV 장비 정보에 맞게 수정합니다. (IP 주소, `system_type` 등)
4.  만약 HV 파라미터 이름을 모를 경우, `python3 hv_diagnostic.py my_config.json` 을 실행하여 확인 후 `parameters` 섹션을 수정합니다.

**5단계: 프로그램 실행**

```bash
python3 monitoring_app.py my_config.json
```

> **Note**: 설정 파일 이름을 지정하지 않으면 기본값으로 `config.json` 파일을 찾아 실행합니다.

## 6\. 파일 구조

```
.
├── monitoring_app.py           # 메인 애플리케이션 실행 파일
├── worker_manager.py           # 백그라운드 스레드 관리 모듈
├── workers/
│   ├── __init__.py             # 'workers' 폴더를 패키지로 선언
│   ├── arduino.py              # ArduinoWorker 클래스
│   └── caen.py                 # CaenHvWorker 클래스
├── find_arduino_port.py        # 아두이노 포트 자동 탐지 유틸리티
├── hv_diagnostic.py            # HV 파라미터 진단 유틸리티
├── config.json                 # 기본 설정 파일 (SMARTHV, SY 계열)
├── config_n1470.json           # N1470 장비용 설정 파일 예시
├── requirements.txt            # Python 라이브러리 목록
├── arduino_sketch/
│   └── multi_sensor_sketch.ino # 아두이노 업로드용 스케치
└── README.md                   # 프로젝트 설명 파일
```
