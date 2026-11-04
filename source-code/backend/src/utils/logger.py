"""
日志工具模块

提供统一的日志配置和输出功能

使用方式：
    1. 在 main.py 中初始化日志系统：
        from backend.src.utils.logger import setup_logger
        logger = setup_logger("Comfyui-Box", level="INFO")
    
    2. 在其他模块中使用日志：
        from backend.src.utils.logger import get_logger
        logger = get_logger()
        logger.info("这是一条日志")
    
    或者直接使用全局实例：
        from backend.src.utils.logger import app_logger
        app_logger.info("这是一条日志")

注意：
    - 不要在模块级别调用 setup_logger()
    - setup_logger() 应该只在 main.py 中调用一次
    - 其他模块使用 get_logger() 或 app_logger
"""

import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional


# 自定义日志级别
DEV_LEVEL = 25  # 在 INFO (20) 和 WARNING (30) 之间
logging.addLevelName(DEV_LEVEL, "DEV")


def dev(self, message, *args, **kwargs):
    """
    DEV 级别日志方法
    
    用于开发时临时调试，设置 level="DEV" 时：
    - 不显示 DEBUG 和 INFO
    - 只显示 DEV、WARNING、ERROR
    """
    if self.isEnabledFor(DEV_LEVEL):
        self._log(DEV_LEVEL, message, args, **kwargs)


# 为 Logger 类添加 dev 方法
logging.Logger.dev = dev


# 常量定义
MAX_LOG_FILE_SIZE = 100 * 1024 * 1024  # 100MB
LOG_FILE_BASE_NAME = "comfyui-box"


def get_log_filename(base_dir: Path, current_date: Optional[datetime] = None) -> Path:
    """
    获取当前日志文件名
    
    策略：
    1. 基础文件名：comfyui-box_YYYYMMDD_HHMMSS.log（每次启动生成新文件）
    2. 如果文件大小超过100MB，添加序号：comfyui-box_YYYYMMDD_HHMMSS_N.log
    
    Args:
        base_dir: 日志目录
        current_date: 当前日期时间（用于测试，默认使用当前系统时间）
        
    Returns:
        日志文件路径
    """
    if current_date is None:
        current_date = datetime.now()
    
    # 生成基础文件名（包含秒级时间戳）
    timestamp_str = current_date.strftime("%Y%m%d_%H%M%S")
    base_filename = f"{LOG_FILE_BASE_NAME}_{timestamp_str}.log"
    base_path = base_dir / base_filename
    
    # 如果基础文件不存在或大小未超限，直接返回
    if not base_path.exists() or base_path.stat().st_size < MAX_LOG_FILE_SIZE:
        return base_path
    
    # 文件大小超限，查找下一个可用的序号
    sequence = 1
    while True:
        filename = f"{LOG_FILE_BASE_NAME}_{timestamp_str}_{sequence}.log"
        file_path = base_dir / filename
        
        # 如果文件不存在或大小未超限，返回该路径
        if not file_path.exists() or file_path.stat().st_size < MAX_LOG_FILE_SIZE:
            return file_path
        
        sequence += 1
        
        # 安全检查：避免无限循环（理论上不应该发生）
        if sequence > 1000:
            raise RuntimeError(f"日志文件序号超过1000，请检查日志目录: {base_dir}")


