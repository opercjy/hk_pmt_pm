import sys, serial, time, csv, json, os, queue
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QLabel, QFrame, QPushButton, QDialog, QComboBox, QDoubleSpinBox
from PyQt5.QtCore import QThread, QObject, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont

# pyqtgraph 라이브러리 및 전역 스타일 설정
import pyqtgraph as pg
import numpy as np

pg.setConfigOption('background', '#FFF8DC') # 그래프 배경색을 Cornsilk(밝은 베이지)으로 설정
pg.setConfigOption('foreground', 'k')      # 그래프 전경색(축, 라벨 등)을 검은색으로 설정

# --- 설정 파일 로드 ---
# 스크립트 시작 시 'config.json' 파일을 읽어오는 함수
def load_config(filename='config.json'):
    if not os.path.exists(filename):
        raise FileNotFoundError(f"설정 파일 '{filename}'을 찾을 수 없습니다.")
    with open(filename, 'r') as f:
        return json.load(f)

# 설정 파일을 전역 변수 CONFIG에 저장
try:
    CONFIG = load_config()
except Exception as e:
    print(f"config.json 파일 로드 오류: {e}")
    sys.exit(1)

# --- 클래스 정의: 아두이노 워커 ---
# 별도의 스레드에서 아두이노와의 시리얼 통신을 담당하는 클래스
class ArduinoWorker(QObject):
    # 데이터 수신 시 발생시킬 신호. (센서 인덱스, 온도, 습도)를 전달
    data_ready = pyqtSignal(int, object, object)
    # 연결 상태 변경 시 발생시킬 신호. (상태 메시지)를 전달
    connection_status = pyqtSignal(str) 
    
    def __init__(self, port, baud_rate):
        super().__init__()
        self.running = True; self.ser = None
        self.port = port; self.baud_rate = baud_rate
    
    # 스레드가 시작될 때 실행되는 메인 루프
    def run(self):
        while self.running:
            try:
                self.connection_status.emit(f"Connecting to ENV Sensor ({self.port})...")
                self.ser = serial.Serial(self.port, self.baud_rate, timeout=2)
                self.connection_status.emit("ENV Status: Connection Successful!")
                
                # 연결이 성공하면 계속해서 데이터 읽기 시도
                while self.running:
                    if self.ser.in_waiting > 0:
                        line = self.ser.readline().decode('utf-8').strip()
                        try:
                            # "SENSOR:0,TEMP:22.5,HUMI:45.8" 형식의 문자열 파싱
                            parts = {p.split(':')[0]: p.split(':')[1] for p in line.split(',')}
                            idx = int(parts.get("SENSOR", -1))
                            if idx != -1: # 유효한 센서 인덱스가 있을 경우
                                if "ERROR" in parts:
                                    self.data_ready.emit(idx, None, None) # 오류 발생 시 None 전달
                                elif "TEMP" in parts and "HUMI" in parts:
                                    self.data_ready.emit(idx, float(parts["TEMP"]), float(parts["HUMI"]))
                        except (ValueError, IndexError, KeyError):
                            pass # 파싱 실패 시 조용히 무시
            except serial.SerialException:
                # 연결 실패 시 상태 업데이트 후 5초 대기
                self.connection_status.emit(f"ENV Status: Connection Failed!")
                time.sleep(5)
            finally:
                if self.ser and self.ser.is_open: self.ser.close()
    
    def stop(self): self.running = False

