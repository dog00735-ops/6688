#!/bin/sh
cd '/Users/wangpindun/python_project' || exit 1
/usr/bin/python3 '/Users/wangpindun/python_project/新聞.py' --mode daily-report --hours 24 --limit 12 >> '/Users/wangpindun/python_project/political_intel.log' 2>&1
