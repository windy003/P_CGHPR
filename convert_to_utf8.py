"""
将UTF-16文件转换为UTF-8并清理控制字符
"""

# 读取UTF-16文件
with open('3.json', 'r', encoding='utf-16') as f:
    content = f.read()

# 清理控制字符
cleaned = ''.join(
    char for char in content
    if ord(char) >= 32 or ord(char) in (9, 10, 13)
)

# 保存为UTF-8
with open('3_utf8.json', 'w', encoding='utf-8') as f:
    f.write(cleaned)

print("✓ 转换完成！")
print("  原文件: 3.json (UTF-16)")
print("  新文件: 3_utf8.json (UTF-8, 已清理控制字符)")
