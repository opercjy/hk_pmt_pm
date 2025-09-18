import sys, json, os, time, csv
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton, QDialog, QComboBox, QDoubleSpinBox
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QFont
import pyqtgraph as pg
import numpy as np
from worker_manager import WorkerManager

pg.setConfigOption('background', '#FFF8DC')
pg.setConfigOption('foreground', 'k')

class HVControlPanel(QDialog):
    control_signal = pyqtSignal(str, int, int, str, object)

    def __init__(self, channels, hv_params, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HV Control Panel")
        self.hv_params = hv_params
        self.layout = QGridLayout(self)
        
        self.channel_selector = QComboBox()
        self.channel_selector.addItems([str(ch) for ch in channels])
        self.voltage_input = QDoubleSpinBox(); self.voltage_input.setRange(0, 8000)
        self.current_input = QDoubleSpinBox(); self.current_input.setRange(0, 1000)
        self.set_voltage_btn = QPushButton("Set Voltage")
        self.set_current_btn = QPushButton("Set Current")
        self.power_on_btn = QPushButton("Turn ON")
        self.power_off_btn = QPushButton("Turn OFF")
        self.feedback_label = QLabel("Status: Ready")

        self.layout.addWidget(QLabel("Target Channel:"), 0, 0); self.layout.addWidget(self.channel_selector, 0, 1, 1, 2)
        self.layout.addWidget(QLabel("Set Voltage (V):"), 1, 0); self.layout.addWidget(self.voltage_input, 1, 1); self.layout.addWidget(self.set_voltage_btn, 1, 2)
        self.layout.addWidget(QLabel("Set Current (uA):"), 2, 0); self.layout.addWidget(self.current_input, 2, 1); self.layout.addWidget(self.set_current_btn, 2, 2)
        self.layout.addWidget(self.power_on_btn, 3, 0, 1, 3); self.layout.addWidget(self.power_off_btn, 4, 0, 1, 3)
        self.layout.addWidget(self.feedback_label, 5, 0, 1, 3)
        
        self.set_voltage_btn.clicked.connect(self.set_voltage)
        self.set_current_btn.clicked.connect(self.set_current)
        self.power_on_btn.clicked.connect(self.turn_on)
        self.power_off_btn.clicked.connect(self.turn_off)
        self.channel_selector.currentIndexChanged.connect(self.request_settings_for_channel)
    
    def get_ch(self): return int(self.channel_selector.currentText())
    def set_voltage(self): self.control_signal.emit('set_param', 0, self.get_ch(), self.hv_params['v_set'], self.voltage_input.value())
    def set_current(self): self.control_signal.emit('set_param', 0, self.get_ch(), self.hv_params['i_set'], self.current_input.value())
    def turn_on(self): self.control_signal.emit('set_param', 0, self.get_ch(), self.hv_params['pw'], 1)
    def turn_off(self): self.control_signal.emit('set_param', 0, self.get_ch(), self.hv_params['pw'], 0)
    def update_feedback(self, msg): self.feedback_label.setText(f"Status: {msg}")
    def request_settings_for_channel(self): self.control_signal.emit('fetch_settings', 0, self.get_ch(), '', '')

    def set_initial_values(self, settings):
        ch = self.get_ch()
        if ch in settings:
            self.voltage_input.setValue(settings[ch]['v_set'])
            self.current_input.setValue(settings[ch]['i_set'])

class MonitoringApp(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.num_sensors = len(config['arduino_settings']['sensors'])
        self.hv_channels = config['caen_hv_settings']['channels_to_monitor']
        self.latest_data = {'sensors': {}, 'hv': {}}
        self.data_buffer = []
        self.graph_time_data, self.graph_temp_data, self.graph_humi_data, self.graph_volt_data, self.graph_curr_data = [], {}, {}, {}, {}

        self.setup_ui()
        self.setup_logger()
        self.setup_timers()

        self.worker_manager = WorkerManager(self.config)
        self.worker_manager.arduino_data_ready.connect(self.update_arduino_data)
        self.worker_manager.caenhv_data_ready.connect(self.update_caenhv_data)
        self.worker_manager.arduino_status_changed.connect(lambda s: self.env_status_label.setText(s))
        self.worker_manager.caenhv_status_changed.connect(lambda s: self.hv_status_label.setText(s))
        self.worker_manager.hv_command_feedback.connect(self.on_hv_feedback)
        self.worker_manager.hv_initial_settings_ready.connect(self.on_hv_initial_settings_ready)
        self.worker_manager.start_workers()

    def setup_ui(self):
        self.setWindowTitle(self.config['ui_options']['window_title'])
        self.setGeometry(100, 100, 1600, 900)
        self.central_widget = QWidget(); self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        status_layout = QGridLayout(); self.main_layout.addLayout(status_layout)
        font = QFont(); font.setPointSize(14)
        
        self.env_status_label = QLabel("ENV Status: Standby"); self.env_status_label.setFont(font)
        self.hv_status_label = QLabel("HV Status: Standby"); self.hv_status_label.setFont(font)
        self.log_status_label = QLabel("Logging: Standby"); self.log_status_label.setFont(font)
        self.control_panel_btn = QPushButton("Open HV Control Panel"); self.control_panel_btn.setFont(font)
        status_layout.addWidget(self.env_status_label, 0, 0, 1, 2); status_layout.addWidget(self.hv_status_label, 0, 2, 1, 2)
        status_layout.addWidget(self.log_status_label, 0, 4, 1, 2); status_layout.addWidget(self.control_panel_btn, 0, 6, 1, 2)
        self.control_panel_btn.clicked.connect(self.open_control_panel)
        
        self.sensor_labels = {i: {'name': s['name'], 'temp': QLabel(f"{s['name']} T: -"), 'humi': QLabel(f"H: -")} for i, s in enumerate(self.config['arduino_settings']['sensors'])}
        for i, labels in self.sensor_labels.items(): status_layout.addWidget(labels['temp'], i + 1, 0, 1, 4); status_layout.addWidget(labels['humi'], i + 1, 4, 1, 4)

        self.hv_v_labels, self.hv_i_labels = {}, {}
        base_row = len(self.sensor_labels) + 1
        for i, ch in enumerate(self.hv_channels):
            self.hv_v_labels[ch] = QLabel(f"Ch{ch} V: -"); self.hv_i_labels[ch] = QLabel(f"Ch{ch} I: -")
            row, col = divmod(i, 4)
            status_layout.addWidget(self.hv_v_labels[ch], base_row + row, col*2); status_layout.addWidget(self.hv_i_labels[ch], base_row + row, col*2 + 1)

        graph_layout = QGridLayout(); self.main_layout.addLayout(graph_layout)
        plots = {k: pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')}) for k in ['temp', 'humi', 'volt', 'curr']}
        for p in plots.values(): p.addLegend()
        graph_layout.addWidget(plots['temp'], 0, 0); graph_layout.addWidget(plots['humi'], 0, 1)
        graph_layout.addWidget(plots['volt'], 1, 0); graph_layout.addWidget(plots['curr'], 1, 1)
        plots['temp'].setTitle("Temperature"); plots['humi'].setTitle("Humidity"); plots['volt'].setTitle("HV Voltage"); plots['curr'].setTitle("HV Current")
        
        self.temp_curves, self.humi_curves, self.volt_curves, self.curr_curves = {}, {}, {}, {}
        for i, s in enumerate(self.config['arduino_settings']['sensors']): self.temp_curves[i] = plots['temp'].plot(pen=(i, self.num_sensors*1.3), name=s['name']); self.humi_curves[i] = plots['humi'].plot(pen=(i, self.num_sensors*1.3), name=s['name'])
        for i, ch in enumerate(self.hv_channels): self.volt_curves[ch] = plots['volt'].plot(pen=(i, len(self.hv_channels)*1.3), name=f'Ch{ch}'); self.curr_curves[ch] = plots['curr'].plot(pen=(i, len(self.hv_channels)*1.3), name=f'Ch{ch}')

    def setup_logger(self):
        log_cfg = self.config['logging_options']
        log_filename = f"{log_cfg['log_file_prefix']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.log_file_path = log_filename
        header = ['Timestamp']
        for s in self.config['arduino_settings']['sensors']: header.extend([f'{s["name"]}_T', f'{s["name"]}_H'])
        for ch in self.hv_channels: header.extend([f'Ch{ch}_V', f'Ch{ch}_I'])
        with open(self.log_file_path, 'w', newline='') as f: csv.writer(f).writerow(header)

    def setup_timers(self):
        ui_cfg = self.config['ui_options']; log_cfg = self.config['logging_options']
        self.indicator_timer = QTimer(self); self.indicator_timer.timeout.connect(self.update_indicators); self.indicator_timer.start(ui_cfg['indicator_update_interval_ms'])
        self.graph_timer = QTimer(self); self.graph_timer.timeout.connect(self.update_graphs); self.graph_timer.start(ui_cfg['graph_update_interval_ms'])
        self.capture_timer = QTimer(self); self.capture_timer.timeout.connect(self.capture_data_point); self.capture_timer.start(log_cfg['capture_interval_ms'])
        self.log_timer = QTimer(self); self.log_timer.timeout.connect(self.log_data_buffer); self.log_timer.start(log_cfg['bulk_write_interval_ms'])

    def update_arduino_data(self, idx, temp, humi): self.latest_data['sensors'][idx] = {'t': temp, 'h': humi}
    def update_caenhv_data(self, results):
        for _, ch, vmon, imon in results: self.latest_data['hv'][ch] = {'v': vmon, 'i': imon}

    def update_indicators(self):
        for i, data in self.latest_data['sensors'].items():
            self.sensor_labels[i]['temp'].setText(f"{self.sensor_labels[i]['name']} T: {data['t']:.2f} C" if data['t'] is not None else "T: Error")
            self.sensor_labels[i]['humi'].setText(f"H: {data['h']:.2f} %" if data['h'] is not None else "H: Error")
        for ch, data in self.latest_data['hv'].items():
            self.hv_v_labels[ch].setText(f"Ch{ch} V: {data['v']:.2f}" if not np.isnan(data['v']) else f"Ch{ch} V: Error")
            self.hv_i_labels[ch].setText(f"Ch{ch} I: {data['i']:.4f}" if not np.isnan(data['i']) else f"Ch{ch} I: Error")
        self.log_status_label.setText(f"Logging: {len(self.data_buffer)} points buffered")

    def update_graphs(self):
        ts = time.time(); self.graph_time_data.append(ts)
        max_points = 1440 # 24 hours of data
        if len(self.graph_time_data) > max_points: self.graph_time_data.pop(0)
        
        for i in range(self.num_sensors):
            data = self.latest_data['sensors'].get(i, {'t': np.nan, 'h': np.nan})
            d_list = self.graph_temp_data.setdefault(i, []); d_list.append(data['t']); self.temp_curves[i].setData(self.graph_time_data, d_list, connect='finite')
            if len(d_list) > max_points: d_list.pop(0)
            d_list = self.graph_humi_data.setdefault(i, []); d_list.append(data['h']); self.humi_curves[i].setData(self.graph_time_data, d_list, connect='finite')
            if len(d_list) > max_points: d_list.pop(0)
        for ch in self.hv_channels:
            data = self.latest_data['hv'].get(ch, {'v': np.nan, 'i': np.nan})
            d_list = self.graph_volt_data.setdefault(ch, []); d_list.append(data['v']); self.volt_curves[ch].setData(self.graph_time_data, d_list, connect='finite')
            if len(d_list) > max_points: d_list.pop(0)
            d_list = self.graph_curr_data.setdefault(ch, []); d_list.append(data['i']); self.curr_curves[ch].setData(self.graph_time_data, d_list, connect='finite')
            if len(d_list) > max_points: d_list.pop(0)

    def capture_data_point(self): self.data_buffer.append({'ts': datetime.now().isoformat(), 'sensors': self.latest_data['sensors'].copy(), 'hv': self.latest_data['hv'].copy()})
    
    def log_data_buffer(self):
        if not self.data_buffer: return
        buffer_copy, self.data_buffer = self.data_buffer, []
        try:
            with open(self.log_file_path, 'a', newline='') as f:
                writer = csv.writer(f)
                for item in buffer_copy:
                    row = [item['ts']]
                    for i in range(self.num_sensors): row.extend([item['sensors'].get(i, {}).get('t'), item['sensors'].get(i, {}).get('h')])
                    for ch in self.hv_channels: row.extend([item['hv'].get(ch, {}).get('v'), item['hv'].get(ch, {}).get('i')])
                    writer.writerow(row)
        except IOError: self.data_buffer = buffer_copy + self.data_buffer

    def open_control_panel(self):
        if not hasattr(self, 'control_panel'):
            hv_params = self.config['caen_hv_settings']['parameters']
            self.control_panel = HVControlPanel(self.hv_channels, hv_params, self)
            self.control_panel.control_signal.connect(self.worker_manager.queue_hv_command)
        self.control_panel.show(); self.control_panel.raise_()
        self.control_panel.request_settings_for_channel()

    def on_hv_feedback(self, msg):
        if hasattr(self, 'control_panel'): self.control_panel.update_feedback(msg)
    
    def on_hv_initial_settings_ready(self, settings):
        if hasattr(self, 'control_panel'): self.control_panel.set_initial_values(settings)

    def closeEvent(self, event):
        self.log_data_buffer()
        self.worker_manager.stop_workers()
        event.accept()

def load_config(config_file):
    with open(config_file, 'r', encoding='utf-8') as f: return json.load(f)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    default_config = 'config.json'
    config_file = sys.argv[1] if len(sys.argv) > 1 else default_config
    if not os.path.exists(config_file):
        print(f"Error: Config file '{config_file}' not found.")
        sys.exit(1)
    config = load_config(config_file)
    window = MonitoringApp(config)
    window.show()
    sys.exit(app.exec_())
