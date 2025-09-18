import sys, json, os, time, signal, sqlite3, csv
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton, QDialog, QComboBox, QDoubleSpinBox, QTabWidget, QDateTimeEdit, QFileDialog, QCheckBox
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QDateTime
from PyQt5.QtGui import QFont
import pyqtgraph as pg
import numpy as np
from worker_manager import WorkerManager
from database_manager import DatabaseManager

class HVControlPanel(QDialog):
    control_signal = pyqtSignal(str, int, int, str, object)
    def __init__(self, channels, hv_params, styles, parent=None):
        super().__init__(parent); self.setWindowTitle("HV Control Panel"); self.hv_params = hv_params
        self.setStyleSheet(f"background-color: {styles['background_color']}; color: {styles['font_color_main']};")
        self.layout = QGridLayout(self)
        font = QFont(); font.setPointSize(styles['font_size_medium'])
        feedback_font = QFont(); feedback_font.setPointSize(styles['font_size_large']); feedback_font.setBold(True)
        self.channel_selector = QComboBox(); self.channel_selector.setFont(font)
        self.channel_selector.addItems([str(ch) for ch in channels])
        self.voltage_input = QDoubleSpinBox(); self.voltage_input.setRange(0, 8000); self.voltage_input.setFont(font)
        self.current_input = QDoubleSpinBox(); self.current_input.setRange(0, 1000); self.current_input.setFont(font)
        self.set_voltage_btn, self.set_current_btn = QPushButton("Set Voltage"), QPushButton("Set Current")
        self.set_voltage_btn.setFont(font); self.set_current_btn.setFont(font)
        self.power_on_btn, self.power_off_btn = QPushButton("Turn ON"), QPushButton("Turn OFF")
        self.power_on_btn.setFont(font); self.power_on_btn.setStyleSheet("background-color: lightgreen;")
        self.power_off_btn.setFont(font); self.power_off_btn.setStyleSheet("background-color: lightcoral;")
        self.feedback_label = QLabel("Status: Ready"); self.feedback_label.setFont(feedback_font)
        for label_text, widget, row in [("Target Channel:", self.channel_selector, 0), ("Set Voltage (V):", self.voltage_input, 1), ("Set Current (uA):", self.current_input, 2)]:
            label = QLabel(label_text); label.setFont(font); self.layout.addWidget(label, row, 0)
            if widget in [self.voltage_input, self.current_input]: self.layout.addWidget(widget, row, 1)
            else: self.layout.addWidget(widget, row, 1, 1, 2)
        self.layout.addWidget(self.set_voltage_btn, 1, 2); self.layout.addWidget(self.set_current_btn, 2, 2)
        self.layout.addWidget(self.power_on_btn, 3, 0, 1, 3); self.layout.addWidget(self.power_off_btn, 4, 0, 1, 3)
        self.layout.addWidget(self.feedback_label, 5, 0, 1, 3)
        self.set_voltage_btn.clicked.connect(self.set_voltage); self.set_current_btn.clicked.connect(self.set_current)
        self.power_on_btn.clicked.connect(self.turn_on); self.power_off_btn.clicked.connect(self.turn_off)
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
        if ch in settings: self.voltage_input.setValue(settings[ch]['v_set']); self.current_input.setValue(settings[ch]['i_set'])

