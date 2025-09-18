import time, queue
from PyQt5.QtCore import QObject, pyqtSignal
import numpy as np

class CaenHvWorker(QObject):
    data_ready = pyqtSignal(list)
    initial_settings_ready = pyqtSignal(dict)
    connection_status = pyqtSignal(str)
    command_feedback = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.running = True
        self.config = config
        self.params = config['parameters']
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
                                cmd = self.command_queue.get_nowait()
                                cmd_type, slot, ch_list, param_name, value = cmd
                                if cmd_type == 'set_param':
                                    device.set_ch_param(slot, ch_list, param_name, value)
                                    self.command_feedback.emit(f"Success: Ch{ch_list[0]} {param_name} set to {value}")
                                elif cmd_type == 'fetch_settings':
                                    settings = {}
                                    for ch in ch_list:
                                        v_set = device.get_ch_param(slot, [ch], self.params['v_set'])[0]
                                        i_set = device.get_ch_param(slot, [ch], self.params['i_set'])[0]
                                        settings[ch] = {'v_set': v_set, 'i_set': i_set}
                                    self.initial_settings_ready.emit(settings)
                            except queue.Empty: pass
                            except hv.Error as e: self.command_feedback.emit(f"Error: {e}")
                            
                            results = []
                            for ch_mon in channels:
                                try:
                                    vmon = device.get_ch_param(0, [ch_mon], self.params['v_mon'])[0]
                                    imon = device.get_ch_param(0, [ch_mon], self.params['i_mon'])[0]
                                    results.append((0, ch_mon, vmon, imon))
                                except hv.Error: results.append((0, ch_mon, np.nan, np.nan))
                            self.data_ready.emit(results)
                            time.sleep(1)
                except hv.Error:
                    self.connection_status.emit("HV Status: Connection Failed!")
                    time.sleep(10)
        except (ImportError, KeyError) as e:
            self.connection_status.emit(f"HV Library/Config Error: {e}")

    def stop(self):
        self.running = False
