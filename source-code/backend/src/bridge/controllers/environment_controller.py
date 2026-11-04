"""
Environment management API controller for Comfyui-Box.

This module provides the API controller for environment management operations,
including adding, deleting, updating, and scanning ComfyUI environments.
"""

import os
from typing import Dict, Optional

from ...core.env.environment_manager import EnvironmentManager
from ...core.env.environment_config_manager import EnvironmentConfigManager
from ...core.env.error_codes import ErrorCode, get_error_message
from ...utils.path_serializer import serialize_response
from ...utils.logger import app_logger as logger
from ...utils.path_validator import (
    check_path_traversal,
    validate_file_path,
    PathValidationError
)


class EnvironmentController:
    """Environment management API controller."""
    
    def __init__(self):
        """Initialize the controller."""
        self.manager = EnvironmentManager()
        self.config_manager = EnvironmentConfigManager()
        self._window = None  # Will be set by Api class
    
    def set_window(self, window):
        """Set the pywebview window reference."""
        self._window = window
    
    @serialize_response
    def get_environments(self) -> dict:
        """
        Get all environments.
        
        Returns:
            Dictionary with environments list
        """
        try:
            result = self.manager.get_environments()
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def add_environment(self, path: str, name: Optional[str] = None, lang: str = "en") -> dict:
        """
        Add a new environment.
        
        Args:
            path: Path to ComfyUI installation
            name: Optional name for the environment
            lang: Language code ("en" or "zh")
            
        Returns:
            Dictionary with operation result
        """
        try:
            try:
                check_path_traversal(path)
            except PathValidationError as e:
                return {
                    "success": False,
                    "error_code": ErrorCode.INVALID_PATH,
                    "error_message": f"路径验证失败: {str(e)}"
                }
            
            result = self.manager.add_environment(path, name, lang)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def delete_environment(self, env_id: str) -> dict:
        """
        Delete an environment.
        
        Args:
            env_id: ID of the environment to delete
            
        Returns:
            Dictionary with operation result
        """
        try:
            result = self.manager.delete_environment(env_id)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def update_environment(self, env_id: str, config: dict) -> dict:
        """
        Update environment configuration.
        
        Args:
            env_id: ID of the environment to update
            config: New configuration data
            
        Returns:
            Dictionary with operation result
        """
        try:
            result = self.manager.update_environment(env_id, config)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def set_current_environment(self, env_id: str) -> dict:
        """
        Set the current active environment.
        
        Args:
            env_id: ID of the environment to set as current
            
        Returns:
            Dictionary with operation result
        """
        try:
            result = self.manager.set_current_environment(env_id)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def reorder_environments(self, env_ids: list) -> dict:
        """
        Reorder environments.
        
        Args:
            env_ids: List of environment IDs in the new order
            
        Returns:
            Dictionary with operation result
        """
        try:
            result = self.manager.reorder_environments(env_ids)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def scan_environment(self, path: str, lang: str = "en") -> dict:
        """
        Scan a ComfyUI environment.
        
        Args:
            path: Path to ComfyUI installation
            lang: Language code ("en" or "zh")
            
        Returns:
            Dictionary with scan results
        """
        try:
            result = self.manager.scan_environment(path, lang)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def get_dependencies(self, env_id: str) -> dict:
        """
        Get dependency information for an environment.
        
        Args:
            env_id: ID of the environment
            
        Returns:
            Dictionary with dependency information
        """
        try:
            result = self.manager.get_dependencies(env_id)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def select_directory(self) -> dict:
        """
        Open directory selection dialog using pywebview.
        
        Returns:
            Dictionary with selected directory path
        """
        logger.debug("[select_directory] 方法被调用")
        try:
            # Use pywebview's file dialog
            if not self._window:
                logger.warning("[select_directory] 窗口未初始化")
                return {
                    "success": False,
                    "error_code": ErrorCode.UNKNOWN_ERROR,
                    "error_message": "Window not initialized"
                }
            
            # Import webview to use constants
            import webview
            
            logger.debug("[select_directory] 准备打开文件对话框")
            result = self._window.create_file_dialog(
                dialog_type=webview.FileDialog.FOLDER,
                allow_multiple=False
            )
            
            logger.debug(f"[select_directory] 文件对话框返回: {result}")
            
            if result and len(result) > 0:
                response = {
                    "success": True,
                    "path": result[0]
                }
                logger.debug(f"[select_directory] 准备返回成功响应: {response}")
                return response
            else:
                response = {
                    "success": False,
                    "error_code": ErrorCode.PATH_NOT_FOUND,
                    "error_message": "No directory selected"
                }
                logger.debug(f"[select_directory] 准备返回取消响应: {response}")
                return response
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"[select_directory] 异常: {error_details}")
            response = {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
            logger.debug(f"[select_directory] 准备返回异常响应: {response}")
            return response
    
    @serialize_response
    def select_file(self, file_types: tuple = ()) -> dict:
        """
        Open file selection dialog using pywebview.
        
        Args:
            file_types: Tuple of file type filters, e.g. ('PEM files (*.pem)', 'All files (*.*)')
        
        Returns:
            Dictionary with selected file path
        """
        try:
            # Use pywebview's file dialog
            if not self._window:
                return {
                    "success": False,
                    "error_code": ErrorCode.UNKNOWN_ERROR,
                    "error_message": "Window not initialized"
                }
            
            # Import webview to use constants
            import webview
            
            default_directory = os.path.expanduser('~')
            result = self._window.create_file_dialog(
                dialog_type=webview.FileDialog.OPEN,
                directory=default_directory,
                allow_multiple=False,
                file_types=file_types
            )
            
            if result and len(result) > 0:
                return {
                    "success": True,
                    "path": result[0]
                }
            else:
                return {
                    "success": False,
                    "error_code": ErrorCode.PATH_NOT_FOUND,
                    "error_message": "No file selected"
                }
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"[select_file] Error: {error_details}")
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def export_config(self, env_id: str) -> dict:
        """
        Export environment configuration.
        
        Args:
            env_id: ID of the environment to export
            
        Returns:
            Dictionary with exported configuration
        """
        try:
            config_data = self.config_manager.export_config(env_id)
            return {
                "success": True,
                "config": config_data
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def import_config(self, config_data: str) -> dict:
        """
        Import environment configuration.
        
        Args:
            config_data: Configuration JSON string
            
        Returns:
            Dictionary with operation result
        """
        try:
            success = self.config_manager.import_config(config_data)
            return {
                "success": success
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def get_compute_devices(self) -> dict:
        """
        获取计算设备列表
        
        Returns:
            Dictionary with devices list:
            {
                "success": True,
                "devices": [
                    {
                        "index": 0,
                        "name": "NVIDIA GeForce RTX 4090",
                        "type": "nvidia",
                        "driver": "31.0.15.3623"
                    }
                ]
            }
        """
        try:
            from ...core.env.device_detector import DeviceDetector
            devices = DeviceDetector.get_compute_devices()
            return {
                "success": True,
                "devices": devices
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }

    @serialize_response
    def get_pytorch_backend(self, env_id: str) -> dict:
        """
        获取指定环境的 PyTorch 后端信息

        Args:
            env_id: 环境 ID

        Returns:
            Dictionary with PyTorch backend info
        """
        try:
            environment = self.manager.get_environment(env_id)
            if not environment:
                return {
                    "success": False,
                    "error_code": ErrorCode.UNKNOWN_ERROR,
                    "error_message": f"环境 '{env_id}' 不存在"
                }

            from ...core.env.types import Environment
            env_obj = Environment.from_dict(environment)

            python_path = env_obj.config.general.python_path
            if not python_path:
                return {
                    "success": False,
                    "error_code": ErrorCode.UNKNOWN_ERROR,
                    "error_message": "环境未配置 Python 路径"
                }

            from ...core.env.device_detector import DeviceDetector
            detector = DeviceDetector()
            backend_info = detector.detect_pytorch_backend(python_path)

            return {
                "success": True,
                "pytorchBackend": backend_info.to_dict()
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }

    @serialize_response
    def get_filtered_compute_devices(self, env_id: str) -> dict:
        """
        获取过滤后的计算设备列表（根据 PyTorch 后端兼容性）

        Args:
            env_id: 环境 ID

        Returns:
            Dictionary with filtered devices list
        """
        try:
            environment = self.manager.get_environment(env_id)
            if not environment:
                return {
                    "success": False,
                    "error_code": ErrorCode.UNKNOWN_ERROR,
                    "error_message": f"环境 '{env_id}' 不存在"
                }

            from ...core.env.types import Environment
            env_obj = Environment.from_dict(environment)

            python_path = env_obj.config.general.python_path

            from ...core.env.device_detector import DeviceDetector
            detector = DeviceDetector()

            devices = detector.detect_devices()

            if python_path:
                backend_info = detector.detect_pytorch_backend(python_path)
                devices = DeviceDetector.filter_devices_by_backend(devices, backend_info)
            else:
                backend_info = None

            return {
                "success": True,
                "devices": [device.to_dict() for device in devices],
                "pytorchBackend": backend_info.to_dict() if backend_info else None
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def save_file_dialog(self, default_name: str, file_filter: str = "") -> dict:
        """
        打开文件保存对话框
        
        Args:
            default_name: 默认文件名（带扩展名）
            file_filter: 文件过滤器（暂不支持，使用系统默认）
            
        Returns:
            Dictionary with save path
        """
        try:
            # Use pywebview's file dialog
            if not self._window:
                return {
                    "success": False,
                    "error_code": ErrorCode.UNKNOWN_ERROR,
                    "error_message": "Window not initialized"
                }
            
            # Import webview to use constants
            import webview
            
            default_directory = os.path.expanduser('~')
            result = self._window.create_file_dialog(
                dialog_type=webview.FileDialog.SAVE,
                directory=default_directory,
                save_filename=default_name
            )
            
            
            if result and len(result) > 0:
                return {
                    "success": True,
                    "path": result[0]
                }
            else:
                return {
                    "success": False,
                    "error_code": ErrorCode.DIALOG_CANCELLED,
                    "error_message": "用户取消了保存"
                }
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"[save_file_dialog] Error: {error_details}")
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def save_preset_to_file(self, file_path: str, preset_data: dict) -> dict:
        """
        保存预设数据到指定文件路径
        
        Args:
            file_path: 文件保存路径
            preset_data: 预设数据
            
        Returns:
            Dictionary with operation result
        """
        try:
            import json
            from pathlib import Path
            from ...utils.paths import get_project_root
            
            try:
                allowed_dirs = [str(get_project_root())]
                validate_file_path(
                    file_path,
                    allowed_extensions=['.json'],
                    allowed_base_dirs=allowed_dirs
                )
            except PathValidationError as e:
                return {
                    "success": False,
                    "error_code": ErrorCode.INVALID_PATH,
                    "error_message": f"路径验证失败: {str(e)}"
                }
            
            file_path_obj = Path(file_path)
            file_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(preset_data, f, indent=2, ensure_ascii=False)
            
            
            return {
                "success": True,
                "message": f"预设已保存到 {file_path}"
            }
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"[save_preset_to_file] Error: {error_details}")
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": f"保存文件失败: {str(e)}"
            }

    @serialize_response
    def batch_export_presets(self, presets_data: list, save_path: str) -> dict:
        """
        批量导出预设到文件
        
        Args:
            presets_data: 预设数据列表
            save_path: 保存路径
        
        Returns:
            操作结果
        """
        import json
        import zipfile
        import re
        
        try:
            from pathlib import Path
            from ...utils.paths import get_project_root
            
            def sanitize_filename(name: str) -> str:
                sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
                sanitized = sanitized.strip('. ')
                return sanitized or 'unnamed_preset'
            
            try:
                allowed_dirs = [str(get_project_root())]
                validate_file_path(
                    save_path,
                    allowed_extensions=['.json', '.zip'],
                    allowed_base_dirs=allowed_dirs
                )
            except PathValidationError as e:
                return {
                    "success": False,
                    "error_code": ErrorCode.INVALID_PATH,
                    "error_message": f"路径验证失败: {str(e)}"
                }
            
            file_path_obj = Path(save_path)
            file_path_obj.parent.mkdir(parents=True, exist_ok=True)
            
            if len(presets_data) == 1:
                preset = presets_data[0]
                with open(str(file_path_obj), 'w', encoding='utf-8') as f:
                    json.dump(preset, f, indent=2, ensure_ascii=False)
            else:
                with zipfile.ZipFile(str(file_path_obj), 'w', zipfile.ZIP_DEFLATED) as zf:
                    for preset in presets_data:
                        safe_name = sanitize_filename(preset.get('name', 'preset'))
                        json_filename = f"{safe_name}.json"
                        json_data = json.dumps(preset, indent=2, ensure_ascii=False)
                        zf.writestr(json_filename, json_data)
            
            return {
                "success": True,
                "message": f"预设已保存到 {save_path}"
            }
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"[batch_export_presets] Error: {error_details}")
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": f"导出预设失败: {str(e)}"
            }

    
    @serialize_response
    def apply_preset(self, env_id: str, preset_id: str) -> dict:
        """
        应用预设方案到环境
        
        Args:
            env_id: 环境 ID
            preset_id: 预设方案 ID
            
        Returns:
            操作结果字典
        """
        try:
            from ...core.env.preset_manager import PresetManager
            preset_manager = PresetManager(self.manager)
            result = preset_manager.apply_preset(env_id, preset_id)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def get_presets(self) -> dict:
        """
        获取所有预设方案
        
        Returns:
            预设方案列表
        """
        try:
            from ...core.env.preset_manager import PresetManager
            preset_manager = PresetManager(self.manager)
            presets = preset_manager.get_presets()
            return {
                "success": True,
                "presets": [preset.to_dict() for preset in presets]
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def add_model_path_config(self, env_id: str, config: dict) -> dict:
        """
        添加模型路径配置
        
        Args:
            env_id: 环境 ID
            config: 模型路径配置字典
            
        Returns:
            操作结果字典
        """
        try:
            from ...core.env.model_path_manager import ModelPathManager
            from ...core.env.types import ModelPathConfig
            
            model_path_manager = ModelPathManager(self.manager)
            model_path_config = ModelPathConfig.from_dict(config)
            result = model_path_manager.add_config(env_id, model_path_config)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def update_model_path_config(self, env_id: str, config_name: str, config: dict) -> dict:
        """
        更新模型路径配置
        
        Args:
            env_id: 环境 ID
            config_name: 配置名称
            config: 新的模型路径配置字典
            
        Returns:
            操作结果字典
        """
        try:
            from ...core.env.model_path_manager import ModelPathManager
            from ...core.env.types import ModelPathConfig
            
            model_path_manager = ModelPathManager(self.manager)
            model_path_config = ModelPathConfig.from_dict(config)
            result = model_path_manager.update_config(env_id, config_name, model_path_config)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def delete_model_path_config(self, env_id: str, config_name: str) -> dict:
        """
        删除模型路径配置
        
        Args:
            env_id: 环境 ID
            config_name: 配置名称
            
        Returns:
            操作结果字典
        """
        try:
            from ...core.env.model_path_manager import ModelPathManager
            
            model_path_manager = ModelPathManager(self.manager)
            result = model_path_manager.delete_config(env_id, config_name)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def generate_model_paths_yaml(self, env_id: str) -> dict:
        """
        生成模型路径 YAML 文件
        
        Args:
            env_id: 环境 ID
            
        Returns:
            操作结果字典
        """
        try:
            from ...core.env.model_path_manager import ModelPathManager
            
            model_path_manager = ModelPathManager(self.manager)
            result = model_path_manager.generate_yaml(env_id)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def get_launch_args(self, env_id: str) -> dict:
        """
        获取启动参数列表
        
        Args:
            env_id: 环境 ID
            
        Returns:
            启动参数列表
        """
        try:
            from ...core.env.launch_args_builder import LaunchArgsBuilder
            
            environment = self.manager.get_environment(env_id)
            if not environment:
                return {
                    "success": False,
                    "error_code": "ENVIRONMENT_NOT_FOUND",
                    "error_message": f"环境 '{env_id}' 不存在"
                }
            
            # 将字典转换为 Environment 对象
            from ...core.env.types import Environment
            env_obj = Environment.from_dict(environment)
            
            builder = LaunchArgsBuilder()
            args = builder.build_args(env_obj)
            
            return {
                "success": True,
                "args": args
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    # ========== 预设管理 API ==========
    
    @serialize_response
    def export_preset(self, env_id: str, name: str, description: str = "", vram_requirement: str = "N/A") -> dict:
        """
        导出当前环境配置为预设
        
        Args:
            env_id: 环境 ID
            name: 预设名称
            description: 预设描述
            vram_requirement: 显存需求（优先使用，不提供则自动检测）
            
        Returns:
            操作结果字典
        """
        try:
                
            from ...core.env.preset_manager import PresetManager
            preset_manager = PresetManager(self.manager)
            result = preset_manager.export_current_config(env_id, name, description, vram_requirement)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def import_preset(self, preset_data: dict, env_id: str) -> dict:
        """
        从预设数据导入配置到环境
        
        Args:
            preset_data: 预设数据字典
            env_id: 目标环境 ID
            
        Returns:
            操作结果字典
        """
        try:
            from ...core.env.preset_manager import PresetManager
            preset_manager = PresetManager(self.manager)
            result = preset_manager.import_preset_to_env(preset_data, env_id)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def create_custom_preset(self, env_id: str, preset_id: str = None, 
                            name: str = "用户预设", description: str = "") -> dict:
        """
        创建用户预设
        
        Args:
            env_id: 源环境 ID
            preset_id: 预设 ID，可选（不提供则自动生成）
            name: 预设名称
            description: 预设描述
            
        Returns:
            操作结果字典
        """
        try:
            from ...core.env.preset_manager import PresetManager
            preset_manager = PresetManager(self.manager)
            result = preset_manager.create_custom_preset(env_id, preset_id, name, description)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def delete_custom_preset(self, preset_id: str) -> dict:
        """
        删除用户预设
        
        Args:
            preset_id: 预设 ID
            
        Returns:
            操作结果字典
        """
        try:
            from ...core.env.preset_manager import PresetManager
            preset_manager = PresetManager(self.manager)
            result = preset_manager.delete_custom_preset(preset_id)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def update_custom_preset(self, preset_id: str, updates: dict) -> dict:
        """
        更新用户预设
        
        Args:
            preset_id: 预设 ID
            updates: 更新字段字典（name, description, config 等）
            
        Returns:
            操作结果字典
        """
        try:
            from ...core.env.preset_manager import PresetManager
            preset_manager = PresetManager(self.manager)
            result = preset_manager.update_custom_preset(preset_id, updates)
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def get_preset_details(self, preset_id: str) -> dict:
        """
        获取预设详细信息
        
        Args:
            preset_id: 预设 ID
            
        Returns:
            操作结果字典，包含预设详情
        """
        try:
            from ...core.env.preset_manager import PresetManager
            from ...core.env.config_transformer import ConfigTransformer
            
            preset_manager = PresetManager(self.manager)
            result = preset_manager.get_preset_details(preset_id)
            
            # 如果成功获取预设,转换config字段名
            if result.get("success") and result.get("data") and "config" in result["data"]:
                result["data"]["config"] = ConfigTransformer.backend_to_frontend(result["data"]["config"])
            
            return result
        except Exception as e:
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def get_all_presets(self) -> dict:
        """
        获取所有预设列表（包含索引信息）
        
        Returns:
            操作结果字典，包含预设列表
        """
        try:
            from ...core.env.preset_manager import PresetManager
            from ...core.env.config_transformer import ConfigTransformer
            
            preset_manager = PresetManager(self.manager)
            result = preset_manager.get_all_preset_list()
            
            # 如果成功获取预设列表,转换每个预设的config字段名
            if result.get("success") and result.get("data"):
                for preset in result["data"]:
                    if "config" in preset:
                        preset["config"] = ConfigTransformer.backend_to_frontend(preset["config"])
            
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error_code": ErrorCode.UNKNOWN_ERROR,
                "error_message": str(e)
            }
    
    @serialize_response
    def detect_model_paths_structure(self, path: str) -> dict:
        """
        检测目录结构，识别模型路径配置
        
        Args:
            path: 要检测的目录路径
            
        Returns:
            {
                "success": True,
                "is_comfyui_style": bool,  # 是否是 ComfyUI 风格目录
                "detected_paths": {        # 检测到的模型路径
                    "checkpoints": "models/checkpoints",
                    "loras": "models/loras",
                    ...
                }
            }
        """
        from pathlib import Path
        
        try:
            dir_path = Path(path)
            
            if not dir_path.exists() or not dir_path.is_dir():
                return {
                    "success": False,
                    "error_message": "路径不存在或不是有效目录"
                }
            
            models_dir = dir_path / "models"
            
            if not models_dir.exists() or not models_dir.is_dir():
                return {
                    "success": True,
                    "is_comfyui_style": False,
                    "detected_paths": {}
                }
            
            standard_model_dirs = [
                "checkpoints", "clip", "clip_vision", "configs",
                "controlnet", "unet", "embeddings", "loras",
                "upscale_models", "vae", "gligen", "hypernetworks",
                "style_models", "diffusers", "vae_approx", "t2i_adapter",
                "latent_upscale_models", "photomaker", "classifiers",
                "model_patches", "audio_encoders", "frame_interpolation",
            ]
            
            detected_paths = {}
            
            for model_dir in standard_model_dirs:
                model_path = models_dir / model_dir
                if model_path.exists() and model_path.is_dir():
                    detected_paths[model_dir] = f"models/{model_dir}"
            
            custom_nodes_dir = dir_path / "custom_nodes"
            if custom_nodes_dir.exists() and custom_nodes_dir.is_dir():
                detected_paths["custom_nodes"] = "custom_nodes"
            
            return {
                "success": True,
                "is_comfyui_style": len(detected_paths) > 0,
                "detected_paths": detected_paths
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error_message": str(e)
            }
