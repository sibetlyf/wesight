import httpx
import json
import os
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# 确保日志目录存在
os.makedirs(LOG_DIR, exist_ok=True)


def get_log_file():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(LOG_DIR, f"raw_data_{timestamp}.log")


def test_rawdata_stream():
    """测试 /rawdata 接口 (流式)"""
    print("\n--- 测试 /rawdata (Streaming) ---")
    url = f"{BASE_URL}/rawdata"
    data = {
        "message": "创建一个subagent，让它列出当前目录下的所有文件",
        "stream": "true"
    }

    # 注意：/rawdata 接收的是 Form 数据
    log_file = get_log_file()
    print(f"原始数据将保存至: {log_file}")

    with open(log_file, "w", encoding="utf-8") as f:
        with httpx.stream("POST", url, data=data, timeout=None) as response:
            for line in response.iter_lines():
                if line:
                    f.write(line + "\n")
                    f.flush()
                    print(f"收到数据: {line}")


def test_orchestrator_run():
    """测试 /api/orchestrator/run 接口 (JSON)"""
    print("\n--- 测试 /api/orchestrator/run ---")
    url = f"{BASE_URL}/api/orchestrator/run"
    payload = {
        "message": "创建一个subagent，让它列出当前目录下的所有文件",
        "extra": {
            "location": "上海"
        }
    }

    log_file = get_log_file()
    print(f"原始数据将保存至: {log_file}")

    with open(log_file, "w", encoding="utf-8") as f:
        with httpx.stream("POST", url, json=payload, timeout=None) as response:
            for line in response.iter_lines():
                if line:
                    f.write(line + "\n")
                    f.flush()
                    if line.startswith("data: "):
                        event_data = line[6:]  # 去掉 "data: " 前缀
                        try:
                            data = json.loads(event_data)
                            print(f"事件内容: {data}")
                        except json.JSONDecodeError:
                            print(f"无法解析: {event_data}")


if __name__ == "__main__":
    # 你可以根据需要运行其中一个
    try:
        test_orchestrator_run()
    except Exception as e:
        print(f"请求失败: {e}")
