#!/bin/sh
cd '/Users/wangpindun/python_project' || exit 1
/usr/bin/python3 '/Users/wangpindun/python_project/新聞.py' --mode monitor >> '/Users/wangpindun/python_project/political_intel.log' 2>&1
