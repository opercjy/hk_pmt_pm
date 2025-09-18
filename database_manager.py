import sqlite3
import csv
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path, config):
        self.db_path = db_path
        self.config = config
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        
        sensor_cols = []
        for sensor in self.config['arduino_settings']['sensors']:
            name = sensor['name'].replace(" ", "_")
            sensor_cols.append(f"{name}_T REAL")
            sensor_cols.append(f"{name}_H REAL")
        
        hv_cols = []
        for ch in self.config['caen_hv_settings']['channels_to_monitor']:
            hv_cols.append(f"Ch{ch}_V REAL")
            hv_cols.append(f"Ch{ch}_I REAL")
            
        cols_str = ", ".join(sensor_cols + hv_cols)
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS monitoring_data (
                timestamp TEXT PRIMARY KEY,
                {cols_str}
            )
        ''')
        self.conn.commit()

    def log_data(self, data_point):
        cursor = self.conn.cursor()
        
        columns = ['timestamp']
        values = [data_point['ts']]
        
        for i in range(len(self.config['arduino_settings']['sensors'])):
            sensor_data = data_point['sensors'].get(i, {'t': None, 'h': None})
            values.extend([sensor_data['t'], sensor_data['h']])

        for ch in self.config['caen_hv_settings']['channels_to_monitor']:
            hv_data = data_point['hv'].get(ch, {'v': None, 'i': None})
            values.extend([hv_data['v'], hv_data['i']])

        placeholders = ', '.join(['?'] * len(values))
        
        # Build column names dynamically
        sensor_names = []
        for s in self.config['arduino_settings']['sensors']:
            name = s['name'].replace(" ", "_")
            sensor_names.extend([f'{name}_T', f'{name}_H'])
        
        hv_names = []
        for ch in self.config['caen_hv_settings']['channels_to_monitor']:
            hv_names.extend([f'Ch{ch}_V', f'Ch{ch}_I'])
            
        all_cols = "timestamp, " + ", ".join(sensor_names + hv_names)

        sql = f"INSERT OR REPLACE INTO monitoring_data ({all_cols}) VALUES ({placeholders})"
        
        try:
            cursor.execute(sql, values)
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Database log error: {e}")

    def fetch_data_range(self, start_dt, end_dt):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM monitoring_data WHERE timestamp BETWEEN ? AND ?", (start_dt, end_dt))
        
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        
        data = {col: [] for col in columns}
        timestamps = []
        
        for row in rows:
            dt_obj = datetime.fromisoformat(row[0])
            timestamps.append(dt_obj.timestamp())
            for i, col in enumerate(columns):
                if i > 0: # Skip timestamp
                    data[col].append(row[i])
        
        return timestamps, data

    def close(self):
        self.conn.close()
