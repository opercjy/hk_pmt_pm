### **`README.md` (v2.0)**

새로운 모듈식 구조와 사용법을 반영한 README 파일입니다.

-----

# 실시간 환경 및 고전압(HV) 모니터링 시스템 v2.0

## 1\. 프로젝트 개요

본 프로젝트는 실험실 환경의 물리적 조건(온/습도)과 CAEN 고전압(HV) 장비의 상태를 실시간으로 통합 모니터링하고 원격으로 제어하기 위한 Python 기반 GUI 애플리케이션입니다.

v2.0은 대대적인 리팩토링을 통해 **모듈식 아키텍처**를 도입하여, 향후 새로운 하드웨어를 추가하거나 기능을 확장하기 매우 용이한 구조로 개선되었습니다. 모든 설정은 `config.json` 파일을 통해 관리되므로, 코드 수정 없이 다양한 하드웨어 구성에 유연하게 대응할 수 있습니다.

## 2\. 핵심 기능

  * **모듈식 아키텍처**: GUI, 백그라운드 작업, 데이터 관리가 명확히 분리되어 유지보수성 및 확장성 극대화
  * **동적 하드웨어 지원**: `config.json` 설정 변경만으로 `SMARTHV`, `N1470` 등 다양한 CAEN 장비와 포트가 다른 Arduino 보드 지원
  * **안정적인 멀티스레딩**: 하드웨어 통신은 별도의 스레드에서 처리되어 GUI의 응답성을 보장하며 장시간 안정적으로 동작
  * **실시간 시각화**: `PyQtGraph`를 이용해 모든 센서 및 HV 채널 데이터를 실시간 그래프로 시각화
  * **원격 HV 제어**: GUI 제어판을 통해 각 HV 채널의 전압/전류 설정 및 전원 ON/OFF 원격 제어
  * **사용자 편의 도구**: Arduino 시리얼 포트를 자동으로 찾아주는 `find_arduino_port.py` 유틸리티 제공

## 3\. 시스템 아키텍처 (논리 제어 흐름)

본 시스템은 각자 명확한 책임을 가진 여러 모듈이 유기적으로 상호작용하는 구조로 설계되었습니다.

```
[하드웨어] <------> [workers.py] <------> [worker_manager.py] <------> [main_app.py (GUI)]
 (Arduino,                               (하드웨어 통신 전문가)         (백그라운드 작업 총괄)          (최종 사용자 인터페이스)
 CAEN HV)
```

  * **`config.json` (프로젝트의 두뇌)**

      * 모든 하드웨어 연결 정보, 장비별 파라미터 이름, UI 옵션 등 프로젝트의 모든 동작 방식을 정의하는 중앙 설정 파일입니다.

  * **`workers.py` (하드웨어 통신 전문가)**

      * `ArduinoWorker`: 아두이노와 시리얼 통신을 담당합니다.
      * `CaenHvWorker`: CAEN HV 장비와 TCPIP/USB 통신을 담당하며, `config.json`에 정의된 파라미터 이름을 동적으로 사용합니다.

  * **`worker_manager.py` (백그라운드 작업 총괄)**

      * 모든 `Worker`들을 `QThread`(백그라운드 스레드)에서 생성, 실행, 안전하게 종료하는 모든 생명주기를 관리합니다.
      * GUI(`main_app.py`)와 `Worker`들 사이의 통신을 중계하여, GUI가 스레드 관리의 복잡성을 전혀 알 필요가 없도록 추상화합니다.

  * **`main_app.py` (최종 지휘자 및 GUI)**

      * `MonitoringApp` 메인 윈도우를 생성하고 사용자에게 보여주는 최종 결과물입니다.
      * `WorkerManager`를 통해 백그라운드 작업을 시작/종료시키고, 전달받은 데이터를 UI에 표시하는 역할만 수행합니다.

## 4\. 사전 요구사항

  * Python 3.x
  * Arduino IDE
  * [CAEN HV C/C++ Wrapper Library](https://www.caen.it/products/caen-hv-wrapper-library/): 사용하는 운영체제에 맞게 **반드시 먼저 설치**해야 합니다.

## 5\. 설치 및 사용법

**1단계: 사용자 권한 설정 (리눅스 최초 1회)**
USB 시리얼 포트 접근을 위해 현재 사용자를 `dialout` 그룹에 추가합니다. **명령어 실행 후 반드시 재부팅 또는 재로그인**해야 합니다.

```bash
sudo usermod -a -G dialout $USER
```

**2단계: Python 라이브러리 설치**
프로젝트 폴더 내의 터미널에서 아래 명령어를 실행하여 필요한 모든 라이브러리를 한 번에 설치합니다.

```bash
pip install -r requirements.txt
```

**3단계: 아두이노 설정**

1.  `arduino_sketch/multi_sensor_sketch.ino` 파일을 Arduino IDE로 열어 보드에 업로드합니다.
2.  터미널에서 `python3 find_arduino_port.py`를 실행하여 내 아두이노의 정확한 포트 이름(예: `/dev/ttyACM0`)을 확인합니다.

**4단계: `config.json` 설정**

1.  `config.json` (SMARTHV, SY 계열용) 또는 `config_n1470.json` (N1470용) 파일을 복사하여 `my_config.json`과 같이 나만의 설정 파일을 만듭니다.
2.  `find_arduino_port.py`로 찾은 포트 이름을 `arduino_settings`의 `port` 값에 입력합니다.
3.  `caen_hv_settings` 섹션을 사용하는 HV 장비 정보에 맞게 수정합니다. (IP 주소, `system_type`, 채널 수 등)

**5단계: 프로그램 실행**
터미널에서 아래 명령어를 실행하여 모니터링 프로그램을 시작합니다. `my_config.json` 부분은 4단계에서 만든 설정 파일 이름으로 변경합니다.

```bash
python3 main_app.py my_config.json
```

(만약 파일 이름을 지정하지 않으면 기본값으로 `config.json`을 사용합니다.)

## 6\. 파일 구조

```
.
├── main_app.py                 # 메인 애플리케이션 실행 파일
├── worker_manager.py           # 백그라운드 스레드 관리 모듈
├── workers.py                  # 실제 하드웨어 통신 로직 모듈
├── find_arduino_port.py        # 아두이노 포트 자동 탐지 유틸리티
├── config.json                 # 기본 설정 파일 (SMARTHV, SY 계열)
├── config_n1470.json           # N1470 장비용 설정 파일 예시
├── requirements.txt            # Python 라이브러리 목록
├── arduino_sketch/
│   └── multi_sensor_sketch.ino # 아두이노 업로드용 스케치
└── README.md                   # 프로젝트 설명 파일
```
