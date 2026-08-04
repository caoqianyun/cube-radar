"""关键词严格过滤模块

规则：一条 mention 必须在 title / content / url / author 中真实包含以下之一：
  - "cube sandbox"（大小写不敏感，允许中间空格）
  - "cubesandbox"
  - "cubesandbox.ai"
  - "TencentCloud/CubeSandbox"（GitHub 仓库路径）

同时排除明显误命中：
  - 只出现"cube"但没有"sandbox"的（会漏掉 Minecraft cube / cube.js 等）
  - 只出现"sandbox"但没有"cube"的

特殊源：
  - github_code 源（代码集成扫描）直接放行——它的指纹已经在采集器里做了
    精确匹配（CubeSandboxClient / envdAccessToken 等），不需要再过一遍
    自然语言关键字过滤。
"""
import re
import json


# 精确匹配：任一命中即视为相关
STRICT_PATTERNS = [
    re.compile(r"\bcube\s*sandbox\b", re.IGNORECASE),   # "cube sandbox" / "cubesandbox"
    re.compile(r"cubesandbox\.ai", re.IGNORECASE),
    re.compile(r"tencentcloud/cubesandbox", re.IGNORECASE),
]

# 代码指纹：github_code 源的命中等价于相关，不需要再匹配自然语言关键字
# 这些是 Cube 原生 API 的独有特征，命中即说明是 Cube 集成
CODE_FINGERPRINT_MARKERS = [
    "CubeSandboxClient",
    "CubeSandboxConfig",
    "envdAccessToken",
    "trafficAccessToken",
    "AGENT_SPACE_CUBE",
    "CUBE_TEMPLATE_ID",
]

# 直接放行的源（这些源在采集时已经做了精确指纹匹配）
PASS_THROUGH_SOURCES = {"github_code"}

# 仅出现这些"游戏/无关"上下文的 → 明确排除（即使误匹配了也直接扔掉）
BLOCK_PATTERNS = [
    re.compile(r"\bminecraft\b", re.IGNORECASE),
    re.compile(r"\brubik", re.IGNORECASE),        # 魔方
    re.compile(r"\bice\s*cube\b", re.IGNORECASE), # 冰块
    re.compile(r"\bcube\s*root\b", re.IGNORECASE),
    re.compile(r"\bcube\.js\b", re.IGNORECASE),   # cube.js 是另一个数据分析开源项目
    re.compile(r"\bcube\s*maps?\b", re.IGNORECASE),
]


def is_relevant(item: dict) -> bool:
    """判断一条 mention 是否真的和 Cube Sandbox 相关"""
    # 代码集成扫描结果直接放行——指纹已在采集器里做了精确匹配
    if item.get("source") in PASS_THROUGH_SOURCES:
        return True

    # 拼接所有可搜索字段
    haystack = " ".join([
        str(item.get("title") or ""),
        str(item.get("content") or ""),
        str(item.get("url") or ""),
        str(item.get("author") or ""),
    ])

    # 必须命中至少一个严格模式
    if not any(p.search(haystack) for p in STRICT_PATTERNS):
        return False

    # 明确排除的上下文 → 即使命中了也扔（防守型：如果主题就是 minecraft，肯定不是我们的）
    # 但要小心：如果标题主题是 CubeSandbox，正文里恰好提到"cube.js" 也不该扔
    # 所以 BLOCK 只针对标题
    title_only = str(item.get("title") or "")
    for bp in BLOCK_PATTERNS:
        if bp.search(title_only):
            # 但如果标题**同时**明确包含 "cube sandbox" 三个字，还是保留（罕见但可能）
            if not any(p.search(title_only) for p in STRICT_PATTERNS):
                return False

    return True


def filter_items(items: list) -> tuple:
    """返回 (相关的, 被过滤的)"""
    kept = []
    dropped = []
    for it in items:
        if is_relevant(it):
            kept.append(it)
        else:
            dropped.append(it)
    return kept, dropped
