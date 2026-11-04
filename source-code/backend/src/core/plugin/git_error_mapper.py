"""
Git 错误消息映射器

该模块负责将原始的 Git 命令错误输出转换为用户友好的中文描述，
并提供针对性的解决方案。

作者: Comfyui-Box 开发团队
日期: 2025-02-03
"""

from dataclasses import dataclass
from typing import List, Dict, OrderedDict
from collections import OrderedDict
import re


# 错误类型常量
ERROR_TYPE_REMOTE = "remote"           # 远端地址相关错误
ERROR_TYPE_BRANCH = "branch"           # 分支相关错误
ERROR_TYPE_COMMIT = "commit"           # 提交相关错误
ERROR_TYPE_PERMISSION = "permission"   # 权限相关错误
ERROR_TYPE_NETWORK = "network"         # 网络相关错误
ERROR_TYPE_REPOSITORY = "repository"   # 仓库状态相关错误
ERROR_TYPE_AUTHENTICATION = "authentication"  # 认证相关错误
ERROR_TYPE_CONFLICT = "conflict"       # 冲突和合并相关错误
ERROR_TYPE_TIMEOUT = "timeout"         # 超时错误
ERROR_TYPE_UNKNOWN = "unknown"         # 未知错误


@dataclass
class ErrorPattern:
    """
    错误模式定义
    
    用于匹配特定类型的 Git 错误并提供相应的用户友好信息。
    
    Attributes:
        pattern: 匹配模式（字符串或正则表达式对象）
        error_type: 错误类型（使用 ERROR_TYPE_* 常量）
        user_message: 用户友好的错误描述（中文）
        causes: 可能的原因列表（中文）
        solutions: 解决方案列表（中文）
        priority: 匹配优先级（数字越大优先级越高，默认为 0）
    """
    pattern: str | re.Pattern
    error_type: str
    user_message: str
    causes: List[str]
    solutions: List[str]
    priority: int = 0


@dataclass
class ErrorInfo:
    """
    错误信息
    
    包含用户友好的错误描述、可能原因、解决方案和原始错误消息。
    
    Attributes:
        error_type: 错误类型（使用 ERROR_TYPE_* 常量）
        user_message: 用户友好的错误描述（中文）
        causes: 可能的原因列表（中文）
        solutions: 解决方案列表（中文）
        original_error: 原始的 Git 错误消息（英文）
    """
    error_type: str
    user_message: str
    causes: List[str]
    solutions: List[str]
    original_error: str


