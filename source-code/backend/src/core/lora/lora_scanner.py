"""
LoRA 模型扫描器

扫描指定目录下的 LoRA 模型文件，提取模型信息并保存为 JSON。
"""

import os
import json
import uuid
import requests
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from ...utils.logger import app_logger as logger
from ...utils.paths import get_project_root


class LoraModelInfo:
    """LoRA 模型信息"""
    
    def __init__(
        self,
        id: str,
        name: str,
        size_kb: float,
        path: str,
        folder: str = "",
        file_extension: str = "",
        created_at: str = "",
        modified_at: str = "",
        category: str = "uncategorized",
        preview_url: str = "",
        trigger_words: List[str] = None,
        tags: List[str] = None,
        default_weight: str = "",
        recommended_sampler: str = "",
        civitai_url: str = "",
        notes: str = "",
        file_hash: str = "",
        is_local: Optional[bool] = None,
        preview_blurred: bool = False,
        pull_status: int = 0,
        imported_preview_paths: List[str] = None
    ):
        self.id = id
        self.name = name
        self.size_kb = size_kb
        self.path = path
        self.folder = folder
        self.file_extension = file_extension
        self.created_at = created_at
        self.modified_at = modified_at
        self.category = category
        self.preview_url = preview_url
        self.trigger_words = trigger_words or []
        self.tags = tags or []
        self.default_weight = default_weight
        self.recommended_sampler = recommended_sampler
        self.civitai_url = civitai_url
        self.notes = notes
        self.file_hash = file_hash
        self.is_local = is_local
        self.preview_blurred = preview_blurred
        self.pull_status = pull_status
        self.imported_preview_paths = imported_preview_paths or []
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "size_kb": self.size_kb,
            "path": self.path,
            "folder": self.folder,
            "file_extension": self.file_extension,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "category": self.category,
            "preview_url": self.preview_url,
            "trigger_words": self.trigger_words,
            "tags": self.tags,
            "default_weight": self.default_weight,
            "recommended_sampler": self.recommended_sampler,
            "civitai_url": self.civitai_url,
            "notes": self.notes,
            "file_hash": self.file_hash,
            "is_local": self.is_local,
            "preview_blurred": self.preview_blurred,
            "pull_status": self.pull_status,
            "imported_preview_paths": self.imported_preview_paths
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'LoraModelInfo':
        """从字典创建"""
        is_local_value = data.get("is_local")
        logger.debug(f"[LoraModelInfo] from_dict: {data.get('name')}, is_local={is_local_value}, type={type(is_local_value)}")
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            size_kb=data.get("size_kb", 0),
            path=data.get("path", ""),
            folder=data.get("folder", ""),
            file_extension=data.get("file_extension", ""),
            created_at=data.get("created_at", ""),
            modified_at=data.get("modified_at", ""),
            category=data.get("category", "uncategorized"),
            preview_url=data.get("preview_url", ""),
            trigger_words=data.get("trigger_words", []),
            tags=data.get("tags", []),
            default_weight=data.get("default_weight", ""),
            recommended_sampler=data.get("recommended_sampler", ""),
            civitai_url=data.get("civitai_url", ""),
            notes=data.get("notes", ""),
            file_hash=data.get("file_hash", ""),
            is_local=is_local_value,
            preview_blurred=data.get("preview_blurred", False),
            pull_status=data.get("pull_status", 0),
            imported_preview_paths=data.get("imported_preview_paths", [])
        )


