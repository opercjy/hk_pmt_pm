# -*- coding: utf-8 -*-
"""
실시간 환경(온/습도) 및 고전압(HV) 모니터링 및 제어 시스템
- 작성자: 최지영 (전남대학교)
- 최종 수정일: 2025-09-11
- 기능:
    - 다중 DHT22 센서 및 CAEN SMARTHV 모니터링
    - 실시간 데이터 시각화 (PyQtGraph)
    - 원격 HV 제어 기능 (전압/전류/전원)
    - 장기간 데이터 로깅 (CSV)
    - 모든 설정을 config.json 파일로 관리
"""

import sys, serial, time, csv, json, os, queue
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QLabel, QFrame, QPushButton, QDialog, QComboBox, QDoubleSpinBox
from PyQt5.QtCore import QThread, QObject, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont

# pyqtgraph 라이브러리 및 전역 스타일 설정
import pyqtgraph as pg
import numpy as np

pg.setConfigOption('background', '#FFF8DC') # 그래프 배경색 (Cornsilk)
pg.setConfigOption('foreground', 'k')      # 그래프 전경색 (검은색)

# --- 설정 파일 로드 ---
def load_config(filename='config.json'):
    """스크립트와 동일한 경로에 있는 JSON 설정 파일을 읽어오는 함수"""
    if not os.path.exists(filename):
        raise FileNotFoundError(f"설정 파일 '{filename}'을 찾을 수 없습니다.")
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

# 스크립트 시작 시 설정 파일을 전역 변수 CONFIG에 저장
try:
    CONFIG = load_config()
except Exception as e:
    print(f"config.json 파일 로드 오류: {e}")
    sys.exit(1)

# --- 클래스 정의: 아두이노 워커 ---
class ArduinoWorker(QObject):
    """별도의 스레드에서 아두이노와의 시리얼 통신을 담당"""
    data_ready = pyqtSignal(int, object, object)
    connection_status = pyqtSignal(str)
    
    def __init__(self, port, baud_rate):
        super().__init__()
        self.running = True
        self.ser = None
        self.port = port
        self.baud_rate = baud_rate
    
    def run(self):
        """스레드가 시작될 때 실행되는 메인 루프"""
        while self.running:
            try:
                self.connection_status.emit(f"Connecting to ENV Sensor ({self.port})...")
                self.ser = serial.Serial(self.port, self.baud_rate, timeout=2)
                self.connection_status.emit("ENV Status: Connection Successful!")
                
                while self.running:
                    if self.ser.in_waiting > 0:
                        line = self.ser.readline().decode('utf-8').strip()
                        try:
                            parts = {p.split(':')[0]: p.split(':')[1] for p in line.split(',')}
                            idx = int(parts.get("SENSOR", -1))
                            if idx != -1:
                                if "ERROR" in parts:
                                    self.data_ready.emit(idx, None, None)
                                elif "TEMP" in parts and "HUMI" in parts:
                                    self.data_ready.emit(idx, float(parts["TEMP"]), float(parts["HUMI"]))
                        except (ValueError, IndexError, KeyError):
                            pass
            except serial.SerialException:
                self.connection_status.emit(f"ENV Status: Connection Failed!")
                time.sleep(5)
            finally:
                if self.ser and self.ser.is_open:
                    self.ser.close()
    
    def stop(self):
        self.running = False

# --- 클래스 정의: CAEN HV 워커 ---
class CaenHvWorker(QObject):
    """별도의 스레드에서 HV 장비와의 통신 및 제어를 담당"""
    data_ready = pyqtSignal(list)
    connection_status = pyqtSignal(str)
    command_feedback = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.running = True
        self.config = config
        self.command_queue = queue.Queue()

    def run(self):
        cfg = self.config
        try:
            from caen_libs import caenhvwrapper as hv
            system_type = hv.SystemType[cfg['system_type']]
            link_type = hv.LinkType[cfg['link_type']]
            channels = cfg['channels_to_monitor']
            
            while self.running:
                try:
                    self.connection_status.emit(f"Connecting to HV ({cfg['connection_argument']})...")
                    with hv.Device.open(system_type, link_type, cfg['connection_argument'], cfg['username'], cfg['password']) as device:
                        self.connection_status.emit("HV Status: Connection Successful!")
                        while self.running:
                            try:
                                command = self.command_queue.get_nowait()
                                _, slot, ch, param, value = command
                                device.set_ch_param(slot, [ch], param, value)
                                self.command_feedback.emit(f"Success: Ch{ch} {param} set to {value}")
                            except queue.Empty:
                                pass
                            except hv.Error as e:
                                self.command_feedback.emit(f"Error on Ch{ch} {param}: {e}")
                            
                            results = []
                            for ch_mon in channels:
                                try:
                                    vmon = device.get_ch_param(0, [ch_mon], 'VMon')[0]
                                    imon = device.get_ch_param(0, [ch_mon], 'IMon')[0]
                                    results.append((0, ch_mon, vmon, imon))
                                except hv.Error:
                                    results.append((0, ch_mon, 0.0, 0.0))
                            self.data_ready.emit(results)
                            time.sleep(1)
                except hv.Error as e:
                    self.connection_status.emit(f"HV Status: Connection Failed!")
                    time.sleep(10)
        except (ImportError, KeyError) as e:
            self.connection_status.emit(f"HV Library/Config Error: {e}")

    def stop(self):
        self.running = False

