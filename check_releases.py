import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import os
import sys
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
    description = item.get('description', '')
    language = item.get('language', '')
    languages_url = item.get('languages_url', '')
    created_at = item.get('created_at', 'N/A')
    updated_at = item.get('updated_at', 'N/A')
    pushed_at = item.get('pushed_at', 'N/A')

    # 去掉 {/id} 部分
    releases_api_url = releases_url.replace('{/id}', '')

    with print_lock:
        print(f"[{index}/{total}] 检查仓库: {repo_name}")

    try:
        # 访问releases API（带认证头）
        response = requests.get(releases_api_url, headers=headers, timeout=10)

        if response.status_code == 200:
            releases = response.json()

            # 过滤出有assets的releases
            releases_with_assets = [r for r in releases if r.get('assets') and len(r.get('assets', [])) > 0]

            # 检查是否有包含assets的releases
            if releases_with_assets and len(releases_with_assets) > 0:
                with print_lock:
                    print(f"    ✓ {repo_name} 有 {len(releases_with_assets)} 个有assets的release")

                # 获取语言信息
                languages_data = {}
                if languages_url:
                    try:
                        lang_response = requests.get(languages_url, headers=headers, timeout=10)
                        if lang_response.status_code == 200:
                            languages_bytes = lang_response.json()
                            # 转换字节数为行数（假设平均每行35字节）
                            BYTES_PER_LINE = 35
                            for lang_name, byte_count in languages_bytes.items():
                                line_count = round(byte_count / BYTES_PER_LINE)
                                languages_data[lang_name] = {
                                    'bytes': byte_count,
                                    'lines': line_count
                                }

                            with print_lock:
                                print(f"    语言信息:")
                                for lang_name, data in languages_data.items():
                                    print(f"      - {lang_name}: {data['bytes']} 字节 (~{data['lines']} 行)")
                    except Exception as e:
                        with print_lock:
                            print(f"    ! 获取语言信息失败: {str(e)}")

                return {
                    'name': repo_name,
                    'repo_url': repo_url,  # 仓库地址
                    'description': description,  # 仓库描述
                    'language': language,  # 主要编程语言
                    'languages_url': languages_url,  # 语言API地址
                    'languages': languages_data,  # 语言详细信息（包含字节数和行数）
                    'releases_count': len(releases_with_assets),  # 只统计有assets的release
                    'created_at': created_at,
                    'updated_at': updated_at,
                    'pushed_at': pushed_at
                }
            else:
                with print_lock:
                    print(f"    ✗ {repo_name} 没有包含assets的releases")
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
        # 提取full_name, description, language, languages_url, releases_url和时间字段
        repo_pattern = r'"full_name":\s*"([^"]+)".*?"description":\s*("(?:[^"\\]|\\.)*?"|null).*?"language":\s*("(?:[^"\\]|\\.)*?"|null).*?"languages_url":\s*"([^"]+)".*?"created_at":\s*"([^"]+)".*?"updated_at":\s*"([^"]+)".*?"pushed_at":\s*"([^"]+)".*?"releases_url":\s*"https://api\.github\.com/repos/([^/]+/[^/]+)/releases'

        matches = re.finditer(repo_pattern, content, re.DOTALL)
        for match in matches:
            full_name = match.group(1)
            description_raw = match.group(2)
            language_raw = match.group(3)
            languages_url = match.group(4)
            created_at = match.group(5)
            updated_at = match.group(6)
            pushed_at = match.group(7)
            repo_path = match.group(8)  # 格式：用户名/仓库名

            # 处理description（去掉引号，处理null情况）
            if description_raw == 'null':
                description = ''
            else:
                description = description_raw.strip('"')

            # 处理language（去掉引号，处理null情况）
            if language_raw == 'null':
                language = ''
            else:
                language = language_raw.strip('"')

            items.append({
                'full_name': full_name,
                'html_url': f'https://github.com/{repo_path}',  # 从releases_url构建
                'description': description,
                'language': language,
                'languages_url': languages_url,
                'releases_url': f'https://api.github.com/repos/{repo_path}/releases{{/id}}',
                'created_at': created_at,
                'updated_at': updated_at,
                'pushed_at': pushed_at
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
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("用法: python check_releases.py <JSON文件名>")
        print("示例: python check_releases.py 3.json")
        sys.exit(1)

    # 获取输入文件名
    input_file = sys.argv[1]

    # 检查文件是否存在
    if not os.path.exists(input_file):
        print(f"错误: 文件 '{input_file}' 不存在")
        sys.exit(1)

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
    repos, total_repos = check_repo_releases(input_file, max_workers=20, github_token=token)

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
