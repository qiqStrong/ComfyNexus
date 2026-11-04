"""
ComfyUI 进程检测器

负责扫描系统进程，识别不受管理的 ComfyUI 进程，检测端口冲突。
"""

import psutil
from typing import Optional, List, Dict

from ...utils.logger import app_logger as logger


class ProcessDetector:
    """ComfyUI 进程检测器"""
    
    def __init__(self, managed_pid: Optional[int] = None, managed_cmdline: Optional[str] = None, managed_cwd: Optional[str] = None):
        """
        初始化检测器
        
        Args:
            managed_pid: 当前应用管理的进程 PID（用于排除）
            managed_cmdline: 受管理进程的完整命令行参数（用于排除子进程，会自动去掉 Python 解释器路径）
            managed_cwd: 受管理进程的工作目录（用于排除子进程）
        """
        self.managed_pid = managed_pid
        self.managed_cwd = managed_cwd.lower() if managed_cwd else None
        
        # 自动去掉 Python 解释器路径，只保留脚本和参数部分
        if managed_cmdline:
            cmdline_list = managed_cmdline.split() if isinstance(managed_cmdline, str) else managed_cmdline
            self.managed_cmdline = self._extract_cmdline_without_python(cmdline_list)
        else:
            self.managed_cmdline = None
    
    def is_comfyui_process(self, proc: psutil.Process) -> bool:
        """
        判断进程是否是 ComfyUI 进程
        
        检查逻辑：
        1. 进程名称包含 "python"
        2. 命令行参数包含 "main.py" 且路径中包含 comfyui 相关目录
        
        Args:
            proc: psutil 进程对象
            
        Returns:
            True 如果是 ComfyUI 进程，否则返回 False
        """
        try:
            # 获取进程名称（小写，便于比较）
            process_name = proc.name().lower()
            
            # 检查进程名称是否包含 "python"
            if "python" not in process_name:
                return False
            
            # 获取完整命令行参数
            cmdline = proc.cmdline()
            if not cmdline:
                return False
            
            # 将命令行参数转换为单个字符串（小写，便于搜索）
            cmdline_str = " ".join(cmdline).lower()
            
            # 必须包含 main.py 才认为是 ComfyUI 进程
            # 这样可以排除其他 Python 进程（如 npm、vite 等）
            if "main.py" not in cmdline_str:
                return False
            
            # 进一步验证：检查是否是 ComfyUI 的 main.py
            # 通过检查路径中是否包含 comfyui 相关目录
            # 但要排除只是路径名包含 comfyui 的情况
            has_comfyui_indicator = False
            
            # 检查命令行中是否有明确的 ComfyUI 标识
            for arg in cmdline:
                arg_lower = arg.lower()
                # 检查是否是 ComfyUI 的 main.py 文件
                if "main.py" in arg_lower:
                    # 检查 main.py 所在的目录路径
                    # 如果路径中包含 comfyui（但不是 Comfyui-Box 这样的项目名）
                    if "comfyui" in arg_lower and "comfyui-box" not in arg_lower:
                        has_comfyui_indicator = True
                        break
                    # 或者检查是否在典型的 ComfyUI 目录结构中
                    # 例如：包含 custom_nodes、models 等目录
                    if any(indicator in arg_lower for indicator in ["custom_nodes", "comfy/", "comfy\\"]):
                        has_comfyui_indicator = True
                        break
            
            if has_comfyui_indicator:
                logger.debug(f"识别到 ComfyUI 进程: PID={proc.pid}, 名称={process_name}, 命令行={cmdline_str}")
                return True
            
            return False
            
        except psutil.AccessDenied:
            # 权限不足，无法访问进程信息
            logger.debug(f"无法访问进程 {proc.pid} 的信息（权限不足）")
            return False
        except psutil.NoSuchProcess:
            # 进程已不存在
            logger.debug(f"进程 {proc.pid} 已不存在")
            return False
        except Exception as e:
            # 其他异常，记录日志但不抛出
            logger.warning(f"检查进程 {proc.pid} 时发生异常: {e}")
            return False
    
    def _is_related_process(self, cmdline: List[str], cwd: str) -> bool:
        """
        检查进程是否与受管理的进程相关（子进程）
        
        桌面版 ComfyUI 在启动时会使用 UV Python 重新启动一个子进程，
        这个子进程会有相同的工作目录和命令行参数（除了 Python 解释器路径）。
        
        Args:
            cmdline: 进程的命令行参数列表
            cwd: 进程的工作目录
            
        Returns:
            True 如果是相关进程，否则返回 False
        """
        if not self.managed_cmdline or not self.managed_cwd:
            # logger.dev(f"[_is_related_process] 跳过检查：managed_cmdline 或 managed_cwd 为空")
            return False
        
        if not cmdline or not cwd:
            # logger.dev(f"[_is_related_process] 跳过检查：cmdline 或 cwd 为空")
            return False
        
        cwd_lower = cwd.lower()
        
        if cwd_lower != self.managed_cwd:
            # logger.dev(f"[_is_related_process] 工作目录不同：{cwd_lower} != {self.managed_cwd}")
            return False
        
        cmdline_without_python = self._extract_cmdline_without_python(cmdline)
        if not cmdline_without_python:
            # logger.dev(f"[_is_related_process] 无法提取命令行参数（不含 Python）")
            return False
        
        is_related = cmdline_without_python == self.managed_cmdline
        # logger.dev(f"[_is_related_process] 命令行比较：")
        # logger.dev(f"[_is_related_process]   待检查进程：{cmdline_without_python}")
        # logger.dev(f"[_is_related_process]   受管理进程：{self.managed_cmdline}")
        # logger.dev(f"[_is_related_process]   是否相关：{is_related}")
        
        return is_related
    
    def _extract_cmdline_without_python(self, cmdline: List[str]) -> Optional[str]:
        """
        提取命令行参数（不包含 Python 解释器路径）
        
        Args:
            cmdline: 完整的命令行参数列表
            
        Returns:
            不包含 Python 解释器路径的命令行参数字符串（小写），如果无法提取则返回 None
        """
        if not cmdline or len(cmdline) < 2:
            return None
        
        for i, arg in enumerate(cmdline):
            arg_lower = arg.lower()
            if "python" in arg_lower and (arg_lower.endswith(".exe") or "python" in arg_lower):
                remaining_args = cmdline[i + 1:]
                if remaining_args:
                    return " ".join(remaining_args).lower()
                return None
        
        return None
    
    def extract_port_from_cmdline(self, cmdline: List[str]) -> int:
        """
        从命令行参数中提取端口号
        
        支持的参数格式：
        - --port 8188
        - --port=8188
        - --listen 0.0.0.0:8188
        - --listen=0.0.0.0:8188
        
        Args:
            cmdline: 命令行参数列表
            
        Returns:
            端口号，如果未指定则返回 8188（ComfyUI 默认端口）
        """
        default_port = 8188
        
        try:
            # 遍历命令行参数
            for i, arg in enumerate(cmdline):
                # 处理 --port 参数
                if arg == "--port":
                    # 格式: --port 8188
                    if i + 1 < len(cmdline):
                        try:
                            port = int(cmdline[i + 1])
                            logger.debug(f"从命令行提取端口: {port} (--port 格式)")
                            return port
                        except ValueError:
                            logger.warning(f"无效的端口值: {cmdline[i + 1]}")
                            continue
                elif arg.startswith("--port="):
                    # 格式: --port=8188
                    try:
                        port_str = arg.split("=", 1)[1]
                        port = int(port_str)
                        logger.debug(f"从命令行提取端口: {port} (--port= 格式)")
                        return port
                    except (ValueError, IndexError):
                        logger.warning(f"无效的端口参数: {arg}")
                        continue
                
                # 处理 --listen 参数
                elif arg == "--listen":
                    # 格式: --listen 0.0.0.0:8188
                    if i + 1 < len(cmdline):
                        listen_value = cmdline[i + 1]
                        port = self._extract_port_from_listen(listen_value)
                        if port:
                            logger.debug(f"从命令行提取端口: {port} (--listen 格式)")
                            return port
                elif arg.startswith("--listen="):
                    # 格式: --listen=0.0.0.0:8188
                    try:
                        listen_value = arg.split("=", 1)[1]
                        port = self._extract_port_from_listen(listen_value)
                        if port:
                            logger.debug(f"从命令行提取端口: {port} (--listen= 格式)")
                            return port
                    except IndexError:
                        logger.warning(f"无效的 listen 参数: {arg}")
                        continue
            
            # 未找到端口参数，返回默认端口
            logger.debug(f"命令行中未指定端口，使用默认端口: {default_port}")
            return default_port
            
        except Exception as e:
            # 发生异常，记录日志并返回默认端口
            logger.warning(f"提取端口时发生异常: {e}，使用默认端口: {default_port}")
            return default_port
    
    def _extract_port_from_listen(self, listen_value: str) -> Optional[int]:
        """
        从 --listen 参数值中提取端口号
        
        支持的格式：
        - 0.0.0.0:8188
        - 127.0.0.1:8188
        - :8188
        - 8188
        
        Args:
            listen_value: --listen 参数的值
            
        Returns:
            端口号，如果无法提取则返回 None
        """
        try:
            # 如果包含冒号，提取冒号后的部分
            if ":" in listen_value:
                port_str = listen_value.split(":")[-1]
            else:
                # 没有冒号，整个值可能就是端口号
                port_str = listen_value
            
            # 尝试转换为整数
            port = int(port_str)
            
            # 验证端口范围（1-65535）
            if 1 <= port <= 65535:
                return port
            else:
                logger.warning(f"端口号超出有效范围: {port}")
                return None
                
        except ValueError:
            logger.warning(f"无法从 listen 值中提取端口: {listen_value}")
            return None
    
    def scan_comfyui_processes(self) -> List[Dict]:
        """
        扫描系统中的 ComfyUI 进程
        
        遍历所有系统进程，识别不受当前应用管理的 ComfyUI 进程。
        
        Returns:
            进程信息列表，每个进程包含:
            - pid: 进程 ID
            - port: 监听端口（如果能检测到）
            - cmdline: 完整命令行（字符串形式）
            - cwd: 工作目录
            - create_time: 创建时间戳
        """
        comfyui_processes = []
        
        logger.debug(f"[进程扫描] 开始扫描，managed_pid={self.managed_pid}")
        
        try:
            python_process_count = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd', 'create_time']):
                try:
                    process_name = proc.info['name'] or ""
                    if "python" in process_name.lower():
                        python_process_count += 1
                        cmdline = proc.info['cmdline'] or []
                        cmdline_str = " ".join(cmdline) if cmdline else ""
                        cwd = proc.info['cwd'] or ""
                        logger.debug(f"[进程扫描] 发现 Python 进程: PID={proc.info['pid']}, 名称={process_name}, 工作目录={cwd}")
                        logger.debug(f"[进程扫描]   命令行: {cmdline_str}")
                    
                    if not self.is_comfyui_process(proc):
                        continue
                    
                    pid = proc.info['pid']
                    
                    if self.managed_pid is not None and pid == self.managed_pid:
                        logger.debug(f"排除受管理的进程: PID={pid}")
                        continue
                    
                    cmdline = proc.info['cmdline'] or []
                    cwd = proc.info['cwd'] or ""
                    create_time = proc.info['create_time'] or 0
                    
                    if self._is_related_process(cmdline, cwd):
                        logger.debug(f"排除相关进程（子进程）: PID={pid}")
                        continue
                    
                    port = self.extract_port_from_cmdline(cmdline)
                    
                    process_info = {
                        'pid': pid,
                        'port': port,
                        'cmdline': ' '.join(cmdline),
                        'cwd': cwd,
                        'create_time': create_time
                    }
                    
                    comfyui_processes.append(process_info)
                    logger.debug(f"发现不受管理的 ComfyUI 进程: PID={pid}, 端口={port}, 路径={cwd}")
                    
                except psutil.AccessDenied:
                    # 权限不足，跳过该进程
                    logger.debug(f"无法访问进程信息（权限不足），跳过")
                    continue
                except psutil.NoSuchProcess:
                    # 进程已结束，跳过
                    logger.debug(f"进程已结束，跳过")
                    continue
                except Exception as e:
                    # 其他异常，记录日志但继续扫描
                    logger.warning(f"处理进程时发生异常: {e}，继续扫描")
                    continue
            
            logger.debug(f"[进程扫描] 扫描完成，共发现 {len(comfyui_processes)} 个不受管理的 ComfyUI 进程")
            return comfyui_processes
            
        except Exception as e:
            # 扫描过程发生严重异常，记录日志但不抛出
            logger.error(f"扫描进程时发生严重异常: {e}，返回空列表")
            return []
    
    def check_port_conflict(self, processes: List[Dict], target_port: int) -> bool:
        """
        检查是否存在端口冲突
        
        遍历进程列表，检查是否有进程使用目标端口。
        
        Args:
            processes: 进程列表（由 scan_comfyui_processes 返回）
            target_port: 目标端口号
            
        Returns:
            True 如果存在端口冲突，否则返回 False
        """
        try:
            logger.debug(f"检查端口冲突: 目标端口={target_port}, 进程数={len(processes)}")
            
            # 遍历进程列表
            for proc in processes:
                proc_port = proc.get('port')
                
                # 检查端口是否匹配
                if proc_port == target_port:
                    logger.warning(
                        f"检测到端口冲突: PID={proc.get('pid')}, "
                        f"端口={proc_port}, 路径={proc.get('cwd')}"
                    )
                    return True
            
            logger.debug(f"未检测到端口冲突（目标端口: {target_port}）")
            return False
            
        except Exception as e:
            # 发生异常，记录日志并返回 False（不阻塞启动）
            logger.error(f"检查端口冲突时发生异常: {e}，返回 False")
            return False
    
    @staticmethod
    def kill_process(pid: int) -> Dict:
        """
        终止指定进程
        
        使用 psutil 终止指定 PID 的进程。处理常见异常情况：
        - 权限不足（AccessDenied）
        - 进程不存在（NoSuchProcess）
        - 其他异常
        
        Args:
            pid: 进程 ID
            
        Returns:
            操作结果字典:
            - success: bool - 是否成功
            - message: str - 结果消息
            - error: str - 错误信息（如果失败）
        """
        try:
            logger.info(f"尝试终止进程: PID={pid}")
            
            # 获取进程对象
            proc = psutil.Process(pid)
            
            # 获取进程名称（用于日志）
            try:
                proc_name = proc.name()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                proc_name = "未知"
            
            # 终止进程
            proc.terminate()
            
            # 等待进程结束（最多等待 3 秒）
            try:
                proc.wait(timeout=3)
                logger.info(f"成功终止进程: PID={pid}, 名称={proc_name}")
                return {
                    'success': True,
                    'message': f'成功终止进程 {pid}',
                    'error': None
                }
            except psutil.TimeoutExpired:
                # 进程未在超时时间内结束，尝试强制杀死
                logger.warning(f"进程 {pid} 未在超时时间内结束，尝试强制杀死")
                proc.kill()
                logger.info(f"强制杀死进程: PID={pid}")
                return {
                    'success': True,
                    'message': f'强制终止进程 {pid}',
                    'error': None
                }
                
        except psutil.NoSuchProcess:
            # 进程不存在（可能已经结束）
            logger.info(f"进程 {pid} 不存在（可能已结束）")
            return {
                'success': True,
                'message': f'进程 {pid} 已不存在',
                'error': None
            }
            
        except psutil.AccessDenied:
            # 权限不足
            error_msg = f'权限不足，无法终止进程 {pid}。请以管理员身份运行应用。'
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error': 'AccessDenied'
            }
            
        except Exception as e:
            # 其他异常
            error_msg = f'终止进程 {pid} 时发生异常: {str(e)}'
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg,
                'error': str(e)
            }