# --- 클래스 정의: CAEN HV 워커 ---
# 별도의 스레드에서 HV 장비와의 통신 및 제어를 담당하는 클래스
class CaenHvWorker(QObject):
    data_ready = pyqtSignal(list)
    connection_status = pyqtSignal(str)
    command_feedback = pyqtSignal(str) # 제어 명령 결과 피드백을 위한 신호

    def __init__(self, config):
        super().__init__()
        self.running = True
        self.config = config
        self.command_queue = queue.Queue() # 스레드 간의 안전한 통신을 위한 명령 큐

    def run(self):
        cfg = self.config
        try:
            # HV 라이브러리는 스레드 내에서 import하여 안정성 확보
            from caen_libs import caenhvwrapper as hv
            system_type = hv.SystemType[cfg['system_type']]
            link_type = hv.LinkType[cfg['link_type']]
            channels = cfg['channels_to_monitor']
            
            while self.running:
                try:
                    self.connection_status.emit(f"Connecting to HV ({cfg['connection_argument']})...")
                    # 'with' 구문을 사용하여 장비 연결 및 자동 해제
                    with hv.Device.open(system_type, link_type, cfg['connection_argument'], cfg['username'], cfg['password']) as device:
                        self.connection_status.emit("HV Status: Connection Successful!")
                        while self.running:
                            # 1. 명령 큐 확인 및 처리
                            try:
                                command = self.command_queue.get_nowait()
                                cmd_type, slot, ch, param, value = command
                                device.set_ch_param(slot, [ch], param, value)
                                self.command_feedback.emit(f"Success: Ch{ch} {param} set to {value}")
                            except queue.Empty:
                                pass # 큐가 비어있으면 다음 작업으로
                            except hv.Error as e:
                                self.command_feedback.emit(f"Error: Failed to set Ch{ch} {param}. {e}")
                            
                            # 2. 실시간 값 모니터링
                            results = []
                            for ch_mon in channels:
                                try:
                                    vmon = device.get_ch_param(0, [ch_mon], 'VMon')[0]
                                    imon = device.get_ch_param(0, [ch_mon], 'IMon')[0]
                                    results.append((0, ch_mon, vmon, imon))
                                except hv.Error: results.append((0, ch_mon, 0.0, 0.0))
                            self.data_ready.emit(results)
                            time.sleep(1) # 1초 간격으로 모니터링
                except hv.Error as e:
                    self.connection_status.emit(f"HV Status: Connection Failed!"); time.sleep(10)
        except (ImportError, KeyError) as e:
            self.connection_status.emit(f"HV Library/Config Error: {e}")

    def stop(self): self.running = False
