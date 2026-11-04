"""
预设方案管理器模块

该模块负责管理 ComfyUI 的预设配置方案，包括：
- 定义预设方案
- 应用预设方案到环境
- 检测当前配置匹配的预设方案
- 用户预设管理（创建、删除、更新）
- 预设导入导出
"""

from typing import Dict, List, Optional
from pathlib import Path
from .types import PresetConfig, AccelerationSettings
from .preset_file_manager import PresetFileManager
from .preset_index_manager import PresetIndexManager
from ...utils.logger import app_logger as logger


class PresetManager:
    """预设方案管理器"""
    
    def __init__(self, environment_manager=None, config_dir: Path = None):
        """
        初始化预设方案管理器
        
        Args:
            environment_manager: EnvironmentManager 实例（用于获取和更新环境）
            config_dir: 配置目录路径，默认为 backend/config
        """
        self.environment_manager = environment_manager
        
        # 初始化文件和索引管理器
        if config_dir is None:
            # 使用绝对路径工具函数
            from backend.src.utils.paths import get_config_dir
            config_dir = get_config_dir()
        
        self.presets_dir = config_dir / "presets"
        self.index_file = config_dir / "preset_index.json"
        
        self._file_manager = PresetFileManager(self.presets_dir)
        self._index_manager = PresetIndexManager(self.index_file)
        
        # 定义内置预设
        self._presets = self._define_presets()
        
        # 加载用户预设
        self._load_custom_presets()
    
    def _load_custom_presets(self):
        """加载用户预设"""
        try:
            # 从索引获取用户预设列表
            preset_list = self._index_manager.get_preset_list()
            
            for preset_info in preset_list:
                preset_type = preset_info.get("type")
                
                if preset_type == "custom":
                    preset_id = preset_info.get("id")
                    
                    # 从文件加载预设
                    preset_data = self._file_manager.load_preset(preset_id)
                    
                    if preset_data:
                        # 创建 PresetConfig 对象
                        preset_config = PresetConfig.from_dict(preset_data)
                        
                        if preset_config:
                            self._presets[preset_id] = preset_config
        except Exception as e:
            logger.warning(f"[PresetManager] 加载用户预设失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _define_presets(self) -> Dict[str, PresetConfig]:
        """定义所有预设方案"""
        return {
            "author": PresetConfig(
                id="author",
                name="作者自用",
                description="作者自用配置，显卡3080ti 12g，内存128g",
                vram_requirement="12GB+",
                config={
                    "vramStrategy": "normal",
                    "cpuOnly": False,
                    "gpuOnly": False,
                    "reserveVram": 1.5,
                    "unetPrecision": "auto",
                    "vaePrecision": "auto",
                    "textEncPrecision": "auto",
                    "attentionMode": "flash",
                    "disableXformers": True,
                    "disableSmartMemory": False,
                    "forceChannelsLast": False,
                    "cacheLru": 0,
                    "deterministic": False,
                    "fastMode": True,
                    "previewMethod": "taesd",
                    "previewSize": 512,
                    "logLevel": "INFO",
                    "cudaMalloc": "disable",
                }
            ),
            "debug": PresetConfig(
                id="debug",
                name="Debug 模式",
                description="不使用任何参数启动，适用于调试和测试",
                vram_requirement="N/A",
                config={
                    "vramStrategy": "",
                    "cpuOnly": False,
                    "gpuOnly": False,
                    "reserveVram": 0,
                    "unetPrecision": "auto",
                    "vaePrecision": "auto",
                    "textEncPrecision": "auto",
                    "attentionMode": "auto",
                    "disableXformers": False,
                    "disableSmartMemory": False,
                    "forceChannelsLast": False,
                    "cacheLru": 0,
                    "deterministic": False,
                    "fastMode": False,
                    "previewMethod": "auto",
                    "previewSize": 512,
                    "logLevel": "INFO",
                    "cudaMalloc": "auto",
                    "enableManager": False,
                }
            ),
        }
    
    def get_presets(self) -> List[PresetConfig]:
        """
        获取所有预设方案
        
        Returns:
            预设方案列表
        """
        return list(self._presets.values())
    
    def get_preset(self, preset_id: str) -> Optional[PresetConfig]:
        """
        获取指定预设方案
        
        Args:
            preset_id: 预设方案 ID
            
        Returns:
            预设方案对象，如果不存在则返回 None
        """
        return self._presets.get(preset_id)
    
    def apply_preset(self, env_id: str, preset_id: str) -> dict:
        """
        应用预设方案到环境
        
        Args:
            env_id: 环境 ID
            preset_id: 预设方案 ID
            
        Returns:
            操作结果字典
        """
        if not self.environment_manager:
            return {
                "success": False,
                "error_code": "MANAGER_NOT_INITIALIZED",
                "error_message": "EnvironmentManager 未初始化"
            }
        
        # 获取预设方案
        preset = self.get_preset(preset_id)
        if not preset:
            return {
                "success": False,
                "error_code": "PRESET_NOT_FOUND",
                "error_message": f"预设方案 '{preset_id}' 不存在"
            }
        
        # 获取环境
        env_result = self.environment_manager.get_environment(env_id)
        if not env_result.get("success"):
            return {
                "success": False,
                "error_code": "ENVIRONMENT_NOT_FOUND",
                "error_message": f"环境 '{env_id}' 不存在或获取失败"
            }
        
        # 转换为 Environment 对象
        from .types import Environment
        environment = Environment.from_dict(env_result["environment"])
        
        # 应用预设配置
        if preset_id != "custom":
            # 更新 AccelerationSettings 配置
            for key, value in preset.config.items():
                if hasattr(environment.config.acceleration, key):
                    setattr(environment.config.acceleration, key, value)
        
        # 设置 current_preset_id
        environment.config.acceleration.current_preset_id = preset_id
        
        # 保存环境
        result = self.environment_manager.update_environment(env_id, environment.to_dict())
        
        return result
    
    def detect_preset(self, config: AccelerationSettings) -> str:
        """
        检测配置匹配的预设方案
        
        Args:
            config: 加速配置对象
            
        Returns:
            匹配的预设方案 ID，如果不匹配任何预设则返回 'custom'
        """
        # 如果已经设置了 current_preset_id，先检查是否仍然匹配
        if config.current_preset_id and config.current_preset_id != "custom":
            preset = self.get_preset(config.current_preset_id)
            if preset and self._matches_preset(config, preset):
                return config.current_preset_id
        
        # 遍历所有预设方案（除了 custom）
        for preset_id, preset in self._presets.items():
            if preset_id == "custom":
                continue
            
            if self._matches_preset(config, preset):
                return preset_id
        
        return "custom"
    
    def _matches_preset(self, config: AccelerationSettings, preset: PresetConfig) -> bool:
        """
        检查配置是否匹配预设方案
        
        Args:
            config: 加速配置对象
            preset: 预设方案对象
            
        Returns:
            是否匹配
        """
        for key, value in preset.config.items():
            if hasattr(config, key):
                if getattr(config, key) != value:
                    return False
        
        return True
    
    def _estimate_vram_requirement(self, config_dict: dict) -> str:
        """
        根据配置估算显存需求
        
        Args:
            config_dict: 配置字典
            
        Returns:
            显存需求字符串，如 "4GB+", "8GB+", "12GB+" 或 "N/A"
        """
        try:
            # 基础显存需求评分
            vram_score = 0
            
            # 1. 根据 vram_mode 调整
            vram_mode = config_dict.get("vram_mode", "normal")
            if vram_mode == "low":
                vram_score += 4
            elif vram_mode == "normal":
                vram_score += 8
            elif vram_mode == "high":
                vram_score += 12
            
            # 2. 根据精度调整
            unet_precision = config_dict.get("unet_precision", "auto")
            vae_precision = config_dict.get("vae_precision", "fp32")
            text_enc_precision = config_dict.get("text_enc_precision", "fp16")
            
            # 高精度需要更多显存
            if unet_precision == "fp32":
                vram_score += 4
            elif unet_precision == "fp16":
                vram_score += 0
            
            if vae_precision == "fp32":
                vram_score += 2
            
            if text_enc_precision == "fp32":
                vram_score += 2
            elif text_enc_precision == "fp16":
                vram_score += 0
            elif text_enc_precision == "fp8":
                vram_score -= 1
            
            # 3. 根据其他选项调整
            if config_dict.get("use_gpu_only", False):
                vram_score += 4  # 禁用CPU卸载，需要更多显存
            
            if config_dict.get("disable_smart_memory", False):
                vram_score += 2  # 禁用智能内存管理
            
            if config_dict.get("force_channels_last", False):
                vram_score += 1  # 优化内存格式，实际节省显存，但这里保守估计
            
            if config_dict.get("fast_mode", False):
                vram_score -= 2  # 快速模式牺牲质量但节省显存
            
            cache_lru = config_dict.get("cache_lru", 0)
            if cache_lru > 0:
                vram_score += cache_lru // 1000  # LRU缓存占用显存
            
            # 4. 根据注意力机制调整
            attention_type = config_dict.get("attention_type", "flash")
            if attention_type == "split":
                vram_score -= 2  # 分段处理节省显存
            elif attention_type == "sdpa":
                vram_score += 1  # SDPA需要较多显存
            
            # 5. 根据 CPU 使用情况调整
            if config_dict.get("use_cpu", False):
                return "CPU (低性能)"  # 使用CPU则不需要GPU显存
            
            # 6. 根据评分确定显存需求
            if vram_score <= 4:
                return "4GB+"
            elif vram_score <= 8:
                return "8GB+"
            elif vram_score <= 12:
                return "12GB+"
            elif vram_score <= 16:
                return "16GB+"
            else:
                return "24GB+"
        except Exception as e:
            logger.warning(f"[PresetManager] 估算显存需求失败: {e}")
            return "N/A"
    
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
        if not self.environment_manager:
            return {
                "success": False,
                "error_code": "MANAGER_NOT_INITIALIZED",
                "error_message": "EnvironmentManager 未初始化"
            }
        
        try:
            # 获取环境
            env_result = self.environment_manager.get_environment(env_id)
            if not env_result.get("success"):
                return {
                    "success": False,
                    "error_code": "ENVIRONMENT_NOT_FOUND",
                    "error_message": f"环境 '{env_id}' 不存在或获取失败"
                }
            
            # 转换为 Environment 对象
            from .types import Environment
            environment = Environment.from_dict(env_result["environment"])
            
            # 生成预设 ID
            if preset_id is None:
                preset_id = self._file_manager.generate_preset_id(name)
            
            # 检查 ID 是否已存在
            if preset_id in self._presets:
                return {
                    "success": False,
                    "error_code": "PRESET_ALREADY_EXISTS",
                    "error_message": f"预设 ID '{preset_id}' 已存在"
                }
            
            # 创建预设数据
            preset_data = {
                "id": preset_id,
                "name": name,
                "description": description,
                "vram_requirement": "N/A",
                "config": environment.config.acceleration.to_dict()
            }
            
            # 保存预设文件
            save_result = self._file_manager.save_preset(preset_data)
            if not save_result.get("success"):
                return save_result
            
            # 添加到索引
            preset_info = {
                "id": preset_id,
                "name": name,
                "description": description,
                "vram_requirement": "N/A",
                "type": "custom",
                "file": save_result["data"]["file_path"]
            }
            
            if not self._index_manager.add_preset_index(preset_info):
                # 回滚：删除文件
                self._file_manager.delete_preset(preset_id)
                return {
                    "success": False,
                    "error_code": "INDEX_UPDATE_FAILED",
                    "error_message": "添加预设索引失败"
                }
            
            # 加载到内存
            preset_config = PresetConfig.from_dict(preset_data)
            self._presets[preset_id] = preset_config
            
            return {
                "success": True,
                "data": {
                    "preset_id": preset_id
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": "UNKNOWN_ERROR",
                "error_message": f"创建用户预设失败: {str(e)}"
            }
    
    def delete_custom_preset(self, preset_id: str) -> dict:
        """
        删除用户预设
        
        Args:
            preset_id: 预设 ID
            
        Returns:
            操作结果字典
        """
        try:
            # 检查是否为内置预设
            if preset_id in ["author", "debug"]:
                return {
                    "success": False,
                    "error_code": "CANNOT_DELETE_BUILTIN",
                    "error_message": "不能删除内置预设"
                }
            
            # 检查预设是否存在
            if preset_id not in self._presets:
                return {
                    "success": False,
                    "error_code": "PRESET_NOT_FOUND",
                    "error_message": f"预设 '{preset_id}' 不存在"
                }
            
            # 从索引删除
            if not self._index_manager.delete_preset_index(preset_id):
                return {
                    "success": False,
                    "error_code": "INDEX_UPDATE_FAILED",
                    "error_message": "删除预设索引失败"
                }
            
            # 从文件删除
            if not self._file_manager.delete_preset(preset_id):
                return {
                    "success": False,
                    "error_code": "FILE_DELETE_FAILED",
                    "error_message": "删除预设文件失败"
                }
            
            # 从内存删除
            del self._presets[preset_id]
            
            return {
                "success": True,
                "message": f"预设 '{preset_id}' 已删除"
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": "UNKNOWN_ERROR",
                "error_message": f"删除预设失败: {str(e)}"
            }
    
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
            # 检查预设是否存在
            if preset_id not in self._presets:
                return {
                    "success": False,
                    "error_code": "PRESET_NOT_FOUND",
                    "error_message": f"预设 '{preset_id}' 不存在"
                }
            
            # 不能修改内置预设（custom 除外，它是用户预设）
            if preset_id in ["author", "debug"]:
                return {
                    "success": False,
                    "error_code": "CANNOT_MODIFY_BUILTIN",
                    "error_message": "不能修改内置预设"
                }
            
            # 获取当前预设
            preset = self._presets[preset_id]
            
            # 更新索引
            index_updates = {}
            if "name" in updates:
                index_updates["name"] = updates["name"]
            if "description" in updates:
                index_updates["description"] = updates["description"]
            if "vram_requirement" in updates:
                index_updates["vram_requirement"] = updates["vram_requirement"]
            
            if index_updates:
                if not self._index_manager.update_preset_index(preset_id, index_updates):
                    return {
                        "success": False,
                        "error_code": "INDEX_UPDATE_FAILED",
                        "error_message": "更新预设索引失败"
                    }
            
            # 如果更新了 name、description 或 vram_requirement，需要同时更新预设文件
            if "name" in updates or "description" in updates or "vram_requirement" in updates or "config" in updates:
                # 获取当前预设的 config（如果没有在 updates 中提供）
                current_config = updates.get("config", preset.config if hasattr(preset, 'config') else {})
                
                # 构建新的预设数据
                preset_data = {
                    "id": preset_id,
                    "name": updates.get("name", preset.name),
                    "description": updates.get("description", preset.description),
                    "vram_requirement": updates.get("vram_requirement", preset.vram_requirement),
                    "config": current_config
                }
                
                # 保存文件
                save_result = self._file_manager.save_preset(preset_data)
                if not save_result.get("success"):
                    return save_result
            
            # 更新内存中的预设 - 重新创建 PresetConfig 对象以确保更新生效
            new_preset_data = preset.to_dict()
            if "name" in updates:
                new_preset_data["name"] = updates["name"]
            if "description" in updates:
                new_preset_data["description"] = updates["description"]
            if "vram_requirement" in updates:
                new_preset_data["vram_requirement"] = updates["vram_requirement"]
            if "config" in updates:
                new_preset_data["config"] = updates["config"]
            
            # 重新创建预设对象
            self._presets[preset_id] = PresetConfig.from_dict(new_preset_data)
            
            
            return {
                "success": True,
                "message": f"预设 '{preset_id}' 已更新"
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": "UNKNOWN_ERROR",
                "error_message": f"更新预设失败: {str(e)}"
            }
    
    def export_current_config(self, env_id: str, name: str, description: str = "", vram_requirement_override: str = None) -> dict:
        """
        导出当前环境配置为预设数据
        
        注意：此方法只返回预设数据，不会保存到系统预设列表中。
        用户可以导出配置并保存到任意位置，而不必创建系统预设。
        
        Args:
            env_id: 环境 ID
            name: 预设名称
            description: 预设描述
            vram_requirement_override: 显存需求（优先使用，不提供则自动检测）
            
        Returns:
            操作结果字典，包含预设数据（仅用于导出，不保存到系统）
        """
        if not self.environment_manager:
            return {
                "success": False,
                "error_code": "MANAGER_NOT_INITIALIZED",
                "error_message": "EnvironmentManager 未初始化"
            }
        
        try:
            # 获取环境
            env_result = self.environment_manager.get_environment(env_id)
            if not env_result.get("success"):
                return {
                    "success": False,
                    "error_code": "ENVIRONMENT_NOT_FOUND",
                    "error_message": f"环境 '{env_id}' 不存在或获取失败"
                }
            
            # 转换为 Environment 对象
            from .types import Environment
            environment = Environment.from_dict(env_result["environment"])
            
            # 生成预设 ID（用于导出文件，不保存到系统）
            preset_id = self._file_manager.generate_preset_id(name)
            
            # 获取配置数据
            config_dict = environment.config.acceleration.to_dict()
            
            # 打印接收到的参数
            
            # 优先使用传入的 vram_requirement
            if vram_requirement_override is not None:
                vram_requirement = vram_requirement_override
            else:
                # 转换为 AccelerationSettings 对象用于检测预设
                acceleration_settings = AccelerationSettings.from_dict(config_dict)
                
                # 检测当前配置匹配的预设
                matched_preset_id = self.detect_preset(acceleration_settings)
                
                # 如果匹配到预设，使用预设的 vram_requirement
                if matched_preset_id and matched_preset_id != "custom":
                    matched_preset = self.get_preset(matched_preset_id)
                    if matched_preset:
                        vram_requirement = matched_preset.vram_requirement
                    else:
                        vram_requirement = self._estimate_vram_requirement(config_dict)
                else:
                    # 用户配置，进行估算
                    vram_requirement = self._estimate_vram_requirement(config_dict)
            
            # 参数说明映射（对照前端页面帮助信息修正）
            parameter_descriptions = {
                "compute_device": "计算设备：指定使用的GPU或CPU设备，格式为 nvidia:0, amd:0, intel:0 或 cpu。NVIDIA显卡推荐使用，AMD显卡需安装ROCm版PyTorch，Intel Arc显卡需安装oneAPI版PyTorch。",
                "vram_mode": "VRAM模式：显存使用策略。low(低显存模式，<8GB使用，速度慢)；normal(标准模式，8-12GB推荐)；high(高显存模式，≥16GB推荐)；no(无显存模式，仅CPU内存，极慢)",
                "use_cpu": "使用CPU：是否强制使用CPU进行计算。性能极低，仅用于无显卡或调试时使用。",
                "use_gpu_only": "仅GPU：(--gpu-only)是否禁用CPU卸载，模型必须全部加载到显存。适用于≥24GB显存，显存不足会导致程序崩溃。",
                "reserve_vram": "显存预留：(--reserve-vram)为系统显示或其他软件预留的显存大小，单位为GB，支持小数（如1.2GB）。建议设置1.0GB以上防止系统卡死。",
                "unet_precision": "UNet精度：主模型计算精度。auto(自动选择，通常是FP16)；fp8_e4m3fn(Flux模型必备，极低显存)；fp16(半精度，标准选择)；bf16(脑浮点，30/40系推荐)；fp32(单精度，高显存，仅调试用)",
                "vae_precision": "VAE精度：图像解码器精度。fp32(单精度，默认推荐，最稳定)；fp16(半精度，更快但易产生黑图/伪影)；cpu(CPU解码，省显存但速度慢，保命选项)",
                "text_enc_precision": "文本编码器精度：T5/CLIP等文本编码器的计算精度。fp8_e4m3fn(Flux的T5模型推荐，极低显存)；fp16(标准半精度，默认值)",
                "attention_type": "注意力机制：自注意力计算方式。flash(Flash Attention，速度最快)；sage3(SageAttention3，Flux/Sam2推荐)；sage(SageAttention2)；split(分段处理，省显存)；xformers(旧版优化)；sdpa(Pytorch标准)",
                "disable_xformers": "禁用Xformers：(--disable-xformers)是否禁用Xformers内存优化库。新版PyTorch已不需要Xformers，建议禁用。",
                "disable_smart_memory": "禁用智能内存：(--disable-smart-memory)是否禁用自动内存管理优化。禁用后需要手动管理显存，不推荐。",
                "force_channels_last": "强制通道最后：(--force-channels-last)是否使用channels_last内存格式（NHWC）。GPU优化可能提升性能但实际可能反而更慢。",
                "cache_lru": "LRU缓存：(--cache-lru)最近最少使用缓存大小，单位为MB。0表示禁用，可加速重复生成但占用显存。",
                "deterministic": "确定性：(--deterministic)是否使用确定性算法。可复现但稍慢，仅用于调试。",
                "fast_mode": "快速模式：(--fast)是否启用激进加速模式。质量稍低但更快。",
                "listen": "监听网络：(--listen)是否允许通过IP地址访问（用于局域网访问）。启用后不安全，建议配合防火墙使用。",
                "port": "端口：Web服务监听端口号，默认为8188。如果被占用可修改为其他端口。",
                "enable_cors": "启用CORS：(--enable-cors)是否允许跨域请求。用于开发调试，生产环境不推荐。",
                "tls_keyfile": "TLS密钥：HTTPS加密密钥文件路径。用于安全访问，通常不需要。",
                "tls_certfile": "TLS证书：HTTPS加密证书文件路径。用于安全访问，通常不需要。",
                "base_directory": "基础目录：ComfyUI基础安装目录。通常自动检测，无需手动设置。",
                "input_directory": "输入目录：输入图片文件的目录路径。通常自动检测，无需手动设置。",
                "output_directory": "输出目录：生成图片的输出目录路径。通常自动检测，无需手动设置。",
                "temp_directory": "临时目录：临时文件存储目录。通常自动检测，无需手动设置。",
                "user_directory": "用户目录：用户配置文件目录。通常自动检测，无需手动设置。",
                "extra_model_paths_config": "额外模型路径：额外的模型搜索路径配置文件（model_paths.yaml路径）。用于管理多个模型库。",
                "preview_method": "预览方法：生成过程预览方式。auto(自动选择)；taesd(TinyAE非常快预览)；latent(latent预览)；none(不预览，省显存)",
                "preview_size": "预览大小：预览图片的尺寸（像素），默认512。降低可省显存但预览不清晰。",
                "disable_all_custom_nodes": "安全模式：是否禁用所有自定义节点（安全启动）。用于节点冲突时排查问题。",
                "enable_manager": "启用管理器：是否启用ComfyUI-Manager（ComfyUI插件管理器）。需要先安装ComfyUI-Manager。",
                "verbose": "日志级别：日志输出详细程度。ERROR(仅错误)；WARNING(警告及以上)；INFO(信息及以上，默认)；DEBUG(调试信息)",
                "disable_metadata": "禁用元数据：是否禁用生成图片的元数据记录。可减小文件大小但会损失部分信息。",
                "current_preset_id": "当前预设ID：当前应用的预设方案标识（flux, flagship, legacy, debug, custom）。 readonly字段，不建议手动修改。"
            }
            
            # 启动参数映射
            launch_args_mapping = {
                "compute_device": "--device",
                "vram_mode": "--vram-mode",
                "use_cpu": "--use-cpu",
                "use_gpu_only": "--use-gpu-only",
                "reserve_vram": "--reserve-vram",
                "unet_precision": "--unet-precision",
                "vae_precision": "--vae-precision",
                "text_enc_precision": "--text-enc-precision",
                "attention_type": "--attention-type",
                "disable_xformers": "--disable-xformers",
                "disable_smart_memory": "--disable-smart-memory",
                "force_channels_last": "--force-channels-last",
                "cache_lru": "--cache-lru",
                "deterministic": "--deterministic",
                "fast_mode": "--fast",
                "listen": "--listen",
                "port": "--port",
                "enable_cors": "--enable-cors",
                "tls_keyfile": "--tls-keyfile",
                "tls_certfile": "--tls-certfile",
                "base_directory": "--base-directory",
                "input_directory": "--input-directory",
                "output_directory": "--output-directory",
                "temp_directory": "--temp-directory",
                "user_directory": "--user-directory",
                "extra_model_paths_config": "--extra-model-paths-config",
                "preview_method": "--preview-method",
                "preview_size": "--preview-size",
                "disable_all_custom_nodes": "--disable-all-custom-nodes",
                "enable_manager": "--enable-manager",
                "verbose": "--verbose",
                "disable_metadata": "--disable-metadata"
            }
            
            # 生成启动参数列表
            launch_args = []
            for key, value in config_dict.items():
                if value is not None and value != "":
                    arg_key = launch_args_mapping.get(key)
                    if arg_key:
                        if isinstance(value, bool):
                            if value:
                                launch_args.append(arg_key)
                        else:
                            launch_args.append(f"{arg_key} {value}")
            
            # 创建配置文档视图（整合配置值、描述和启动参数）
            config_with_doc = {}
            for key, value in config_dict.items():
                config_with_doc[key] = {
                    "value": value,
                    "description": parameter_descriptions.get(key, ""),
                    "launch_arg": launch_args_mapping.get(key, "")
                }
            
            # 创建预设数据（仅用于导出）
            preset_data = {
                "id": preset_id,
                "name": name,
                "description": description,
                "vram_requirement": vram_requirement,  # 使用估算的显存需求
                "config": config_with_doc,  # 整合视图（包含配置值、描述、启动参数）
                "metadata": {
                    "version": "1.0.0",
                    "exported_at": __import__('datetime').datetime.now().isoformat(),
                    "note": "此预设文件包含ComfyUI的详细配置参数，可以导入到Comfyui-Box中使用"
                }
            }
            
            
            # 仅返回数据，不保存到系统
            # 用户会在前端通过文件对话框选择保存路径
            return {
                "success": True,
                "data": {
                    "preset": preset_data
                }
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error_code": "UNKNOWN_ERROR",
                "error_message": f"导出预设失败: {str(e)}"
            }
    
    def import_preset_to_env(self, preset_data: dict, env_id: str) -> dict:
        """
        从预设数据导入配置到环境
        
        此方法会：
        1. 创建一个新的用户预设（如果预设ID不存在或与内置预设冲突）
        2. 将预设配置应用到目标环境
        
        Args:
            preset_data: 预设数据字典
            env_id: 目标环境 ID
            
        Returns:
            操作结果字典
        """
        if not self.environment_manager:
            return {
                "success": False,
                "error_code": "MANAGER_NOT_INITIALIZED",
                "error_message": "EnvironmentManager 未初始化"
            }
        
        try:
            logger.info(f"[import_preset_to_env] 开始导入预设到环境: {env_id}")
            logger.debug(f"[import_preset_to_env] preset_data keys: {preset_data.keys()}")
            
            # 验证预设数据
            is_valid, error_msg = self._file_manager.validate_preset(preset_data)
            if not is_valid:
                logger.error(f"[import_preset_to_env] 预设数据验证失败: {error_msg}")
                return {
                    "success": False,
                    "error_code": "INVALID_PRESET",
                    "error_message": error_msg
                }
            
            # 获取环境
            env_result = self.environment_manager.get_environment(env_id)
            if not env_result.get("success"):
                logger.error(f"[import_preset_to_env] 获取环境失败: {env_result}")
                return {
                    "success": False,
                    "error_code": "ENVIRONMENT_NOT_FOUND",
                    "error_message": f"环境 '{env_id}' 不存在或获取失败"
                }
            
            logger.debug(f"[import_preset_to_env] 环境获取成功")
            
            # 转换为 Environment 对象
            from .types import Environment
            environment = Environment.from_dict(env_result["environment"])
            logger.debug(f"[import_preset_to_env] Environment 对象创建成功")
            
            # 步骤1：创建用户预设（如果需要）
            preset_id = preset_data.get("id", "custom")
            preset_name = preset_data.get("name", "导入的预设")
            preset_description = preset_data.get("description", "")
            preset_vram_requirement = preset_data.get("vram_requirement", "N/A")
            
            # 检查预设ID是否与内置预设冲突，或者预设已存在
            builtin_presets = ["author", "debug"]
            if preset_id in builtin_presets or preset_id in self._presets:
                # 生成新的预设ID（基于名称 + 时间戳）
                import time
                timestamp = int(time.time() * 1000) % 100000  # 取最后5位毫秒数
                base_id = self._file_manager.generate_preset_id(preset_name)
                preset_id = f"{base_id}_{timestamp}"
                logger.info(f"[import_preset_to_env] 预设ID冲突或已存在，生成新ID: {preset_id}")
            
            # 创建新预设
            logger.info(f"[import_preset_to_env] 创建新预设: {preset_id}")
            
            # 提取配置（处理 config_with_doc 格式）
            config = preset_data.get("config", {})
            clean_config = {}
            for key, value in config.items():
                if isinstance(value, dict) and "value" in value:
                    clean_config[key] = value["value"]
                else:
                    clean_config[key] = value
            
            # 创建预设数据
            new_preset_data = {
                "id": preset_id,
                "name": preset_name,
                "description": preset_description,
                "vram_requirement": preset_vram_requirement,
                "config": clean_config
            }
            
            # 保存预设文件
            save_result = self._file_manager.save_preset(new_preset_data)
            if not save_result.get("success"):
                logger.error(f"[import_preset_to_env] 保存预设文件失败: {save_result}")
                return save_result
            
            # 添加到索引
            preset_info = {
                "id": preset_id,
                "name": preset_name,
                "description": preset_description,
                "vram_requirement": preset_vram_requirement,
                "type": "custom",
                "file": save_result["data"]["file_path"]
            }
            
            if not self._index_manager.add_preset_index(preset_info):
                # 回滚：删除文件
                self._file_manager.delete_preset(preset_id)
                logger.error(f"[import_preset_to_env] 添加预设索引失败")
                return {
                    "success": False,
                    "error_code": "INDEX_UPDATE_FAILED",
                    "error_message": "添加预设索引失败"
                }
            
            # 加载到内存
            from .types import PresetConfig
            preset_config = PresetConfig.from_dict(new_preset_data)
            self._presets[preset_id] = preset_config
            logger.info(f"[import_preset_to_env] 预设创建成功: {preset_id}")
            
            # 步骤2：应用预设配置到环境
            config = preset_data.get("config", {})
            logger.debug(f"[import_preset_to_env] 配置项数量: {len(config)}")
            
            for key, value in config.items():
                # 检查是否是 config_with_doc 格式（包含 value 字段）
                if isinstance(value, dict) and "value" in value:
                    actual_value = value["value"]
                else:
                    actual_value = value
                
                if hasattr(environment.config.acceleration, key):
                    setattr(environment.config.acceleration, key, actual_value)
                    logger.debug(f"[import_preset_to_env] 设置配置: {key} = {actual_value}")
            
            # 设置 current_preset_id 为新创建的预设ID
            environment.config.acceleration.current_preset_id = preset_id
            logger.debug(f"[import_preset_to_env] 设置 current_preset_id: {preset_id}")
            
            # 保存环境 - 只传递需要更新的配置部分，而不是整个环境对象
            # 这样可以避免 to_dict() 相关的问题
            logger.debug(f"[import_preset_to_env] 准备调用 acceleration.to_dict()")
            logger.debug(f"[import_preset_to_env] geek_mode 类型: {type(environment.config.acceleration.geek_mode)}")
            logger.debug(f"[import_preset_to_env] geek_mode 值: {environment.config.acceleration.geek_mode}")
            
            update_config = {
                "acceleration": environment.config.acceleration.to_dict()
            }
            logger.debug(f"[import_preset_to_env] acceleration.to_dict() 调用成功")
            
            result = self.environment_manager.update_environment(env_id, update_config)
            logger.info(f"[import_preset_to_env] 导入完成，结果: {result.get('success')}")
            
            # 返回结果中包含新创建的预设ID
            if result.get("success"):
                result["data"] = {
                    "preset_id": preset_id,
                    "preset_name": preset_name
                }
            
            return result
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"[import_preset_to_env] 导入失败: {e}")
            logger.error(f"[import_preset_to_env] 错误堆栈:\n{error_trace}")
            return {
                "success": False,
                "error_code": "UNKNOWN_ERROR",
                "error_message": f"导入预设失败: {str(e)}"
            }
    
    def get_preset_details(self, preset_id: str) -> dict:
        """
        获取预设详细信息
        
        Args:
            preset_id: 预设 ID
            
        Returns:
            操作结果字典，包含预设详情
        """
        try:
            # 获取预设
            preset = self._presets.get(preset_id)
            if not preset:
                return {
                    "success": False,
                    "error_code": "PRESET_NOT_FOUND",
                    "error_message": f"预设 '{preset_id}' 不存在"
                }
            
            # 获取索引信息
            preset_info = self._index_manager.get_preset_info(preset_id)
            if preset_info:
                return {
                    "success": True,
                    "data": {
                        **preset.to_dict(),
                        "type": preset_info.get("type", "custom"),
                        "file": preset_info.get("file"),
                        "created_at": preset_info.get("created_at"),
                        "updated_at": preset_info.get("updated_at")
                    }
                }
            else:
                return {
                    "success": True,
                    "data": preset.to_dict()
                }
        except Exception as e:
            return {
                "success": False,
                "error_code": "UNKNOWN_ERROR",
                "error_message": f"获取预设详情失败: {str(e)}"
            }
    
    def get_all_preset_list(self) -> dict:
        """
        获取所有预设列表（包含索引信息）
        
        Returns:
            操作结果字典，包含预设列表
        """
        try:
            preset_list = []
            index_presets = self._index_manager.get_preset_list()
            
            # 打印调试信息
            print(f"[PresetManager] get_all_preset_list 被调用")
            print(f"[PresetManager] 内存中的预设数量: {len(self._presets)}")
            print(f"[PresetManager] 预设 ID 列表: {list(self._presets.keys())}")
            
            # 创建预设索引映射
            index_map = {p["id"]: p for p in index_presets}
            
            # 遍历所有预设
            for preset_id, preset in self._presets.items():
                preset_dict = preset.to_dict()
                preset_info = index_map.get(preset_id, {})
                
                # 合并信息
                preset_dict["type"] = preset_info.get("type", "builtin")
                preset_dict["file"] = preset_info.get("file")
                preset_dict["created_at"] = preset_info.get("created_at")
                preset_dict["updated_at"] = preset_info.get("updated_at")
                
                preset_list.append(preset_dict)
            
            print(f"[PresetManager] 返回的预设列表数量: {len(preset_list)}")
            
            return {
                "success": True,
                "data": preset_list
            }
        except Exception as e:
            return {
                "success": False,
                "error_code": "UNKNOWN_ERROR",
                "error_message": f"获取预设列表失败: {str(e)}"
            }
