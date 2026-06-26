#!/usr/bin/env python3
# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""
EUNICE Tool: Network Scanner
Scans the local network and reports connected devices.

Usage:
  python tools/network_scan.py           # Direct run
  # Or via EUNICE: tell her 'scan my network'

Requirements:
  sudo apt install nmap
"""

import subprocess
import json
import sys
from datetime import datetime

def scan_network(subnet='192.168.1.0/24', timeout=60):
    print(f'Scanning {subnet}...')
    try:
        result = subprocess.run(
            ['nmap', '-sn', subnet],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        lines = result.stdout.split('\n')
        devices = []
        current = {}
        
        for line in lines:
            if 'Nmap scan report for' in line:
                if current:
                    devices.append(current)
                host = line.replace('Nmap scan report for ', '')
                current = {'host': host, 'ip': '', 'mac': '', 'vendor': ''}
            elif 'MAC Address:' in line and current:
                parts = line.split('MAC Address: ')[1].split(' ', 1)
                current['mac'] = parts[0]
                if len(parts) > 1:
                    current['vendor'] = parts[1].strip('()')
            elif 'Host is up' in line and current:
                current['status'] = 'up'
        
        if current:
            devices.append(current)
        
        return {
            'scan_time': datetime.now().isoformat(),
            'subnet': subnet,
            'devices_found': len(devices),
            'devices': devices
        }
    except FileNotFoundError:
        return {'error': 'nmap not installed. Run: sudo apt install nmap'}
    except subprocess.TimeoutExpired:
        return {'error': 'Scan timed out. Network may be large or slow.'}
    except Exception as e:
        return {'error': str(e)}

if __name__ == '__main__':
    subnet = sys.argv[1] if len(sys.argv) > 1 else '192.168.1.0/24'
    result = scan_network(subnet)
    print(json.dumps(result, indent=2))