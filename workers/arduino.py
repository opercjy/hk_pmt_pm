import time, serial
from PyQt5.QtCore import QObject, pyqtSignal

class ArduinoWorker(QObject):
    data_ready = pyqtSignal(int, object, object)
    connection_status = pyqtSignal(str)

    def __init__(self, port, baud_rate):
        super().__init__()
        self.running = True
        self.ser = None
        self.port = port
        self.baud_rate = baud_rate

    def run(self):
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
                                if "ERROR" in parts: self.data_ready.emit(idx, None, None)
                                elif "TEMP" in parts and "HUMI" in parts: self.data_ready.emit(idx, float(parts["TEMP"]), float(parts["HUMI"]))
                        except (ValueError, IndexError, KeyError): pass
            except serial.SerialException:
                self.connection_status.emit("ENV Status: Connection Failed!")
                time.sleep(5)
            finally:
                if self.ser and self.ser.is_open: self.ser.close()

    def stop(self):
        self.running = False