def cleanup_old_logs(log_dir: Path, keep_days: int = 30, current_date: Optional[datetime] = None) -> int:
    """
    清理旧日志文件
    
    删除超过指定天数的日志文件。支持以下命名规范：
    - comfyui-box_YYYYMMDD.log（旧格式）
    - comfyui-box_YYYYMMDD_N.log（旧格式）
    - comfyui-box_YYYYMMDD_HHMMSS.log（新格式）
    - comfyui-box_YYYYMMDD_HHMMSS_N.log（新格式）
    
    Args:
        log_dir: 日志目录
        keep_days: 保留天数（默认30天）
        current_date: 当前日期（用于测试，默认使用当前系统日期）
        
    Returns:
        删除的文件数量
        
    Raises:
        无异常抛出，所有错误都会被捕获并记录
    """
    if current_date is None:
        current_date = datetime.now()
    
    # 确保日志目录存在
    if not log_dir.exists():
        return 0
    
    # 计算截止日期
    cutoff_date = current_date - timedelta(days=keep_days)
    
    deleted_count = 0
    
    # 匹配日志文件的正则表达式
    import re
    # 匹配旧格式: comfyui-box_YYYYMMDD.log 或 comfyui-box_YYYYMMDD_N.log
    # 匹配新格式: comfyui-box_YYYYMMDD_HHMMSS.log 或 comfyui-box_YYYYMMDD_HHMMSS_N.log
    log_pattern = re.compile(rf'^{LOG_FILE_BASE_NAME}_(\d{{8}})(?:_\d{{6}})?(?:_\d+)?\.log$')
    
    # 遍历日志目录中的所有文件
    try:
        for file_path in log_dir.iterdir():
            # 跳过目录
            if not file_path.is_file():
                continue
            
            # 检查文件名是否匹配日志文件格式
            match = log_pattern.match(file_path.name)
            if not match:
                continue
            
            # 提取日期字符串
            date_str = match.group(1)
            
            try:
                # 解析文件日期
                file_date = datetime.strptime(date_str, "%Y%m%d")
                
                # 检查是否需要删除
                if file_date < cutoff_date:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except PermissionError:
                        # 文件被占用或权限不足，记录警告但继续处理其他文件
                        logger.warning(f"警告: 无法删除日志文件（权限不足）: {file_path}")
                    except OSError as e:
                        # 其他文件系统错误
                        logger.warning(f"警告: 无法删除日志文件: {file_path}, 错误: {e}")
                        
            except ValueError:
                # 日期解析失败，跳过该文件
                print(f"警告: 无法解析日志文件日期: {file_path.name}", file=sys.stderr)
                continue
                
    except OSError as e:
        # 目录访问错误
        print(f"警告: 无法访问日志目录: {log_dir}, 错误: {e}", file=sys.stderr)
        return deleted_count
    
    return deleted_count


def cleanup_old_logs_by_count(log_dir: Path, keep_count: int = 10) -> int:
    """
    按文件数量清理旧日志文件，只保留最新的N个
    
    根据文件修改时间排序，保留最新的N个文件，删除其余文件。
    支持以下命名规范：
    - comfyui-box_YYYYMMDD.log（旧格式）
    - comfyui-box_YYYYMMDD_N.log（旧格式）
    - comfyui-box_YYYYMMDD_HHMMSS.log（新格式）
    - comfyui-box_YYYYMMDD_HHMMSS_N.log（新格式）
    
    Args:
        log_dir: 日志目录
        keep_count: 保留的文件数量（默认10个）
        
    Returns:
        删除的文件数量
        
    Raises:
        无异常抛出，所有错误都会被捕获并记录
    """
    # 确保日志目录存在
    if not log_dir.exists():
        return 0
    
    # 匹配日志文件的正则表达式
    import re
    log_pattern = re.compile(rf'^{LOG_FILE_BASE_NAME}_(\d{{8}})(?:_\d{{6}})?(?:_\d+)?\.log$')
    
    # 收集所有匹配的日志文件
    log_files = []
    try:
        for file_path in log_dir.iterdir():
            # 跳过目录
            if not file_path.is_file():
                continue
            
            # 检查文件名是否匹配日志文件格式
            if log_pattern.match(file_path.name):
                # 获取文件修改时间
                try:
                    mtime = file_path.stat().st_mtime
                    log_files.append((file_path, mtime))
                except OSError:
                    continue
    except OSError as e:
        print(f"警告: 无法访问日志目录: {log_dir}, 错误: {e}", file=sys.stderr)
        return 0
    
    # 如果文件数量不超过保留数量，无需清理
    if len(log_files) <= keep_count:
        return 0
    
    # 按修改时间排序（最新的在前）
    log_files.sort(key=lambda x: x[1], reverse=True)
    
    # 删除超出保留数量的旧文件
    deleted_count = 0
    files_to_delete = log_files[keep_count:]
    
    for file_path, _ in files_to_delete:
        try:
            file_path.unlink()
            deleted_count += 1
        except PermissionError:
            print(f"警告: 无法删除日志文件（权限不足）: {file_path}", file=sys.stderr)
        except OSError as e:
            print(f"警告: 无法删除日志文件: {file_path}, 错误: {e}", file=sys.stderr)
    
    return deleted_count


