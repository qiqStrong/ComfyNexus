"""
ComfyUI 进程管理器

负责启动、停止和监控 ComfyUI 进程,并实时推送日志到前端。
"""

import subprocess
import sys
import threading
import json
import uuid
import re
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from ...utils.logger import app_logger as logger


class ComfyUIProcess:
    """ComfyUI 进程管理器"""
    
    def __init__(self, window):
        """
        初始化进程管理器
        
        Args:
            window: pywebview 窗口对象,用于推送日志到前端
        """
        self.window = window
        self.process: Optional[subprocess.Popen] = None
        self.is_running = False
        self.stdout_thread: Optional[threading.Thread] = None
        self.stderr_thread: Optional[threading.Thread] = None
        self.env_id: Optional[str] = None
        self.traceback_buffer: List[str] = []  # Traceback 缓冲区
        self.in_traceback = False  # 是否正在读取 Traceback
        self.port: int = 8188  # ComfyUI 端口号，默认 8188
        self.start_time: Optional[float] = None  # 启动时间戳
        self._was_started = False  # 是否曾经启动过（用于区分"从未启动"和"启动后崩溃"）
        self._exit_code: Optional[int] = None  # 进程退出码
        self._exit_processed = False  # 是否已处理进程退出
        self._user_stopped = False  # 用户主动停止标记
        
        # 日志持久化
        self.log_file_path: Optional[Path] = None
        self.log_file = None
        self._log_lock = threading.Lock()  # 日志写入锁
    
    @staticmethod
    def _validate_proxy_url(proxy_url: str) -> bool:
        """
        验证代理 URL 格式是否有效
        
        Args:
            proxy_url: 代理 URL 字符串
            
        Returns:
            bool: 是否为有效的代理 URL 格式
        """
        if not proxy_url:
            return True
        pattern = r'^(https?|socks5?)://[^/]+:\d+/?$'
        return bool(re.match(pattern, proxy_url))
    
    @staticmethod
    def _get_clear_proxy_config() -> dict:
        """
        返回清除所有代理配置的环境变量字典
        
        Returns:
            dict: 清除代理的环境变量字典
        """
        return {
            "http_proxy": "",
            "https_proxy": "",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "all_proxy": "",
            "NO_PROXY": "",
            "no_proxy": "",
        }
    
    def _get_proxy_config_for_comfyui(self) -> dict:
        """
        获取代理配置（用于 ComfyUI 进程）
        
        从设置管理器读取代理配置。
        与 Git 代理配置不同，这里不需要 GIT_CONFIG_* 变量。
        
        Returns:
            dict: 代理配置环境变量字典
        """
        try:
            from backend.src.core.settings_manager import SettingsManager
            
            settings_manager = SettingsManager()
            result = settings_manager.get_settings()
            
            if not result.get("success"):
                return self._get_clear_proxy_config()
            
            settings = result.get("settings", {})
            proxy = settings.get("proxy", {})
            
            if not proxy.get("enabled"):
                return self._get_clear_proxy_config()
            
            host = proxy.get("host", "").strip()
            port = proxy.get("port", "").strip()
            
            if not host or not port:
                logger.warning("[ComfyUIProcess] 代理配置不完整")
                return self._get_clear_proxy_config()
            
            proxy_url = f"http://{host}:{port}"
            
            if not self._validate_proxy_url(proxy_url):
                logger.error(f"[ComfyUIProcess] 无效的代理 URL 格式: {proxy_url}")
                return self._get_clear_proxy_config()
            
            return {
                "http_proxy": proxy_url,
                "https_proxy": proxy_url,
                "HTTP_PROXY": proxy_url,
                "HTTPS_PROXY": proxy_url,
                "ALL_PROXY": "",
                "all_proxy": "",
                "NO_PROXY": "",
                "no_proxy": "",
            }
            
        except Exception as e:
            logger.error(f"[ComfyUIProcess] 获取代理配置失败: {e}")
            return self._get_clear_proxy_config()
    
    def start(self, python_path: str, comfyui_path: str, args: List[str] = None, env_config: dict = None, show_console_window: bool = False):
        """
        启动 ComfyUI 进程
        
        Args:
            python_path: Python 目录路径或可执行文件路径
            comfyui_path: ComfyUI 目录路径
            args: 额外的命令行参数
            env_config: 环境配置字典（包含 env_type, advanced_env_vars 等配置）
            show_console_window: 是否显示后台命令行窗口（默认 False，隐藏窗口）
        
        Raises:
            RuntimeError: 如果 ComfyUI 已经在运行中
        """
        if self.is_running:
            raise RuntimeError("ComfyUI 已经在运行中")
        
        # 获取环境类型
        env_type = env_config.get("env_type", "portable") if env_config else "portable"
        
        # 桌面版需要额外参数
        if env_type == "desktop":
            from ..env.desktop_launch_args import DesktopLaunchArgsBuilder
            desktop_data_path = env_config.get("desktop_data_path", "") if env_config else ""
            desktop_args = DesktopLaunchArgsBuilder.build_args(comfyui_path, desktop_data_path)
            if args:
                args = desktop_args + args  # 合并参数（桌面版参数在前）
            else:
                args = desktop_args
            self._push_log('INFO', f'检测到桌面版环境，已注入桌面版启动参数')
        
        # 从启动参数中提取端口号
        self._extract_port_from_args(args)
        
        # 创建日志文件
        self._create_log_file()
        
        # 转换为 Path 对象
        python_path_obj = Path(python_path)
        comfyui_path_obj = Path(comfyui_path)
        main_py_path = comfyui_path_obj / "main.py"
        
        # 推送启动日志
        self._push_log('INFO', f'正在启动 ComfyUI...')
        self._push_log('INFO', f'工作目录: {comfyui_path}')
        
        # 检查 ComfyUI 路径
        if not comfyui_path_obj.exists():
            error_msg = f'ComfyUI 路径不存在: {comfyui_path}'
            self._push_log('ERROR', error_msg)
            raise FileNotFoundError(error_msg)
        
        if not main_py_path.exists():
            error_msg = f'main.py 不存在: {main_py_path}'
            self._push_log('ERROR', error_msg)
            raise FileNotFoundError(error_msg)
        
        # 处理 Python 路径
        # 如果 python_path 是目录，自动拼接 python.exe
        if python_path_obj.is_dir():
            python_exe = python_path_obj / "python.exe"
            if not python_exe.exists():
                error_msg = f'Python 可执行文件不存在: {python_exe}'
                self._push_log('ERROR', error_msg)
                self._push_log('ERROR', f'Python 目录: {python_path}')
                raise FileNotFoundError(error_msg)
            python_path_obj = python_exe
            self._push_log('INFO', f'Python 路径: {python_path_obj}')
        elif python_path_obj.is_file():
            # 如果是文件，直接使用
            self._push_log('INFO', f'Python 路径: {python_path_obj}')
        else:
            # 路径不存在
            error_msg = f'Python 路径不存在: {python_path}'
            self._push_log('ERROR', error_msg)
            raise FileNotFoundError(error_msg)
        
        # 部署 Comfyui-Box Bridge 插件
        self._deploy_bridge_plugin(comfyui_path_obj, env_config)
        
        # 构建命令
        cmd = [str(python_path_obj), str(main_py_path)]
        
        if args:
            cmd.extend(args)
        
        # 输出完整的启动命令到日志文件
        # logger.dev(f'[ComfyUI 启动] 完整命令: {" ".join(cmd)}')
        # logger.dev(f'[ComfyUI 启动] 工作目录: {comfyui_path}')
        
        self._push_log('INFO', f'执行命令: {" ".join(cmd)}')
        self._push_log('INFO', '已设置 UTF-8 编码环境变量（PYTHONIOENCODING=utf-8, PYTHONUTF8=1）')
        
        try:
            # 准备环境变量
            import os
            env = os.environ.copy()
            
            # 设置 UTF-8 编码环境变量（解决中文乱码问题）
            env['PYTHONIOENCODING'] = 'utf-8'  # Python 输出编码
            env['PYTHONUTF8'] = '1'  # Python 3.7+ UTF-8 模式
            
            # Windows 特定设置
            if os.name == 'nt':
                # 设置控制台代码页为 UTF-8
                env['PYTHONLEGACYWINDOWSSTDIO'] = '0'  # 使用新的 Windows 控制台 API
                # 注意：不设置 LANG 和 LC_ALL，因为 Windows 不使用这些变量
            else:
                # Unix/Linux 系统
                env['LANG'] = 'en_US.UTF-8'
                env['LC_ALL'] = 'en_US.UTF-8'
            
            # 注入代理配置
            proxy_config = self._get_proxy_config_for_comfyui()
            env.update(proxy_config)
            
            proxy_url = proxy_config.get('HTTP_PROXY', '')
            if proxy_url:
                self._push_log('INFO', f'🌐 已注入代理配置: {proxy_url}')
            else:
                self._push_log('DEBUG', '未配置代理或代理已禁用')
            
            # 注入 GPU 设备环境变量
            # 极客模式下完全跳过 GPU 环境变量注入，由用户通过自定义参数完全控制
            is_geek_mode = False
            if env_config and 'acceleration' in env_config:
                accel = env_config['acceleration']
                geek_mode = accel.get('geekMode') or accel.get('geek_mode', {})
                is_geek_mode = geek_mode.get('enabled', False) if geek_mode else False

            gpu_env_vars = {}

            if is_geek_mode:
                self._push_log('INFO', '🔧 极客模式已启用，跳过 GPU 环境变量注入（由用户自定义参数控制）')
            elif env_config and 'acceleration' in env_config:
                accel = env_config['acceleration']
                compute_device = accel.get('computeDevice') or accel.get('compute_device', '')
                if compute_device == "auto":
                    compute_device = ''

                if compute_device and compute_device != "cpu":
                    compat_warning = self._check_device_backend_compat(compute_device, str(python_path_obj))
                    if compat_warning:
                        self._push_log('WARNING', compat_warning)

                if compute_device == "cpu":
                    gpu_env_vars['CUDA_VISIBLE_DEVICES'] = '-1'
                    gpu_env_vars['HIP_VISIBLE_DEVICES'] = '-1'
                    gpu_env_vars['ONEAPI_DEVICE_SELECTOR'] = '!*:*'
                    self._push_log('INFO', '💻 使用 CPU 模式')

                elif compute_device.startswith(("gpu:", "nvidia:")):
                    gpu_index = compute_device.split(":")[1] if ":" in compute_device else "0"
                    gpu_env_vars['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
                    gpu_env_vars['CUDA_VISIBLE_DEVICES'] = gpu_index
                    gpu_env_vars['HIP_VISIBLE_DEVICES'] = '-1'
                    gpu_env_vars['ONEAPI_DEVICE_SELECTOR'] = '!*:*'
                    self._push_log('INFO', f'🎮 设置 NVIDIA GPU: {gpu_index} (CUDA_VISIBLE_DEVICES={gpu_index}, PCI_BUS_ID 排序)')

                elif compute_device.startswith(("intel:", "intel-arc:")):
                    gpu_index = compute_device.split(":")[1] if ":" in compute_device else "0"
                    oneapi_selector = f"gpu.{gpu_index}" if gpu_index.isdigit() else gpu_index
                    gpu_env_vars['ONEAPI_DEVICE_SELECTOR'] = oneapi_selector
                    gpu_env_vars['CUDA_VISIBLE_DEVICES'] = '-1'
                    gpu_env_vars['HIP_VISIBLE_DEVICES'] = '-1'
                    self._push_log('INFO', f'🔵 设置 Intel GPU: {gpu_index} (ONEAPI_DEVICE_SELECTOR={oneapi_selector})')

                elif compute_device.startswith("amd:"):
                    gpu_index = compute_device.split(":")[1] if ":" in compute_device else "0"
                    gpu_env_vars['CUDA_VISIBLE_DEVICES'] = '-1'
                    gpu_env_vars['HIP_VISIBLE_DEVICES'] = gpu_index
                    gpu_env_vars['ONEAPI_DEVICE_SELECTOR'] = '!*:*'
                    self._push_log('INFO', f'🔴 设置 AMD GPU (ROCm): {gpu_index} (HIP_VISIBLE_DEVICES={gpu_index}, CUDA 已屏蔽)')
            
            # 注入自定义环境变量（先注入，GPU 设备变量后注入以确保优先级）
            if env_config:
                self._push_log('DEBUG', f'收到 env_config: {list(env_config.keys())}')
                
                if env_config.get('advanced_env_vars'):
                    from backend.src.utils.env_parser import parse_env_vars
                    
                    env_vars_text = env_config['advanced_env_vars']
                    self._push_log('DEBUG', f'环境变量文本长度: {len(env_vars_text)} 字符')
                    
                    custom_env_vars = parse_env_vars(env_vars_text)
                    
                    if custom_env_vars:
                        gpu_env_var_keys = {
                            'CUDA_VISIBLE_DEVICES', 'HIP_VISIBLE_DEVICES',
                            'ONEAPI_DEVICE_SELECTOR', 'CUDA_DEVICE_ORDER',
                        }
                        conflicting_keys = gpu_env_var_keys & set(custom_env_vars.keys())
                        if conflicting_keys and not is_geek_mode:
                            self._push_log('WARNING', f'⚠️ 自定义环境变量 {", ".join(conflicting_keys)} 与 GPU 设备选择冲突，设备选择设置将优先生效')

                        env.update(custom_env_vars)
                        self._push_log('INFO', f'✅ 已注入 {len(custom_env_vars)} 个自定义环境变量')
                        
                        self._push_log('INFO', '📋 注入的环境变量:')
                        for key, value in custom_env_vars.items():
                            self._push_log('INFO', f'   {key} = {value}')
                    else:
                        self._push_log('DEBUG', '解析后的环境变量为空')
                else:
                    self._push_log('DEBUG', '未配置高级环境变量（advanced_env_vars 为空）')
            else:
                self._push_log('DEBUG', '未收到 env_config 参数')
            
            # GPU 设备环境变量最后注入，确保优先级高于自定义环境变量
            if gpu_env_vars:
                env.update(gpu_env_vars)
                self._push_log('DEBUG', f'🔒 已注入 GPU 设备环境变量（优先级最高）: {list(gpu_env_vars.keys())}')
            
            # 根据设置决定是否显示控制台窗口
            creation_flags = 0
            if not show_console_window and hasattr(subprocess, 'CREATE_NO_WINDOW'):
                creation_flags = subprocess.CREATE_NO_WINDOW
                self._push_log('DEBUG', '已设置隐藏控制台窗口')
            else:
                self._push_log('DEBUG', '控制台窗口将显示')
            
            # 启动进程
            self.process = subprocess.Popen(
                cmd,
                cwd=str(comfyui_path_obj),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # 行缓冲
                encoding='utf-8',
                errors='replace',  # 处理编码错误
                env=env,  # 传递环境变量
                creationflags=creation_flags
            )
            
            self.is_running = True
            self.start_time = time.time()  # 记录启动时间
            self._was_started = True  # 标记已启动过
            self._exit_processed = False  # 重置退出处理标记
            self._exit_code = None  # 重置退出码
            self._user_stopped = False  # 重置用户停止标记
            
            # 启动日志监听线程
            self.stdout_thread = threading.Thread(
                target=self._read_output,
                args=(self.process.stdout, 'INFO'),
                daemon=True
            )
            self.stdout_thread.start()
            
            self.stderr_thread = threading.Thread(
                target=self._read_output,
                args=(self.process.stderr, 'INFO'),  # 改为 INFO，让解析器自动判断级别
                daemon=True
            )
            self.stderr_thread.start()
            
            # 推送启动成功日志
            self._push_log('INFO', f'ComfyUI 进程已启动 (PID: {self.process.pid})')
            
        except PermissionError as e:
            self.is_running = False
            error_msg = f'权限不足 (WinError 5): {str(e)}'
            self._push_log('ERROR', error_msg)
            self._push_log('ERROR', '请尝试以管理员身份运行应用程序')
            self._push_log('ERROR', f'Python 路径: {python_path}')
            self._push_log('ERROR', f'ComfyUI 路径: {comfyui_path}')
            raise PermissionError(error_msg)
        except FileNotFoundError as e:
            self.is_running = False
            error_msg = f'文件未找到: {str(e)}'
            self._push_log('ERROR', error_msg)
            raise
        except Exception as e:
            self.is_running = False
            error_msg = f'启动失败: {str(e)}'
            self._push_log('ERROR', error_msg)
            self._push_log('ERROR', f'错误类型: {type(e).__name__}')
            raise

    def _check_device_backend_compat(self, compute_device: str, python_path: str) -> str:
        """
        检查 compute_device 与 PyTorch 后端的兼容性

        Args:
            compute_device: 计算设备标识，如 "nvidia:0", "amd:0", "intel:0"
            python_path: Python 可执行文件路径

        Returns:
            警告字符串，如果兼容则返回空字符串
        """
        try:
            from ..env.device_detector import DeviceDetector
            detector = DeviceDetector()
            backend_info = detector.detect_pytorch_backend(python_path)
            backend = backend_info.backend

            if backend == "unknown":
                return ""

            if backend == "none":
                return f"⚠️ 当前环境未安装 PyTorch，选择 {compute_device} 可能无法正常使用 GPU"

            device_type = compute_device.split(":")[0] if ":" in compute_device else compute_device

            compat_map = {
                "cuda": {"nvidia": True, "gpu": True, "amd": False, "intel": False, "intel-arc": False},
                "rocm": {"nvidia": False, "gpu": False, "amd": True, "intel": False, "intel-arc": False},
                "xpu": {"nvidia": False, "gpu": False, "amd": False, "intel": True, "intel-arc": True},
            }

            if backend in compat_map:
                is_compat = compat_map[backend].get(device_type, None)
                if is_compat is False:
                    backend_label = {"cuda": "CUDA", "rocm": "ROCm", "xpu": "XPU"}.get(backend, backend)
                    return f"⚠️ 不兼容：选择的设备 {compute_device} 与当前环境的 {backend_label} 版 PyTorch 不兼容，可能无法正常使用 GPU"

            return ""
        except Exception as e:
            logger.debug(f"设备兼容性检查失败: {e}")
            return ""

    def stop(self):
        """停止 ComfyUI 进程"""
        if not self.is_running or not self.process:
            self._push_log('WARNING', 'ComfyUI 未运行')
            return
        
        self._user_stopped = True  # 标记为用户主动停止
        self._push_log('INFO', 'ComfyUI 停止中...')
        
        pid = self.process.pid
        port = self.port
        
        try:
            import signal
            import os
            
            if os.name == 'nt':  # Windows
                try:
                    import subprocess as sp
                    sp.run(['taskkill', '/F', '/T', '/PID', str(pid)], 
                           capture_output=True, 
                           timeout=10)
                    self._push_log('INFO', 'ComfyUI 已正常停止')
                except Exception as e:
                    self._push_log('WARNING', f'taskkill 失败，尝试其他方法: {str(e)}')
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                        self._push_log('INFO', 'ComfyUI 已正常停止')
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
                        self._push_log('WARNING', 'ComfyUI 被强制终止')
            else:
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                    self.process.wait(timeout=5)
                    self._push_log('INFO', 'ComfyUI 已正常停止')
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    self.process.wait()
                    self._push_log('WARNING', 'ComfyUI 被强制终止')
            
            for _ in range(50):
                if self.process.poll() is not None:
                    break
                time.sleep(0.1)
            
            self._wait_for_port_release(port)
            
        except Exception as e:
            self._push_log('ERROR', f'停止失败: {str(e)}')
        finally:
            self.is_running = False
            self.process = None
            self.start_time = None
            self._was_started = False
            self._close_log_file()
    
    def _wait_for_port_release(self, port: int, max_wait: float = 5.0) -> bool:
        """
        等待端口释放
        
        Args:
            port: 端口号
            max_wait: 最大等待时间（秒）
            
        Returns:
            True 如果端口已释放，False 如果超时
        """
        waited = 0.0
        while waited < max_wait:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                if result != 0:
                    self._push_log('DEBUG', f'端口 {port} 已释放')
                    return True
            except (socket.error, OSError) as e:
                self._push_log('DEBUG', f'端口检测异常: {e}')
                return True
            
            time.sleep(0.2)
            waited += 0.2
        
        self._push_log('WARNING', f'端口 {port} 未在预期时间内释放')
        return False
    
    def _read_output(self, pipe, default_level: str):
        """
        读取进程输出并推送到前端
        
        Args:
            pipe: stdout 或 stderr
            default_level: 默认日志级别
        """
        logger.info(f"[_read_output] 线程启动，pipe={pipe}, default_level={default_level}")
        try:
            current_line = ""  # 当前行缓冲
            last_progress_id = None  # 上一个进度条日志的ID
            line_count = 0
            
            while True:
                char = pipe.read(1)
                if not char:
                    logger.info(f"[_read_output] 管道关闭，共读取 {line_count} 行")
                    break
                
                if char == '\r':
                    # 回车符：原地更新（进度条）
                    if current_line.strip():
                        # 如果是进度条更新，使用相同的ID覆盖前一条
                        if last_progress_id and self._is_progress_line(current_line):
                            self._update_log(last_progress_id, current_line.strip(), default_level)
                        else:
                            last_progress_id = self._process_log_line(current_line.strip(), default_level, is_progress=True)
                    current_line = ""
                elif char == '\n':
                    # 换行符：新的一行
                    if current_line.strip():
                        self._process_log_line(current_line.strip(), default_level)
                        line_count += 1
                    current_line = ""
                    last_progress_id = None  # 重置进度条ID
                else:
                    current_line += char
            
            # 处理最后一行
            if current_line.strip():
                self._process_log_line(current_line.strip(), default_level)
            
            # 处理最后可能残留的 Traceback
            if self.in_traceback and self.traceback_buffer:
                self._flush_traceback()
            
            # 管道关闭，检查进程是否异常退出（只处理一次）
            # 使用局部变量保存进程引用，避免在检查过程中 self.process 被设置为 None
            current_process = self.process
            if current_process and not self._exit_processed:
                self._exit_processed = True  # 标记已处理
                
                # 等待进程退出（最多等待 5 秒）
                exit_code = None
                for i in range(50):
                    poll_result = current_process.poll()
                    if poll_result is not None:
                        exit_code = poll_result
                        break
                    time.sleep(0.1)
                
                logger.info(f"[_read_output] 进程退出，exit_code={exit_code}, user_stopped={self._user_stopped}")
                
                if exit_code is not None:
                    self._exit_code = exit_code  # 记录退出码
                    
                    # 只有在非用户主动停止且退出码非 0 时才显示启动失败
                    if exit_code != 0 and not self._user_stopped:
                        # 进程异常退出，写入启动失败提示到日志文件
                        logger.info(f"[_read_output] 进程异常退出，准备写入启动失败提示")
                        self._write_startup_failed_message(exit_code)
                    elif self._user_stopped:
                        # 用户主动停止，不显示错误提示
                        logger.info(f"[_read_output] 用户主动停止进程")
                    else:
                        # 进程正常退出
                        self._push_log('INFO', 'ComfyUI 进程已退出')
                    
                    # 更新运行状态
                    self.is_running = False
                    self.start_time = None
                else:
                    logger.warning("[_read_output] 进程未在预期时间内退出")
                
        except Exception as e:
            self._push_log('ERROR', f'日志读取错误: {str(e)}')
        finally:
            try:
                pipe.close()
            except (OSError, IOError):
                pass
    
    def _is_progress_line(self, line: str) -> bool:
        """
        判断是否是进度条行
        
        Args:
            line: 日志行
            
        Returns:
            是否是进度条
        """
        # 常见的进度条特征
        progress_indicators = ['%', 'MB/s', 'KB/s', 'GB/s', 'it/s', 'ETA', '[', ']', '█', '▓', '░']
        return any(indicator in line for indicator in progress_indicators)
    
    def _update_log(self, log_id: str, message: str, level: str):
        """
        更新已存在的日志（用于进度条）
        
        Args:
            log_id: 日志ID
            message: 新的消息内容
            level: 日志级别
        """
        log = {
            'id': log_id,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': level,
            'source': 'comfyui',
            'message': message,
            'isUpdate': True  # 标记为更新
        }
        
        # 推送更新到前端
        try:
            js_code = f'window.onComfyUILog && window.onComfyUILog({json.dumps(log)})'
            self.window.evaluate_js(js_code)
        except Exception as e:
            logger.warning(f'推送日志更新失败: {e}')
    
    def _process_log_line(self, line: str, default_level: str, is_progress: bool = False) -> str:
        """
        处理单行日志，识别并合并 Traceback
        
        Args:
            line: 日志行
            default_level: 默认日志级别
            is_progress: 是否是进度条
            
        Returns:
            日志ID（如果创建了新日志）
        """
        line_upper = line.upper()
        
        # 检查是否是 Traceback 开始
        if 'TRACEBACK' in line_upper and 'MOST RECENT CALL LAST' in line_upper:
            # 如果之前有未完成的 Traceback，先推送
            if self.in_traceback and self.traceback_buffer:
                self._flush_traceback()
            
            # 开始新的 Traceback
            self.in_traceback = True
            self.traceback_buffer = [line]
            return None
        
        # 如果正在读取 Traceback
        if self.in_traceback:
            # 先检查这一行是否是新的日志行（不属于 Traceback）
            if self._is_new_log_line(line):
                # 结束 Traceback，但不包含这一行
                self._flush_traceback()
                # 继续处理这一行作为普通日志
                parsed_level = self._parse_log_level(line)
                return self._push_log(parsed_level or default_level, line)
            
            # 这一行属于 Traceback，添加到缓冲区
            self.traceback_buffer.append(line)
            
            # 检查是否是 Traceback 的最后一行（异常类型行）
            if self._is_exception_line(line):
                self._flush_traceback()
            return None
        
        # 普通日志行
        parsed_level = self._parse_log_level(line)
        return self._push_log(parsed_level or default_level, line)
    
    def _is_new_log_line(self, line: str) -> bool:
        """
        判断是否是新的日志行（不属于 Traceback）
        
        关键判断：
        1. 如果行以 [INFO]/[ERROR] 等标记开头，提取标记后的内容
        2. 检查内容是否是 Traceback 的一部分
        
        Traceback 的特征：
        - File "...", line X, in Y
        - 代码行（包含 import, from, return, raise 等）
        - 异常类型行（ImportError:, ValueError: 等）
        - Cannot import ... module for custom nodes
        - ^^^^ 错误位置指示符（Python 3.10+）
        - ~~~~ 波浪线指示符
        
        新日志的特征：
        - 不包含上述 Traceback 特征
        - 包含中文字符
        - 是正常的日志消息（如 "Loading models..."）
        
        Args:
            line: 日志行
            
        Returns:
            True 如果是新的日志行
        """
        line_stripped = line.strip()
        
        # 空行不是新日志
        if not line_stripped:
            return False
        
        # 提取实际内容（移除 [INFO], [ERROR] 等标记）
        content = line_stripped
        if line_stripped.startswith('['):
            bracket_end = line_stripped.find(']')
            if bracket_end > 0:
                content = line_stripped[bracket_end + 1:].strip()
        
        # 如果没有内容，不是新日志
        if not content:
            return False
        
        # 检查是否是错误位置指示符（Python 3.10+ 特性）
        # 如 ^^^^, ~~~~, ----
        if len(content) > 3 and all(c in '^~-' for c in content):
            return False
        
        # 以空格或 Tab 开头（缩进），是 Traceback 的一部分
        if content.startswith(' ') or content.startswith('\t'):
            return False
        
        # 以 File " 开头，是 Traceback 的文件行
        if content.startswith('File "') or content.startswith("File '"):
            return False
        
        # 检查是否是异常类型行
        if self._is_exception_line(content):
            return False
        
        # 检查是否包含 Traceback 相关的错误消息模式
        content_lower = content.lower()
        error_message_patterns = [
            'cannot import',
            'module for custom nodes',
            'failed to load',
            'error loading',
            'import error',
            'module not found',
            'no module named',
            'failed to import',
            'could not import',
            'unable to import',
            'connection reset',
            'connection error',
            'timeout error',
            'ssl error',
            'handshake'
        ]
        
        if any(pattern in content_lower for pattern in error_message_patterns):
            return False
        
        # 检查是否是代码行（包含 Python 关键词）
        # 这些通常是 Traceback 堆栈中的代码
        code_patterns = [
            'import ',
            'from ',
            ' import',
            'return ',
            'raise ',
            'await ',
            'async ',
            'def ',
            'class ',
            ' = ',
            '()',
            '.py"',
            ".py'",
            'exec_module',
            '_bootstrap',
            '__init__',
            '__enter__',
            '__exit__',
            'self.',
            'await ',
            'waiter'
        ]
        
        if any(pattern in content for pattern in code_patterns):
            return False
        
        # 包含中文字符，很可能是新日志
        if any('\u4e00' <= char <= '\u9fff' for char in content):
            return True
        
        # 如果到这里，检查是否看起来像正常的日志消息
        # 正常日志通常是完整的句子，不包含代码特征
        # 如果内容较长且不包含代码特征，可能是新日志
        if len(content) > 20 and not any(char in content for char in ['(', ')', '"', "'"]):
            return True
        
        # 默认认为是 Traceback 的一部分（保守策略）
        return False
    
    def _is_exception_line(self, line: str) -> bool:
        """
        判断是否是异常类型行（Traceback 的最后一行）
        
        Args:
            line: 日志行
            
        Returns:
            True 如果是异常类型行
        """
        line_stripped = line.strip()
        
        # 空行不是异常行
        if not line_stripped:
            return False
        
        # 必须包含冒号
        if ':' not in line_stripped:
            return False
        
        # 提取冒号前的部分
        first_part = line_stripped.split(':')[0].strip()
        
        # 常见的异常类型
        exception_types = [
            'ERROR', 'EXCEPTION', 'IMPORTERROR', 'VALUEERROR', 
            'TYPEERROR', 'ATTRIBUTEERROR', 'KEYERROR', 'INDEXERROR',
            'RUNTIMEERROR', 'NAMEERROR', 'SYNTAXERROR', 'OSERROR',
            'IOERROR', 'FILENOTFOUNDERROR', 'PERMISSIONERROR',
            'MODULENOTFOUNDERROR', 'ASSERTIONERROR', 'ZERODIVISIONERROR'
        ]
        
        # 检查是否是异常类型
        first_part_upper = first_part.upper().replace(' ', '')
        return any(exc in first_part_upper for exc in exception_types)
    
    def _flush_traceback(self):
        """推送完整的 Traceback 到前端"""
        if self.traceback_buffer:
            # 合并所有行
            full_traceback = '\n'.join(self.traceback_buffer)
            self._push_log('ERROR', full_traceback)
            
            # 清空缓冲区
            self.traceback_buffer = []
            self.in_traceback = False
    
    def _parse_log_level(self, line: str) -> Optional[str]:
        """
        从日志行中解析级别
        
        ComfyUI 日志格式示例:
        - [INFO] Loading models...
        - [WARNING] Model not found
        - [ERROR] Failed to load
        - ERROR: Failed to load
        - WARNING: Model not found
        - [DEPRECATION WARNING] Detected import of deprecated legacy API
        
        Args:
            line: 日志行
            
        Returns:
            日志级别 (ERROR/WARNING/INFO/DEBUG) 或 None
        """
        line_upper = line.upper()
        
        # 特殊处理：检测需要安装包的错误消息
        # 例如：To use the `--use-flash-attention` feature, the `flash-attn` package must be installed first.
        # 这类消息会导致 ComfyUI 无法启动，但显示的是 INFO 级别，需要识别为 ERROR
        if 'MUST BE INSTALLED FIRST' in line_upper or 'PACKAGE MUST BE INSTALLED' in line_upper:
            return 'ERROR'
        
        # 特殊处理：如果日志内容中包含 "Warning:" 或 "WARNING"，即使有 [ERROR] 标记也应该是 WARNING
        # 例如：[ERROR] [W129 ...] Warning: PYTORCH_CUDA_ALLOC_CONF is deprecated
        # 例如：[INFO] [DEPRECATION WARNING] Detected import of deprecated legacy API
        if 'WARNING:' in line_upper or '] WARNING:' in line_upper or 'WARNING]' in line_upper:
            return 'WARNING'
        
        # 优先检查明确的日志级别标记
        if '[ERROR]' in line_upper or line_upper.startswith('ERROR:'):
            return 'ERROR'
        elif '[WARNING]' in line_upper or line_upper.startswith('WARNING:'):
            return 'WARNING'
        elif '[DEBUG]' in line_upper or line_upper.startswith('DEBUG:'):
            return 'DEBUG'
        elif '[INFO]' in line_upper or line_upper.startswith('INFO:'):
            return 'INFO'
        
        # 检查是否包含错误关键词（但要排除误报）
        error_keywords = [
            # 英文错误关键词
            'ERROR',
            'FAILED',
            'FAILURE',
            'EXCEPTION',
            'TRACEBACK',
            'CRITICAL',
            'FATAL',
            'CANNOT',
            'CAN NOT',
            'CAN\'T',
            'UNABLE',
            'INVALID',
            'MISSING',
            'NOT FOUND',
            'NOTFOUND',
            'DENIED',
            'REFUSED',
            'TIMEOUT',
            'TIMED OUT',
            'ABORTED',
            'ABORT',
            'CRASH',
            'CRASHED',
            'PANIC',
            'CORRUPT',
            'CORRUPTED',
            'BROKEN',
            'DAMAGE',
            'DAMAGED',
            'UNAVAILABLE',
            'UNREACHABLE',
            'INACCESSIBLE',
            'PERMISSION',
            'FORBIDDEN',
            'UNAUTHORIZED',
            'ACCESS DENIED',
            'OUT OF MEMORY',
            'MEMORY ERROR',
            'SEGMENTATION FAULT',
            'SEGFAULT',
            'CORE DUMP',
            'STACK OVERFLOW',
            'BUFFER OVERFLOW',
            'NULL POINTER',
            'ASSERTION FAILED',
            'ASSERT FAILED',
            'SYNTAX ERROR',
            'PARSE ERROR',
            'COMPILATION ERROR',
            'RUNTIME ERROR',
            'IMPORT ERROR',
            'MODULE ERROR',
            'DEPENDENCY ERROR',
            'VERSION MISMATCH',
            'INCOMPATIBLE',
            'CONFLICT',
            'DUPLICATE',
            'ALREADY EXISTS',
            'DOES NOT EXIST',
            'NO SUCH',
            'UNRECOGNIZED',
            'UNKNOWN',
            'UNSUPPORTED',
            'DEPRECATED',
            'OBSOLETE',
            'DISCONNECTED',
            'CONNECTION LOST',
            'CONNECTION FAILED',
            'NETWORK ERROR',
            'SOCKET ERROR',
            'SSL ERROR',
            'TLS ERROR',
            'CERTIFICATE ERROR',
            'HANDSHAKE FAILED',
            'AUTHENTICATION FAILED',
            'LOGIN FAILED',
            'BIND FAILED',
            'LISTEN FAILED',
            'READ ERROR',
            'WRITE ERROR',
            'IO ERROR',
            'FILE ERROR',
            'DISK ERROR',
            'QUOTA EXCEEDED',
            'LIMIT EXCEEDED',
            'TOO MANY',
            'OVERFLOW',
            'UNDERFLOW',
            'DIVISION BY ZERO',
            'ZERO DIVISION',
            'INDEX OUT OF',
            'OUT OF RANGE',
            'OUT OF BOUNDS',
            'ILLEGAL',
            'VIOLATION',
            'BREACH',
            'VULNERABILITY',
            'EXPLOIT',
            'MALFORMED',
            'MALICIOUS',
            'SUSPICIOUS',
            'ANOMALY',
            'ABNORMAL',
            'UNEXPECTED',
            'UNHANDLED',
            'UNCAUGHT',
            'UNINITIALIZED',
            'UNDEFINED',
            'NULL',
            'EMPTY',
            'BLANK',
            'ZERO',
            'NEGATIVE',
            'POSITIVE INFINITY',
            'NEGATIVE INFINITY',
            'NOT A NUMBER',
            
            # 中文错误关键词
            '错误',
            '失败',
            '异常',
            '崩溃',
            '无法',
            '不能',
            '未找到',
            '找不到',
            '不存在',
            '已损坏',
            '损坏',
            '无效',
            '非法',
            '拒绝',
            '超时',
            '中止',
            '终止',
            '中断',
            '丢失',
            '缺失',
            '缺少',
            '不支持',
            '不兼容',
            '冲突',
            '重复',
            '溢出',
            '越界',
            '内存不足',
            '磁盘已满',
            '权限不足',
            '访问被拒绝',
            '连接失败',
            '网络错误',
            '读取失败',
            '写入失败',
            '解析失败',
            '编译失败',
            '导入失败',
            '加载失败',
            '初始化失败',
            '配置错误',
            '参数错误',
            '类型错误',
            '值错误',
            '键错误',
            '索引错误',
            '属性错误',
            '名称错误',
            '运行时错误',
            '语法错误',
            '断言失败',
            '未定义',
            '未初始化',
            '未处理',
            '未捕获',
            '意外',
            '异常退出',
            '强制退出',
            '非正常退出'
        ]
        
        # 排除的关键词（这些不是真正的错误）
        exclude_keywords = [
            'LOADING',
            'LOADED',
            'DETECTED',
            'UPDATED',
            'INITIALIZED',
            'REVISION',
            'VERSION',
            'CACHE',
            'PREVIEW',
            'OVERRIDE',
            'DISABLED',
            'DETACHED',
            'SUCCESSFULLY',
            'SUCCESS',
            'COMPLETE',
            'COMPLETED',
            'FINISHED',
            'DONE',
            'OK',
            'READY',
            'AVAILABLE',
            'ENABLED',
            'ACTIVATED',
            'STARTED',
            'RUNNING',
            'PROCESSING',
            'SKIPPED',
            'SKIPPING',
            'IGNORED',
            'IGNORING',
            'OPTIONAL',
            'RECOMMENDED',
            'SUGGESTED',
            'TIP',
            'HINT',
            'NOTE',
            'INFO',
            'INFORMATION',
            '成功',
            '完成',
            '已完成',
            '正常',
            '正在',
            '加载中',
            '已加载',
            '检测到',
            '已更新',
            '已初始化',
            '可用',
            '已启用',
            '已激活',
            '已启动',
            '运行中',
            '处理中',
            '跳过',
            '忽略',
            '可选',
            '建议',
            '提示',
            '注意',
            '信息'
        ]
        
        # 如果包含排除关键词，不认为是错误
        if any(keyword in line_upper for keyword in exclude_keywords):
            return 'INFO'
        
        # 如果包含错误关键词，才认为是错误
        if any(keyword in line_upper for keyword in error_keywords):
            return 'ERROR'
        
        return None
    
    def _push_log(self, level: str, message: str) -> str:
        """
        推送日志到前端并写入文件
        
        Args:
            level: 日志级别 (INFO/WARNING/ERROR/DEBUG)
            message: 日志消息
            
        Returns:
            日志ID
        """
        log_id = str(uuid.uuid4())
        log = {
            'id': log_id,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'level': level,
            'source': 'comfyui',
            'message': message
        }
        
        # 写入日志文件
        self._write_to_log_file(log)
        
        # 通过 pywebview 推送到前端
        try:
            js_code = f'window.onComfyUILog && window.onComfyUILog({json.dumps(log)})'
            self.window.evaluate_js(js_code)
        except Exception as e:
            # 推送失败时记录到日志
            logger.debug(f'[{level}] {message}')
            logger.warning(f'推送日志失败: {e}')
        
        return log_id
    
    def get_status(self) -> dict:
        """
        获取进程状态
        
        Returns:
            包含运行状态、进程ID、端口信息、任务状态和运行时长的字典
        """
        # 检查进程是否存活
        process_alive = self.is_alive()
        
        # 如果进程已死，更新 is_running 状态
        if not process_alive and self.is_running:
            self.is_running = False
            self.start_time = None
            self._close_log_file()
        
        # 首先尝试检测外部 ComfyUI 进程
        external_info = self._detect_external_comfyui()
        external_pid = None
        external_port = None
        
        if external_info:
            external_pid = external_info.get('pid')
            external_port = external_info.get('port')
            logger.debug(f"检测到外部 ComfyUI 进程: PID={external_pid}, 端口={external_port}")
        
        # 确定要检查的端口：优先使用外部进程的端口，否则使用配置的端口
        check_port = external_port if external_port else self.port
        
        # 检查端口是否可访问
        port_available = self._check_port_available(check_port)
        has_task = False
        
        # 如果进程存活且端口可用，检测任务状态
        if process_alive and port_available:
            has_task = self._check_has_task()
        
        # 计算运行时长（秒）
        uptime = 0
        if self.is_running and self.start_time is not None:
            uptime = int(time.time() - self.start_time)
        
        # 判断运行状态：
        # 1. Comfyui-Box 启动的进程：self.is_running 且进程存活且端口可用
        # 2. 外部进程：检测到外部进程且端口可用
        is_external = external_info is not None and port_available
        is_running = (self.is_running and process_alive and port_available) or is_external
        
        # 诊断日志
        # logger.dev(f"[get_status] process_alive={process_alive}, port_available={port_available}")
        # logger.dev(f"[get_status] is_running={is_running}, is_external={is_external}")
        # logger.dev(f"[get_status] self.is_running={self.is_running}, self.process={self.process}")
        # logger.dev(f"[get_status] external_info={external_info}")
        # logger.dev(f"[get_status] check_port={check_port}, self.port={self.port}")
        
        return {
            'is_running': is_running,
            'is_external': is_external,
            'pid': self.process.pid if self.process else external_pid,
            'env_id': self.env_id,
            'port': check_port,
            'port_available': port_available,
            'has_task': has_task,
            'uptime': uptime,
            'was_started': self._was_started,
            'exit_code': self._exit_code,
            'process_alive': process_alive
        }
    
    def _detect_external_comfyui(self) -> Optional[dict]:
        """
        检测外部启动的 ComfyUI 进程
        
        Returns:
            包含 pid 和 port 的字典，如果未检测到则返回 None
        """
        try:
            import psutil
            from .process_detector import ProcessDetector
            
            managed_pid = self.process.pid if self.process else None
            managed_cmdline = None
            managed_cwd = None
            
            if managed_pid:
                try:
                    psutil_proc = psutil.Process(managed_pid)
                    managed_cmdline = " ".join(psutil_proc.cmdline()) if psutil_proc.cmdline() else None
                    managed_cwd = psutil_proc.cwd()
                except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.Error):
                    pass
            
            # logger.dev(f"[_detect_external_comfyui] 开始检测外部进程")
            # logger.dev(f"[_detect_external_comfyui] managed_pid={managed_pid}")
            # logger.dev(f"[_detect_external_comfyui] managed_cmdline={managed_cmdline}")
            # logger.dev(f"[_detect_external_comfyui] managed_cwd={managed_cwd}")
            # logger.dev(f"[_detect_external_comfyui] self.process={self.process}")
            # logger.dev(f"[_detect_external_comfyui] self.is_running={self.is_running}")
            
            detector = ProcessDetector(
                managed_pid=managed_pid,
                managed_cmdline=managed_cmdline,
                managed_cwd=managed_cwd
            )
            
            processes = detector.scan_comfyui_processes()
            
            if not processes:
                logger.debug(f"[_detect_external_comfyui] 未检测到外部进程")
                return None
            
            for i, proc in enumerate(processes):
                logger.debug(f"[_detect_external_comfyui] 检测到外部进程 #{i+1}: PID={proc.get('pid')}, 端口={proc.get('port')}, 工作目录={proc.get('cwd')}")
                logger.debug(f"[_detect_external_comfyui]   命令行: {proc.get('cmdline')}")
            
            proc = processes[0]
            return {
                'pid': proc.get('pid'),
                'port': proc.get('port', 8188)
            }
            
        except Exception as e:
            logger.debug(f"检测外部进程失败: {e}")
            return None
    
    def is_alive(self) -> bool:
        """
        检查进程是否存活
        
        Returns:
            True 如果进程正在运行
        """
        if not self.process:
            return False
        
        return self.process.poll() is None
    
    def _extract_port_from_args(self, args: Optional[List[str]]):
        """
        从启动参数中提取端口号
        
        Args:
            args: 启动参数列表
        """
        if not args:
            self.port = 8188  # 默认端口
            return
        
        # 查找 --port 参数
        try:
            if '--port' in args:
                port_index = args.index('--port')
                if port_index + 1 < len(args):
                    self.port = int(args[port_index + 1])
                    self._push_log('INFO', f'检测到端口配置: {self.port}')
                    return
        except (ValueError, IndexError):
            pass
        
        # 默认端口
        self.port = 8188
    
    def _check_port_available(self, port: Optional[int] = None) -> bool:
        """
        检查端口是否可访问
        
        Args:
            port: 端口号，如果为 None 则使用 self.port
            
        Returns:
            True 如果端口可访问
        """
        if port is None:
            port = self.port
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)  # 1秒超时
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            
            return result == 0  # 0 表示连接成功
        except Exception:
            return False
    
    def _create_log_file(self):
        """创建日志文件"""
        try:
            from backend.src.utils.paths import get_log_dir
            logs_dir = get_log_dir("comfyui")
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_filename = f"comfyui_{timestamp}.log"
            self.log_file_path = logs_dir / log_filename
            
            self.log_file = open(self.log_file_path, 'a', encoding='utf-8')
            
            self.log_file.write("=" * 80 + "\n")
            self.log_file.write(f"ComfyUI 日志文件\n")
            self.log_file.write(f"创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            self.log_file.write("=" * 80 + "\n\n")
            self.log_file.flush()
            
        except Exception as e:
            logger.error(f"创建日志文件失败: {str(e)}")
            if self.log_file:
                try:
                    self.log_file.close()
                except (OSError, IOError):
                    pass
            self.log_file_path = None
            self.log_file = None
    
    def _write_to_log_file(self, log: dict):
        """
        写入日志到文件
        
        Args:
            log: 日志字典
        """
        if not self.log_file or not self.log_file_path:
            return
        
        try:
            with self._log_lock:
                # 格式化日志行
                log_line = f"[{log['timestamp']}] [{log['level']}] {log['message']}\n"
                self.log_file.write(log_line)
                self.log_file.flush()  # 立即刷新到磁盘
        except Exception as e:
            logger.warning(f"写入日志文件失败: {str(e)}")
    
    def _write_startup_failed_message(self, exit_code: int):
        """写入启动失败提示到日志文件"""
        logger.info(f"[_write_startup_failed_message] 被调用，exit_code={exit_code}, log_file={self.log_file}")
        if not self.log_file:
            logger.warning("[_write_startup_failed_message] 日志文件未打开，无法写入")
            return
        
        try:
            with self._log_lock:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                message = "❌ ComfyUI 启动失败，请检查上方的错误日志了解详情"
                log_line = f"[{timestamp}] [ERROR] {message}\n"
                self.log_file.write(log_line)
                self.log_file.flush()
                logger.info(f"[_write_startup_failed_message] 启动失败提示已写入日志文件")
        except Exception as e:
            logger.warning(f"[_write_startup_failed_message] 写入启动失败提示失败: {str(e)}")
    
    def _close_log_file(self):
        """关闭日志文件"""
        if self.log_file:
            file_to_close = self.log_file
            self.log_file = None
            
            try:
                with self._log_lock:
                    try:
                        file_to_close.write("\n" + "=" * 80 + "\n")
                        file_to_close.write(f"日志结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        file_to_close.write("=" * 80 + "\n")
                        file_to_close.flush()
                    except Exception as write_error:
                        logger.warning(f"写入日志文件尾失败: {str(write_error)}")
                    finally:
                        try:
                            file_to_close.close()
                        except Exception as close_error:
                            logger.warning(f"关闭日志文件句柄失败: {str(close_error)}")
            except Exception as e:
                logger.warning(f"关闭日志文件失败: {str(e)}")
    
    def get_log_file_path(self) -> Optional[str]:
        """
        获取当前日志文件路径
        
        Returns:
            日志文件路径字符串，如果没有则返回 None
        """
        if self.log_file_path:
            return str(self.log_file_path)
        return None
    
    def _check_has_task(self) -> bool:
        """
        检查 ComfyUI 是否有任务正在执行或等待
        
        通过调用 ComfyUI 的 /queue API 检查任务队列状态
        
        Returns:
            True 如果有任务正在执行或等待
        """
        try:
            import requests
            
            # 调用 ComfyUI API 获取队列状态
            response = requests.get(
                f"http://127.0.0.1:{self.port}/queue",
                timeout=2
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # 检查是否有正在运行或等待的任务
                queue_running = data.get("queue_running", [])
                queue_pending = data.get("queue_pending", [])
                
                return len(queue_running) > 0 or len(queue_pending) > 0
            
            return False
            
        except Exception as e:
            # API 调用失败，假设没有任务
            # 不打印错误，避免日志污染
            return False
    
    def _deploy_bridge_plugin(self, comfyui_path: Path, env_config: dict = None):
        """
        部署 Comfyui-Box Bridge 插件到 ComfyUI
        
        Args:
            comfyui_path: ComfyUI 目录路径
            env_config: 环境配置字典（包含 env_type, desktop_data_path 等）
        """
        try:
            from backend.src.bridge.plugins import get_bridge_plugin_version, get_plugin_content
            
            init_py_content, bridge_js_content = get_plugin_content()
            bridge_plugin_version = get_bridge_plugin_version()
            
            env_type = env_config.get("env_type", "portable") if env_config else "portable"
            
            if env_type == "desktop":
                desktop_data_path = env_config.get("desktop_data_path", "") if env_config else ""
                if desktop_data_path:
                    custom_nodes_path = Path(desktop_data_path) / "custom_nodes"
                    self._push_log('INFO', f'桌面版环境，custom_nodes 路径: {custom_nodes_path}')
                else:
                    custom_nodes_path = comfyui_path / "custom_nodes"
                    self._push_log('WARNING', '桌面版环境但未指定 desktop_data_path，使用默认路径')
            else:
                custom_nodes_path = comfyui_path / "custom_nodes"
            
            plugin_dir = custom_nodes_path / "Comfyui-Box_Bridge"
            plugin_dir_disabled = custom_nodes_path / "Comfyui-Box_Bridge.disabled"
            version_banner = f'========== [Comfyui-Box Bridge v{bridge_plugin_version}] =========='
            self._push_log('INFO', version_banner)
            logger.dev(version_banner)

            # 兼容旧品牌部署目录：旧目录存在且新目录不存在时原地迁移，并清理旧 js 文件名
            legacy_plugin_dir = custom_nodes_path / "ComfyNexus_Bridge"
            legacy_plugin_dir_disabled = custom_nodes_path / "ComfyNexus_Bridge.disabled"
            try:
                if legacy_plugin_dir_disabled.exists() and not plugin_dir_disabled.exists():
                    legacy_plugin_dir_disabled.rename(plugin_dir_disabled)
                elif legacy_plugin_dir.exists() and not plugin_dir.exists():
                    legacy_plugin_dir.rename(plugin_dir)
                legacy_js_file = plugin_dir / "js" / "comfynexus_bridge.js"
                if legacy_js_file.exists():
                    legacy_js_file.unlink()
            except Exception as e:
                logger.warning(f'迁移旧版 Bridge 插件目录失败: {e}')

            if plugin_dir_disabled.exists():
                self._push_log('WARNING', '⚠️ Comfyui-Box Bridge 插件已被禁用，跳过注入。\n   禁用后以下功能将不可用：实时预览进度、右键保存图片、资产库推送\n   如需启用，请在插件管理中启用该插件。')
                logger.dev('[Comfyui-Box Bridge] 插件已被禁用，跳过注入')
                return
            
            js_dir = plugin_dir / "js"
            
            plugin_dir.mkdir(parents=True, exist_ok=True)
            js_dir.mkdir(parents=True, exist_ok=True)
            
            # 检查是否需要更新插件
            init_py_file = plugin_dir / "__init__.py"
            bridge_js_file = js_dir / "comfyui-box_bridge.js"
            
            needs_update = False
            
            # 检查文件是否存在
            if not init_py_file.exists():
                needs_update = True
            else:
                existing_content = init_py_file.read_text(encoding='utf-8')
                if existing_content != init_py_content:
                    needs_update = True
            
            if not bridge_js_file.exists():
                needs_update = True
            else:
                existing_content = bridge_js_file.read_text(encoding='utf-8')
                if existing_content != bridge_js_content:
                    needs_update = True
            
            if needs_update:
                # 写入文件
                init_py_file.write_text(init_py_content, encoding='utf-8')
                bridge_js_file.write_text(bridge_js_content, encoding='utf-8')
                self._push_log('INFO', '✅ Comfyui-Box Bridge 插件已部署')
                logger.dev('[Comfyui-Box Bridge] 插件已更新')
            else:
                logger.dev('[Comfyui-Box Bridge] 插件已是最新版本')
                
        except Exception as e:
            logger.warning(f'部署 Comfyui-Box Bridge 插件失败: {e}')
            self._push_log('WARNING', f'部署 Comfyui-Box Bridge 插件失败: {e}')
