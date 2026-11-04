"""
Git 仓库权限修复器

提供 Git 仓库权限检测和修复功能，解决因系统重装或用户切换导致的所有权问题。
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .git_utils import GitUtils


# 延迟获取日志记录器（避免在模块导入时触发警告）
def _get_logger():
    """获取日志记录器（延迟初始化）"""
    return logging.getLogger("Comfyui-Box")


@dataclass
class PermissionCheckResult:
    """权限检查结果"""
    total: int                    # 总仓库数
    checked: int                  # 已检查数
    problem_count: int            # 问题仓库数
    problem_repos: List[Dict]     # 问题仓库列表
    errors: List[Dict]            # 检查错误列表
    git_version: str              # Git 版本
    is_supported: bool            # 是否支持 safe.directory


@dataclass
class PermissionFixResult:
    """权限修复结果"""
    success: bool                 # 整体是否成功
    total: int                    # 总仓库数
    fixed: int                    # 成功修复数
    failed: int                   # 失败数
    failed_repos: List[Dict]      # 失败仓库详情
    duration: float               # 总耗时（秒）


class GitPermissionFixer:
    """Git 仓库权限修复器"""
    
    def __init__(self, git_utils: GitUtils, max_workers: int = 10, timeout: int = 10):
        """
        初始化权限修复器
        
        Args:
            git_utils: Git 工具类实例
            max_workers: 最大并发数（默认 10）
            timeout: 单个仓库操作超时时间（秒，默认 10）
        """
        self.git_utils = git_utils
        self.max_workers = max_workers
        self.timeout = timeout
    
    def check_repository_permission(
        self,
        repo_path: Path
    ) -> Tuple[bool, Optional[str]]:
        """
        检查单个仓库的权限状态
        
        Args:
            repo_path: 仓库路径
            
        Returns:
            (是否有权限问题, 错误信息)
            - (False, None): 无权限问题
            - (True, error_msg): 有权限问题
        """
        try:
            repo_name = repo_path.name
            
            # 使用 GitUtils 检查 safe.directory 问题
            has_issue, error_msg = self.git_utils.check_safe_directory_issue(repo_path)
            
            if has_issue:
                _get_logger().debug(f"[GitPermissionFix] 检测 - {repo_name} - 发现权限问题")
                return True, error_msg
            else:
                _get_logger().debug(f"[GitPermissionFix] 检测 - {repo_name} - 无权限问题")
                return False, None
                
        except Exception as e:
            error_msg = f"检测异常: {str(e)}"
            _get_logger().error(f"[GitPermissionFix] 检测 - {repo_path.name} - {error_msg}")
            return True, error_msg
    
    def check_all_repositories(
        self,
        repo_paths: List[Path],
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        批量检查仓库权限状态
        
        Args:
            repo_paths: 仓库路径列表
            progress_callback: 进度回调函数 (current, total, repo_name)
            
        Returns:
            {
                'total': int,              # 总仓库数
                'checked': int,            # 已检查数
                'problem_count': int,      # 问题仓库数
                'problem_repos': List[Dict],  # 问题仓库列表
                'errors': List[Dict],      # 检查错误列表
                'git_version': str,        # Git 版本
                'is_supported': bool       # 是否支持 safe.directory
            }
        """
        total = len(repo_paths)
        checked = 0
        problem_repos = []
        errors = []
        
        _get_logger().debug(f"[GitPermissionFix] 批量检测 - 开始检测 {total} 个仓库")
        
        # 获取 Git 版本信息
        git_version = self.git_utils.get_git_version() or "未知"
        is_supported = self.git_utils.is_safe_directory_supported()
        
        if not is_supported:
            _get_logger().warning(f"[GitPermissionFix] 批量检测 - Git 版本 {git_version} 不支持 safe.directory 功能")
        
        # 使用线程池并发检查
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有检查任务
            future_to_repo = {
                executor.submit(self._check_with_timeout, repo_path): repo_path
                for repo_path in repo_paths
            }
            
            # 处理完成的任务
            for future in as_completed(future_to_repo):
                repo_path = future_to_repo[future]
                repo_name = repo_path.name
                checked += 1
                
                try:
                    has_issue, error_msg = future.result()
                    
                    if has_issue:
                        problem_repos.append({
                            'name': repo_name,
                            'path': str(repo_path),
                            'error': error_msg or "未知错误"
                        })
                    
                except Exception as e:
                    error_info = {
                        'name': repo_name,
                        'path': str(repo_path),
                        'error': f"检测失败: {str(e)}"
                    }
                    errors.append(error_info)
                    _get_logger().error(f"[GitPermissionFix] 检测 - {repo_name} - 检测失败: {str(e)}")
                
                # 调用进度回调
                if progress_callback:
                    try:
                        progress_callback(checked, total, repo_name)
                    except Exception as e:
                        _get_logger().warning(f"[GitPermissionFix] 进度回调失败: {str(e)}")
        
        problem_count = len(problem_repos)
        _get_logger().debug(f"[GitPermissionFix] 批量检测 - 完成，共 {total} 个仓库，{problem_count} 个有问题")
        
        return {
            'total': total,
            'checked': checked,
            'problem_count': problem_count,
            'problem_repos': problem_repos,
            'errors': errors,
            'git_version': git_version,
            'is_supported': is_supported
        }
    
    def fix_repository_permission(
        self,
        repo_path: Path
    ) -> Tuple[bool, str]:
        """
        修复单个仓库的权限问题
        
        Args:
            repo_path: 仓库路径
            
        Returns:
            (是否成功, 消息)
        """
        try:
            repo_name = repo_path.name
            
            # 使用 GitUtils 添加 safe.directory 配置
            success, message = self.git_utils.add_safe_directory(repo_path)
            
            if success:
                _get_logger().debug(f"[GitPermissionFix] 修复 - {repo_name} - 成功添加到 safe.directory")
            else:
                _get_logger().error(f"[GitPermissionFix] 修复 - {repo_name} - 失败: {message}")
            
            return success, message
            
        except Exception as e:
            error_msg = f"修复异常: {str(e)}"
            _get_logger().error(f"[GitPermissionFix] 修复 - {repo_path.name} - {error_msg}")
            return False, error_msg
    
    def fix_all_repositories(
        self,
        repo_paths: List[Path],
        progress_callback: Optional[Callable[[int, int, str, bool], None]] = None
    ) -> Dict[str, Any]:
        """
        批量修复仓库权限问题
        
        注意：由于 Git 全局配置文件不支持并发写入，此方法使用串行执行
        
        Args:
            repo_paths: 仓库路径列表
            progress_callback: 进度回调函数 (current, total, repo_name, success)
            
        Returns:
            {
                'success': bool,           # 整体是否成功
                'total': int,              # 总仓库数
                'fixed': int,              # 成功修复数
                'failed': int,             # 失败数
                'failed_repos': List[Dict],  # 失败仓库详情
                'duration': float          # 总耗时（秒）
            }
        """
        start_time = time.time()
        total = len(repo_paths)
        fixed = 0
        failed = 0
        failed_repos = []
        
        _get_logger().debug(f"[GitPermissionFix] 批量修复 - 开始修复 {total} 个仓库（串行执行）")
        
        # 串行执行修复操作（避免 .gitconfig 文件锁冲突）
        for index, repo_path in enumerate(repo_paths, 1):
            repo_name = repo_path.name
            
            try:
                success, message = self.fix_repository_permission(repo_path)
                
                if success:
                    fixed += 1
                else:
                    failed += 1
                    failed_repos.append({
                        'name': repo_name,
                        'path': str(repo_path),
                        'error': message
                    })
                
                # 调用进度回调
                if progress_callback:
                    try:
                        progress_callback(index, total, repo_name, success)
                    except Exception as e:
                        _get_logger().warning(f"[GitPermissionFix] 进度回调失败: {str(e)}")
                
            except Exception as e:
                failed += 1
                error_msg = f"修复失败: {str(e)}"
                failed_repos.append({
                    'name': repo_name,
                    'path': str(repo_path),
                    'error': error_msg
                })
                _get_logger().error(f"[GitPermissionFix] 修复 - {repo_name} - {error_msg}")
                
                # 调用进度回调（失败）
                if progress_callback:
                    try:
                        progress_callback(index, total, repo_name, False)
                    except Exception as e:
                        _get_logger().warning(f"[GitPermissionFix] 进度回调失败: {str(e)}")
        
        duration = time.time() - start_time
        overall_success = failed == 0
        
        _get_logger().info(
            f"[GitPermissionFix] 批量修复 - 完成，"
            f"共 {total} 个仓库，成功 {fixed} 个，失败 {failed} 个，"
            f"耗时 {duration:.2f} 秒"
        )
        
        return {
            'success': overall_success,
            'total': total,
            'fixed': fixed,
            'failed': failed,
            'failed_repos': failed_repos,
            'duration': duration
        }
    
    def _check_with_timeout(self, repo_path: Path) -> Tuple[bool, Optional[str]]:
        """
        带超时的检查操作
        
        Args:
            repo_path: 仓库路径
            
        Returns:
            (是否有权限问题, 错误信息)
        """
        import concurrent.futures
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.check_repository_permission, repo_path)
            try:
                return future.result(timeout=self.timeout)
            except concurrent.futures.TimeoutError:
                error_msg = f"检测超时（{self.timeout}秒）"
                _get_logger().warning(f"[GitPermissionFix] 检测 - {repo_path.name} - {error_msg}")
                return True, error_msg
    
    def _fix_with_timeout(self, repo_path: Path) -> Tuple[bool, str]:
        """
        带超时的修复操作
        
        Args:
            repo_path: 仓库路径
            
        Returns:
            (是否成功, 消息)
        """
        import concurrent.futures
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.fix_repository_permission, repo_path)
            try:
                return future.result(timeout=self.timeout)
            except concurrent.futures.TimeoutError:
                error_msg = f"修复超时（{self.timeout}秒）"
                _get_logger().warning(f"[GitPermissionFix] 修复 - {repo_path.name} - {error_msg}")
                return False, error_msg
