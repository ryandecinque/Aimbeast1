# Road to Master 3

My Aimbeast practice log, published automatically.

- `index.html`: the page.
- `data.json`: the data it shows. Rebuilt by `publish.py` from my local game logs.
- `publish.py`: run by a Windows scheduled task named **Aimbeast publish** every 5 minutes. It only publishes after a session ends.

**To stop publishing:** open Task Scheduler and delete **Aimbeast publish**, or run:

```
schtasks /Delete /TN "Aimbeast publish" /F
```

**Notes on each day** use Cusdis (cusdis.com). New notes wait for approval in the Cusdis dashboard.
