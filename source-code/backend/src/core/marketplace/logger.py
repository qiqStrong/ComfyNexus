"""
插件市场日志工具

为插件市场功能提供专用的日志记录器
"""

from pathlib import Path
from datetime import datetime
from typing import Optional
import logging

from backend.src.utils.logger import get_logger
from .constants import get_logs_dir, LOG_FILE_PREFIX


class MarketplaceLogger:
    """
    插件市场日志管理器
    
    提供统一的日志记录接口，支持：
    - 通用日志记录（使用全局日志记录器）
    - 插件安装日志记录（每个安装任务独立日志文件）
    """
    
    def __init__(self):
        """初始化日志管理器"""
        # 延迟初始化日志记录器（避免在模块导入时触发警告）
        self._logger = None
    
    @property
    def logger(self):
        """获取日志记录器（延迟初始化）"""
        if self._logger is None:
            # 使用 Comfyui-Box 日志记录器，避免创建新的未初始化的日志记录器
            self._logger = get_logger("Comfyui-Box")
        return self._logger
    
    def debug(self, message: str) -> None:
        """记录调试信息"""
        self.logger.debug(message)
    
    def dev(self, message: str) -> None:
        """记录开发调试信息"""
        self.logger.dev(message)
    
    def info(self, message: str) -> None:
        """记录一般信息"""
        self.logger.info(message)
    
    def warning(self, message: str) -> None:
        """记录警告信息"""
        self.logger.warning(message)
    
    def error(self, message: str) -> None:
        """记录错误信息"""
        self.logger.error(message)
    
    def exception(self, message: str) -> None:
        """记录异常信息（包含堆栈跟踪）"""
        self.logger.exception(message)
    
    @staticmethod
    def create_install_log_file(plugin_name: str) -> Path:
        """
        创建插件安装日志文件
        
        文件名格式：plugin_install_[插件名]_[时间戳].log
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            日志文件路径
        """
        # 清理插件名称（移除特殊字符）
        safe_plugin_name = "".join(
            c if c.isalnum() or c in ('-', '_') else '_' 
            for c in plugin_name
        )
        
        # 生成时间戳（精确到秒）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 生成日志文件名
        log_filename = f"{LOG_FILE_PREFIX}_{safe_plugin_name}_{timestamp}.log"
        
        # 获取日志目录
        logs_dir = get_logs_dir()
        
        # 返回完整路径
        return logs_dir / log_filename
    
    @staticmethod
    def write_to_install_log(
        log_file: Path,
        message: str,
        level: str = "INFO"
    ) -> None:
        """
        写入安装日志文件
        
        Args:
            log_file: 日志文件路径
            message: 日志消息
            level: 日志级别（INFO/WARNING/ERROR）
        """
        # 生成时间戳（ISO 8601 格式，精确到秒）
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 格式化日志行
        log_line = f"[{timestamp}] [{level}] {message}\n"
        
        # 追加写入文件
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_line)
        except Exception as e:
            # 如果写入失败，记录到全局日志
            logger = get_logger("Comfyui-Box")
            logger.error(f"无法写入安装日志文件 {log_file}: {e}")
    
    @staticmethod
    def write_command_output(
        log_file: Path,
        command: str,
        output: str,
        error: Optional[str] = None
    ) -> None:
        """
        写入命令输出到日志文件
        
        Args:
            log_file: 日志文件路径
            command: 执行的命令
            output: 标准输出
            error: 标准错误（可选）
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"[{timestamp}] 执行命令: {command}\n")
                f.write(f"{'='*80}\n\n")
                
                if output:
                    f.write("标准输出:\n")
                    f.write(output)
                    f.write("\n\n")
                
                if error:
                    f.write("标准错误:\n")
                    f.write(error)
                    f.write("\n\n")
        except Exception as e:
            logger = get_logger("Comfyui-Box")
            logger.error(f"无法写入命令输出到日志文件 {log_file}: {e}")
    
    @staticmethod
    def write_exception(log_file: Path, exception: Exception) -> None:
        """
        写入异常信息到日志文件（包含完整堆栈跟踪）
        
        Args:
            log_file: 日志文件路径
            exception: 异常对象
        """
        import traceback
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"[{timestamp}] 发生异常\n")
                f.write(f"{'='*80}\n\n")
                f.write(f"异常类型: {type(exception).__name__}\n")
                f.write(f"异常消息: {str(exception)}\n\n")
                f.write("堆栈跟踪:\n")
                f.write(traceback.format_exc())
                f.write("\n")
        except Exception as e:
            logger = get_logger("Comfyui-Box")
            logger.error(f"无法写入异常信息到日志文件 {log_file}: {e}")


# 创建全局日志管理器实例
marketplace_logger = MarketplaceLogger()