# 错误模式映射表
# 按照优先级从高到低排列，确保更具体的错误优先匹配
ERROR_PATTERNS = [
    # ========== 远端地址相关错误 (remote) - 优先级 100 ==========
    ErrorPattern(
        pattern="No such remote 'origin'",
        error_type=ERROR_TYPE_REMOTE,
        user_message="未配置远端地址",
        causes=[
            "仓库没有配置 origin 远端",
            "远端配置被删除或损坏",
        ],
        solutions=[
            "检查是否为有效的 Git 仓库",
            "运行 git remote add origin <url> 添加远端",
            "查看所有远端配置：git remote -v",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="could not read remote",
        error_type=ERROR_TYPE_REMOTE,
        user_message="无法读取远端配置",
        causes=[
            "远端配置文件损坏",
            ".git/config 文件格式错误",
        ],
        solutions=[
            "检查 .git/config 文件是否完整",
            "重新配置远端地址",
            "尝试删除并重新添加远端",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="does not appear to be a git repository",
        error_type=ERROR_TYPE_REMOTE,
        user_message="远端仓库不存在或无法访问",
        causes=[
            "远端 URL 配置错误",
            "远端仓库已被删除",
            "没有访问权限",
        ],
        solutions=[
            "检查远端 URL 是否正确",
            "确认仓库是否存在",
            "检查网络连接和访问权限",
        ],
        priority=100,
    ),
    
    # ========== 分支相关错误 (branch) - 优先级 100 ==========
    ErrorPattern(
        pattern="unknown revision or path not in the working tree",
        error_type=ERROR_TYPE_BRANCH,
        user_message="分支不存在",
        causes=[
            "指定的分支名称不存在",
            "分支已被删除",
            "拼写错误",
        ],
        solutions=[
            "运行 git branch -a 查看所有分支",
            "检查分支名称拼写",
            "切换到正确的分支",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="no upstream configured",
        error_type=ERROR_TYPE_BRANCH,
        user_message="未配置上游分支",
        causes=[
            "本地分支没有关联远程分支",
            "新创建的分支尚未推送",
        ],
        solutions=[
            "运行 git branch --set-upstream-to=origin/<branch> 设置上游分支",
            "或使用 git push -u origin <branch> 推送并设置上游",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="detached HEAD",
        error_type=ERROR_TYPE_BRANCH,
        user_message="处于游离 HEAD 状态",
        causes=[
            "当前不在任何分支上",
            "检出了特定的提交或标签",
        ],
        solutions=[
            "运行 git checkout <branch> 切换到分支",
            "或创建新分支：git checkout -b <new-branch>",
            "如需保留更改，先创建分支再切换",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="ambiguous argument",
        error_type=ERROR_TYPE_BRANCH,
        user_message="分支引用不明确",
        causes=[
            "存在同名的分支和标签",
            "引用名称有歧义",
        ],
        solutions=[
            "使用完整引用：refs/heads/<branch> 或 refs/tags/<tag>",
            "重命名冲突的分支或标签",
        ],
        priority=100,
    ),
    
    # ========== 提交相关错误 (commit) - 优先级 100 ==========
    ErrorPattern(
        pattern="does not have any commits yet",
        error_type=ERROR_TYPE_COMMIT,
        user_message="仓库没有任何提交记录",
        causes=[
            "这是一个新建的空仓库",
            "所有提交都被删除了",
        ],
        solutions=[
            "至少需要一次提交才能进行其他操作",
            "创建初始提交：git commit --allow-empty -m 'Initial commit'",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="needed a single revision",
        error_type=ERROR_TYPE_COMMIT,
        user_message="无法解析提交引用",
        causes=[
            "HEAD 引用丢失或损坏",
            "提交历史不完整",
        ],
        solutions=[
            "检查 .git/HEAD 文件是否存在",
            "运行 git fsck 检查仓库完整性",
            "可能需要重新克隆仓库",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="bad object",
        error_type=ERROR_TYPE_COMMIT,
        user_message="提交对象损坏",
        causes=[
            "Git 对象数据库损坏",
            "磁盘错误或文件系统问题",
        ],
        solutions=[
            "运行 git fsck --full 检查所有对象",
            "尝试从备份恢复",
            "可能需要重新克隆仓库",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="invalid object",
        error_type=ERROR_TYPE_COMMIT,
        user_message="无效的提交对象",
        causes=[
            "对象引用错误",
            "对象文件损坏",
        ],
        solutions=[
            "运行 git fsck 检查并修复",
            "检查 .git/objects 目录权限",
            "可能需要重新克隆仓库",
        ],
        priority=100,
    ),
    
    # ========== 权限相关错误 (permission) - 优先级 100 ==========
    ErrorPattern(
        pattern="detected dubious ownership",
        error_type=ERROR_TYPE_PERMISSION,
        user_message="Git 仓库所有权异常",
        causes=[
            "仓库所有者与当前用户不匹配",
            "从其他用户或系统复制的仓库",
            "Git 安全检查机制触发",
        ],
        solutions=[
            "点击「Git 权限修复」按钮自动修复",
            "或手动运行：git config --global --add safe.directory <path>",
            "确保有足够的文件系统权限",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="safe.directory",
        error_type=ERROR_TYPE_PERMISSION,
        user_message="需要配置安全目录",
        causes=[
            "Git 安全检查失败",
            "目录所有权不匹配",
        ],
        solutions=[
            "点击「Git 权限修复」按钮自动修复",
            "或运行：git config --global --add safe.directory <path>",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="Permission denied",
        error_type=ERROR_TYPE_PERMISSION,
        user_message="Git 权限被拒绝",
        causes=[
            "文件系统权限不足",
            "目录或文件被锁定",
            "需要管理员权限",
        ],
        solutions=[
            "检查文件夹权限设置",
            "以管理员身份运行程序",
            "确保文件没有被其他程序占用",
            "点击「Git 权限修复」按钮尝试修复",
        ],
        priority=50,
    ),
    
    # ========== 网络相关错误 (network) - 优先级 100 ==========
    ErrorPattern(
        pattern="Could not resolve host",
        error_type=ERROR_TYPE_NETWORK,
        user_message="无法解析主机地址",
        causes=[
            "DNS 解析失败",
            "网络连接问题",
            "主机名拼写错误",
        ],
        solutions=[
            "检查网络连接是否正常",
            "检查 DNS 设置",
            "确认主机名拼写正确",
            "尝试使用其他 DNS 服务器",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="Failed to connect",
        error_type=ERROR_TYPE_NETWORK,
        user_message="连接失败",
        causes=[
            "无法连接到远程服务器",
            "防火墙阻止连接",
            "服务器不可用",
        ],
        solutions=[
            "检查网络连接",
            "在系统设置中配置代理",
            "检查防火墙设置",
            "确认服务器是否在线",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="Connection timed out",
        error_type=ERROR_TYPE_NETWORK,
        user_message="连接超时",
        causes=[
            "网络延迟过高",
            "服务器响应缓慢",
            "网络不稳定",
        ],
        solutions=[
            "检查网络连接质量",
            "配置代理或更换网络",
            "稍后重试",
            "增加 Git 超时设置",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="SSL certificate problem",
        error_type=ERROR_TYPE_NETWORK,
        user_message="SSL 证书验证失败",
        causes=[
            "SSL 证书无效或过期",
            "系统证书库过期",
            "中间人攻击（罕见）",
        ],
        solutions=[
            "更新系统证书库",
            "检查系统时间是否正确",
            "临时禁用 SSL 验证（不推荐）：git config --global http.sslVerify false",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="unable to access",
        error_type=ERROR_TYPE_NETWORK,
        user_message="无法访问远程仓库",
        causes=[
            "网络连接问题",
            "代理配置错误",
            "仓库访问权限不足",
        ],
        solutions=[
            "检查网络连接",
            "在系统设置中配置代理",
            "检查仓库访问权限",
            "确认仓库 URL 是否正确",
        ],
        priority=110,
    ),
    
    # ========== 仓库状态相关错误 (repository) - 优先级 100 ==========
    ErrorPattern(
        pattern="not a git repository",
        error_type=ERROR_TYPE_REPOSITORY,
        user_message="不是有效的 Git 仓库",
        causes=[
            ".git 目录不存在",
            ".git 目录损坏",
            "在错误的目录中执行命令",
        ],
        solutions=[
            "检查是否在正确的目录",
            "确认 .git 目录是否存在",
            "重新克隆仓库",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="index file corrupt",
        error_type=ERROR_TYPE_REPOSITORY,
        user_message="索引文件损坏",
        causes=[
            ".git/index 文件损坏",
            "Git 操作被中断",
        ],
        solutions=[
            "删除 .git/index 文件",
            "运行 git reset 重建索引",
            "如果问题持续，重新克隆仓库",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern=re.compile(r"\bcorrupt\b", re.IGNORECASE),
        error_type=ERROR_TYPE_REPOSITORY,
        user_message="仓库数据损坏",
        causes=[
            "Git 对象数据库损坏",
            "磁盘错误",
            "文件系统问题",
        ],
        solutions=[
            "运行 git fsck --full 检查损坏程度",
            "尝试从备份恢复",
            "可能需要重新克隆仓库",
        ],
        priority=50,
    ),
    ErrorPattern(
        pattern="unable to read",
        error_type=ERROR_TYPE_REPOSITORY,
        user_message="无法读取仓库数据",
        causes=[
            "文件权限问题",
            "文件损坏",
            "磁盘错误",
        ],
        solutions=[
            "检查文件权限",
            "运行 git fsck 检查仓库",
            "检查磁盘健康状态",
        ],
        priority=50,
    ),
    
    # ========== 认证相关错误 (authentication) - 优先级 100 ==========
    ErrorPattern(
        pattern="fatal: Authentication failed for",
        error_type=ERROR_TYPE_AUTHENTICATION,
        user_message="远程仓库认证失败",
        causes=[
            "访问令牌过期或无效",
            "用户名或密码错误",
            "SSH 密钥未配置",
        ],
        solutions=[
            "更新访问令牌或密码",
            "配置 SSH 密钥认证",
            "检查凭据管理器中的凭据",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="Authentication failed",
        error_type=ERROR_TYPE_AUTHENTICATION,
        user_message="身份验证失败",
        causes=[
            "用户名或密码错误",
            "访问令牌无效",
            "认证方式不支持",
        ],
        solutions=[
            "检查用户名和密码",
            "使用 SSH 密钥或访问令牌",
            "更新凭据信息",
        ],
        priority=50,
    ),
    ErrorPattern(
        pattern="could not read Username",
        error_type=ERROR_TYPE_AUTHENTICATION,
        user_message="需要提供用户名",
        causes=[
            "缺少认证信息",
            "凭据未配置",
        ],
        solutions=[
            "配置 Git 凭据",
            "使用 SSH 密钥认证",
            "在 URL 中包含用户名",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="could not read Password",
        error_type=ERROR_TYPE_AUTHENTICATION,
        user_message="需要提供密码",
        causes=[
            "缺少密码",
            "凭据未保存",
        ],
        solutions=[
            "配置 Git 凭据管理器",
            "使用 SSH 密钥或访问令牌",
            "手动输入密码",
        ],
        priority=100,
    ),
    
    # ========== 冲突和合并相关错误 (conflict) - 优先级 100 ==========
    ErrorPattern(
        pattern="Automatic merge failed",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="自动合并失败",
        causes=[
            "无法自动合并更改",
            "存在冲突需要手动解决",
        ],
        solutions=[
            "查看冲突文件：git status",
            "手动解决冲突后继续",
            "或放弃合并操作",
        ],
        priority=110,
    ),
    ErrorPattern(
        pattern="CONFLICT",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="存在合并冲突",
        causes=[
            "本地和远程有冲突的更改",
            "同一文件的不同修改",
        ],
        solutions=[
            "手动编辑冲突文件解决冲突",
            "运行 git add <file> 标记已解决",
            "完成合并：git commit",
            "或放弃合并：git merge --abort",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="unmerged files",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="存在未解决的合并冲突",
        causes=[
            "之前的合并或变基操作未完成",
            "工作区有未解决的冲突文件",
        ],
        solutions=[
            "解决冲突：手动编辑冲突文件后 git add",
            "或放弃当前操作：git merge --abort / git rebase --abort",
            "然后重新执行更新",
        ],
        priority=110,
    ),
    ErrorPattern(
        pattern="You have not concluded your merge",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="之前的合并操作未完成",
        causes=[
            "上次合并因冲突中断，未提交结果",
            "MERGE_HEAD 文件仍存在",
        ],
        solutions=[
            "完成合并：git add . && git commit",
            "或放弃合并：git merge --abort",
        ],
        priority=110,
    ),
    ErrorPattern(
        pattern="rebase is already in progress",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="变基操作正在进行中",
        causes=[
            "上次变基操作未完成",
            "工作区处于变基中间状态",
        ],
        solutions=[
            "继续变基：git rebase --continue",
            "跳过当前提交：git rebase --skip",
            "放弃变基：git rebase --abort",
        ],
        priority=110,
    ),
    ErrorPattern(
        pattern="cherry-pick is already in progress",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="拣选操作正在进行中",
        causes=[
            "上次 cherry-pick 操作未完成",
        ],
        solutions=[
            "继续拣选：git cherry-pick --continue",
            "放弃拣选：git cherry-pick --abort",
        ],
        priority=110,
    ),
    ErrorPattern(
        pattern="revert is already in progress",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="回退操作正在进行中",
        causes=[
            "上次 revert 操作未完成",
        ],
        solutions=[
            "继续回退：git revert --continue",
            "放弃回退：git revert --abort",
        ],
        priority=110,
    ),
    ErrorPattern(
        pattern="You have unstaged changes",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="存在未暂存的更改",
        causes=[
            "工作区有未提交的更改",
            "需要先处理本地更改",
        ],
        solutions=[
            "提交更改：git add . && git commit",
            "或暂存更改：git stash",
            "或放弃更改：git checkout -- .",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="would be overwritten",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="本地更改将被覆盖",
        causes=[
            "操作会覆盖本地未提交的更改",
            "需要先保存本地工作",
        ],
        solutions=[
            "提交更改：git add . && git commit",
            "或暂存更改：git stash",
            "或放弃更改：git checkout -- .",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="Your local changes to the following files would be overwritten",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="本地修改将被合并覆盖",
        causes=[
            "本地修改的文件与远程更新冲突",
        ],
        solutions=[
            "提交更改：git add . && git commit",
            "或暂存更改：git stash",
            "或强制更新覆盖本地修改",
        ],
        priority=110,
    ),
    ErrorPattern(
        pattern="untracked working tree files would be overwritten",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="未跟踪的文件将被覆盖",
        causes=[
            "本地有未跟踪的文件与远程文件同名",
        ],
        solutions=[
            "移动或删除冲突的未跟踪文件",
            "或重命名文件避免冲突",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="untracked working tree files would be removed",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="未跟踪的文件将被删除",
        causes=[
            "远程删除了本地未跟踪的同名文件",
        ],
        solutions=[
            "备份并移动冲突的未跟踪文件",
            "或接受删除操作",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="local changes are stashed, however applying them resulted in conflicts",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="暂存的本地更改应用时产生冲突",
        causes=[
            "autostash 恢复时与更新内容冲突",
        ],
        solutions=[
            "解决冲突后 git add 并提交",
            "或放弃操作：git reset --hard",
            "稍后从 stash 恢复：git stash pop",
        ],
        priority=100,
    ),
    ErrorPattern(
        pattern="cannot apply a stash in the middle of a merge",
        error_type=ERROR_TYPE_CONFLICT,
        user_message="无法在合并过程中应用暂存",
        causes=[
            "合并进行中尝试应用 stash",
        ],
        solutions=[
            "先完成或放弃当前合并",
            "然后再应用 stash",
        ],
        priority=100,
    ),
]


class GitError(Exception):
    """
    Git 操作错误
    
    自定义异常类，用于封装 Git 操作失败时的详细错误信息。
    包含用户友好的错误描述、可能原因、解决方案和原始错误消息。
    
    Attributes:
        error_info: ErrorInfo 对象，包含完整的错误信息
    
    使用方法:
        try:
            # Git 操作
            pass
        except GitError as e:
            print(e.error_info.user_message)
            print(e.error_info.causes)
            print(e.error_info.solutions)
    """
    
    def __init__(self, error_info: ErrorInfo):
        """
        初始化 GitError 异常
        
        Args:
            error_info: ErrorInfo 对象，包含错误的详细信息
        """
        self.error_info = error_info
        # 调用父类构造函数，使用用户友好的消息作为异常消息
        super().__init__(error_info.user_message)


class GitErrorMapper:
    """
    Git 错误消息映射器
    
    负责将原始的 Git 命令错误输出转换为用户友好的中文描述，
    并提供针对性的解决方案。
    
    使用 LRU 缓存机制提高性能，避免重复匹配相同的错误。
    
    使用方法:
        mapper = GitErrorMapper()
        error_info = mapper.map_error(git_stderr)
    """
    
    def __init__(self, cache_size: int = 100):
        """
        初始化映射器，加载错误模式
        
        加载预定义的错误模式列表，并按优先级排序。
        初始化 LRU 缓存。
        
        Args:
            cache_size: 缓存大小限制，默认为 100
        """
        self.patterns: List[ErrorPattern] = []
        self._cache: OrderedDict[str, ErrorInfo] = OrderedDict()
        self._cache_size_limit = cache_size
        self._load_patterns()
    
    def _load_patterns(self):
        """
        加载错误模式定义
        
        从 ERROR_PATTERNS 列表加载所有错误模式，
        并按优先级从高到低排序，确保更具体的错误优先匹配。
        
        对于字符串模式，如果看起来像正则表达式，则预编译为 re.Pattern 对象。
        """
        # 复制模式列表
        self.patterns = []
        
        for pattern_def in ERROR_PATTERNS:
            # 创建模式副本
            pattern = ErrorPattern(
                pattern=pattern_def.pattern,
                error_type=pattern_def.error_type,
                user_message=pattern_def.user_message,
                causes=pattern_def.causes.copy(),
                solutions=pattern_def.solutions.copy(),
                priority=pattern_def.priority,
            )
            
            # 如果 pattern 是字符串且包含正则表达式特殊字符，尝试预编译
            if isinstance(pattern.pattern, str):
                # 检查是否包含正则表达式特殊字符
                regex_chars = r'[\^$.*+?{}()\[\]|\\]'
                if re.search(regex_chars, pattern.pattern):
                    try:
                        # 尝试预编译为正则表达式
                        pattern.pattern = re.compile(pattern.pattern, re.IGNORECASE)
                    except re.error:
                        # 如果编译失败，保持原字符串
                        pass
            
            self.patterns.append(pattern)
        
        # 按优先级从高到低排序
        self.patterns.sort(key=lambda p: p.priority, reverse=True)
    
    def map_error(self, git_error: str) -> ErrorInfo:
        """
        将 Git 错误映射为用户友好的错误信息
        
        使用 LRU 缓存机制提高性能，避免重复匹配相同的错误。
        
        Args:
            git_error: Git 命令的 stderr 输出
            
        Returns:
            ErrorInfo 对象，包含用户友好的错误描述、可能原因和解决方案
        """
        # 检查缓存
        if git_error in self._cache:
            # 缓存命中，将该项移到末尾（最近使用）
            self._cache.move_to_end(git_error)
            return self._cache[git_error]
        
        # 缓存未命中，执行映射
        error_info = self._do_map(git_error)
        
        # 更新缓存（LRU）
        if len(self._cache) >= self._cache_size_limit:
            # 缓存已满，删除最旧的项（第一个）
            self._cache.popitem(last=False)
        
        # 添加新项到缓存末尾
        self._cache[git_error] = error_info
        
        return error_info
    
    def _do_map(self, git_error: str) -> ErrorInfo:
        """
        执行实际的错误映射逻辑
        
        Args:
            git_error: Git 命令的 stderr 输出
            
        Returns:
            ErrorInfo 对象
        """
        # 尝试匹配错误模式
        matched_pattern = self._match_pattern(git_error)
        
        if matched_pattern:
            # 找到匹配的模式，返回对应的错误信息
            return ErrorInfo(
                error_type=matched_pattern.error_type,
                user_message=matched_pattern.user_message,
                causes=matched_pattern.causes.copy(),
                solutions=matched_pattern.solutions.copy(),
                original_error=git_error,
            )
        else:
            # 未找到匹配的模式，返回未知错误
            return self._create_unknown_error(git_error)
    
    def _match_pattern(self, error: str) -> ErrorPattern | None:
        """
        匹配错误模式
        
        按优先级顺序遍历所有错误模式，返回第一个匹配的模式。
        支持字符串包含匹配和正则表达式匹配。
        
        Args:
            error: 错误消息
            
        Returns:
            匹配的 ErrorPattern，未匹配返回 None
        """
        for pattern in self.patterns:
            try:
                if isinstance(pattern.pattern, re.Pattern):
                    # 正则表达式匹配
                    if pattern.pattern.search(error):
                        return pattern
                else:
                    # 字符串包含匹配（不区分大小写）
                    if pattern.pattern.lower() in error.lower():
                        return pattern
            except Exception as e:
                # 匹配过程中出现异常，记录并继续
                # 注意：这里应该使用日志记录，但为了简化暂时跳过
                continue
        
        return None
    
    def _create_unknown_error(self, error: str) -> ErrorInfo:
        """
        创建未知错误的 ErrorInfo
        
        当无法匹配任何已知模式时，创建一个默认的错误信息。
        
        Args:
            error: 原始错误消息
            
        Returns:
            ErrorInfo 对象，error_type 为 "unknown"
        """
        # 截取前 50 个字符作为用户消息
        user_message = error[:50]
        if len(error) > 50:
            user_message += "..."
        
        return ErrorInfo(
            error_type=ERROR_TYPE_UNKNOWN,
            user_message=user_message,
            causes=["未知错误"],
            solutions=[
                "查看详细日志了解更多信息",
                "尝试重新获取插件信息",
                "如果问题持续，请联系技术支持",
            ],
            original_error=error,
        )
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息
        
        Returns:
            包含缓存统计信息的字典：
            - size: 当前缓存大小
            - limit: 缓存大小限制
        """
        return {
            "size": len(self._cache),
            "limit": self._cache_size_limit,
        }
    
    def clear_cache(self):
        """
        清空缓存
        
        用于测试或需要强制重新映射所有错误的场景。
        """
        self._cache.clear()
