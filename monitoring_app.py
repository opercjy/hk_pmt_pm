import sys, json, os, time, signal, sqlite3
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton, QDialog, QComboBox, QDoubleSpinBox, QTabWidget, QDateTimeEdit, QFileDialog
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QDateTime
import pyqtgraph as pg
import numpy as np
from worker_manager import WorkerManager
from database_manager import DatabaseManager

pg.setConfigOption('background', '#FFF8DC')
pg.setConfigOption('foreground', 'k')

# HVControlPanel class (as before, no changes needed)
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
        self.latest_data = {'sensors': {}, 'hv': {}}
        
        self.db_manager = DatabaseManager(f"{config['logging_options']['log_file_prefix']}.db", config)
        self.worker_manager = WorkerManager(self.config)
        
        self.setup_ui()
        self.connect_signals()
        self.setup_timers()
        
        self.worker_manager.start_workers()

    def setup_ui(self):
        self.setWindowTitle(self.config['ui_options']['window_title'])
        self.setGeometry(100, 100, 1600, 900)
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.monitor_tab = QWidget()
        self.analysis_tab = QWidget()
        self.tabs.addTab(self.monitor_tab, "실시간 모니터")
        self.tabs.addTab(self.analysis_tab, "데이터 분석")
        self.setup_monitor_ui()
        self.setup_analysis_ui()

    def setup_monitor_ui(self):
        layout = QVBoxLayout(self.monitor_tab)
        # Status UI (as before)
        status_layout = QGridLayout()
        font = QFont(); font.setPointSize(14)
        self.env_status_label = QLabel("ENV Status: Standby"); self.env_status_label.setFont(font)
        self.hv_status_label = QLabel("HV Status: Standby"); self.hv_status_label.setFont(font)
        self.control_panel_btn = QPushButton("Open HV Control Panel"); self.control_panel_btn.setFont(font)
        status_layout.addWidget(self.env_status_label, 0, 0); status_layout.addWidget(self.hv_status_label, 0, 1)
        status_layout.addWidget(self.control_panel_btn, 0, 2)
        self.sensor_labels = {i: {'name': s['name'], 'temp': QLabel(f"{s['name']} T: -"), 'humi': QLabel(f"H: -")} for i, s in enumerate(self.config['arduino_settings']['sensors'])}
        for i, labels in self.sensor_labels.items(): status_layout.addWidget(labels['temp'], i+1, 0); status_layout.addWidget(labels['humi'], i+1, 1)
        self.hv_v_labels, self.hv_i_labels = {}, {}
        base_row = len(self.sensor_labels) + 1
        for i, ch in enumerate(self.config['caen_hv_settings']['channels_to_monitor']):
            self.hv_v_labels[ch] = QLabel(f"Ch{ch} V: -"); self.hv_i_labels[ch] = QLabel(f"Ch{ch} I: -")
            row, col = divmod(i, 4)
            status_layout.addWidget(self.hv_v_labels[ch], base_row + row, col*2); status_layout.addWidget(self.hv_i_labels[ch], base_row + row, col*2 + 1)
        # Graph UI (as before)
        graph_layout = QGridLayout()
        plots = {k: pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')}) for k in ['temp', 'humi', 'volt', 'curr']}
        for p in plots.values(): p.addLegend()
        graph_layout.addWidget(plots['temp'], 0, 0); graph_layout.addWidget(plots['humi'], 0, 1)
        graph_layout.addWidget(plots['volt'], 1, 0); graph_layout.addWidget(plots['curr'], 1, 1)
        self.temp_curves, self.humi_curves, self.volt_curves, self.curr_curves = {}, {}, {}, {}
        for i, s in enumerate(self.config['arduino_settings']['sensors']): self.temp_curves[i] = plots['temp'].plot(pen=(i, 5), name=s['name']); self.humi_curves[i] = plots['humi'].plot(pen=(i,5), name=s['name'])
        for i, ch in enumerate(self.config['caen_hv_settings']['channels_to_monitor']): self.volt_curves[ch] = plots['volt'].plot(pen=(i,8), name=f'Ch{ch}'); self.curr_curves[ch] = plots['curr'].plot(pen=(i,8), name=f'Ch{ch}')
        layout.addLayout(status_layout); layout.addLayout(graph_layout)

    def setup_analysis_ui(self):
        layout = QVBoxLayout(self.analysis_tab)
        control_layout = QGridLayout()
        self.start_time_edit = QDateTimeEdit(QDateTime.currentDateTime().addDays(-1))
        self.end_time_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.load_data_btn = QPushButton("데이터 불러오기")
        self.export_csv_btn = QPushButton("CSV로 내보내기")
        control_layout.addWidget(QLabel("Start:"), 0, 0); control_layout.addWidget(self.start_time_edit, 0, 1)
        control_layout.addWidget(QLabel("End:"), 0, 2); control_layout.addWidget(self.end_time_edit, 0, 3)
        control_layout.addWidget(self.load_data_btn, 0, 4); control_layout.addWidget(self.export_csv_btn, 0, 5)
        self.analysis_plot = pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')})
        self.analysis_plot.addLegend()
        layout.addLayout(control_layout); layout.addWidget(self.analysis_plot)
        self.load_data_btn.clicked.connect(self.load_and_plot_data)

    def connect_signals(self):
        self.worker_manager.arduino_data_ready.connect(self.update_arduino_data)
        self.worker_manager.caenhv_data_ready.connect(self.update_caenhv_data)
        self.worker_manager.arduino_status_changed.connect(lambda s: self.env_status_label.setText(s))
        self.worker_manager.caenhv_status_changed.connect(lambda s: self.hv_status_label.setText(s))
        self.worker_manager.hv_command_feedback.connect(self.on_hv_feedback)
        self.worker_manager.hv_initial_settings_ready.connect(self.on_hv_initial_settings_ready)
        self.control_panel_btn.clicked.connect(self.open_control_panel)
    
    def setup_timers(self):
        self.indicator_timer = QTimer(self); self.indicator_timer.timeout.connect(self.update_indicators); self.indicator_timer.start(2000)
        self.graph_timer = QTimer(self); self.graph_timer.timeout.connect(self.update_graphs); self.graph_timer.start(60000)
        self.capture_timer = QTimer(self); self.capture_timer.timeout.connect(self.capture_data_point); self.capture_timer.start(60000)

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
    
    def update_graphs(self):
        # This function updates the real-time graph, logic remains similar
        pass

    def capture_data_point(self):
        data_point = {'ts': datetime.now().isoformat(), 'sensors': self.latest_data['sensors'].copy(), 'hv': self.latest_data['hv'].copy()}
        self.db_manager.log_data(data_point)
    
    def load_and_plot_data(self):
        start_str = self.start_time_edit.dateTime().toString(Qt.ISODate)
        end_str = self.end_time_edit.dateTime().toString(Qt.ISODate)
        timestamps, data = self.db_manager.fetch_data_range(start_str, end_str)
        
        self.analysis_plot.clear()
        self.analysis_plot.addLegend()
        if not timestamps: return

        pen_index = 0
        for col_name, values in data.items():
            if col_name != 'timestamp' and any(v is not None for v in values):
                self.analysis_plot.plot(timestamps, values, pen=(pen_index, 10), name=col_name)
                pen_index += 1

    def open_control_panel(self):
        if not hasattr(self, 'control_panel'):
            hv_params = self.config['caen_hv_settings']['parameters']
            self.control_panel = HVControlPanel(self.config['caen_hv_settings']['channels_to_monitor'], hv_params, self)
            self.control_panel.control_signal.connect(self.worker_manager.queue_hv_command)
        self.control_panel.show(); self.control_panel.raise_()
        self.control_panel.request_settings_for_channel()
    
    def on_hv_feedback(self, msg):
        if hasattr(self, 'control_panel'): self.control_panel.update_feedback(msg)
    def on_hv_initial_settings_ready(self, settings):
        if hasattr(self, 'control_panel'): self.control_panel.set_initial_values(settings)

    def closeEvent(self, event):
        print("Shutting down...")
        self.worker_manager.stop_workers()
        self.db_manager.close()
        event.accept()

def load_config(config_file):
    with open(config_file, 'r', encoding='utf-8') as f: return json.load(f)

if __name__ == '__main__':
    # --- Graceful exit on Ctrl+C ---
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    
    default_config = 'config.json'
    config_file = sys.argv[1] if len(sys.argv) > 1 else default_config
    if not os.path.exists(config_file):
        print(f"Error: Config file '{config_file}' not found.")
        sys.exit(1)
        
    config = load_config(config_file)
    window = MonitoringApp(config)
    window.show()
    
    # --- Timer for signal handling ---
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    sys.exit(app.exec_())