class LoraScanner:
    """LoRA 模型扫描器"""
    
    SUPPORTED_EXTENSIONS = {'.safetensors', '.pt', '.pth', '.bin', '.ckpt'}
    
    PREVIEW_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.mp4', '.webm', '.mov', '.mkv', '.avi'}
    
    _stop_flag = False
    _stopping = False
    _pulling = False
    _pull_progress = None
    
    def __init__(self, project_root: str = None):
        """
        初始化扫描器
        
        Args:
            project_root: 显式指定的旧版项目根目录（含 lora_data/ 子目录）；
                为空时使用机器级用户数据根下的 lora_data/（可迁移、可清理）
        """
        if project_root is None:
            from backend.src.utils.paths import get_lora_data_dir
            self.project_root = get_lora_data_dir()
            self.data_dir = self.project_root
        else:
            self.project_root = Path(project_root)
            self.data_dir = self.project_root / "lora_data"
        self.models_file = self.data_dir / "models.json"
        self.folders_file = self.data_dir / "folders.json"
        self.preview_dir = self.data_dir / "preview"
        
        self._ensure_data_dir()
    
    @classmethod
    def is_pulling(cls) -> bool:
        """检查是否正在拉取"""
        return cls._pulling
    
    @classmethod
    def is_stopping(cls) -> bool:
        """检查是否正在停止"""
        return cls._stopping
    
    @classmethod
    def get_pull_progress(cls) -> Optional[Dict]:
        """获取当前拉取进度"""
        return cls._pull_progress
    
    @classmethod
    def stop_pull(cls):
        """停止拉取操作"""
        cls._stop_flag = True
        cls._stopping = True
    
    @classmethod
    def reset_stop_flag(cls):
        """重置停止标志"""
        cls._stop_flag = False
        cls._stopping = False
    
    def _ensure_data_dir(self):
        """确保数据目录存在"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.preview_dir.mkdir(parents=True, exist_ok=True)
    
    def _find_local_preview_files(self, model_file_path: Path) -> List[Path]:
        """
        查找模型文件同目录下的同名预览图/视频文件
        
        Args:
            model_file_path: 模型文件路径
            
        Returns:
            预览图文件路径列表
        """
        preview_files = []
        model_dir = model_file_path.parent
        model_name_without_ext = model_file_path.stem
        
        try:
            for file in model_dir.iterdir():
                if file.is_file() and file.stem == model_name_without_ext:
                    ext = file.suffix.lower()
                    if ext in self.PREVIEW_EXTENSIONS:
                        preview_files.append(file)
            
            if preview_files:
                logger.info(f"[LoraScanner] 发现同名预览文件: {model_file_path.name} -> {len(preview_files)} 个")
        
        except Exception as e:
            logger.warning(f"[LoraScanner] 查找预览文件失败: {model_file_path}, {str(e)}")
        
        return preview_files
    
    def _import_local_previews(self, model_id: str, preview_files: List[Path], already_imported_paths: List[str] = None) -> List[str]:
        """
        导入本地预览图/视频文件到应用内
        
        Args:
            model_id: 模型 ID
            preview_files: 预览文件路径列表
            already_imported_paths: 已导入的源文件路径列表（用于避免重复导入）
            
        Returns:
            本次成功导入的源文件路径列表
        """
        imported_paths = []
        
        if not preview_files:
            return imported_paths
        
        if already_imported_paths is None:
            already_imported_paths = []
        
        try:
            preview_path = self.get_preview_dir(model_id)
            existing_files = self.get_preview_list(model_id)
            next_index = len(existing_files) + 1
            
            import shutil
            for preview_file in preview_files:
                source_path_str = str(preview_file)
                
                if source_path_str in already_imported_paths:
                    logger.debug(f"[LoraScanner] 预览文件已导入过，跳过: {preview_file.name}")
                    continue
                
                ext = preview_file.suffix.lower()
                target_file = preview_path / f"preview_{next_index}{ext}"
                
                shutil.copy2(preview_file, target_file)
                
                logger.info(f"[LoraScanner] 已导入本地预览: {preview_file.name} -> preview_{next_index}{ext}")
                imported_paths.append(source_path_str)
                next_index += 1
        
        except Exception as e:
            logger.error(f"[LoraScanner] 导入预览文件失败: model_id={model_id}, {str(e)}")
        
        return imported_paths
    
    def scan_directory(self, directory: str, category: str = "uncategorized") -> List[LoraModelInfo]:
        """
        扫描单个目录下的所有 LoRA 模型文件
        
        Args:
            directory: 要扫描的目录路径
            category: 模型分类
            
        Returns:
            模型信息列表
        """
        models = []
        dir_path = Path(directory)
        
        if not dir_path.exists() or not dir_path.is_dir():
            logger.warning(f"[LoraScanner] 目录不存在或不是有效目录: {directory}")
            return models
        
        try:
            for root, dirs, files in os.walk(dir_path):
                root_path = Path(root)
                
                for file in files:
                    file_path = root_path / file
                    ext = file_path.suffix.lower()
                    
                    if ext not in self.SUPPORTED_EXTENSIONS:
                        continue
                    
                    try:
                        model_info = self._create_model_info(
                            file_path=file_path,
                            base_dir=dir_path,
                            category=category
                        )
                        if model_info:
                            models.append(model_info)
                    except Exception as e:
                        logger.warning(f"[LoraScanner] 处理文件失败: {file_path}, {str(e)}")
        
        except Exception as e:
            logger.error(f"[LoraScanner] 扫描目录失败: {directory}, {str(e)}")
        
        return models
    
    def _create_model_info(self, file_path: Path, base_dir: Path, category: str) -> Optional[LoraModelInfo]:
        """
        创建模型信息对象
        
        Args:
            file_path: 模型文件路径
            base_dir: 基础目录（用于计算相对路径）
            category: 分类
            
        Returns:
            模型信息对象
        """
        try:
            stat_info = file_path.stat()
            size_bytes = stat_info.st_size
            size_kb = round(size_bytes / 1024, 2)
            
            rel_path = file_path.relative_to(base_dir)
            folder = str(rel_path.parent).replace(os.sep, "/") if rel_path.parent != Path('.') else ""
            
            created_at = datetime.fromtimestamp(stat_info.st_ctime).isoformat()
            modified_at = datetime.fromtimestamp(stat_info.st_mtime).isoformat()
            
            model_id = str(uuid.uuid4())
            
            preview_url = ""
            imported_preview_paths = []
            preview_files = self._find_local_preview_files(file_path)
            if preview_files:
                imported_paths = self._import_local_previews(model_id, preview_files)
                if imported_paths:
                    imported_preview_paths = imported_paths
                    preview_list = self.get_preview_list(model_id)
                    if preview_list:
                        first_preview = preview_list[0]
                        preview_url = f"lora://preview/{model_id}/{first_preview}"
            
            return LoraModelInfo(
                id=model_id,
                name=file_path.name,
                size_kb=size_kb,
                path=str(file_path),
                folder=folder,
                file_extension=file_path.suffix.lower(),
                created_at=created_at,
                modified_at=modified_at,
                category=category,
                preview_url=preview_url,
                is_local=True if imported_preview_paths else None,
                imported_preview_paths=imported_preview_paths
            )
        
        except Exception as e:
            logger.error(f"[LoraScanner] 创建模型信息失败: {file_path}, {str(e)}")
            return None
    
    def scan_all_paths(self, scan_paths: List[Dict]) -> List[LoraModelInfo]:
        """
        扫描所有配置的路径
        
        Args:
            scan_paths: 扫描路径配置列表，格式为 [{"id": "...", "path": "...", "category": "...", "enabled": true}, ...]
            
        Returns:
            所有模型信息列表
        """
        all_models = []
        
        for path_config in scan_paths:
            if not path_config.get("enabled", True):
                continue
            
            path = path_config.get("path", "")
            category = path_config.get("category", "uncategorized")
            
            if not path:
                continue
            
            models = self.scan_directory(path, category)
            all_models.extend(models)
        
        logger.info(f"[LoraScanner] 扫描完成，共发现 {len(all_models)} 个模型")
        return all_models
    
    def load_existing_models(self) -> Dict[str, LoraModelInfo]:
        """
        加载已存在的模型数据
        
        Returns:
            以路径为键的模型信息字典
        """
        if not self.models_file.exists():
            return {}
        
        try:
            with open(self.models_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            models = {}
            for item in data.get("models", []):
                model = LoraModelInfo.from_dict(item)
                models[model.path] = model
            
            logger.info(f"[LoraScanner] 加载已有模型数据: {len(models)} 个")
            return models
        
        except Exception as e:
            logger.error(f"[LoraScanner] 加载模型数据失败: {str(e)}")
            return {}
    
    def save_models(self, models: List[LoraModelInfo]) -> bool:
        """
        保存模型数据到 JSON 文件
        
        Args:
            models: 模型信息列表
            
        Returns:
            是否成功
        """
        try:
            data = {
                "version": "1.0.0",
                "updated_at": datetime.now().isoformat(),
                "count": len(models),
                "models": [m.to_dict() for m in models]
            }
            
            temp_file = self.models_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            temp_file.replace(self.models_file)
            logger.info(f"[LoraScanner] 模型数据已保存: {len(models)} 个模型")
            return True
        
        except Exception as e:
            logger.error(f"[LoraScanner] 保存模型数据失败: {str(e)}")
            return False
    
    def sync_models(self, scan_paths: List[Dict]) -> Dict:
        """
        同步模型数据（增量更新）
        
        增量更新逻辑：
        1. 加载已有模型数据
        2. 扫描配置的路径
        3. 对比已有数据，保留用户编辑的信息（tags, trigger_words, preview_url 等）
        4. 添加新模型
        5. 移除不存在的模型
        6. 更新模型大小和修改时间（如果文件有变化）
        
        Args:
            scan_paths: 扫描路径配置列表
            
        Returns:
            同步结果
        """
        existing_models = self.load_existing_models()
        scanned_models = self.scan_all_paths(scan_paths)
        
        result = {
            "added": 0,
            "updated": 0,
            "removed": 0,
            "unchanged": 0
        }
        
        final_models = []
        scanned_paths = set()
        
        for scanned in scanned_models:
            scanned_paths.add(scanned.path)
            
            if scanned.path in existing_models:
                existing = existing_models[scanned.path]
                
                if (existing.size_kb != scanned.size_kb or 
                    existing.modified_at != scanned.modified_at):
                    existing.size_kb = scanned.size_kb
                    existing.modified_at = scanned.modified_at
                    existing.file_extension = scanned.file_extension
                    result["updated"] += 1
                else:
                    result["unchanged"] += 1
                
                preview_files = self._find_local_preview_files(Path(scanned.path))
                if preview_files:
                    imported_paths = self._import_local_previews(existing.id, preview_files, existing.imported_preview_paths)
                    if imported_paths:
                        existing.imported_preview_paths.extend(imported_paths)
                        existing.is_local = True
                        if not existing.preview_url:
                            preview_list = self.get_preview_list(existing.id)
                            if preview_list:
                                existing.preview_url = f"lora://preview/{existing.id}/{preview_list[0]}"
                
                final_models.append(existing)
            else:
                final_models.append(scanned)
                result["added"] += 1
        
        for path, model in existing_models.items():
            if path not in scanned_paths:
                result["removed"] += 1
        
        self.save_models(final_models)
        
        self.sync_folder_structure(scan_paths)
        
        logger.info(f"[LoraScanner] 同步完成: 新增 {result['added']}, 更新 {result['updated']}, 移除 {result['removed']}, 未变 {result['unchanged']}")
        
        return {
            "success": True,
            "result": result,
            "total": len(final_models),
            "models": [m.to_dict() for m in final_models]
        }
    
    def get_models(self) -> Dict:
        """
        获取所有模型数据
        
        Returns:
            模型数据
        """
        existing_models = self.load_existing_models()
        models_list = list(existing_models.values())
        
        return {
            "success": True,
            "count": len(models_list),
            "models": [m.to_dict() for m in models_list]
        }
    
    def update_model(self, model_id: str, updates: Dict) -> Dict:
        """
        更新单个模型的信息
        
        Args:
            model_id: 模型 ID
            updates: 要更新的字段
            
        Returns:
            操作结果
        """
        existing_models = self.load_existing_models()
        
        for path, model in existing_models.items():
            if model.id == model_id:
                for key, value in updates.items():
                    if hasattr(model, key):
                        setattr(model, key, value)
                
                self.save_models(list(existing_models.values()))
                
                return {
                    "success": True,
                    "message": "模型信息已更新",
                    "model": model.to_dict()
                }
        
        return {
            "success": False,
            "message": f"模型 ID 不存在: {model_id}"
        }
    
    def batch_update_folder(self, model_ids: List[str], folder_id: str) -> Dict:
        """
        批量更新模型的 folder 字段，并实际移动文件
        
        Args:
            model_ids: 模型 ID 列表
            folder_id: 目标文件夹 ID（相对路径，空字符串表示移动到扫描根目录）
            
        Returns:
            操作结果
        """
        import shutil
        
        existing_models = self.load_existing_models()
        logger.info(f"[batch_update_folder] 开始批量移动 {len(model_ids)} 个模型到 folder: {folder_id}")
        logger.info(f"[batch_update_folder] 当前 models.json 中有 {len(existing_models)} 个模型")
        
        updated_count = 0
        moved_files = []
        errors = []
        keys_to_update = []
        
        for path, model in existing_models.items():
            if model.id in model_ids:
                try:
                    logger.info(f"[batch_update_folder] 处理模型：{model.name} (id={model.id}), 当前 folder={model.folder}, 当前 path={model.path}")
                    old_path = Path(model.path)
                    if not old_path.exists():
                        errors.append(f"文件不存在: {model.path}")
                        continue
                    
                    scan_paths = self._get_scan_paths_for_model(model)
                    if not scan_paths:
                        errors.append(f"无法找到模型的扫描路径: {model.path}")
                        continue
                    
                    scan_path_config = scan_paths[0]
                    scan_root = Path(scan_path_config.get("path", ""))
                    
                    if not scan_root.exists():
                        errors.append(f"扫描根目录不存在: {scan_root}")
                        continue
                    
                    if folder_id:
                        target_dir = scan_root / folder_id
                    else:
                        target_dir = scan_root
                    
                    target_dir.mkdir(parents=True, exist_ok=True)
                    
                    target_path = target_dir / old_path.name
                    
                    if target_path.exists() and target_path != old_path:
                        errors.append(f"目标位置已存在同名文件: {target_path}")
                        continue
                    
                    if old_path != target_path:
                        shutil.move(str(old_path), str(target_path))
                        moved_files.append({
                            "old_path": str(old_path),
                            "new_path": str(target_path),
                            "model_id": model.id
                        })
                        
                        model.path = str(target_path)
                        model.folder = folder_id
                        
                        new_key = str(target_path)
                        keys_to_update.append((path, new_key, model))
                        
                        logger.info(f"[batch_update_folder] 移动文件：{old_path} -> {target_path}")
                    else:
                        model.folder = folder_id
                        logger.info(f"[batch_update_folder] 文件未移动，仅更新 folder: {folder_id}")
                    
                    updated_count += 1
                    
                except Exception as e:
                    error_msg = f"移动文件失败 ({model.name}): {str(e)}"
                    errors.append(error_msg)
                    logger.error(f"[batch_update_folder] {error_msg}")
        
        for old_key, new_key, model in keys_to_update:
            if old_key != new_key:
                del existing_models[old_key]
                existing_models[new_key] = model
                logger.info(f"[batch_update_folder] 更新字典 key: {old_key} -> {new_key}")
        
        if updated_count > 0:
            self.save_models(list(existing_models.values()))
            logger.info(f"[batch_update_folder] 已移动 {updated_count} 个模型到分组: {folder_id}")
        
        return {
            "success": updated_count > 0,
            "message": f"已移动 {updated_count} 个模型" + (f"，{len(errors)} 个失败" if errors else ""),
            "updated_count": updated_count,
            "moved_files": moved_files,
            "errors": errors if errors else None
        }
    
    def _get_scan_paths_for_model(self, model: LoraModelInfo) -> List[Dict]:
        """
        获取模型所属的扫描路径配置
        
        Args:
            model: 模型信息
            
        Returns:
            扫描路径配置列表
        """
        try:
            from backend.src.core.config import LoraConfigManager
            config_manager = LoraConfigManager()
            config = config_manager.load_config()
            scan_paths = config.get("scan_paths", [])
            
            model_path = Path(model.path)
            matching_paths = []
            
            for sp in scan_paths:
                sp_path = Path(sp.get("path", ""))
                try:
                    model_path.relative_to(sp_path)
                    matching_paths.append(sp)
                except ValueError:
                    continue
            
            return matching_paths
        except Exception as e:
            logger.error(f"[_get_scan_paths_for_model] 获取扫描路径失败: {str(e)}")
            return []
    
    def delete_model(self, model_id: str) -> Dict:
        """
        删除模型（同时删除模型文件、预览图和元数据）
        
        Args:
            model_id: 模型 ID
            
        Returns:
            操作结果
        """
        import shutil
        
        existing_models = self.load_existing_models()
        
        model_to_delete = None
        path_to_remove = None
        for path, model in existing_models.items():
            if model.id == model_id:
                model_to_delete = model
                path_to_remove = path
                break
        
        if not model_to_delete:
            return {
                "success": False,
                "message": f"模型 ID 不存在: {model_id}"
            }
        
        deleted_files = []
        errors = []
        
        if model_to_delete.path and os.path.exists(model_to_delete.path):
            try:
                os.remove(model_to_delete.path)
                deleted_files.append(model_to_delete.path)
                logger.info(f"[delete_model] 已删除模型文件: {model_to_delete.path}")
            except Exception as e:
                error_msg = f"删除模型文件失败: {str(e)}"
                errors.append(error_msg)
                logger.error(f"[delete_model] {error_msg}")
        
        preview_dir = self.preview_dir / model_id
        if preview_dir.exists():
            try:
                shutil.rmtree(preview_dir)
                deleted_files.append(str(preview_dir))
                logger.info(f"[delete_model] 已删除预览图目录: {preview_dir}")
            except Exception as e:
                error_msg = f"删除预览图目录失败: {str(e)}"
                errors.append(error_msg)
                logger.error(f"[delete_model] {error_msg}")
        
        del existing_models[path_to_remove]
        self.save_models(list(existing_models.values()))
        
        if errors:
            return {
                "success": True,
                "message": f"模型已删除，但部分文件删除失败: {'; '.join(errors)}",
                "deleted_files": deleted_files,
                "errors": errors
            }
        
        return {
            "success": True,
            "message": "模型已成功删除",
            "deleted_files": deleted_files
        }
    
    def rename_model(self, model_id: str, new_name: str) -> Dict:
        """
        重命名模型（修改文件名 + 更新 models.json）
        
        Args:
            model_id: 模型 ID
            new_name: 新的模型名称（不含后缀）
            
        Returns:
            操作结果
        """
        if not new_name or not new_name.strip():
            return {
                "success": False,
                "message": "模型名称不能为空"
            }
        
        new_name = new_name.strip()
        
        existing_models = self.load_existing_models()
        
        model_to_rename = None
        old_path = None
        
        for path, model in existing_models.items():
            if model.id == model_id:
                model_to_rename = model
                old_path = path
                break
        
        if not model_to_rename:
            return {
                "success": False,
                "message": f"模型 ID 不存在: {model_id}"
            }
        
        old_file_path = Path(old_path)
        if not old_file_path.exists():
            return {
                "success": False,
                "message": f"模型文件不存在: {old_path}"
            }
        
        file_ext = model_to_rename.file_extension or old_file_path.suffix
        new_filename = f"{new_name}{file_ext}"
        new_file_path = old_file_path.parent / new_filename
        
        if new_file_path.exists() and new_file_path != old_file_path:
            return {
                "success": False,
                "message": f"文件名已存在: {new_filename}"
            }
        
        try:
            old_stat = old_file_path.stat()
            
            import shutil
            shutil.move(str(old_file_path), str(new_file_path))
            
            del existing_models[old_path]
            
            model_to_rename.name = new_filename
            model_to_rename.path = str(new_file_path)
            
            new_stat = new_file_path.stat()
            model_to_rename.modified_at = datetime.fromtimestamp(new_stat.st_mtime).isoformat()
            
            existing_models[str(new_file_path)] = model_to_rename
            self.save_models(list(existing_models.values()))
            
            logger.info(f"[LoraScanner] 模型重命名成功: {old_path} -> {new_file_path}")
            
            return {
                "success": True,
                "message": "模型重命名成功",
                "model": model_to_rename.to_dict(),
                "old_path": old_path,
                "new_path": str(new_file_path)
            }
        
        except Exception as e:
            logger.error(f"[LoraScanner] 重命名模型失败: {str(e)}")
            return {
                "success": False,
                "message": f"重命名失败: {str(e)}"
            }
    
    def get_folders(self) -> Dict:
        """
        获取所有文件夹列表（用于左侧目录树）
        
        Returns:
            文件夹列表
        """
        existing_models = self.load_existing_models()
        
        folders = set()
        for model in existing_models.values():
            if model.folder:
                parts = model.folder.split(os.sep)
                for i in range(len(parts)):
                    folder_path = os.sep.join(parts[:i+1])
                    folders.add(folder_path)
        
        folder_list = sorted(list(folders))
        
        return {
            "success": True,
            "folders": folder_list
        }
    
    def get_categories_with_count(self) -> Dict:
        """
        获取分类及其模型数量
        
        Returns:
            分类列表
        """
        existing_models = self.load_existing_models()
        
        category_counts = {}
        for model in existing_models.values():
            cat = model.category or "uncategorized"
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        return {
            "success": True,
            "categories": category_counts
        }
    
    def scan_folder_structure(self, scan_paths: List[Dict]) -> List[Dict]:
        """
        扫描文件夹结构
        
        Args:
            scan_paths: 扫描路径配置列表
            
        Returns:
            文件夹结构树（不包含最外层根目录）
        """
        folder_tree = []
        
        for path_config in scan_paths:
            if not path_config.get("enabled", True):
                continue
            
            path = path_config.get("path", "")
            category = path_config.get("category", "uncategorized")
            
            if not path:
                continue
            
            dir_path = Path(path)
            if not dir_path.exists() or not dir_path.is_dir():
                continue
            
            try:
                items = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                
                for item in items:
                    if item.is_dir():
                        if item.name.startswith('.') or item.name.startswith('__'):
                            continue
                        
                        child_node = self._build_folder_tree(item, dir_path, category)
                        if child_node:
                            folder_tree.append(child_node)
            except PermissionError:
                pass
        
        return folder_tree
    
    def _build_folder_tree(self, current_path: Path, base_path: Path, category: str) -> Optional[Dict]:
        """
        递归构建文件夹树
        
        Args:
            current_path: 当前路径
            base_path: 基础路径
            category: 分类
            
        Returns:
            文件夹树节点
        """
        try:
            relative_path = current_path.relative_to(base_path)
            node_id = str(relative_path).replace(os.sep, "/")
            if node_id == ".":
                node_id = category
        except ValueError:
            node_id = category
        
        node = {
            "id": node_id,
            "name": current_path.name,
            "path": str(current_path),
            "category": category,
            "children": []
        }
        
        try:
            items = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item in items:
                if item.is_dir():
                    if item.name.startswith('.') or item.name.startswith('__'):
                        continue
                    
                    child_node = self._build_folder_tree(item, base_path, category)
                    if child_node:
                        node["children"].append(child_node)
        except PermissionError:
            pass
        
        return node
    
    def save_folder_structure(self, folder_tree: List[Dict]) -> bool:
        """
        保存文件夹结构到 JSON 文件
        
        Args:
            folder_tree: 文件夹树
            
        Returns:
            是否成功
        """
        try:
            data = {
                "version": "1.0.0",
                "updated_at": datetime.now().isoformat(),
                "folders": folder_tree
            }
            
            temp_file = self.folders_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            temp_file.replace(self.folders_file)
            logger.info(f"[LoraScanner] 文件夹结构已保存")
            return True
        
        except Exception as e:
            logger.error(f"[LoraScanner] 保存文件夹结构失败: {str(e)}")
            return False
    
    def load_folder_structure(self) -> List[Dict]:
        """
        加载已保存的文件夹结构
        
        Returns:
            文件夹树
        """
        if not self.folders_file.exists():
            return []
        
        try:
            with open(self.folders_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            folders = data.get("folders", [])
            logger.info(f"[LoraScanner] 加载文件夹结构: {len(folders)} 个根节点")
            return folders
        
        except Exception as e:
            logger.error(f"[LoraScanner] 加载文件夹结构失败: {str(e)}")
            return []
    
    def sync_folder_structure(self, scan_paths: List[Dict]) -> Dict:
        """
        同步文件夹结构
        
        Args:
            scan_paths: 扫描路径配置列表
            
        Returns:
            同步结果
        """
        folder_tree = self.scan_folder_structure(scan_paths)
        self.save_folder_structure(folder_tree)
        
        return {
            "success": True,
            "folders": folder_tree
        }
    
    def get_folder_structure(self) -> Dict:
        """
        获取文件夹结构
        
        Returns:
            文件夹结构数据
        """
        folders = self.load_folder_structure()
        
        return {
            "success": True,
            "folders": folders
        }
    
    def create_folder(self, scan_path_id: str, folder_name: str, parent_folder_id: str = None) -> Dict:
        """
        在指定扫描路径下创建文件夹
        
        Args:
            scan_path_id: 扫描路径 ID（或路径本身）
            folder_name: 新文件夹名称
            parent_folder_id: 父文件夹 ID（可选，相对于扫描路径的路径）
            
        Returns:
            操作结果
        """
        from backend.src.core.config import LoraConfigManager
        
        try:
            config_manager = LoraConfigManager()
            config = config_manager.load_config()
            scan_paths = config.get("scan_paths", [])
            
            target_scan_path = None
            for sp in scan_paths:
                if sp.get("id") == scan_path_id or sp.get("path") == scan_path_id:
                    target_scan_path = sp
                    break
            
            if not target_scan_path:
                return {
                    "success": False,
                    "message": f"未找到扫描路径: {scan_path_id}"
                }
            
            if not target_scan_path.get("enabled", True):
                return {
                    "success": False,
                    "message": "该扫描路径已禁用"
                }
            
            base_path = Path(target_scan_path["path"])
            if not base_path.exists():
                return {
                    "success": False,
                    "message": "扫描路径不存在"
                }
            
            if parent_folder_id:
                folder_path = base_path / parent_folder_id / folder_name
            else:
                folder_path = base_path / folder_name
            
            if folder_path.exists():
                return {
                    "success": False,
                    "message": "文件夹已存在"
                }
            
            folder_path.mkdir(parents=True, exist_ok=False)
            logger.info(f"[LoraScanner] 创建文件夹成功: {folder_path}")
            
            return {
                "success": True,
                "message": "文件夹创建成功",
                "folder": {
                    "id": str(folder_path.relative_to(base_path)).replace(os.sep, "/"),
                    "name": folder_name,
                    "path": str(folder_path),
                    "category": target_scan_path.get("category", "uncategorized"),
                    "children": []
                }
            }
            
        except FileExistsError:
            return {
                "success": False,
                "message": "文件夹已存在"
            }
        except PermissionError:
            return {
                "success": False,
                "message": "没有权限创建文件夹"
            }
        except Exception as e:
            logger.error(f"[LoraScanner] 创建文件夹失败: {str(e)}")
            return {
                "success": False,
                "message": f"创建文件夹失败: {str(e)}"
            }
    
    def update_folder(self, folder_id: str, new_name: str = None, new_parent_id: str = None) -> Dict:
        """
        更新文件夹（重命名和/或移动）
        
        Args:
            folder_id: 文件夹 ID（相对路径）
            new_name: 新名称（可选）
            new_parent_id: 新父文件夹 ID（可选，相对路径，空字符串表示移动到根目录）
            
        Returns:
            操作结果
        """
        from backend.src.core.config import LoraConfigManager
        
        if new_name is None and new_parent_id is None:
            return {
                "success": False,
                "message": "没有要更新的内容"
            }
        
        try:
            config_manager = LoraConfigManager()
            config = config_manager.load_config()
            scan_paths = config.get("scan_paths", [])
            
            folder_path = None
            base_path = None
            category = "uncategorized"
            
            for sp in scan_paths:
                if not sp.get("enabled", True):
                    continue
                sp_base = Path(sp["path"])
                potential_path = sp_base / folder_id
                if potential_path.exists() and potential_path.is_dir():
                    folder_path = potential_path
                    base_path = sp_base
                    category = sp.get("category", "uncategorized")
                    break
            
            if not folder_path:
                return {
                    "success": False,
                    "message": "文件夹不存在"
                }
            
            if new_parent_id is not None:
                if new_parent_id == "" or new_parent_id == "root":
                    target_parent = base_path
                else:
                    target_parent = base_path / new_parent_id
                    if not target_parent.exists():
                        return {
                            "success": False,
                            "message": "目标父文件夹不存在"
                        }
            else:
                target_parent = folder_path.parent
            
            final_name = new_name if new_name else folder_path.name
            new_path = target_parent / final_name
            
            if new_path.exists() and new_path != folder_path:
                return {
                    "success": False,
                    "message": "目标位置已存在同名文件夹"
                }
            
            if new_path != folder_path:
                import shutil
                shutil.move(str(folder_path), str(new_path))
                logger.info(f"[LoraScanner] 移动文件夹成功: {folder_path} -> {new_path}")
            
            return {
                "success": True,
                "message": "文件夹更新成功",
                "folder": {
                    "id": str(new_path.relative_to(base_path)).replace(os.sep, "/"),
                    "name": final_name,
                    "path": str(new_path),
                    "category": category,
                    "children": []
                }
            }
            
        except PermissionError:
            return {
                "success": False,
                "message": "没有权限更新文件夹"
            }
        except Exception as e:
            logger.error(f"[LoraScanner] 更新文件夹失败: {str(e)}")
            return {
                "success": False,
                "message": f"更新文件夹失败: {str(e)}"
            }
    
    def delete_folder(self, folder_id: str) -> Dict:
        """
        删除文件夹（仅支持空文件夹）
        
        Args:
            folder_id: 文件夹 ID（相对路径）
            
        Returns:
            操作结果
        """
        from backend.src.core.config import LoraConfigManager
        
        try:
            config_manager = LoraConfigManager()
            config = config_manager.load_config()
            scan_paths = config.get("scan_paths", [])
            
            folder_path = None
            
            for sp in scan_paths:
                if not sp.get("enabled", True):
                    continue
                sp_base = Path(sp["path"])
                potential_path = sp_base / folder_id
                if potential_path.exists() and potential_path.is_dir():
                    folder_path = potential_path
                    break
            
            if not folder_path:
                return {
                    "success": False,
                    "message": "文件夹不存在"
                }
            
            if any(folder_path.iterdir()):
                return {
                    "success": False,
                    "message": "文件夹不为空，无法删除"
                }
            
            folder_path.rmdir()
            logger.info(f"[LoraScanner] 删除文件夹成功: {folder_path}")
            
            return {
                "success": True,
                "message": "文件夹删除成功"
            }
            
        except PermissionError:
            return {
                "success": False,
                "message": "没有权限删除文件夹"
            }
        except Exception as e:
            logger.error(f"[LoraScanner] 删除文件夹失败: {str(e)}")
            return {
                "success": False,
                "message": f"删除文件夹失败: {str(e)}"
            }
    
    def get_preview_dir(self, model_id: str) -> Path:
        """
        获取模型预览图目录
        
        Args:
            model_id: 模型 ID
            
        Returns:
            预览图目录路径
        """
        preview_path = self.preview_dir / model_id
        preview_path.mkdir(parents=True, exist_ok=True)
        return preview_path
    
    def save_preview(self, model_id: str, file_data: bytes, filename: str) -> Dict:
        """
        保存预览图/视频（支持多个，追加模式）
        
        Args:
            model_id: 模型 ID
            file_data: 文件数据
            filename: 原始文件名
            
        Returns:
            操作结果
        """
        allowed_image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        allowed_video_extensions = {'.mp4', '.webm', '.mov'}
        allowed_extensions = allowed_image_extensions | allowed_video_extensions
        
        ext = Path(filename).suffix.lower()
        if ext not in allowed_extensions:
            return {
                "success": False,
                "message": f"不支持的文件格式: {ext}"
            }
        
        try:
            preview_path = self.get_preview_dir(model_id)
            
            existing_files = self.get_preview_list(model_id)
            next_index = len(existing_files) + 1
            
            preview_file = preview_path / f"preview_{next_index}{ext}"
            with open(preview_file, 'wb') as f:
                f.write(file_data)
            
            logger.info(f"[LoraScanner] 预览图已保存: {preview_file}")
            
            return {
                "success": True,
                "message": "预览图保存成功",
                "filename": f"preview_{next_index}{ext}"
            }
        
        except Exception as e:
            logger.error(f"[LoraScanner] 保存预览图失败: {str(e)}")
            return {
                "success": False,
                "message": f"保存失败: {str(e)}"
            }
    
    def get_preview_list(self, model_id: str) -> List[str]:
        """
        获取模型预览图文件列表
        
        Args:
            model_id: 模型 ID
            
        Returns:
            预览图文件名列表（按序号排序）
        """
        allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.webm', '.mov']
        
        preview_path = self.preview_dir / model_id
        if not preview_path.exists():
            return []
        
        files = []
        for f in preview_path.iterdir():
            if f.is_file() and f.suffix.lower() in allowed_extensions:
                files.append(f.name)
        
        def sort_key(filename):
            try:
                num = int(filename.replace('preview_', '').split('.')[0])
                return num
            except (ValueError, TypeError, IndexError):
                return 999
        
        files.sort(key=sort_key)
        return files
    
    def get_preview_path(self, model_id: str, filename: str = None) -> Optional[Path]:
        """
        获取模型预览图文件路径
        
        Args:
            model_id: 模型 ID
            filename: 文件名（可选，不指定则返回第一个）
            
        Returns:
            预览图文件路径，不存在则返回 None
        """
        preview_path = self.preview_dir / model_id
        if not preview_path.exists():
            return None
        
        if filename:
            file_path = preview_path / filename
            if file_path.exists():
                return file_path
            return None
        
        files = self.get_preview_list(model_id)
        if files:
            return preview_path / files[0]
        return None
    
    def delete_preview(self, model_id: str, filename: str = None) -> Dict:
        """
        删除模型预览图
        
        Args:
            model_id: 模型 ID
            filename: 文件名（可选，不指定则删除全部）
            
        Returns:
            操作结果
        """
        try:
            preview_path = self.preview_dir / model_id
            if not preview_path.exists():
                return {
                    "success": False,
                    "message": "预览图目录不存在"
                }
            
            if filename:
                file_path = preview_path / filename
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"[LoraScanner] 预览图已删除: {file_path}")
                else:
                    return {
                        "success": False,
                        "message": "文件不存在"
                    }
            else:
                import shutil
                shutil.rmtree(preview_path)
                logger.info(f"[LoraScanner] 预览图目录已删除: {preview_path}")
            
            return {
                "success": True,
                "message": "预览图已删除"
            }
        
        except Exception as e:
            logger.error(f"[LoraScanner] 删除预览图失败: {str(e)}")
            return {
                "success": False,
                "message": f"删除失败: {str(e)}"
            }

    def batch_export_previews(self, model_ids: List[str]) -> Dict:
        """
        批量导出预览图到模型文件所在目录

        将应用内存储的预览图反向导出到 LoRA 模型文件同目录，
        用模型文件名（不带后缀）命名。目标文件已存在则跳过。

        Args:
            model_ids: 模型 ID 列表

        Returns:
            导出结果，包含 exported_count、skipped_count、failed_count
        """
        import shutil

        if not model_ids:
            return {
                "success": True,
                "exported_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "details": []
            }

        try:
            existing_models = self.load_existing_models()

            # 建立 id -> model 索引，避免 O(n*m) 查找
            model_index = {model.id: model for model in existing_models.values()}

            exported_count = 0
            skipped_count = 0
            failed_count = 0
            details = []

            for model_id in model_ids:
                # 查找模型
                target_model = model_index.get(model_id)

                if not target_model:
                    skipped_count += 1
                    details.append({"model_id": model_id, "status": "not_found"})
                    continue

                # 获取预览图列表
                preview_list = self.get_preview_list(model_id)
                if not preview_list:
                    skipped_count += 1
                    details.append({"model_id": model_id, "name": target_model.name, "status": "no_preview"})
                    continue

                # 构造源路径（第一张预览图）
                first_preview = preview_list[0]
                source_path = (self.preview_dir / model_id / first_preview).resolve()

                # 路径安全校验：确保源路径在预览图目录内
                if not str(source_path).startswith(str(self.preview_dir.resolve())):
                    failed_count += 1
                    details.append({"model_id": model_id, "name": target_model.name, "status": "invalid_path"})
                    logger.warning(f"[LoraScanner] 预览图路径不合法: {source_path}")
                    continue

                if not source_path.exists():
                    failed_count += 1
                    details.append({"model_id": model_id, "name": target_model.name, "status": "source_not_found"})
                    continue

                # 检查模型文件是否存在
                model_file_path = Path(target_model.path)
                if not model_file_path.exists():
                    failed_count += 1
                    details.append({"model_id": model_id, "name": target_model.name, "status": "model_file_not_found"})
                    continue

                # 构造目标路径：模型文件同目录，用模型文件名（不带后缀）+ 预览图扩展名
                model_stem = model_file_path.stem
                preview_ext = Path(first_preview).suffix
                target_path = model_file_path.parent / f"{model_stem}{preview_ext}"

                # 目标已存在则跳过
                if target_path.exists():
                    skipped_count += 1
                    details.append({"model_id": model_id, "name": target_model.name, "status": "target_exists", "target": str(target_path)})
                    continue

                # 复制文件
                try:
                    shutil.copy2(source_path, target_path)
                    exported_count += 1
                    details.append({"model_id": model_id, "name": target_model.name, "status": "exported", "target": str(target_path)})
                    logger.info(f"[LoraScanner] 预览图已导出: {source_path} -> {target_path}")
                except Exception as e:
                    failed_count += 1
                    details.append({"model_id": model_id, "name": target_model.name, "status": "failed", "error": str(e)})
                    logger.error(f"[LoraScanner] 导出预览图失败: {target_model.name}, {str(e)}")

            return {
                "success": True,
                "exported_count": exported_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
                "details": details
            }

        except Exception as e:
            logger.error(f"[LoraScanner] 批量导出预览图异常: {str(e)}")
            return {
                "success": False,
                "exported_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "details": [],
                "message": f"批量导出失败: {str(e)}"
            }

    def pull_from_civitai(self, full: bool = False, progress_callback=None) -> Dict:
        """
        从 Civitai 拉取模型信息
        
        Args:
            full: 是否全量拉取（True=重新计算所有hash，False=仅处理hash为空的模型）
            progress_callback: 进度回调函数，接收 (stage, current, total, message) 参数
        
        Returns:
            操作结果
        """
        if LoraScanner._pulling:
            return {
                "success": False,
                "message": "已有拉取任务在进行中"
            }
        
        LoraScanner._pulling = True
        LoraScanner._pull_progress = None
        self.reset_stop_flag()
        
        def internal_progress_callback(stage, current, total, message, model_data=None):
            LoraScanner._pull_progress = {
                "stage": stage,
                "current": current,
                "total": total,
                "message": message,
                "modelData": model_data
            }
            if progress_callback:
                progress_callback(stage, current, total, message, model_data)
        
        try:
            return self._do_pull_from_civitai(full, internal_progress_callback)
        finally:
            LoraScanner._pulling = False
            LoraScanner._pull_progress = None
    
    def _do_pull_from_civitai(self, full: bool = False, progress_callback=None) -> Dict:
        """实际执行拉取操作"""
        civitai_api_key = self._get_civitai_api_key()
        if not civitai_api_key:
            return {
                "success": False,
                "message": "未配置 Civitai API Key，请在设置中配置"
            }
        
        existing_models = self.load_existing_models()
        
        models_to_process = []
        skipped_count = 0
        for path, model in existing_models.items():
            if full:
                models_to_process.append(model)
            elif model.pull_status == 0:
                logger.debug(f"[LoraScanner] 待处理模型: {model.name}, pull_status={model.pull_status}")
                models_to_process.append(model)
            else:
                logger.debug(f"[LoraScanner] 跳过模型: {model.name}, pull_status={model.pull_status}")
                skipped_count += 1
        
        logger.info(f"[LoraScanner] {'全量' if full else '增量'}拉取: 跳过 {skipped_count} 个已处理的模型，待处理 {len(models_to_process)} 个")
        
        total_models = len(models_to_process)
        if not models_to_process:
            if progress_callback:
                progress_callback("done", 0, 0, "没有需要处理的模型")
            return {
                "success": True,
                "message": "没有需要处理的模型",
                "updated": 0
            }
        
        logger.info(f"[LoraScanner] 开始计算 {total_models} 个模型的 Hash（10并发）")
        
        if progress_callback:
            progress_callback("hash", 0, total_models, "准备计算 Hash...")
        
        hash_results = self._calculate_hashes_parallel(
            models_to_process, 
            max_workers=10, 
            progress_callback=lambda current, total, name: progress_callback("hash", current, total, f"计算 Hash: {name}") if progress_callback else None
        )
        
        if self._stop_flag:
            logger.info("[LoraScanner] 用户停止拉取操作")
            return {
                "success": True,
                "message": "已停止拉取",
                "updated": 0,
                "stopped": True
            }
        
        if progress_callback:
            progress_callback("fetch", 0, total_models, "开始获取模型信息...")
        
        updated_count = 0
        has_changes = False
        preview_download_limit = self._get_preview_download_limit()
        
        for idx, model in enumerate(models_to_process):
            if self._stop_flag:
                logger.info("[LoraScanner] 用户停止拉取操作")
                break
            
            if model.id in hash_results:
                model.file_hash = hash_results[model.id]
            
            if not model.file_hash:
                if progress_callback:
                    progress_callback("fetch", idx + 1, total_models, f"跳过（无Hash）: {model.name}")
                continue
            
            if progress_callback:
                progress_callback("fetch", idx + 1, total_models, f"获取信息: {model.name}")
            
            try:
                result = self._query_civitai_by_hash(model.file_hash)
                
                if result:
                    if result.get("error") == "Model not found":
                        model.is_local = True
                        model.pull_status = 2
                        has_changes = True
                        logger.info(f"[LoraScanner] 模型未在 Civitai 找到: {model.name}")
                    else:
                        model.is_local = False
                        model.pull_status = 1
                        has_changes = True
                        
                        trained_words = result.get("trainedWords") or result.get("triggerWords")
                        
                        if not trained_words:
                            trained_words = result.get("trainedWords", [])
                        
                        if not trained_words:
                            model_info = result.get("model", {})
                            if model_info:
                                trained_words = model_info.get("trainedWords") or model_info.get("triggerWords", [])
                        
                        if trained_words:
                            if isinstance(trained_words, str):
                                trained_words = [w.strip() for w in trained_words.split(',') if w.strip()]
                            elif isinstance(trained_words, list):
                                expanded_words = []
                                for word in trained_words:
                                    if isinstance(word, str) and ',' in word:
                                        expanded_words.extend([w.strip() for w in word.split(',') if w.strip()])
                                    elif isinstance(word, str) and word.strip():
                                        expanded_words.append(word.strip())
                                trained_words = expanded_words
                            model.trigger_words = trained_words
                            logger.info(f"[LoraScanner] 设置触发词: {model.name} -> {trained_words[:3]}{'...' if len(trained_words) > 3 else ''}")
                        
                        model_id = result.get("modelId")
                        if model_id:
                            model.civitai_url = f"https://civitai.com/models/{model_id}"
                        
                        base_model = result.get("baseModel") or result.get("baseModelType")
                        if not base_model:
                            model_info = result.get("model", {})
                            if model_info:
                                base_model = model_info.get("baseModel") or model_info.get("baseModelType")
                        
                        if base_model:
                            existing_tags = model.tags or []
                            other_tags = [t for t in existing_tags if t != base_model]
                            model.tags = [base_model] + other_tags
                            logger.info(f"[LoraScanner] 设置 baseModel 标签: {model.name} -> {base_model}")
                        
                        images = result.get("images", [])
                        if images:
                            if full:
                                self._clear_preview_images(model.id)
                            
                            existing_previews = self.get_preview_list(model.id)
                            existing_count = len(existing_previews)
                            
                            if existing_count < preview_download_limit or preview_download_limit == 0:
                                remaining_slots = preview_download_limit - existing_count if preview_download_limit > 0 else len(images)
                                images_to_download = images[:remaining_slots]
                                for img in images_to_download:
                                    preview_url = img.get("url")
                                    if preview_url:
                                        self._download_preview_image(model, preview_url)
                    
                    updated_count += 1
                    
                    if progress_callback:
                        progress_callback("fetch", idx + 1, total_models, f"获取信息: {model.name}", model.to_dict())
                else:
                    model.is_local = True
                    model.pull_status = 0
                    has_changes = True
                    if progress_callback:
                        progress_callback("fetch", idx + 1, total_models, f"获取信息: {model.name}", model.to_dict())
                
            except Exception as e:
                logger.warning(f"[LoraScanner] 查询 Civitai 失败: {model.name}, {str(e)}")
                model.pull_status = 0
                has_changes = True
        
        if has_changes:
            self.save_models(list(existing_models.values()))
        
        if progress_callback:
            progress_callback("done", total_models, total_models, "完成")
            import time
            time.sleep(0.1)
        
        return {
            "success": True,
            "message": f"已更新 {updated_count} 个模型信息",
            "updated": updated_count
        }
    
    def _calculate_hashes_parallel(self, models: List['LoraModelInfo'], max_workers: int = 10, progress_callback=None) -> Dict[str, str]:
        """
        并行计算模型文件的 Hash
        
        Args:
            models: 模型列表
            max_workers: 最大并发数
            progress_callback: 进度回调函数，接收 (current, total, model_name) 参数
            
        Returns:
            {model_id: hash} 字典
        """
        import hashlib
        import time
        import threading
        
        results = {}
        completed_count = [0]
        total_count = len(models)
        lock = threading.Lock()
        
        def calculate_single_hash(model: 'LoraModelInfo') -> tuple:
            if self._stop_flag:
                return (model.id, "", model.name)
            
            try:
                file_path = Path(model.path)
                if not file_path.exists():
                    logger.warning(f"[LoraScanner] 文件不存在: {model.path}")
                    return (model.id, "", model.name)
                
                chunk_size = 32 * 1024 * 1024
                sha256_hash = hashlib.sha256()
                
                file_size = file_path.stat().st_size
                start_time = time.time()
                
                with open(file_path, "rb") as f:
                    while True:
                        if self._stop_flag:
                            return (model.id, "", model.name)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        sha256_hash.update(data)
                
                file_hash = sha256_hash.hexdigest()
                elapsed = time.time() - start_time
                
                speed_mb = (file_size / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                logger.info(f"[LoraScanner] 计算Hash完成: {model.name} -> {file_hash[:16]}... ({elapsed:.1f}s, {speed_mb:.1f}MB/s)")
                
                return (model.id, file_hash, model.name)
                    
            except Exception as e:
                logger.warning(f"[LoraScanner] 计算Hash异常: {model.name}, {str(e)}")
                return (model.id, "", model.name)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(calculate_single_hash, model): model for model in models}
            
            for future in as_completed(futures):
                try:
                    model_id, file_hash, model_name = future.result()
                    results[model_id] = file_hash
                    
                    with lock:
                        completed_count[0] += 1
                        if progress_callback:
                            progress_callback(completed_count[0], total_count, model_name)
                            
                except Exception as e:
                    logger.error(f"[LoraScanner] 并发计算Hash异常: {str(e)}")
        
        return results
    
    def _get_civitai_api_key(self) -> Optional[str]:
        """获取 Civitai API Key"""
        from backend.src.core.config import LoraConfigManager
        config_manager = LoraConfigManager()
        config = config_manager.load_config()
        return config.get("civitai", {}).get("api_key", "")
    
    def _get_preview_download_limit(self) -> int:
        """获取预览图下载限制"""
        from backend.src.core.config import LoraConfigManager
        config_manager = LoraConfigManager()
        config = config_manager.load_config()
        return config.get("civitai", {}).get("preview_download_limit", 5)
    
    def _get_proxy_config(self) -> Optional[Dict]:
        """
        获取代理配置
        
        Returns:
            dict: 代理配置 {"http": "...", "https": "..."} 或 None
        """
        try:
            from backend.src.core.settings_manager import SettingsManager
            
            settings_manager = SettingsManager()
            result = settings_manager.get_settings()
            
            if not result.get("success"):
                return None
            
            settings = result.get("settings", {})
            proxy = settings.get("proxy", {})
            
            if not proxy.get("enabled"):
                return None
            
            host = proxy.get("host", "").strip()
            port = proxy.get("port", "").strip()
            
            if not host or not port:
                return None
            
            proxy_url = f"http://{host}:{port}"
            
            logger.info(f"[LoraScanner] 使用代理: {proxy_url}")
            
            return {
                "http": proxy_url,
                "https": proxy_url
            }
        except Exception as e:
            logger.warning(f"[LoraScanner] 获取代理配置失败: {str(e)}")
            return None
    
    def _clear_preview_images(self, model_id: str) -> None:
        """
        清除模型的所有预览图
        
        Args:
            model_id: 模型ID
        """
        import shutil
        
        preview_dir = self.get_preview_dir(model_id)
        if preview_dir.exists():
            try:
                shutil.rmtree(preview_dir)
                preview_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"[LoraScanner] 已清除模型预览图: {model_id}")
            except Exception as e:
                logger.warning(f"[LoraScanner] 清除预览图失败: {model_id}, {str(e)}")
    
    def _query_civitai_by_hash(self, file_hash: str, max_retries: int = 3) -> Optional[Dict]:
        """
        根据哈希值查询 Civitai 模型信息（带重试机制）
        
        Args:
            file_hash: 文件哈希值
            max_retries: 最大重试次数，默认3次
            
        Returns:
            成功返回模型信息字典
            未找到返回 {"error": "Model not found"}
            其他错误返回 None
        """
        import time
        
        civitai_api_key = self._get_civitai_api_key()
        if not civitai_api_key:
            return None
        
        url = f"https://civitai.com/api/v1/model-versions/by-hash/{file_hash}"
        headers = {
            "Authorization": f"Bearer {civitai_api_key}",
            "Content-Type": "application/json"
        }
        proxies = self._get_proxy_config()
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=30, proxies=proxies)
                
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict) and data.get("error"):
                        return {"error": data.get("error")}
                    return data
                
                if response.status_code == 404:
                    return {"error": "Model not found"}
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"[LoraScanner] Civitai API 请求失败 (状态码: {response.status_code})，{wait_time}秒后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"[LoraScanner] Civitai API 请求超时，{wait_time}秒后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"[LoraScanner] Civitai API 请求超时，已达到最大重试次数")
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"[LoraScanner] Civitai API 连接错误: {str(e)}，{wait_time}秒后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"[LoraScanner] Civitai API 连接错误，已达到最大重试次数: {str(e)}")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"[LoraScanner] Civitai API 请求失败: {str(e)}，{wait_time}秒后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"[LoraScanner] Civitai API 请求失败，已达到最大重试次数: {str(e)}")
        
        return None
    
    def _download_preview_image(self, model: 'LoraModelInfo', image_url: str, max_retries: int = 3) -> bool:
        """
        下载预览图/视频（带重试机制）
        
        Args:
            model: 模型信息
            image_url: 预览文件URL（图片或视频）
            max_retries: 最大重试次数，默认3次
            
        Returns:
            是否成功
        """
        import time
        
        proxies = self._get_proxy_config()
        
        for attempt in range(max_retries):
            try:
                response = requests.get(image_url, timeout=60, proxies=proxies)
                if response.status_code == 200:
                    preview_path = self.get_preview_dir(model.id)
                    
                    existing_files = self.get_preview_list(model.id)
                    next_index = len(existing_files) + 1
                    
                    ext = None
                    
                    if 'format=' in image_url:
                        format_param = image_url.split('format=')[-1].split('&')[0]
                        if format_param in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'webm', 'mov']:
                            ext = f'.{format_param}'
                    
                    if not ext:
                        url_lower = image_url.lower()
                        for suffix in ['.mp4', '.webm', '.mov', '.jpg', '.jpeg', '.png', '.gif', '.webp']:
                            if url_lower.endswith(suffix):
                                ext = suffix
                                break
                    
                    if not ext:
                        content_type = response.headers.get('Content-Type', '')
                        if 'video/mp4' in content_type:
                            ext = '.mp4'
                        elif 'video/webm' in content_type:
                            ext = '.webm'
                        elif 'video/quicktime' in content_type:
                            ext = '.mov'
                        elif 'image/jpeg' in content_type or 'image/jpg' in content_type:
                            ext = '.jpg'
                        elif 'image/png' in content_type:
                            ext = '.png'
                        elif 'image/gif' in content_type:
                            ext = '.gif'
                        elif 'image/webp' in content_type:
                            ext = '.webp'
                    
                    if not ext:
                        ext = '.png'
                    
                    preview_file = preview_path / f"preview_{next_index}{ext}"
                    
                    with open(preview_file, 'wb') as f:
                        f.write(response.content)
                    
                    model.preview_url = f"lora://preview/{model.id}/preview_{next_index}{ext}"
                    logger.info(f"[LoraScanner] 预览文件下载成功: {model.name} -> preview_{next_index}{ext}")
                    return True
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"[LoraScanner] 预览图下载失败 (状态码: {response.status_code})，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {model.name}")
                    time.sleep(wait_time)
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"[LoraScanner] 预览图下载超时，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {model.name}")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"[LoraScanner] 预览图下载超时，已达到最大重试次数: {model.name}")
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"[LoraScanner] 预览图下载连接错误: {str(e)}，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {model.name}")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"[LoraScanner] 预览图下载连接错误，已达到最大重试次数: {model.name}")
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"[LoraScanner] 预览图下载失败: {str(e)}，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {model.name}")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"[LoraScanner] 预览图下载失败，已达到最大重试次数: {model.name}, {str(e)}")
        
        return False
