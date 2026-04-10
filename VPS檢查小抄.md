# VPS 檢查小抄

## 最常用 3 個

```bash
date
crontab -u wangpindun-mac -l
tail -n 50 /home/wangpindun-mac/6688/news_monitor.log
```

## 看目前時間

```bash
date
```

## 看排程有沒有在

```bash
crontab -u wangpindun-mac -l
```

## 看最近執行狀況

```bash
tail -n 50 /home/wangpindun-mac/6688/news_monitor.log
```

## 持續追 log

```bash
tail -f /home/wangpindun-mac/6688/news_monitor.log
```

## 手動跑一次監控

```bash
cd /home/wangpindun-mac/6688
/home/wangpindun-mac/6688/.venv311/bin/python 新聞.py --mode monitor
```

## 手動跑一次日報

```bash
cd /home/wangpindun-mac/6688
/home/wangpindun-mac/6688/.venv311/bin/python 新聞.py --mode daily-report --hours 24 --limit 12
```

## 看 Git 狀態

```bash
cd /home/wangpindun-mac/6688
git status
```

## 拉 GitHub 最新版

```bash
cd /home/wangpindun-mac/6688
git pull --ff-only
```

## 看目前有哪些 stash

```bash
cd /home/wangpindun-mac/6688
git stash list
```

## 看有沒有程式正在跑

```bash
ps aux | grep 新聞.py
```
