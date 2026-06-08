import http.client
import json
import os
from datetime import datetime

os.makedirs("log", exist_ok=True)
log_file = os.path.join("log", f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

conn = http.client.HTTPConnection("127.0.0.1", 8000)
payload = json.dumps({
   "message": "创建多个subagent，规划从北京出发，分别到密云、平谷、阿那亚、天津、大连、烟台这几个地方的自驾路线、耗时信息，整理以html网页展示"
})
headers = {
   'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
   'Content-Type': 'application/json',
   'Connection': 'keep-alive'
}
conn.request("POST", "/api/orchestrator/run", payload, headers)
res = conn.getresponse()
print(f"Status: {res.status} {res.reason}")

with open(log_file, "w", encoding="utf-8") as f:
    for line in res:
        decoded_line = line.decode("utf-8").strip()
        print(decoded_line)
        f.write(decoded_line + "\n")
        f.flush()

print(f"\n日志已保存到: {log_file}")