# --- 클래스 정의: HV 제어판 ---
# HV 채널 제어를 위한 별도의 QDialog 창
class HVControlPanel(QDialog):
    # 제어 명령을 메인 앱으로 전달하기 위한 신호
    control_signal = pyqtSignal(tuple)

    def __init__(self, channels_to_monitor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HV Control Panel")
        self.layout = QGridLayout(self)

        # UI 위젯 생성
        self.layout.addWidget(QLabel("Target Channel:"), 0, 0)
        self.channel_selector = QComboBox()
        self.channel_selector.addItems([str(ch) for ch in channels_to_monitor])
        self.layout.addWidget(self.channel_selector, 0, 1, 1, 2)

        self.layout.addWidget(QLabel("Set Voltage (V0Set):"), 1, 0)
        self.voltage_input = QDoubleSpinBox(); self.voltage_input.setRange(0, 8000); self.voltage_input.setDecimals(2)
        self.layout.addWidget(self.voltage_input, 1, 1)
        self.set_voltage_btn = QPushButton("Set Voltage"); self.set_voltage_btn.clicked.connect(self.set_voltage)
        self.layout.addWidget(self.set_voltage_btn, 1, 2)
        
        self.layout.addWidget(QLabel("Set Current (I0Set, uA):"), 2, 0)
        self.current_input = QDoubleSpinBox(); self.current_input.setRange(0, 1000); self.current_input.setDecimals(2)
        self.layout.addWidget(self.current_input, 2, 1)
        self.set_current_btn = QPushButton("Set Current"); self.set_current_btn.clicked.connect(self.set_current)
        self.layout.addWidget(self.set_current_btn, 2, 2)

        self.power_on_btn = QPushButton("Turn ON"); self.power_on_btn.setStyleSheet("background-color: lightgreen")
        self.power_on_btn.clicked.connect(self.turn_on)
        self.layout.addWidget(self.power_on_btn, 3, 0, 1, 3)

        self.power_off_btn = QPushButton("Turn OFF"); self.power_off_btn.setStyleSheet("background-color: lightcoral")
        self.power_off_btn.clicked.connect(self.turn_off)
        self.layout.addWidget(self.power_off_btn, 4, 0, 1, 3)
        
        # 제어 결과 피드백을 표시할 라벨
        self.feedback_label = QLabel("Status: Ready"); self.feedback_label.setWordWrap(True)
        self.layout.addWidget(self.feedback_label, 5, 0, 1, 3)

    # 선택된 채널 번호를 반환하는 헬퍼 함수
    def get_selected_channel(self):
        return int(self.channel_selector.currentText())

    # 각 버튼 클릭 시 실행될 함수들
    def set_voltage(self):
        # (명령 종류, 슬롯, 채널, 파라미터명, 값) 형식의 튜플로 명령 생성 후 신호 발생
        command = ('set_param', 0, self.get_selected_channel(), 'V0Set', self.voltage_input.value())
        self.control_signal.emit(command)

    def set_current(self):
        command = ('set_param', 0, self.get_selected_channel(), 'I0Set', self.current_input.value())
        self.control_signal.emit(command)

    def turn_on(self):
        command = ('set_param', 0, self.get_selected_channel(), 'Pw', 1)
        self.control_signal.emit(command)

    def turn_off(self):
        command = ('set_param', 0, self.get_selected_channel(), 'Pw', 0)
        self.control_signal.emit(command)
    
    # 메인 앱으로부터 피드백 메시지를 받아 라벨에 업데이트하는 슬롯
    def update_feedback(self, message):
        self.feedback_label.setText(f"Status: {message}")

# --- 클래스 정의: 메인 애플리케이션 ---
class MonitoringApp(QMainWindow):
    def __init__(self, config):
        super().__init__()
        # 설정 파일로부터 주요 설정값들을 멤버 변수로 저장
        self.config = config
        self.num_sensors = len(self.config['arduino_settings']['sensors'])
        self.hv_channels = self.config['caen_hv_settings']['channels_to_monitor']
        
        # 윈도우 기본 설정
        self.setWindowTitle(self.config['ui_options']['window_title'])
        self.setGeometry(100, 100, 1800, 950)
        self.setStyleSheet("background-color: #FFF8DC;")
        self.central_widget = QWidget(); self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # 데이터 저장을 위한 변수들 초기화
        self.latest_data = {'sensors': {}, 'hv': {}} # 1초마다 업데이트되는 최신 데이터
        self.data_buffer = [] # 1분마다 수집되어 30분간 쌓이는 로깅용 데이터 버퍼
        self.graph_time_data = [] # 그래프 x축(시간) 데이터
        self.graph_temp_data = {i: [] for i in range(self.num_sensors)}
        self.graph_humi_data = {i: [] for i in range(self.num_sensors)}
        self.graph_volt_data = {ch: [] for ch in self.hv_channels}
        self.graph_curr_data = {ch: [] for ch in self.hv_channels}

        # UI 생성 및 백엔드 로직 설정
        self.setup_ui()
        self.setup_timers()
        self.setup_logger()
        self.setup_workers()

    # --- UI 설정 함수들 ---
    def setup_ui(self):
        # 상단 상태 표시부 UI 설정
        status_layout = QGridLayout(); self.main_layout.addLayout(status_layout)
        font_large = QFont(); font_large.setPointSize(14)
        
        self.env_status_label = QLabel("ENV Status: Standby"); self.env_status_label.setFont(font_large)
        self.hv_status_label = QLabel("HV Status: Standby"); self.hv_status_label.setFont(font_large)
        self.log_status_label = QLabel("Logging: Standby..."); self.log_status_label.setFont(font_large)
        status_layout.addWidget(self.env_status_label, 0, 0, 1, 2)
        status_layout.addWidget(self.hv_status_label, 0, 2, 1, 2)
        status_layout.addWidget(self.log_status_label, 0, 4, 1, 3)

        self.control_panel_btn = QPushButton("Open HV Control Panel"); self.control_panel_btn.setFont(font_large)
        self.control_panel_btn.clicked.connect(self.open_control_panel)
        status_layout.addWidget(self.control_panel_btn, 0, 7, 1, 2)

        # config.json에 정의된 센서 개수만큼 라벨 동적 생성
        self.sensor_labels = {i: {} for i in range(self.num_sensors)}
        for i, sensor_info in enumerate(self.config['arduino_settings']['sensors']):
            name = sensor_info['name']
            temp_label = QLabel(f"{name} T: - °C"); temp_label.setFont(font_large)
            humi_label = QLabel(f"H: - %"); humi_label.setFont(font_large)
            row, col = divmod(i, 2)
            status_layout.addWidget(temp_label, row + 1, col * 4, 1, 2)
            status_layout.addWidget(humi_label, row + 1, col * 4 + 2, 1, 2)
            self.sensor_labels[i]['temp'] = temp_label; self.sensor_labels[i]['humi'] = humi_label
        
        line1 = QFrame(); line1.setFrameShape(QFrame.HLine); line1.setFrameShadow(QFrame.Sunken)
        status_layout.addWidget(line1, 3, 0, 1, 9)
        
        # config.json에 정의된 HV 채널 개수만큼 라벨 동적 생성
        volt_header = QLabel("Voltage (V):"); volt_header.setFont(font_large)
        curr_header = QLabel("Current (uA):"); curr_header.setFont(font_large)
        status_layout.addWidget(volt_header, 4, 0); status_layout.addWidget(curr_header, 5, 0)
        self.hv_v_labels, self.hv_i_labels = {}, {}
        for ch in self.hv_channels:
            v_label = QLabel(f"Ch{ch}: -"); v_label.setFont(font_large)
            i_label = QLabel(f"Ch{ch}: -"); i_label.setFont(font_large)
            status_layout.addWidget(v_label, 4, ch + 1); status_layout.addWidget(i_label, 5, ch + 1)
            self.hv_v_labels[ch] = v_label; self.hv_i_labels[ch] = i_label
        
        # 그래프 UI 설정
        graph_layout = QGridLayout(); self.main_layout.addLayout(graph_layout)
        plots = {
            'temp': pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')}),
            'humi': pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')}),
            'volt': pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')}),
            'curr': pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        }
        plots['humi'].setXLink(plots['temp']); plots['volt'].setXLink(plots['temp']); plots['curr'].setXLink(plots['temp'])
        plots['temp'].setTitle("Temperature", color='k'); plots['temp'].setLabel('left', 'Temp (°C)')
        plots['humi'].setTitle("Humidity", color='k'); plots['humi'].setLabel('left', 'Humidity (%)')
        plots['volt'].setTitle("HV Voltage", color='k'); plots['volt'].setLabel('left', 'Voltage (V)')
        plots['curr'].setTitle("HV Current", color='k'); plots['curr'].setLabel('left', 'Current (uA)')
        graph_layout.addWidget(plots['temp'], 0, 0); graph_layout.addWidget(plots['humi'], 0, 1)
        graph_layout.addWidget(plots['volt'], 1, 0); graph_layout.addWidget(plots['curr'], 1, 1)
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
        
        # 레전드 폰트 크기 설정을 위한 트릭
        for plot in plots.values():
            legend = plot.addLegend()
            if legend:
                dummy_item = plot.plot(pen=None, name=" ")
                if legend.items: label_item = legend.items[0][1]; label_item.setFont(QFont("sans-serif", 12))
                plot.removeItem(dummy_item)

        # 센서 및 채널별 그래프 곡선 동적 생성
        self.temp_curves, self.humi_curves = {}, {}
        for i, sensor_info in enumerate(self.config['arduino_settings']['sensors']):
            name = sensor_info['name']; color = colors[i % len(colors)]
            self.temp_curves[i] = plots['temp'].plot(pen=pg.mkPen(color, width=3), name=name)
            self.humi_curves[i] = plots['humi'].plot(pen=pg.mkPen(color, width=3), name=name)
        
        self.volt_curves, self.curr_curves = {}, {}
        for i, ch in enumerate(self.hv_channels):
            color = colors[i % len(colors)]; label = f"Ch{ch}"
            self.volt_curves[ch] = plots['volt'].plot(pen=pg.mkPen(color, width=3), name=label)
            self.curr_curves[ch] = plots['curr'].plot(pen=pg.mkPen(color, width=3), name=label)
        
        # 하단 정보 UI 설정
        bottom_layout = QGridLayout(); self.main_layout.addLayout(bottom_layout)
        font_small = QFont(); font_small.setPointSize(12)
        self.shifter_label = QLabel(self.config['ui_options']['shifter_name']); self.shifter_label.setFont(font_small)
        self.datetime_label = QLabel("-"); self.datetime_label.setFont(font_small)
        self.shifter_label.setAlignment(Qt.AlignLeft); self.datetime_label.setAlignment(Qt.AlignRight)
        bottom_layout.addWidget(self.shifter_label, 0, 0); bottom_layout.addWidget(self.datetime_label, 0, 1)
    
    # --- 백엔드 설정 함수들 ---
    def setup_timers(self):
        ui_cfg = self.config['ui_options']; log_cfg = self.config['logging_options']
        # 각 기능별 타이머 생성 및 시작
        self.log_timer = QTimer(); self.log_timer.timeout.connect(self.log_data_buffer); self.log_timer.start(log_cfg['bulk_write_interval_ms'])
        self.capture_timer = QTimer(); self.capture_timer.timeout.connect(self.capture_data_point); self.capture_timer.start(log_cfg['capture_interval_ms'])
        self.datetime_timer = QTimer(); self.datetime_timer.timeout.connect(self.update_datetime); self.datetime_timer.start(1000)
        self.graph_update_timer = QTimer(); self.graph_update_timer.timeout.connect(self.update_graphs); self.graph_update_timer.start(ui_cfg['graph_update_interval_ms'])
        self.indicator_update_timer = QTimer(); self.indicator_update_timer.timeout.connect(self.update_indicators); self.indicator_update_timer.start(ui_cfg['indicator_update_interval_ms'])

    def setup_logger(self):
        # config.json 기반으로 CSV 파일 헤더를 동적으로 생성하고 파일 생성
        log_cfg = self.config['logging_options']
        log_filename = f"{log_cfg['log_file_prefix']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.log_file_path = log_filename
        header = ['Timestamp']
        for sensor_info in self.config['arduino_settings']['sensors']: name = sensor_info['name'].replace(" ", "_"); header.extend([f'{name}_T', f'{name}_H'])
        for ch in self.hv_channels: header.extend([f'Ch{ch}_V', f'Ch{ch}_I'])
        with open(self.log_file_path, 'w', newline='') as f: csv.writer(f).writerow(header)
        print(f"Log file created: {self.log_file_path}")

    def setup_workers(self):
        # Arduino 워커 스레드 설정 및 시작
        arduino_cfg = self.config['arduino_settings']
        self.arduino_worker = ArduinoWorker(arduino_cfg['port'], arduino_cfg['baud_rate'])
        self.arduino_thread = QThread(); self.arduino_worker.moveToThread(self.arduino_thread)
        self.arduino_thread.started.connect(self.arduino_worker.run)
        self.arduino_worker.data_ready.connect(self.update_arduino_data)
        self.arduino_worker.connection_status.connect(self.update_env_status)
        self.arduino_thread.start()
        
        # HV 워커 스레드 설정 및 시작
        hv_cfg = self.config['caen_hv_settings']
        self.caenhv_worker = CaenHvWorker(hv_cfg)
        self.caenhv_thread = QThread(); self.caenhv_worker.moveToThread(self.caenhv_thread)
        self.caenhv_thread.started.connect(self.caenhv_worker.run)
        self.caenhv_worker.data_ready.connect(self.update_caenhv_data)
        self.caenhv_worker.connection_status.connect(self.update_hv_status)
        self.caenhv_worker.command_feedback.connect(self.on_hv_feedback)
        self.caenhv_thread.start()

# --- 데이터 처리 및 UI 업데이트를 위한 슬롯 함수들 ---
    def capture_data_point(self):
        # 1분마다 호출되어 최신 데이터를 버퍼에 저장
        snapshot = {'timestamp': datetime.now().isoformat(), 'sensors': self.latest_data['sensors'].copy(), 'hv': self.latest_data['hv'].copy()}
        self.data_buffer.append(snapshot)

    def log_data_buffer(self):
        # 30분마다 호출되어 버퍼의 모든 데이터를 CSV 파일에 기록
        if not self.data_buffer: return
        buffer_copy = self.data_buffer.copy(); self.data_buffer.clear()
        try:
            with open(self.log_file_path, 'a', newline='') as f:
                writer = csv.writer(f)
                for item in buffer_copy:
                    row = [item['timestamp']]
                    for i in range(self.num_sensors):
                        sensor = item['sensors'].get(i, {'t': np.nan, 'h': np.nan}); row.extend([sensor['t'], sensor['h']])
                    for ch in self.hv_channels:
                        hv = item['hv'].get(ch, {'v': 0, 'i': 0}); row.extend([hv['v'], hv['i']])
                    writer.writerow(row)
            print(f"[{datetime.now().isoformat()}] Bulk logged {len(buffer_copy)} data points.")
        except IOError as e: print(f"File write error: {e}"); self.data_buffer = buffer_copy + self.data_buffer
    
    def update_indicators(self):
        # 2초마다 호출되어 상단의 모든 텍스트 라벨을 최신 데이터로 업데이트
        for i, sensor_info in enumerate(self.config['arduino_settings']['sensors']):
            name = sensor_info['name']; data = self.latest_data['sensors'].get(i, {'t': None, 'h': None})
            if data['t'] is None or np.isnan(data['t']):
                self.sensor_labels[i]['temp'].setText(f"{name} T: None"); self.sensor_labels[i]['humi'].setText(f"H: None")
            else:
                self.sensor_labels[i]['temp'].setText(f"{name} T: {data['t']:.2f} °C"); self.sensor_labels[i]['humi'].setText(f"H: {data['h']:.2f} %")
        for ch in self.hv_channels:
            data = self.latest_data['hv'].get(ch, {'v': 0, 'i': 0})
            self.hv_v_labels[ch].setText(f"Ch{ch}: {data['v']:.2f}"); self.hv_i_labels[ch].setText(f"Ch{ch}: {data['i']:.4f}")
        self.log_status_label.setText(f"Logging: {len(self.data_buffer)} point(s) collected (Next log in {self.log_timer.remainingTime()//60000 + 1} min)")

    def update_graphs(self):
        # 1분마다 호출되어 그래프에 새로운 데이터 포인트를 추가
        timestamp = time.time(); self.graph_time_data.append(timestamp)
        for i in range(self.num_sensors):
            sensor = self.latest_data['sensors'].get(i, {'t': np.nan, 'h': np.nan})
            self.graph_temp_data[i].append(sensor['t']); self.graph_humi_data[i].append(sensor['h'])
        for ch in self.hv_channels:
            hv = self.latest_data['hv'].get(ch, {'v': 0, 'i': 0})
            self.graph_volt_data[ch].append(hv['v']); self.graph_curr_data[ch].append(hv['i'])
        # 그래프 데이터가 너무 많아지면(24시간) 오래된 데이터 삭제
        if len(self.graph_time_data) > 1440:
            self.graph_time_data.pop(0)
            for i in range(self.num_sensors): self.graph_temp_data[i].pop(0); self.graph_humi_data[i].pop(0)
            for ch in self.hv_channels: self.graph_volt_data[ch].pop(0); self.graph_curr_data[ch].pop(0)
        # 모든 곡선의 데이터를 업데이트하여 그래프를 다시 그림
        for i in range(self.num_sensors):
            self.temp_curves[i].setData(self.graph_time_data, self.graph_temp_data[i], connect='finite')
            self.humi_curves[i].setData(self.graph_time_data, self.graph_humi_data[i], connect='finite')
        for ch in self.hv_channels:
            self.volt_curves[ch].setData(self.graph_time_data, self.graph_volt_data[ch])
            self.curr_curves[ch].setData(self.graph_time_data, self.graph_curr_data[ch])

    # --- Worker 신호 처리를 위한 슬롯 함수들 ---
    def update_arduino_data(self, idx, temp, humi):
        # Arduino 워커로부터 받은 최신 센서 데이터를 저장
        self.latest_data['sensors'][idx] = {'t': temp if temp is not None else np.nan, 'h': humi if humi is not None else np.nan}
        
    def update_caenhv_data(self, results):
        # HV 워커로부터 받은 최신 HV 데이터를 저장
        for _, ch, vmon, imon in results:
            self.latest_data['hv'][ch] = {'v': vmon, 'i': imon}
            
    def update_env_status(self, status): self.env_status_label.setText(status)
    def update_hv_status(self, status): self.hv_status_label.setText(status)
    def update_datetime(self): self.datetime_label.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    # --- HV 제어판 관련 함수들 ---
    def open_control_panel(self):
        if not hasattr(self, 'control_panel'):
            self.control_panel = HVControlPanel(self.hv_channels, self)
            self.control_panel.control_signal.connect(self.queue_hv_command)
        self.control_panel.show()
    
    def queue_hv_command(self, command):
        self.caenhv_worker.command_queue.put(command)

    def on_hv_feedback(self, message):
        if hasattr(self, 'control_panel'):
            self.control_panel.update_feedback(message)

    # --- 프로그램 종료 처리 ---
    def closeEvent(self, event):
        print("Closing application... saving remaining data.")
        self.log_data_buffer() # 버퍼에 남은 데이터 저장
        # 모든 워커 스레드를 안전하게 종료
        self.arduino_worker.stop(); self.caenhv_worker.stop()
        self.arduino_thread.quit(); self.caenhv_thread.quit()
        self.arduino_thread.wait(); self.caenhv_thread.wait()
        event.accept()

# --- 프로그램 실행부 ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MonitoringApp(CONFIG)
    window.show()
    sys.exit(app.exec_())
