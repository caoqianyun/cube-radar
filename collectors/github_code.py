"""GitHub Code Search 采集器 —— 扫描全 GitHub 代码里的 Cube 集成指纹

和 github.py（搜 issues/PRs 标题正文）不同，这个采集器调 GitHub Code Search API
（/search/code 端点），搜的是**代码文件内容**。

为什么要单独搞一个：
    前面的 github.py 只搜 issue/PR 的 title/body，所以只能抓到"有人在 issue 里
    讨论 Cube"这种舆论信号。但很多项目是**默默集成、不喊出来**的——他们在自己
    仓库的代码里写了 CubeSandboxClient、调了 /sandboxes API、import 了 Cube
    配置，但从来没在 issue 里提过。这种项目舆论监测根本抓不到。

    代表案例：HKUDS/AgentSpace（876 star，原生 API 深度集成，README 只提一句
    "Cube scaffold"，issues 里 0 条 Cube 相关讨论）。

指纹策略：
    不靠单一关键字（容易被 "cube" / "sandbox" 这类常见词污染），而是用 Cube 原生
    API 的**独有特征组合**做指纹：

    1. 原生 API 字段名（E2B 没有、Cube 独有）：
       envdAccessToken / trafficAccessToken / sandboxID + templateID
    2. 原生 API 路由（Cube 独有）：
       /sandboxes/{sandboxId}/snapshots
    3. 大驼峰类型前缀（代码里最常见的写法）：
       CubeSandboxClient / CubeSandboxConfig / CubeClient
    4. 认证头（Cube 原生用 X-API-Key，E2B 用 Bearer）：
       "X-API-Key" + "sandboxes" 组合
    5. import / package 名：
       cubesandbox / @cubesandbox

    每条指纹单独搜一次，命中即收录。然后通过 repo 字段聚合——同一个 repo 多条
    指纹命中，说明集成深度高，是高质量案例候选。
"""
import requests
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional


GH_API = "https://api.github.com"


def _headers(token: Optional[str] = None):
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# Cube 原生 API 的独有指纹清单
# 每条都是 GitHub Code Search 语法支持的 query
# 这些指纹的设计原则：尽量排除 E2B / 通用 sandbox 命中，只保留 Cube 特征
#
# 设计教训（2026-07-29 首次清洗后修正）：
#   以下字段看起来是 Cube 独有，实际上是 E2B envd 协议的通用字段，任何做了 E2B
#   适配的项目都会有。不能单独用它们做指纹，否则会把 dify / cmux / suna / higress
#   这类"只是适配了 E2B、没用 Cube"的项目误判为 Cube 集成：
#     - envdAccessToken       ← E2B envd 协议字段，dify/cmux/suna 都有
#     - trafficAccessToken    ← 同上
#     - CUBE_TEMPLATE_ID      ← E2B 生态广泛使用，不是 Cube 独有
#
#   正确的 Cube 独有指纹应该是：
#     1. 类名/类型名：CubeSandboxClient / CubeSandboxConfig（代码里的命名）
#     2. 环境变量前缀：AGENT_SPACE_CUBE（HKUDS 独有命名）
#     3. 包名/import：cubesandbox（直接 import）
#     4. 文件路径含 /cube/ 子目录（强信号）
CODE_FINGERPRINTS = [
    # --- 类名/类型名（Cube 集成代码里最常见的命名）---
    # CubeSandboxClient / CubeSandboxConfig 几乎只出现在 Cube 集成代码里
    "CubeSandboxClient",
    "CubeSandboxConfig",
    "CubeSandboxProvider",
    "CubeSandboxConnection",

    # --- 环境变量命名（项目特有，E2B 不会用）---
    # AgentSpace 的命名风格
    "AGENT_SPACE_CUBE",
    # Cube 原生 SDK 的环境变量（不是 E2B 的 E2B_API_KEY）
    "CUBESANDBOX_API_KEY",
    "CUBESANDBOX_API_URL",

    # --- import / package 名（直接引用 Cube 包）---
    "cubesandbox in:file language:typescript",
    "cubesandbox in:file language:python",
    # Go / Rust 也覆盖一下
    "cubesandbox in:file language:go",
    "cubesandbox in:file language:rust",

    # --- 文件路径强信号（cube 子目录）---
    # /cube/cube-client 这种路径结构几乎只出现在 Cube 集成里
    "path:*/cube/cube-client*",
    "path:*/cube/cube-sandbox*",

    # --- README 里明确提到 CubeSandbox 的 ---
    # 用 in:file 限定 README，避免命中无关讨论
    "CubeSandbox in:file filename:README.md",
]


