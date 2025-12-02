import requests
from dotenv import load_dotenv
import os
from datetime import datetime

# 加载 .env 文件
load_dotenv()

token = os.getenv('GITHUB_TOKEN')

if token:
    headers = {'Authorization': f'token {token}'}
else:
    headers = {}

# 检查速率限制
response = requests.get('https://api.github.com/rate_limit', headers=headers)

if response.status_code == 200:
    data = response.json()
    core = data['rate']

    print("="*60)
    print("GitHub API 速率限制状态")
    print("="*60)
    print(f"剩余请求数: {core['remaining']}/{core['limit']}")

    # 转换重置时间
    reset_timestamp = core['reset']
    reset_time = datetime.fromtimestamp(reset_timestamp)
    now = datetime.now()
    time_diff = reset_time - now

    print(f"重置时间: {reset_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"距离重置: {int(time_diff.total_seconds() / 60)} 分钟")
    print("="*60)

    if core['remaining'] == 0:
        print(f"\n⚠️ 配额已用完，请等待 {int(time_diff.total_seconds() / 60)} 分钟后再试")
    else:
        print(f"\n✓ 还有 {core['remaining']} 次请求可用")
else:
    print(f"✗ 检查失败: {response.status_code}")
