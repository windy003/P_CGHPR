import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 全局锁，用于线程安全的打印
print_lock = Lock()

def check_single_repo(item, index, total, headers=None):
    """
    检查单个仓库是否有releases

    参数:
        item: 仓库信息字典
        index: 当前索引
        total: 总数
        headers: 请求头（包含认证信息）
    """
    repo_name = item.get('full_name', 'Unknown')
    repo_url = item.get('html_url', 'N/A')
    releases_url = item.get('releases_url', '')

    # 去掉 {/id} 部分
    releases_api_url = releases_url.replace('{/id}', '')

    with print_lock:
        print(f"[{index}/{total}] 检查仓库: {repo_name}")

    try:
        # 访问releases API（带认证头）
        response = requests.get(releases_api_url, headers=headers, timeout=10)

        if response.status_code == 200:
            releases = response.json()

            # 检查是否有releases（不是空数组）
            if releases and len(releases) > 0:
                with print_lock:
                    print(f"    ✓ {repo_name} 有 {len(releases)} 个release")
                return {
                    'name': repo_name,
                    'repo_url': repo_url,  # 仓库地址
                    'releases_count': len(releases)
                }
            else:
                with print_lock:
                    print(f"    ✗ {repo_name} 没有releases")
                return None
        elif response.status_code == 403:
            # 检查是否是限流
            if 'X-RateLimit-Remaining' in response.headers:
                remaining = response.headers.get('X-RateLimit-Remaining', '0')
                with print_lock:
                    print(f"    ! {repo_name} API限流 (剩余: {remaining})")
            else:
                with print_lock:
                    print(f"    ! {repo_name} API返回403 (可能是私有仓库)")
            return None
        else:
            with print_lock:
                print(f"    ! {repo_name} API返回错误: {response.status_code}")
            return None

    except requests.exceptions.RequestException as e:
        with print_lock:
            print(f"    ! {repo_name} 请求失败: {str(e)}")
        return None


def check_repo_releases(json_file='3.json', max_workers=10, github_token=None):
    """
    检查GitHub搜索结果中哪些仓库有releases

    参数:
        json_file: JSON文件路径
        max_workers: 最大并发线程数（默认10）
        github_token: GitHub Personal Access Token（可选）
    """
    # 设置请求头
    headers = {}
    if github_token:
        headers['Authorization'] = f'token {github_token}'
        print("✓ 使用GitHub Token认证")
        print("  限制: 5000次/小时\n")
    else:
        print("⚠ 未使用Token认证")
        print("  限制: 60次/小时")
        print("  建议设置环境变量 GITHUB_TOKEN 或在代码中提供token\n")

    # 读取JSON文件
    print(f"正在读取文件: {json_file}")

    try:
        # 以UTF-8方式读取JSON文件
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✓ 成功读取JSON文件\n")

    except json.JSONDecodeError as e:
        print(f"✗ JSON解析失败: {e}")
        print(f"  错误位置: line {e.lineno} column {e.colno}")
        print("\n尝试使用简化方法直接提取数据...")

        # 备用方案：直接用正则表达式提取需要的字段
        import re

        with open(json_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取所有仓库的信息
        items = []
        # 简化方案：只提取full_name和releases_url，从releases_url推导仓库URL
        repo_pattern = r'"full_name":\s*"([^"]+)".*?"releases_url":\s*"https://api\.github\.com/repos/([^/]+/[^/]+)/releases'

        matches = re.finditer(repo_pattern, content, re.DOTALL)
        for match in matches:
            full_name = match.group(1)
            repo_path = match.group(2)  # 格式：用户名/仓库名
            items.append({
                'full_name': full_name,
                'html_url': f'https://github.com/{repo_path}',  # 从releases_url构建
                'releases_url': f'https://api.github.com/repos/{repo_path}/releases{{/id}}'
            })

        if not items:
            print("✗ 无法提取仓库信息")
            return [], 0

        print(f"✓ 使用正则表达式提取到 {len(items)} 个仓库\n")
        data = {'items': items}

    except Exception as e:
        print(f"✗ 读取文件失败: {e}")
        return [], 0

    items = data.get('items', [])
    total = len(items)
    print(f"找到 {total} 个仓库")
    print(f"使用 {max_workers} 个线程并发检查...\n")

    repos_with_releases = []

    # 使用线程池并发检查
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_repo = {
            executor.submit(check_single_repo, item, idx, total, headers): item
            for idx, item in enumerate(items, 1)
        }

        # 获取结果
        for future in as_completed(future_to_repo):
            result = future.result()
            if result:
                repos_with_releases.append(result)

    # 打印汇总
    print("\n" + "="*60)
    print(f"检查完成！共找到 {len(repos_with_releases)} 个有releases的仓库:")
    print("="*60 + "\n")

    # 按releases数量排序
    repos_with_releases.sort(key=lambda x: x['releases_count'], reverse=True)

    for repo in repos_with_releases:
        print(f"✓ {repo['name']} ({repo['releases_count']} 个releases)")
        print(f"  {repo['repo_url']}\n")

    return repos_with_releases, total


if __name__ == "__main__":
    # 获取GitHub Token
    # 方法1: 从环境变量读取（推荐）
    token = os.getenv('GITHUB_TOKEN')

    # 方法2: 直接在这里填写（不推荐，容易泄露）
    # token = 'ghp_your_token_here'

    if not token:
        print("="*60)
        print("如何获取并配置GitHub Token:")
        print("1. 访问 https://github.com/settings/tokens")
        print("2. 点击 'Generate new token' -> 'Generate new token (classic)'")
        print("3. 设置名称，勾选 'public_repo' 权限")
        print("4. 生成后复制token")
        print("5. 在当前目录创建 .env 文件，添加一行：")
        print("   GITHUB_TOKEN=ghp_你的token")
        print("   (可以复制 .env.example 文件并重命名为 .env)")
        print("="*60)
        print()

    # 运行脚本
    # max_workers可以调整，有token后可以设置更大的值（20-30）
    repos, total_repos = check_repo_releases('3.json', max_workers=20, github_token=token)

    # 保存结果到文件
    if repos:
        # 构建带统计信息的JSON结构
        output_data = {
            '__comment': f'{len(repos)}/{total_repos} 仓库有releases',
            'repos': repos
        }

        with open('repos_with_releases.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"结果已保存到 repos_with_releases.json")