class DateRotatingFileHandler(logging.Handler):
    """
    按文件大小轮转的文件处理器
    
    特性：
    - 每次启动创建新文件（基于秒级时间戳）
    - 文件大小超过限制时创建新文件
    - 支持异步写入和缓冲区管理
    """
    
    def __init__(
        self,
        base_dir: Path,
        max_bytes: int = MAX_LOG_FILE_SIZE,
        encoding: str = 'utf-8'
    ):
        """
        初始化处理器
        
        Args:
            base_dir: 日志目录
            max_bytes: 单个文件最大字节数
            encoding: 文件编码
        """
        super().__init__()
        self.base_dir = Path(base_dir)
        self.max_bytes = max_bytes
        self.encoding = encoding
        self.stream = None
        self.current_file = None
        
        # 创建日志目录
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化文件流
        self._open_stream()
    
    def _open_stream(self):
        """打开日志文件流"""
        # 获取当前日志文件路径（每次调用都会生成新的时间戳）
        self.current_file = get_log_filename(self.base_dir)
        
        # 打开文件流（追加模式）
        self.stream = open(self.current_file, 'a', encoding=self.encoding, buffering=1)
    
    def _should_rollover(self) -> bool:
        """
        检查是否需要轮转
        
        Returns:
            True 如果需要轮转
        """
        # 只检查文件大小是否超限
        # 需要先刷新流以确保文件大小准确
        if self.stream and self.current_file.exists():
            self.stream.flush()
            if self.current_file.stat().st_size >= self.max_bytes:
                return True
        
        return False
    
    def _do_rollover(self):
        """执行轮转"""
        # 关闭当前流
        if self.stream:
            self.stream.flush()
            self.stream.close()
        
        # 打开新的流
        self._open_stream()
    
    def emit(self, record: logging.LogRecord):
        """
        发送日志记录
        
        Args:
            record: 日志记录对象
        """
        try:
            # 格式化消息
            msg = self.format(record)
            
            # 写入文件
            if self.stream:
                self.stream.write(msg + '\n')
                # 立即刷新（行缓冲）
                self.stream.flush()
            
            # 写入后检查是否需要轮转
            if self._should_rollover():
                self._do_rollover()
        except Exception:
            self.handleError(record)
    
    def close(self):
        """关闭处理器，确保缓冲区刷新"""
        try:
            if self.stream:
                self.stream.flush()
                self.stream.close()
                self.stream = None
        finally:
            super().close()