# --- 클래스 정의: HV 제어판 ---
class HVControlPanel(QDialog):
    """HV 채널 제어를 위한 별도의 QDialog 창"""
    control_signal = pyqtSignal(tuple)

    def __init__(self, channels_to_monitor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HV Control Panel")
        self.layout = QGridLayout(self)
        self.layout.addWidget(QLabel("Target Channel:"), 0, 0)
        self.channel_selector = QComboBox()
        self.channel_selector.addItems([str(ch) for ch in channels_to_monitor])
        self.layout.addWidget(self.channel_selector, 0, 1, 1, 2)
        self.layout.addWidget(QLabel("Set Voltage (VSet):"), 1, 0)
        self.voltage_input = QDoubleSpinBox(); self.voltage_input.setRange(0, 8000); self.voltage_input.setDecimals(2)
        self.layout.addWidget(self.voltage_input, 1, 1)
        self.set_voltage_btn = QPushButton("Set Voltage"); self.set_voltage_btn.clicked.connect(self.set_voltage)
        self.layout.addWidget(self.set_voltage_btn, 1, 2)
        self.layout.addWidget(QLabel("Set Current (ISet, uA):"), 2, 0)
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
        self.feedback_label = QLabel("Status: Ready"); self.feedback_label.setWordWrap(True)
        self.layout.addWidget(self.feedback_label, 5, 0, 1, 3)

    def get_selected_channel(self): return int(self.channel_selector.currentText())
    def set_voltage(self): self.control_signal.emit(('set_param', 0, self.get_selected_channel(), 'VSet', self.voltage_input.value()))
    def set_current(self): self.control_signal.emit(('set_param', 0, self.get_selected_channel(), 'ISet', self.current_input.value()))
    def turn_on(self): self.control_signal.emit(('set_param', 0, self.get_selected_channel(), 'Pw', 1))
    def turn_off(self): self.control_signal.emit(('set_param', 0, self.get_selected_channel(), 'Pw', 0))
    def update_feedback(self, message): self.feedback_label.setText(f"Status: {message}")

# --- 클래스 정의: 메인 애플리케이션 ---
class MonitoringApp(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.num_sensors = len(self.config['arduino_settings']['sensors'])
        self.hv_channels = self.config['caen_hv_settings']['channels_to_monitor']
        self.setWindowTitle(self.config['ui_options']['window_title'])
        self.setGeometry(100, 100, 1800, 950)
        self.setStyleSheet("background-color: #FFF8DC;")
        self.central_widget = QWidget(); self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.latest_data = {'sensors': {}, 'hv': {}}
        self.data_buffer, self.graph_time_data = [], []
        self.graph_temp_data = {i: [] for i in range(self.num_sensors)}
        self.graph_humi_data = {i: [] for i in range(self.num_sensors)}
        self.graph_volt_data = {ch: [] for ch in self.hv_channels}
        self.graph_curr_data = {ch: [] for ch in self.hv_channels}

        self.setup_ui()
        self.setup_timers()
        self.setup_logger()
        self.setup_workers()

    def setup_ui(self):
        status_layout = QGridLayout(); self.main_layout.addLayout(status_layout)
        font_large = QFont(); font_large.setPointSize(14)
        style_status_bold = "color: black; font-weight: bold;"
        style_sensor = "color: blue;"
        style_voltage = "color: crimson;"
        style_current = "color: darkorange;"
        
        self.env_status_label = QLabel("ENV Status: Standby"); self.env_status_label.setFont(font_large); self.env_status_label.setStyleSheet(style_status_bold)
        self.hv_status_label = QLabel("HV Status: Standby"); self.hv_status_label.setFont(font_large); self.hv_status_label.setStyleSheet(style_status_bold)
        self.log_status_label = QLabel("Logging: Standby..."); self.log_status_label.setFont(font_large); self.log_status_label.setStyleSheet(style_status_bold)
        status_layout.addWidget(self.env_status_label, 0, 0, 1, 2)
        status_layout.addWidget(self.hv_status_label, 0, 2, 1, 2)
        status_layout.addWidget(self.log_status_label, 0, 4, 1, 3)
        self.control_panel_btn = QPushButton("Open HV Control Panel"); self.control_panel_btn.setFont(font_large)
        self.control_panel_btn.clicked.connect(self.open_control_panel); status_layout.addWidget(self.control_panel_btn, 0, 7, 1, 2)

        self.sensor_labels = {i: {} for i in range(self.num_sensors)}
        for i, sensor_info in enumerate(self.config['arduino_settings']['sensors']):
            name = sensor_info['name']
            temp_label = QLabel(f"{name} T: - °C"); temp_label.setFont(font_large); temp_label.setStyleSheet(style_sensor)
            humi_label = QLabel(f"H: - %"); humi_label.setFont(font_large); humi_label.setStyleSheet(style_sensor)
            row, col = divmod(i, 2)
            status_layout.addWidget(temp_label, row + 1, col * 4, 1, 2)
            status_layout.addWidget(humi_label, row + 1, col * 4 + 2, 1, 2)
            self.sensor_labels[i]['temp'] = temp_label; self.sensor_labels[i]['humi'] = humi_label
        
        line1 = QFrame(); line1.setFrameShape(QFrame.HLine); line1.setFrameShadow(QFrame.Sunken); status_layout.addWidget(line1, 3, 0, 1, 9)
        
        volt_header = QLabel("Voltage (V):"); volt_header.setFont(font_large); volt_header.setStyleSheet(style_voltage)
        curr_header = QLabel("Current (uA):"); curr_header.setFont(font_large); curr_header.setStyleSheet(style_current)
        status_layout.addWidget(volt_header, 4, 0); status_layout.addWidget(curr_header, 5, 0)
        self.hv_v_labels, self.hv_i_labels = {}, {}
        for ch in self.hv_channels:
            v_label = QLabel(f"Ch{ch}: -"); v_label.setFont(font_large); v_label.setStyleSheet(style_voltage)
            i_label = QLabel(f"Ch{ch}: -"); i_label.setFont(font_large); i_label.setStyleSheet(style_current)
            status_layout.addWidget(v_label, 4, ch + 1); status_layout.addWidget(i_label, 5, ch + 1)
            self.hv_v_labels[ch] = v_label; self.hv_i_labels[ch] = i_label
        
        graph_layout = QGridLayout(); self.main_layout.addLayout(graph_layout)
        plots = {'temp': pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')}),'humi': pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')}),'volt': pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')}),'curr': pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})}
        plots['humi'].setXLink(plots['temp']); plots['volt'].setXLink(plots['temp']); plots['curr'].setXLink(plots['temp'])
        plots['temp'].setTitle("Temperature", color='k'); plots['temp'].setLabel('left', 'Temp (°C)'); plots['humi'].setTitle("Humidity", color='k'); plots['humi'].setLabel('left', 'Humidity (%)'); plots['volt'].setTitle("HV Voltage", color='k'); plots['volt'].setLabel('left', 'Voltage (V)'); plots['curr'].setTitle("HV Current", color='k'); plots['curr'].setLabel('left', 'Current (uA)')
        graph_layout.addWidget(plots['temp'], 0, 0); graph_layout.addWidget(plots['humi'], 0, 1); graph_layout.addWidget(plots['volt'], 1, 0); graph_layout.addWidget(plots['curr'], 1, 1)
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
        for plot in plots.values():
            legend = plot.addLegend();
            if legend:
                dummy_item = plot.plot(pen=None, name=" ");
                if legend.items: label_item = legend.items[0][1]; label_item.setFont(QFont("sans-serif", 12))
                plot.removeItem(dummy_item)

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
        
        bottom_layout = QGridLayout(); self.main_layout.addLayout(bottom_layout)
        font_small = QFont(); font_small.setPointSize(12)
        self.shifter_label = QLabel(self.config['ui_options']['shifter_name']); self.shifter_label.setFont(font_small)
        self.datetime_label = QLabel("-"); self.datetime_label.setFont(font_small)
        self.shifter_label.setAlignment(Qt.AlignLeft); self.datetime_label.setAlignment(Qt.AlignRight)
        bottom_layout.addWidget(self.shifter_label, 0, 0); bottom_layout.addWidget(self.datetime_label, 0, 1)
    
    def setup_timers(self):
        ui_cfg = self.config['ui_options']; log_cfg = self.config['logging_options']
        self.log_timer = QTimer(); self.log_timer.timeout.connect(self.log_data_buffer); self.log_timer.start(log_cfg['bulk_write_interval_ms'])
        self.capture_timer = QTimer(); self.capture_timer.timeout.connect(self.capture_data_point); self.capture_timer.start(log_cfg['capture_interval_ms'])
        self.datetime_timer = QTimer(); self.datetime_timer.timeout.connect(self.update_datetime); self.datetime_timer.start(1000)
        self.graph_update_timer = QTimer(); self.graph_update_timer.timeout.connect(self.update_graphs); self.graph_update_timer.start(ui_cfg['graph_update_interval_ms'])
        self.indicator_update_timer = QTimer(); self.indicator_update_timer.timeout.connect(self.update_indicators); self.indicator_update_timer.start(ui_cfg['indicator_update_interval_ms'])

    def setup_logger(self):
        log_cfg = self.config['logging_options']
        log_filename = f"{log_cfg['log_file_prefix']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.log_file_path = log_filename
        header = ['Timestamp']
        for sensor_info in self.config['arduino_settings']['sensors']: name = sensor_info['name'].replace(" ", "_"); header.extend([f'{name}_T', f'{name}_H'])
        for ch in self.hv_channels: header.extend([f'Ch{ch}_V', f'Ch{ch}_I'])
        with open(self.log_file_path, 'w', newline='') as f: csv.writer(f).writerow(header)
        print(f"Log file created: {self.log_file_path}")

    def setup_workers(self):
        arduino_cfg = self.config['arduino_settings']
        self.arduino_worker = ArduinoWorker(arduino_cfg['port'], arduino_cfg['baud_rate'])
        self.arduino_thread = QThread(); self.arduino_worker.moveToThread(self.arduino_thread)
        self.arduino_thread.started.connect(self.arduino_worker.run); self.arduino_worker.data_ready.connect(self.update_arduino_data)
        self.arduino_worker.connection_status.connect(self.update_env_status); self.arduino_thread.start()
        hv_cfg = self.config['caen_hv_settings']
        self.caenhv_worker = CaenHvWorker(hv_cfg)
        self.caenhv_thread = QThread(); self.caenhv_worker.moveToThread(self.caenhv_thread)
        self.caenhv_thread.started.connect(self.caenhv_worker.run); self.caenhv_worker.data_ready.connect(self.update_caenhv_data)
        self.caenhv_worker.connection_status.connect(self.update_hv_status); self.caenhv_worker.command_feedback.connect(self.on_hv_feedback)
        self.caenhv_thread.start()
    
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

    def capture_data_point(self):
        snapshot = {'timestamp': datetime.now().isoformat(), 'sensors': self.latest_data['sensors'].copy(), 'hv': self.latest_data['hv'].copy()}
        self.data_buffer.append(snapshot)

    def log_data_buffer(self):
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
        timestamp = time.time(); self.graph_time_data.append(timestamp)
        for i in range(self.num_sensors):
            sensor = self.latest_data['sensors'].get(i, {'t': np.nan, 'h': np.nan})
            self.graph_temp_data[i].append(sensor['t']); self.graph_humi_data[i].append(sensor['h'])
        for ch in self.hv_channels:
            hv = self.latest_data['hv'].get(ch, {'v': 0, 'i': 0})
            self.graph_volt_data[ch].append(hv['v']); self.graph_curr_data[ch].append(hv['i'])
        if len(self.graph_time_data) > 1440:
            self.graph_time_data.pop(0)
            for i in range(self.num_sensors): self.graph_temp_data[i].pop(0); self.graph_humi_data[i].pop(0)
            for ch in self.hv_channels: self.graph_volt_data[ch].pop(0); self.graph_curr_data[ch].pop(0)
        for i in range(self.num_sensors):
            self.temp_curves[i].setData(self.graph_time_data, self.graph_temp_data[i], connect='finite')
            self.humi_curves[i].setData(self.graph_time_data, self.graph_humi_data[i], connect='finite')
        for ch in self.hv_channels:
            self.volt_curves[ch].setData(self.graph_time_data, self.graph_volt_data[ch])
            self.curr_curves[ch].setData(self.graph_time_data, self.graph_curr_data[ch])

    def update_arduino_data(self, idx, temp, humi):
        self.latest_data['sensors'][idx] = {'t': temp if temp is not None else np.nan, 'h': humi if humi is not None else np.nan}
        
    def update_caenhv_data(self, results):
        for _, ch, vmon, imon in results:
            self.latest_data['hv'][ch] = {'v': vmon, 'i': imon}
            
    def update_env_status(self, status): self.env_status_label.setText(status)
    def update_hv_status(self, status): self.hv_status_label.setText(status)
    def update_datetime(self): self.datetime_label.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

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

    def closeEvent(self, event):
        print("Closing application... saving remaining data.")
        self.log_data_buffer()
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
