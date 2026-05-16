#!/bin/bash
cd "$(dirname "$0")"
/usr/bin/python3 update_data.py > update_log.txt 2>&1
echo "EXIT_CODE:$?" >> update_log.txt