def setup_logger(
    name: str = "Comfyui-Box",
    log_dir: Path = None,
    console: bool = True,
    level: str = "INFO"
) -> logging.Logger:
    """
    设置日志记录器
    
    应该在应用启动时调用一次，配置日志处理器。
    其他模块应该使用 get_logger() 获取已配置的 logger。
    
    Args:
        name: 日志记录器名称
        log_dir: 日志文件目录（如果为None，使用项目根目录的logs文件夹）
        console: 是否同时输出到控制台
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        
    Returns:
        配置好的日志记录器
        
    Warning:
        不要在模块级别调用此函数！应该在 main.py 中调用一次。
    """
    # 验证日志级别
    valid_levels = {"DEBUG", "DEV", "INFO", "WARNING", "ERROR"}
    level = level.upper()
    if level not in valid_levels:
        print(f"警告: 无效的日志级别 '{level}'，使用默认级别 INFO", file=sys.stderr)
        level = "INFO"
    
    # 获取或创建日志记录器
    logger = logging.getLogger(name)
    
    # 将级别字符串转换为日志级别值
    level_value = {
        "DEBUG": logging.DEBUG,      # 10
        "DEV": DEV_LEVEL,            # 25
        "INFO": logging.INFO,        # 20
        "WARNING": logging.WARNING,  # 30
        "ERROR": logging.ERROR       # 40
    }.get(level, logging.INFO)
    
    logger.setLevel(level_value)
    
    # 清除已有的处理器（避免重复初始化）
    if logger.handlers:
        for handler in logger.handlers:
            handler.close()
        logger.handlers.clear()
    
    # 确定日志目录
    if log_dir is None:
        from backend.src.utils.paths import get_log_dir
        log_dir = get_log_dir()
    
    # 创建日志目录
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 执行日志清理（在启动时）
    try:
        # 先按数量清理，只保留最新的10个启动日志文件
        deleted_count = cleanup_old_logs_by_count(log_dir, keep_count=10)
        if deleted_count > 0:
            print(f"已清理 {deleted_count} 个历史启动日志文件", file=sys.stderr)
        
        # 再按天数清理（保留30天的日志）
        try:
            from core.settings_manager import SettingsManager
            settings_manager = SettingsManager()
            keep_days = settings_manager.get_log_keep_days()
        except Exception:
            # 如果无法读取设置，使用默认值
            keep_days = 30
        
        deleted_count = cleanup_old_logs(log_dir, keep_days=keep_days)
        if deleted_count > 0:
            print(f"已清理 {deleted_count} 个超过 {keep_days} 天的旧日志文件", file=sys.stderr)
    except Exception as e:
        print(f"警告: 日志清理失败: {e}", file=sys.stderr)
    
    # 创建日期轮转文件处理器
    try:
        # 尝试从设置管理器读取最大文件大小
        try:
            from core.settings_manager import SettingsManager
            settings_manager = SettingsManager()
            max_file_size = settings_manager.get_log_max_file_size()
        except Exception:
            # 如果无法读取设置，使用默认值
            max_file_size = MAX_LOG_FILE_SIZE
        
        file_handler = DateRotatingFileHandler(log_dir, max_bytes=max_file_size)
        file_handler.setLevel(level_value)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # 添加文件处理器
        logger.addHandler(file_handler)
    except Exception as e:
        # 如果文件处理器创建失败，降级到控制台输出
        print(f"警告: 无法创建日志文件处理器，降级到控制台输出: {e}", file=sys.stderr)
    
    # 如果需要，添加控制台处理器
    if console:
        # 创建一个自定义的 StreamHandler,处理编码问题
        class SafeStreamHandler(logging.StreamHandler):
            """安全的流处理器,自动处理编码问题"""
            
            # Emoji 映射表
            EMOJI_MAP = {
                '🚀': '[启动]', '💾': '[数据]', '📁': '[目录]', '🌐': '[文件]',
                '🔗': '[地址]', '🔌': '[端口]', '📡': '[API]', '🖥️': '[屏幕]',
                '📍': '[位置]', '📐': '[尺寸]', '✅': '[成功]', '⚠️': '[警告]',
                '❌': '[错误]', '🔍': '[调试]', '🎯': '[目标]', '📝': '[记录]',
            }
            
            def emit(self, record):
                """重写 emit 方法,处理编码问题"""
                try:
                    msg = self.format(record)
                    # 替换 emoji 为文本
                    for emoji, replacement in self.EMOJI_MAP.items():
                        msg = msg.replace(emoji, replacement)
                    
                    stream = self.stream
                    # 尝试直接写入
                    try:
                        stream.write(msg + self.terminator)
                    except UnicodeEncodeError:
                        # 如果编码失败,使用 errors='replace' 替换无法编码的字符
                        safe_msg = msg.encode(stream.encoding or 'utf-8', errors='replace').decode(stream.encoding or 'utf-8')
                        stream.write(safe_msg + self.terminator)
                    
                    self.flush()
                except Exception:
                    self.handleError(record)
        
        console_handler = SafeStreamHandler(sys.stdout)
        console_handler.setLevel(level_value)
        
        formatter = logging.Formatter(
            '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    logger.info(f"日志系统已初始化，级别: {level}")
    
    return logger


def get_logger(name: str = "Comfyui-Box") -> logging.Logger:
    """
    获取日志记录器
    
    获取已配置的日志记录器实例。如果 logger 尚未配置，
    会返回一个基础的 logger（只输出到 stderr）。
    
    Args:
        name: 日志记录器名称
        
    Returns:
        日志记录器实例
        
    Example:
        from backend.src.utils.logger import get_logger
        logger = get_logger()
        logger.info("这是一条日志")
    """
    logger = logging.getLogger(name)
    
    # 如果 logger 没有处理器，说明还未初始化
    # 添加一个基础的 stderr 处理器，避免日志丢失
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.warning(
            f"Logger '{name}' 尚未通过 setup_logger() 初始化，"
            "使用默认配置（仅输出到 stderr）"
        )
    
    return logger


# 全局日志记录器实例（延迟初始化）
_app_logger = None


def _get_app_logger() -> logging.Logger:
    """
    获取全局日志记录器实例（延迟初始化）
    
    Returns:
        日志记录器实例
    """
    global _app_logger
    if _app_logger is None:
        _app_logger = get_logger("Comfyui-Box")
    return _app_logger


# 创建一个属性访问器，使得 app_logger 看起来像一个全局变量
class _AppLoggerProxy:
    """日志记录器代理，实现延迟初始化"""
    
    def __getattr__(self, name):
        """转发所有属性访问到实际的日志记录器"""
        return getattr(_get_app_logger(), name)
    
    def __call__(self, *args, **kwargs):
        """支持直接调用"""
        return _get_app_logger()(*args, **kwargs)


app_logger = _AppLoggerProxy()


class _DeprecatedLoggerWrapper:
    """
    弃用的日志记录器包装器
    
    在使用 plugin_logger 时输出弃用警告
    """
    def __init__(self, logger):
        self._logger = logger
        self._warned = False
    
    def _warn_deprecated(self):
        """输出弃用警告（只警告一次）"""
        if not self._warned:
            import warnings
            warnings.warn(
                "plugin_logger 已弃用，请使用 app_logger 代替。"
                "plugin_logger 将在未来版本中移除。",
                DeprecationWarning,
                stacklevel=3
            )
            self._warned = True
    
    def __getattr__(self, name):
        """代理所有属性访问到实际的日志记录器"""
        self._warn_deprecated()
        return getattr(self._logger, name)
    
    def debug(self, msg, *args, **kwargs):
        """代理 debug 方法"""
        self._warn_deprecated()
        return self._logger.debug(msg, *args, **kwargs)
    
    def dev(self, msg, *args, **kwargs):
        """代理 dev 方法"""
        self._warn_deprecated()
        return self._logger.dev(msg, *args, **kwargs)
    
    def info(self, msg, *args, **kwargs):
        """代理 info 方法"""
        self._warn_deprecated()
        return self._logger.info(msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        """代理 warning 方法"""
        self._warn_deprecated()
        return self._logger.warning(msg, *args, **kwargs)
    
    def error(self, msg, *args, **kwargs):
        """代理 error 方法"""
        self._warn_deprecated()
        return self._logger.error(msg, *args, **kwargs)
    
    def critical(self, msg, *args, **kwargs):
        """代理 critical 方法"""
        self._warn_deprecated()
        return self._logger.critical(msg, *args, **kwargs)
    
    def exception(self, msg, *args, **kwargs):
        """代理 exception 方法"""
        self._warn_deprecated()
        return self._logger.exception(msg, *args, **kwargs)


# 向后兼容性：保留 plugin_logger 作为别名
# 使用时会输出弃用警告
plugin_logger = _DeprecatedLoggerWrapper(app_logger)
