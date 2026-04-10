# 輿情維護 SOP

## 目前架構

- 本機原始碼：`/Users/wangpindun/python_project`
- 本機 Git repo：`/Users/wangpindun/6688`
- VPS 執行目錄：`/home/wangpindun-mac/6688`
- VPS 真正生效的設定檔：`/home/wangpindun-mac/6688/.env`

本機 `python_project` 只用來修改原始碼，不會自動執行。
真正執行的是 VPS。

## 一、改功能 / 改程式 的 SOP

### 1. 在本機改原始碼

請修改：

- `/Users/wangpindun/python_project/新聞.py`
- `/Users/wangpindun/python_project/.env.example`

### 2. 把修改同步到 Git repo

把改好的檔案複製到本機 Git repo：

- `/Users/wangpindun/6688/新聞.py`

然後執行：

```bash
cd /Users/wangpindun/6688
git status
git add .
git commit -m "update monitor settings"
git push origin main
```

### 3. 到 VPS 拉新版

```bash
cd /home/wangpindun-mac/6688
git pull --ff-only
```

### 4. 手動測一次

```bash
cd /home/wangpindun-mac/6688
/home/wangpindun-mac/6688/.venv311/bin/python 新聞.py --mode monitor
```

### 5. 看 log

```bash
tail -n 50 /home/wangpindun-mac/6688/news_monitor.log
```

## 二、改參數 的 SOP

如果你改的是「執行參數」，不要只改本機 `.env.example`。
真正生效的是 VPS 上這份：

- `/home/wangpindun-mac/6688/.env`

例如：

```bash
nano /home/wangpindun-mac/6688/.env
```

常改參數：

- `MONITOR_NAME`
- `MONITOR_KEYWORDS`
- `PRIORITY_KEYWORDS`
- `MAX_ITEMS_PER_RUN`
- `DAILY_REPORT_LIMIT`
- `DEDUPE_HOURS`
- `MIN_PUSH_IMPORTANCE`
- `ENABLE_TELEGRAM`
- `OPENAI_MODEL`

改完後請手動測一次：

```bash
cd /home/wangpindun-mac/6688
/home/wangpindun-mac/6688/.venv311/bin/python 新聞.py --mode monitor
```

再看 log：

```bash
tail -n 50 /home/wangpindun-mac/6688/news_monitor.log
```

## 三、確認 VPS 排程

查看目前排程：

```bash
crontab -u wangpindun-mac -l
```

目前設定是：

- 每天 `09:00` 到 `22:00` 每整點跑 monitor
- 每天 `08:30` 跑 daily-report

## 四、日常檢查

### 看最近執行紀錄

```bash
tail -n 50 /home/wangpindun-mac/6688/news_monitor.log
```

### 看 Git 狀態

本機：

```bash
cd /Users/wangpindun/6688
git status
```

VPS：

```bash
cd /home/wangpindun-mac/6688
git status
```

## 五、一句話版本

### 改功能

本機 `python_project` 改 -> 複製到 `6688` -> `git push` -> VPS `git pull`

### 改參數

直接改 VPS `.env` -> 手動測一次 -> 看 log