class MonitoringApp(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config = config; self.styles = config['ui_styles']
        self.latest_data = {'sensors': {}, 'hv': {}}
        self.graph_data = {'time': [], 'temp': {}, 'humi': {}, 'volt': {}, 'curr': {}}
        self.is_dual_current = 'i_mon_low' in self.config['caen_hv_settings']['parameters']
        pg.setConfigOption('background', self.styles['background_color']); pg.setConfigOption('foreground', self.styles['font_color_main'])
        self.plot_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        self._is_closing = False
        self.db_manager = DatabaseManager(f"{config['logging_options']['log_file_prefix']}.db", config)
        self.worker_manager = WorkerManager(self.config)
        self.setup_ui(); self.connect_signals(); self.setup_timers()
        self.worker_manager.start_workers()

    def setup_ui(self):
        self.setWindowTitle(self.config['ui_options']['window_title']); self.setGeometry(100, 100, 1800, 950)
        self.setStyleSheet(f"background-color: {self.styles['background_color']};")
        self.tabs = QTabWidget(); self.setCentralWidget(self.tabs)
        self.monitor_tab = QWidget(); self.analysis_tab = QWidget()
        self.tabs.addTab(self.monitor_tab, "실시간 모니터"); self.tabs.addTab(self.analysis_tab, "데이터 분석")
        self.setup_monitor_ui(); self.setup_analysis_ui()

    def setup_monitor_ui(self):
        main_layout = QVBoxLayout(self.monitor_tab); status_layout = QGridLayout(); font_large = QFont(); font_large.setPointSize(self.styles['font_size_large'])
        self.env_status_label = QLabel("ENV Status:"); self.hv_status_label = QLabel("Connecting to HV...")
        self.log_status_label = QLabel("Logging: 0 point(s) collected"); self.control_panel_btn = QPushButton("Open HV Control Panel")
        for widget in [self.env_status_label, self.hv_status_label, self.log_status_label, self.control_panel_btn]: widget.setFont(font_large)
        status_layout.addWidget(self.env_status_label, 0, 0, 1, 4); status_layout.addWidget(self.hv_status_label, 0, 4, 1, 4)
        status_layout.addWidget(self.log_status_label, 0, 8, 1, 4); status_layout.addWidget(self.control_panel_btn, 0, 12, 1, 4)
        self.sensor_labels = {i: {'name': s['name'], 'temp': QLabel(f"{s['name']} T: None"), 'humi': QLabel(f"H: None")} for i, s in enumerate(self.config['arduino_settings']['sensors'])}
        for i, labels in self.sensor_labels.items():
            labels['temp'].setFont(font_large); labels['humi'].setFont(font_large)
            labels['temp'].setStyleSheet(f"color: {self.styles['font_color_sensor']};"); labels['humi'].setStyleSheet(f"color: {self.styles['font_color_sensor']};")
            row, col = divmod(i, 2); status_layout.addWidget(labels['temp'], row + 1, col * 8, 1, 4); status_layout.addWidget(labels['humi'], row + 1, col * 8 + 4, 1, 4)
        self.hv_labels = {}
        base_row, headers_added = 3, False
        for i, ch in enumerate(self.config['caen_hv_settings']['channels_to_monitor']):
            if not headers_added:
                volt_header = QLabel("Voltage (V):"); volt_header.setFont(font_large); volt_header.setStyleSheet(f"color: {self.styles['font_color_voltage']}; font-weight: bold;"); status_layout.addWidget(volt_header, base_row, 0, 1, 2)
                if self.is_dual_current:
                    curH_header = QLabel("Current H (uA):"); curL_header = QLabel("Current L (uA):")
                    for h in [curH_header, curL_header]: h.setFont(font_large); h.setStyleSheet(f"color: {self.styles['font_color_current']}; font-weight: bold;")
                    status_layout.addWidget(curH_header, base_row + 1, 0, 1, 2); status_layout.addWidget(curL_header, base_row + 2, 0, 1, 2)
                else:
                    cur_header = QLabel("Current (uA):"); cur_header.setFont(font_large); cur_header.setStyleSheet(f"color: {self.styles['font_color_current']}; font-weight: bold;"); status_layout.addWidget(cur_header, base_row + 1, 0, 1, 2)
                headers_added = True
            self.hv_labels[ch] = {'v': QLabel("-"), 'i': QLabel("-"), 'il': QLabel("-"), 'ih': QLabel("-")}
            for label in self.hv_labels[ch].values(): label.setFont(font_large)
            self.hv_labels[ch]['v'].setStyleSheet(f"color: {self.styles['font_color_voltage']};"); self.hv_labels[ch]['i'].setStyleSheet(f"color: {self.styles['font_color_current']};"); self.hv_labels[ch]['il'].setStyleSheet(f"color: {self.styles['font_color_current']};"); self.hv_labels[ch]['ih'].setStyleSheet(f"color: {self.styles['font_color_current']};")
            col_offset = (i * 2) + 2; status_layout.addWidget(QLabel(f"Ch{ch}:"), base_row, col_offset); status_layout.addWidget(self.hv_labels[ch]['v'], base_row, col_offset+1)
            if self.is_dual_current:
                status_layout.addWidget(QLabel(f"Ch{ch}:"), base_row + 1, col_offset); status_layout.addWidget(self.hv_labels[ch]['ih'], base_row + 1, col_offset+1); status_layout.addWidget(QLabel(f"Ch{ch}:"), base_row + 2, col_offset); status_layout.addWidget(self.hv_labels[ch]['il'], base_row + 2, col_offset+1)
            else: status_layout.addWidget(QLabel(f"Ch{ch}:"), base_row + 1, col_offset); status_layout.addWidget(self.hv_labels[ch]['i'], base_row + 1, col_offset+1)
        graph_widget = QWidget(); graph_layout = QGridLayout(graph_widget)
        self.monitor_plots = {k: pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')}) for k in ['temp', 'humi', 'volt', 'curr']}
        for p in self.monitor_plots.values(): p.addLegend()
        self.monitor_plots['temp'].setTitle("Temperature"); self.monitor_plots['humi'].setTitle("Humidity"); self.monitor_plots['volt'].setTitle("HV Voltage"); self.monitor_plots['curr'].setTitle("HV Current")
        graph_layout.addWidget(self.monitor_plots['temp'], 0, 0); graph_layout.addWidget(self.monitor_plots['humi'], 0, 1); graph_layout.addWidget(self.monitor_plots['volt'], 1, 0); graph_layout.addWidget(self.monitor_plots['curr'], 1, 1)
        self.monitor_curves = {'temp': {}, 'humi': {}, 'volt': {}, 'curr': {}}
        for i, s in enumerate(self.config['arduino_settings']['sensors']):
            pen = pg.mkPen(color=self.plot_colors[i % len(self.plot_colors)], width=3); self.monitor_curves['temp'][i] = self.monitor_plots['temp'].plot(pen=pen, name=s['name']); self.monitor_curves['humi'][i] = self.monitor_plots['humi'].plot(pen=pen, name=s['name'])
        for i, ch in enumerate(self.config['caen_hv_settings']['channels_to_monitor']):
            pen = pg.mkPen(color=self.plot_colors[i % len(self.plot_colors)], width=3); self.monitor_curves['volt'][ch] = self.monitor_plots['volt'].plot(pen=pen, name=f'Ch{ch}'); self.monitor_curves['curr'][ch] = self.monitor_plots['curr'].plot(pen=pen, name=f'Ch{ch}')
        bottom_layout = QGridLayout(); font_medium = QFont(); font_medium.setPointSize(self.styles['font_size_medium'])
        self.shifter_label = QLabel(self.config['ui_options'].get('shifter_name', '')); self.shifter_label.setFont(font_medium)
        self.datetime_label = QLabel(""); self.datetime_label.setFont(font_medium); self.datetime_label.setAlignment(Qt.AlignRight)
        bottom_layout.addWidget(self.shifter_label, 0, 0); bottom_layout.addWidget(self.datetime_label, 0, 1)
        main_layout.addLayout(status_layout); main_layout.addWidget(graph_widget); main_layout.addLayout(bottom_layout)

    def setup_analysis_ui(self):
        layout = QVBoxLayout(self.analysis_tab); control_layout = QGridLayout(); font_large = QFont(); font_large.setPointSize(self.styles['font_size_large'])
        self.start_time_edit = QDateTimeEdit(QDateTime.currentDateTime().addDays(-7)); self.start_time_edit.setFont(font_large)
        self.end_time_edit = QDateTimeEdit(QDateTime.currentDateTime()); self.end_time_edit.setFont(font_large)
        self.load_data_btn = QPushButton("데이터 불러오기"); self.load_data_btn.setFont(font_large)
        self.export_csv_btn = QPushButton("선택 항목 CSV로 내보내기"); self.export_csv_btn.setFont(font_large)
        control_layout.addWidget(QLabel("Start:"), 0, 0); control_layout.addWidget(self.start_time_edit, 0, 1); control_layout.addWidget(QLabel("End:"), 0, 2); control_layout.addWidget(self.end_time_edit, 0, 3)
        control_layout.addWidget(self.load_data_btn, 0, 4); control_layout.addWidget(self.export_csv_btn, 0, 5)
        self.analysis_checkboxes = {}
        checkbox_widget = QWidget(); checkbox_layout = QGridLayout(checkbox_widget)
        btn_all = QPushButton("전체 선택"); btn_none = QPushButton("전체 해제")
        checkbox_layout.addWidget(btn_all, 0, 0); checkbox_layout.addWidget(btn_none, 0, 1)
        col_count = 12; row_idx, col_idx = 1, 0
        db_cols = self.db_manager._get_expected_columns()
        for col_def in db_cols:
            col_name = col_def.split()[0]; cb = QCheckBox(col_name); cb.setFont(font_large); self.analysis_checkboxes[col_name] = cb
            checkbox_layout.addWidget(cb, row_idx, col_idx); col_idx += 1
            if col_idx >= col_count: col_idx = 0; row_idx += 1
        btn_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self.analysis_checkboxes.values()]); btn_none.clicked.connect(lambda: [cb.setChecked(False) for cb in self.analysis_checkboxes.values()])
        self.analysis_plots_widget = QWidget(); graph_layout = QGridLayout(self.analysis_plots_widget)
        self.analysis_plots = {k: pg.PlotWidget(axisItems={'bottom': pg.DateAxisItem(orientation='bottom')}) for k in ['temp', 'humi', 'volt', 'curr']}
        for p in self.analysis_plots.values(): p.addLegend()
        self.analysis_plots['temp'].setTitle("Temperature History"); self.analysis_plots['humi'].setTitle("Humidity History"); self.analysis_plots['volt'].setTitle("HV Voltage History"); self.analysis_plots['curr'].setTitle("HV Current History")
        graph_layout.addWidget(self.analysis_plots['temp'], 0, 0); graph_layout.addWidget(self.analysis_plots['humi'], 0, 1); graph_layout.addWidget(self.analysis_plots['volt'], 1, 0); graph_layout.addWidget(self.analysis_plots['curr'], 1, 1)
        layout.addLayout(control_layout); layout.addWidget(checkbox_widget); layout.addWidget(self.analysis_plots_widget)
        self.load_data_btn.clicked.connect(self.load_and_plot_data); self.export_csv_btn.clicked.connect(self.export_analysis_to_csv)

    def connect_signals(self):
        self.worker_manager.arduino_data_ready.connect(self.update_arduino_data); self.worker_manager.caenhv_data_ready.connect(self.update_caenhv_data)
        self.worker_manager.arduino_status_changed.connect(lambda s: self.env_status_label.setText(f"ENV Status: {s}")); self.worker_manager.caenhv_status_changed.connect(self.hv_status_label.setText)
        self.worker_manager.hv_command_feedback.connect(self.on_hv_feedback); self.worker_manager.hv_initial_settings_ready.connect(self.on_hv_initial_settings_ready)
        self.control_panel_btn.clicked.connect(self.open_control_panel); self.worker_manager.shutdown_complete.connect(self.close)
    
    def setup_timers(self):
        self.indicator_timer = QTimer(self); self.indicator_timer.timeout.connect(self.update_indicators); self.indicator_timer.start(2000)
        self.capture_timer = QTimer(self); self.capture_timer.timeout.connect(self.capture_data_point); self.capture_timer.start(60000)
        self.graph_timer = QTimer(self); self.graph_timer.timeout.connect(self.update_graphs); self.graph_timer.start(60000)
        self.datetime_timer = QTimer(self); self.datetime_timer.timeout.connect(lambda: self.datetime_label.setText(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))); self.datetime_timer.start(1000)

    def update_arduino_data(self, idx, temp, humi): self.latest_data['sensors'][idx] = {'t': np.nan if temp is None else temp, 'h': np.nan if humi is None else humi}
    def update_caenhv_data(self, results):
        for data_dict in results:
            ch = data_dict['ch']; self.latest_data['hv'][ch] = data_dict
            for key in ['v', 'i', 'il', 'ih']:
                if key in self.latest_data['hv'][ch] and self.latest_data['hv'][ch][key] is None: self.latest_data['hv'][ch][key] = np.nan

    def update_indicators(self):
        for i, data in self.latest_data['sensors'].items():
            self.sensor_labels[i]['temp'].setText(f"{self.sensor_labels[i]['name']} T: {data.get('t'):.2f} C" if not np.isnan(data.get('t', np.nan)) else f"{self.sensor_labels[i]['name']} T: None")
            self.sensor_labels[i]['humi'].setText(f"H: {data.get('h'):.2f} %" if not np.isnan(data.get('h', np.nan)) else f"H: None")
        for ch, data in self.latest_data['hv'].items():
            self.hv_labels[ch]['v'].setText(f"{data.get('v', 0):.2f}")
            if self.is_dual_current: self.hv_labels[ch]['il'].setText(f"{data.get('il', 0):.4f}"); self.hv_labels[ch]['ih'].setText(f"{data.get('ih', 0):.4f}")
            else: self.hv_labels[ch]['i'].setText(f"{data.get('i', 0):.4f}")

    def update_graphs(self):
        ts = time.time(); self.graph_data['time'].append(ts); max_points = 1440 
        if len(self.graph_data['time']) > max_points: self.graph_data['time'].pop(0)
        for i, s_info in enumerate(self.config['arduino_settings']['sensors']):
            data = self.latest_data['sensors'].get(i, {'t': np.nan, 'h': np.nan})
            for key, curve_dict in [('t', 'temp'), ('h', 'humi')]:
                d_list = self.graph_data[curve_dict].setdefault(i, []); d_list.append(data.get(key, np.nan))
                if len(d_list) > max_points: d_list.pop(0)
                self.monitor_curves[curve_dict][i].setData(self.graph_data['time'], d_list, connect='finite')
        for ch in self.config['caen_hv_settings']['channels_to_monitor']:
            data = self.latest_data['hv'].get(ch, {})
            volt_list = self.graph_data['volt'].setdefault(ch, []); volt_list.append(data.get('v', np.nan))
            if len(volt_list) > max_points: volt_list.pop(0)
            self.monitor_curves['volt'][ch].setData(self.graph_data['time'], volt_list, connect='finite')
            current_val = data.get('ih', np.nan) if self.is_dual_current else data.get('i', np.nan)
            curr_list = self.graph_data['curr'].setdefault(ch, []); curr_list.append(current_val)
            if len(curr_list) > max_points: curr_list.pop(0)
            self.monitor_curves['curr'][ch].setData(self.graph_data['time'], curr_list, connect='finite')

    def capture_data_point(self):
        if self._is_closing: return
        data_point = {'ts': datetime.now().isoformat(), 'sensors': self.latest_data['sensors'].copy(), 'hv': self.latest_data['hv'].copy()}
        self.db_manager.log_data(data_point)
        cursor = self.db_manager.conn.cursor(); cursor.execute("SELECT COUNT(*) FROM monitoring_data"); count = cursor.fetchone()[0]
        self.log_status_label.setText(f"Logging: {count} point(s) collected")

    def load_and_plot_data(self):
        start_str = self.start_time_edit.dateTime().toString(Qt.ISODate); end_str = self.end_time_edit.dateTime().toString(Qt.ISODate)
        timestamps, data = self.db_manager.fetch_data_range(start_str, end_str)
        for plot in self.analysis_plots.values(): plot.clear(); plot.addLegend()
        if not timestamps: return
        selected_cols = [name for name, cb in self.analysis_checkboxes.items() if cb.isChecked()]
        color_idx = 0
        for name in selected_cols:
            if name not in data or all(v is None for v in data[name]): continue
            values = data[name]; pen = pg.mkPen(color=self.plot_colors[color_idx % len(self.plot_colors)], width=3)
            if '_T' in name: self.analysis_plots['temp'].plot(timestamps, values, pen=pen, name=name.replace('_', ' '))
            elif '_H' in name: self.analysis_plots['humi'].plot(timestamps, values, pen=pen, name=name.replace('_', ' '))
            elif '_V' in name: self.analysis_plots['volt'].plot(timestamps, values, pen=pen, name=name.replace('_', ' '))
            elif '_I' in name: self.analysis_plots['curr'].plot(timestamps, values, pen=pen, name=name.replace('_', ' '))
            color_idx += 1

    def export_analysis_to_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "CSV Files (*.csv)")
        if not path: return
        start_str = self.start_time_edit.dateTime().toString(Qt.ISODate); end_str = self.end_time_edit.dateTime().toString(Qt.ISODate)
        _, data = self.db_manager.fetch_data_range(start_str, end_str)
        if not data or not data.get('timestamp'): return
        selected_cols = ['timestamp'] + [name for name, cb in self.analysis_checkboxes.items() if cb.isChecked()]
        with open(path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([col for col in selected_cols if col in data])
            num_rows = len(data['timestamp'])
            for i in range(num_rows):
                row = [data[col][i] for col in selected_cols if col in data]
                writer.writerow(row)

    def open_control_panel(self):
        if not hasattr(self, 'control_panel'):
            hv_params = self.config['caen_hv_settings']['parameters']
            self.control_panel = HVControlPanel(self.config['caen_hv_settings']['channels_to_monitor'], hv_params, self.styles, self)
            self.control_panel.control_signal.connect(self.worker_manager.queue_hv_command)
        self.control_panel.show(); self.control_panel.raise_(); self.control_panel.request_settings_for_channel()
    
    def on_hv_feedback(self, msg):
        if hasattr(self, 'control_panel'): self.control_panel.update_feedback(msg)
    def on_hv_initial_settings_ready(self, settings):
        if hasattr(self, 'control_panel'): self.control_panel.set_initial_values(settings)

    def closeEvent(self, event):
        if self._is_closing: event.accept(); return
        print("Close button pressed. Initiating shutdown...")
        self._is_closing = True; event.ignore(); self.setEnabled(False)
        for timer in [self.indicator_timer, self.capture_timer, self.graph_timer, self.datetime_timer]: timer.stop()
        self.db_manager.close()
        self.worker_manager.initiate_shutdown()

def load_config(config_file):
    with open(config_file, 'r', encoding='utf-8') as f: return json.load(f)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    default_config = 'config_n1470.json'
    config_file = sys.argv[1] if len(sys.argv) > 1 else default_config
    if not os.path.exists(config_file): print(f"Error: Config file '{config_file}' not found."); sys.exit(1)
    config = load_config(config_file)
    window = MonitoringApp(config)
    window.show()
    timer = QTimer(); timer.start(500); timer.timeout.connect(lambda: None)
    sys.exit(app.exec_())
