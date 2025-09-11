# -*- coding: utf-8 -*-
"""
CAEN HV Power Supply Parameter Diagnostic Script

- 목적: CAEN HV 모듈에 연결하여 특정 채널에서 사용 가능한 
        파라미터 이름의 정확한 목록을 가져옵니다.
- 사용법: 이 스크립트를 'config.json' 파일과 동일한 디렉터리에서 실행하세요.
- 최종 수정일: 2025-09-11
"""

import sys
import json
import os

# --- 1. CAEN 라이브러리 임포트 ---
try:
    from caen_libs import caenhvwrapper as hv
except ImportError:
    print(" ERROR: 'caen_libs' 라이브러리를 찾을 수 없습니다.")
    print("CAEN HV Wrapper 라이브러리가 올바르게 설치되었는지 확인하세요.")
    sys.exit(1)

# --- 2. 설정 파일 로드 함수 ---
def load_config(filename='config.json'):
    """스크립트와 동일한 경로에 있는 JSON 설정 파일을 읽어옵니다."""
    if not os.path.exists(filename):
        raise FileNotFoundError(f"설정 파일 '{filename}'을 찾을 수 없습니다.")
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

# --- 3. 메인 진단 로직 ---
if __name__ == "__main__":
    print("--- CAEN HV 파라미터 진단 시작 ---")

    # --- 확인할 파라미터 (필요시 수정 가능) ---
    slot_to_check = 0
    channel_to_check = 0
    
    try:
        # 설정 파일 로드
        print("Loading 'config.json'...")
        config = load_config()
        hv_cfg = config['caen_hv_settings']
        print("설정 파일을 성공적으로 로드했습니다.")

        # 연결 정보 추출
        system_type_str = hv_cfg['system_type']
        link_type_str = hv_cfg['link_type']
        connection_arg = hv_cfg['connection_argument']
        username = hv_cfg['username']
        password = hv_cfg['password']
        
        system_type = hv.SystemType[system_type_str]
        link_type = hv.LinkType[link_type_str]

        # 장비에 연결
        print(f"'{connection_arg}'에 연결을 시도합니다...")
        
        # 'with' 구문은 장비 연결을 안전하게 자동 해제합니다.
        with hv.Device.open(system_type, link_type, connection_arg, username, password) as device:
            print(f" 연결에 성공했습니다!")

            # 지정된 채널의 파라미터 이름 목록 가져오기
            print(f"\nSlot {slot_to_check}, Channel {channel_to_check}의 파라미터 목록을 요청합니다...")
            
            param_list = device.get_ch_param_info(slot_to_check, channel_to_check)
            
            print("\n--- 진단 결과 ---")
            print(f"🔬 사용 가능한 파라미터: \n{param_list}")
            print("-----------------")
            
            print("\n조치 사항: 이 목록을 코드에 사용된 파라미터('VMon', 'IMon')와 비교하세요.")
            print("만약 이름이 다르다면, 메인 스크립트의 파라미터 이름을 수정해야 합니다.")

    except FileNotFoundError as e:
        print(f" ERROR: {e}")
    except KeyError as e:
        print(f" ERROR: 'config.json' 파일에서 '{e}' 키를 찾을 수 없습니다. 파일을 확인해주세요.")
    except hv.Error as e:
        print(f" CAEN HV ERROR: 장비에 연결하거나 파라미터를 가져올 수 없습니다. 상세 정보: {e}")
    except Exception as e:
        print(f" 예기치 않은 오류가 발생했습니다: {e}")

    print("\n--- 진단 스크립트 종료 ---")
