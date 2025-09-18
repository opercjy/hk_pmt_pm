import time, queue
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
import numpy as np

class CaenHvWorker(QObject):
    data_ready = pyqtSignal(list)
    initial_settings_ready = pyqtSignal(dict)
    connection_status = pyqtSignal(str)
    command_feedback = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.params = config['parameters']
        self.is_dual_current = 'i_mon_low' in self.params
        self.command_queue = queue.Queue()
        self.device = None
        self.hv = None
        
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_hv_data)
        
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.timeout.connect(self.run)
        self.reconnect_timer.setSingleShot(True)

    def run(self):
        try:
            if not self.hv:
                from caen_libs import caenhvwrapper
                self.hv = caenhvwrapper
            
            cfg = self.config
            system_type = self.hv.SystemType[cfg['system_type']]
            link_type = self.hv.LinkType[cfg['link_type']]
            
            self.connection_status.emit(f"Connecting to HV ({cfg.get('connection_argument', '')})...")
            self.device = self.hv.Device.open(system_type, link_type, cfg.get('connection_argument', ''), cfg.get('username', ''), cfg.get('password', ''))
            self.connection_status.emit("HV Status: Connection Successful!")
            self.poll_timer.start(1000) # Start polling every 1 second upon successful connection

        except self.hv.Error as e:
            self.connection_status.emit(f"HV Status: Connection Failed! Retrying in 10s...")
            self.reconnect_timer.start(10000) # Retry connection after 10 seconds
        except (ImportError, KeyError) as e:
            self.connection_status.emit(f"HV Library/Config Error: {e}")

    def stop_polling(self):
        self.poll_timer.stop()
        self.reconnect_timer.stop()
        if self.device:
            self.device.close()
            self.device = None
        print("CAEN HV polling stopped.")

    def _poll_hv_data(self):
        if not self.device:
            return

        try:
            # 1. Process command queue
            try:
                cmd = self.command_queue.get_nowait()
                cmd_type, slot, ch_list, param_name, value = cmd
                if cmd_type == 'set_param':
                    self.device.set_ch_param(slot, ch_list, param_name, value)
                    self.command_feedback.emit(f"Success: Ch{ch_list[0]} {param_name} set to {value}")
                elif cmd_type == 'fetch_settings':
                    settings = {}
                    for ch in ch_list:
                        v_set = self.device.get_ch_param(slot, [ch], self.params['v_set'])[0]
                        i_set = self.device.get_ch_param(slot, [ch], self.params['i_set'])[0]
                        settings[ch] = {'v_set': v_set, 'i_set': i_set}
                    self.initial_settings_ready.emit(settings)
            except queue.Empty:
                pass

            # 2. Poll data
            results = []
            for ch_mon in self.config['channels_to_monitor']:
                vmon = self.device.get_ch_param(0, [ch_mon], self.params['v_mon'])[0]
                if self.is_dual_current:
                    imon_l = self.device.get_ch_param(0, [ch_mon], self.params['i_mon_low'])[0]
                    imon_h = self.device.get_ch_param(0, [ch_mon], self.params['i_mon_high'])[0]
                    results.append({'ch': ch_mon, 'v': vmon, 'il': imon_l, 'ih': imon_h})
                else:
                    imon = self.device.get_ch_param(0, [ch_mon], self.params['i_mon'])[0]
                    results.append({'ch': ch_mon, 'v': vmon, 'i': imon})
            self.data_ready.emit(results)

        except self.hv.Error as e:
            self.connection_status.emit(f"HV poll failed: {e}. Attempting to reconnect...")
            self.poll_timer.stop()
            if self.device:
                self.device.close()
                self.device = None
            self.reconnect_timer.start(5000) # Reconnect after 5 seconds