def collect(
    fingerprints: Optional[List[str]] = None,
    token: Optional[str] = None,
    repo_blacklist: Optional[str] = None,
) -> List[Dict]:
    """采集 GitHub 代码里出现 Cube 集成指纹的仓库

    参数：
        fingerprints: 自定义指纹清单（None 则用 CODE_FINGERPRINTS 默认清单）
        token: GitHub token（强烈建议配，否则 /search/code rate limit 只有 10/min）
        repo_blacklist: 要排除的仓库（如 "TencentCloud/CubeSandbox"），避免
                        我们自己的仓库被当成"集成方"抓进来

    返回：
        每个命中的 (repo, fingerprint) 组合一条 record，source = "github_code"
    """
    if fingerprints is None:
        fingerprints = CODE_FINGERPRINTS

    results = []
    now = datetime.now(timezone.utc)
    # 缓存 repo star 数，避免对同一个 repo 多次调 API
    repo_star_cache: Dict[str, int] = {}

    def _get_repo_stars(repo_full: str) -> int:
        """调 /repos/{owner}/{repo} 拿 star 数（Code Search 返回的 repo 对象不带 stars）"""
        if repo_full in repo_star_cache:
            return repo_star_cache[repo_full]
        try:
            r = requests.get(
                f"{GH_API}/repos/{repo_full}",
                headers=_headers(token),
                timeout=10,
            )
            if r.status_code == 200:
                stars = r.json().get("stargazers_count", 0)
                repo_star_cache[repo_full] = stars
                return stars
        except Exception:
            pass
        repo_star_cache[repo_full] = 0
        return 0

    for fp in fingerprints:
        q = fp
        if repo_blacklist:
            q = f"{fp} NOT repo:{repo_blacklist}"

        try:
            r = requests.get(
                f"{GH_API}/search/code",
                params={"q": q, "per_page": 30, "sort": "indexed", "order": "desc"},
                headers=_headers(token),
                timeout=15,
            )
            if r.status_code == 403:
                # rate limit——code search 无 token 只有 10/min
                print(f"  [Code] rate limited on fingerprint {fp!r}, skip")
                continue
            if r.status_code != 200:
                print(f"  [Code] {r.status_code} on fingerprint {fp!r}")
                continue
            data = r.json()
        except Exception as e:
            print(f"  [Code] error on {fp!r}: {e}")
            continue

        total = data.get("total_count", 0)
        if total == 0:
            continue

        print(f"  [Code] fingerprint {fp!r} → {total} hits")

        for item in data.get("items", []):
            repo_full = item.get("repository", {}).get("full_name", "")
            if not repo_full:
                continue
            if repo_blacklist and repo_blacklist in repo_full:
                continue

            # 从 path 推断语言
            path = item.get("path", "")
            ext = path.rsplit(".", 1)[-1] if "." in path else ""
            lang_map = {
                "ts": "typescript", "tsx": "typescript",
                "js": "javascript", "jsx": "javascript",
                "py": "python",
                "go": "go", "rs": "rust", "java": "java",
                "yaml": "yaml", "yml": "yaml",
                "sh": "shell", "md": "markdown",
            }
            lang = lang_map.get(ext, ext or "unknown")

            file_url = item.get("html_url", "")
            # 用 repo + path + fingerprint 做 source_id（同一文件多次命中不同指纹也保留）
            source_id = f"code-{repo_full}-{path}-{fp}"

            results.append({
                "source": "github_code",
                "source_id": source_id,
                "title": f"[code] {repo_full} · {path}",
                "url": file_url,
                "author": item.get("repository", {}).get("owner", {}).get("login"),
                "content": (
                    f"fingerprint: {fp}\n"
                    f"repo: {repo_full}\n"
                    f"path: {path}\n"
                    f"language: {lang}\n"
                    f"repo_url: {item.get('repository', {}).get('html_url', '')}\n"
                ),
                "created_at": now,  # code search 没有可靠的 created_at，用抓取时间
                "points": _get_repo_stars(repo_full),  # 真实 star 数
                "comments": 0,
                "extra": json.dumps({
                    "type": "code_integration",
                    "repo": repo_full,
                    "path": path,
                    "language": lang,
                    "fingerprint": fp,
                    "repo_stars": _get_repo_stars(repo_full),
                    "repo_url": item.get("repository", {}).get("html_url", ""),
                }, ensure_ascii=False),
            })

    return _dedupe(results)


def aggregate_by_repo(items: List[Dict]) -> Dict[str, Dict]:
    """把同一 repo 的多条命中聚合，输出 {repo: {stars, fingerprints, files, ...}}

    用于在报告里一眼看出"哪些 repo 是深度集成"（多指纹命中 = 深度集成）。
    """
    by_repo = {}
    for it in items:
        if it.get("source") != "github_code":
            continue
        extra = json.loads(it.get("extra") or "{}")
        repo = extra.get("repo", "")
        if not repo:
            continue
        if repo not in by_repo:
            by_repo[repo] = {
                "repo": repo,
                "stars": extra.get("repo_stars", 0),
                "repo_url": extra.get("repo_url", ""),
                "fingerprints": set(),
                "files": set(),
                "languages": set(),
            }
        by_repo[repo]["fingerprints"].add(extra.get("fingerprint", ""))
        by_repo[repo]["files"].add(extra.get("path", ""))
        by_repo[repo]["languages"].add(extra.get("language", ""))
        # 取最大的 star 数（不同文件命中可能 star 数不一致，取最大）
        by_repo[repo]["stars"] = max(by_repo[repo]["stars"], extra.get("repo_stars", 0))

    # 把 set 转成 list 方便序列化
    for v in by_repo.values():
        v["fingerprints"] = sorted(v["fingerprints"])
        v["files"] = sorted(v["files"])
        v["languages"] = sorted(v["languages"])
        v["fingerprint_count"] = len(v["fingerprints"])
        v["file_count"] = len(v["files"])
    return by_repo


def _dedupe(items):
    seen = set()
    out = []
    for x in items:
        key = (x["source"], x["source_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out
