from PyQt5.QtCore import QObject, pyqtSignal, QThread
from workers import ArduinoWorker, CaenHvWorker

class WorkerManager(QObject):
    arduino_data_ready = pyqtSignal(int, object, object)
    caenhv_data_ready = pyqtSignal(list)
    arduino_status_changed = pyqtSignal(str)
    caenhv_status_changed = pyqtSignal(str)
    hv_command_feedback = pyqtSignal(str)
    hv_initial_settings_ready = pyqtSignal(dict)
    shutdown_complete = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config

        self._arduino_worker = ArduinoWorker(config['arduino_settings']['port'], config['arduino_settings']['baud_rate'])
        self._arduino_thread = QThread()
        self._arduino_worker.moveToThread(self._arduino_thread)
        self._arduino_thread.started.connect(self._arduino_worker.run)

        self._caenhv_worker = CaenHvWorker(config['caen_hv_settings'])
        self._caenhv_thread = QThread()
        self._caenhv_worker.moveToThread(self._caenhv_thread)
        self._caenhv_thread.started.connect(self._caenhv_worker.run)

        self._arduino_worker.data_ready.connect(self.arduino_data_ready)
        self._arduino_worker.connection_status.connect(self.arduino_status_changed)
        self._caenhv_worker.data_ready.connect(self.caenhv_data_ready)
        self._caenhv_worker.connection_status.connect(self.caenhv_status_changed)
        self._caenhv_worker.command_feedback.connect(self.hv_command_feedback)
        self._caenhv_worker.initial_settings_ready.connect(self.hv_initial_settings_ready)

        self.threads = [self._arduino_thread, self._caenhv_thread]
        self.threads_remaining = len(self.threads)

    def start_workers(self):
        self._arduino_thread.start()
        self._caenhv_thread.start()

    def initiate_shutdown(self):
        print("Initiating worker shutdown...")
        for thread in self.threads:
            thread.finished.connect(self._on_thread_finished)
        
        if self._arduino_thread.isRunning():
            self._arduino_worker.stop_polling()
        if self._caenhv_thread.isRunning():
            self._caenhv_worker.stop_polling()

        self._arduino_thread.quit()
        self._caenhv_thread.quit()

    def _on_thread_finished(self):
        self.threads_remaining -= 1
        print(f"A thread has finished. Remaining: {self.threads_remaining}")
        if self.threads_remaining == 0:
            print("All worker threads stopped safely.")
            self.shutdown_complete.emit()
            
    def queue_hv_command(self, command_type, slot, ch, param_name, value):
        ch_list = [ch] if isinstance(ch, int) else ch
        self._caenhv_worker.command_queue.put((command_type, slot, ch_list, param_name, value))
