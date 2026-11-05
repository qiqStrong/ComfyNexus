"""
救援模式控制器
提供环境快照备份与恢复功能，包括创建快照、列出快照、删除快照、
智能回滚（差异对比）和直接恢复等操作。
"""

from typing import Dict, List, Optional, TypedDict
from pathlib import Path
from datetime import datetime, timezone
import json
import logging
import os
import zipfile

from ...utils.logger import app_logger as logger
from ...utils.python_command import PythonCommandBuilder
from ...utils.file_utils import force_remove_directory


class DependencyItem(TypedDict):
    """依赖项数据结构"""
    name: str
    version: str


class SnapshotIndex(TypedDict):
    """快照索引数据结构，内嵌于 zip 包中的 snapshot_index.json"""
    environment_id: str          # 环境 ID
    name: str                    # 快照名称
    backup_option: str           # 备份选项: "deps_only" | "plugins_only" | "all"
    include_git: bool            # 是否保留插件 .git 目录
    note: str                    # 备注信息
    created_at: str              # ISO8601 时间戳
    dependencies: List[DependencyItem]  # 依赖列表
    plugins: List[str]           # 插件列表（custom_nodes 子目录名）


class RescueController:
    """
    救援模式控制器

    通过 pywebview JS Bridge 暴露 API，提供环境快照备份与恢复功能。
    遵循现有 Controller 模式，与 DependencyController 保持一致的初始化和调用方式。
    """

    def __init__(self, environment_manager=None):
        """
        初始化控制器

        Args:
            environment_manager: 环境管理器实例，用于获取当前激活环境信息
        """
        self.environment_manager = environment_manager
        self._window = None
        self._process_manager = None

    def set_window(self, window):
        """设置 pywebview 窗口引用"""
        self._window = window

    def set_process_manager(self, process_manager):
        """
        设置进程管理器实例

        由 Api 层在延迟初始化 ComfyUIProcess 后调用注入。

        Args:
            process_manager: ComfyUIProcess 实例，用于检查/管理 ComfyUI 进程
        """
        self._process_manager = process_manager

    def rescue_check_process(self) -> Dict:
        """
        检查 ComfyUI 进程是否正在运行

        通过注入的 process_manager 获取进程状态，
        返回简洁的运行状态字典供前端使用。

        Returns:
            {"running": bool} — 进程是否正在运行
        """
        try:
            if not self._process_manager:
                logger.warning("[RescueController] 进程管理器未设置，默认返回未运行")
                return {"running": False}

            # 通过 get_status() 获取完整状态，取 is_running 字段
            status = self._process_manager.get_status()
            running = status.get("is_running", False)

            logger.debug(f"[RescueController] ComfyUI 进程状态: running={running}")
            return {"running": running}

        except Exception as e:
            logger.error(
                f"[RescueController] 检查进程状态失败: {str(e)}",
                exc_info=True
            )
            return {"running": False}

    def rescue_create_snapshot(self, name: str, backup_option: str,
                               include_git: bool, note: str) -> Dict:
        """
        创建环境快照

        将当前激活环境的依赖目录和/或插件目录压缩为 zip 快照文件，
        同时生成 snapshot_index.json 元数据索引。

        Args:
            name: 快照名称（1-50 字符）
            backup_option: 备份选项 "deps_only" | "plugins_only" | "all"
            include_git: 是否保留插件 .git 目录
            note: 备注信息（0-500 字符）

        Returns:
            {success, snapshot_info, error_message}
        """
        try:
            # === 参数验证 ===
            if not name or len(name) < 1 or len(name) > 50:
                return {
                    "success": False,
                    "snapshot_info": None,
                    "error_message": "快照名称长度必须在 1 到 50 个字符之间"
                }

            if note is None:
                note = ""
            if len(note) > 500:
                return {
                    "success": False,
                    "snapshot_info": None,
                    "error_message": "备注长度不能超过 500 个字符"
                }

            if backup_option not in ("deps_only", "plugins_only", "all"):
                return {
                    "success": False,
                    "snapshot_info": None,
                    "error_message": f"无效的备份选项: {backup_option}"
                }

            # === 获取环境信息 ===
            env = self._get_current_env()
            if not env:
                return {
                    "success": False,
                    "snapshot_info": None,
                    "error_message": "无法获取当前环境信息，请确认已选中环境"
                }

            env_id = env.get("id", "unknown")
            pip_path = env.get("pipPath")
            comfyui_path = env.get("comfyuiPath")
            python_path = env.get("pythonPath")

            # === 确定依赖目录路径 ===
            deps_dir = None
            if python_path and backup_option in ("deps_only", "all"):
                python_p = Path(python_path)
                # python_path 可能是目录（如 python_embeded/）或 python.exe 完整路径
                if python_p.is_file():
                    python_dir = python_p.parent
                else:
                    python_dir = python_p

                # Windows 标准 venv：python.exe 在 Scripts/ 下，依赖在上级目录
                # ComfyUI 便携版：python_path 直接指向 python_embeded/ 目录本身
                if python_dir.name.lower() == "scripts":
                    deps_dir = python_dir.parent
                else:
                    deps_dir = python_dir  # python_embeded/ 本身

            # === 确定插件目录路径 ===
            plugins_dir = None
            if comfyui_path and backup_option in ("plugins_only", "all"):
                plugins_dir = Path(comfyui_path) / "custom_nodes"

            # === 执行 pip list 获取依赖列表 ===
            # 使用 PythonCommandBuilder 统一处理路径和命令构建
            dependencies = []
            if python_path:
                try:
                    builder = PythonCommandBuilder(python_path)
                    cmd = builder.pip_list()
                    result = builder.run(cmd, timeout=30, use_proxy=False)
                    
                    if result.returncode == 0 and result.stdout.strip():
                        dependencies = json.loads(result.stdout)
                    else:
                        logger.warning(
                            f"[RescueController] pip list 返回非零退出码: "
                            f"{result.returncode}, stderr: {result.stderr}"
                        )
                except Exception as e:
                    logger.warning(f"[RescueController] pip list 执行失败: {e}")
                    dependencies = []

            # === 扫描 custom_nodes 获取插件列表 ===
            plugins = []
            if comfyui_path:
                custom_nodes_path = Path(comfyui_path) / "custom_nodes"
                if custom_nodes_path.exists() and custom_nodes_path.is_dir():
                    plugins = [
                        d.name for d in custom_nodes_path.iterdir()
                        if d.is_dir() and not d.name.startswith(".")
                    ]

            # === 生成 snapshot_index.json 内容 ===
            now = datetime.now(timezone.utc)
            created_at = now.isoformat()

            snapshot_index: SnapshotIndex = {
                "environment_id": env_id,
                "name": name,
                "backup_option": backup_option,
                "include_git": include_git,
                "note": note,
                "created_at": created_at,
                "dependencies": dependencies,
                "plugins": plugins,
            }

            # === 生成文件名并确定输出路径 ===
            timestamp = now.strftime("%Y%m%dT%H%M%S")
            # 清理名称中不适合文件名的字符
            safe_name = "".join(
                c if c.isalnum() or c in ("-", "_") else "_"
                for c in name
            )
            zip_filename = f"{env_id}_{safe_name}_{timestamp}.zip"
            backup_dir = self._get_backup_dir()
            zip_path = backup_dir / zip_filename

            # === 使用 zipfile 压缩 ===
            logger.info(
                f"[RescueController] 开始创建快照: {zip_filename}, "
                f"备份选项: {backup_option}, 保留git: {include_git}"
            )

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 写入 snapshot_index.json
                index_json = json.dumps(snapshot_index, ensure_ascii=False, indent=2)
                zf.writestr("snapshot_index.json", index_json)

                # 压缩依赖目录
                if backup_option in ("deps_only", "all") and deps_dir and deps_dir.exists():
                    self._add_directory_to_zip(
                        zf, deps_dir, "deps", include_git=True
                    )

                # 压缩插件目录
                if backup_option in ("plugins_only", "all") and plugins_dir and plugins_dir.exists():
                    self._add_directory_to_zip(
                        zf, plugins_dir, "plugins", include_git=include_git
                    )

            # === 获取文件大小 ===
            file_size = zip_path.stat().st_size

            snapshot_info = {
                "filePath": str(zip_path),
                "name": name,
                "backupOption": backup_option,
                "note": note,
                "createdAt": created_at,
                "fileSize": file_size,
            }

            metadata = self._load_metadata()
            metadata.setdefault("snapshots", []).append({
                "filePath": str(zip_path),
                "name": name,
                "backupOption": backup_option,
                "note": note,
                "createdAt": created_at,
                "fileSize": file_size,
            })
            self._save_metadata(metadata)

            logger.info(
                f"[RescueController] 快照创建成功: {zip_filename}, "
                f"大小: {file_size} 字节"
            )

            return {
                "success": True,
                "snapshot_info": snapshot_info,
                "error_message": None,
            }

        except PermissionError as e:
            logger.error(f"[RescueController] 权限错误: {str(e)}", exc_info=True)
            # 清理可能的不完整文件
            if 'zip_path' in locals() and zip_path.exists():
                try:
                    zip_path.unlink()
                except OSError:
                    pass
            return {
                "success": False,
                "snapshot_info": None,
                "error_message": f"权限不足，无法写入备份目录: {str(e)}"
            }

        except OSError as e:
            logger.error(f"[RescueController] 系统错误: {str(e)}", exc_info=True)
            # 清理可能的不完整文件
            if 'zip_path' in locals() and zip_path.exists():
                try:
                    zip_path.unlink()
                except OSError:
                    pass
            error_msg = "磁盘空间不足，无法创建快照" if e.errno == 28 else f"系统错误: {str(e)}"
            return {
                "success": False,
                "snapshot_info": None,
                "error_message": error_msg
            }

        except (zipfile.BadZipFile, zipfile.LargeFileNotAllowedError) as e:
            logger.error(f"[RescueController] zip 压缩失败: {str(e)}", exc_info=True)
            if 'zip_path' in locals() and zip_path.exists():
                try:
                    zip_path.unlink()
                except OSError:
                    pass
            return {
                "success": False,
                "snapshot_info": None,
                "error_message": f"zip 压缩失败: {str(e)}"
            }

        except Exception as e:
            logger.error(f"[RescueController] 创建快照失败: {str(e)}", exc_info=True)
            if 'zip_path' in locals() and zip_path.exists():
                try:
                    zip_path.unlink()
                except OSError:
                    pass
            return {
                "success": False,
                "snapshot_info": None,
                "error_message": f"创建快照失败: {str(e)}"
            }

    def rescue_list_snapshots(self) -> Dict:
        """
        列出当前环境的所有快照

        使用外部元数据文件管理快照信息，支持自动迁移历史快照。
        优先使用外部元数据，不存在时从 zip 内提取。

        Returns:
            {success, snapshots[], error_message}
        """
        try:
            env = self._get_current_env()
            if not env:
                return {
                    "success": False,
                    "snapshots": [],
                    "error_message": "无法获取当前环境信息，请确认已选中环境"
                }

            env_id = env.get("id", "")
            backup_dir = self._get_backup_dir()

            if not backup_dir.exists():
                return {
                    "success": True,
                    "snapshots": [],
                    "error_message": None
                }

            metadata = self._load_metadata()
            existing_paths = {
                s.get("filePath"): s
                for s in metadata.get("snapshots", [])
            }

            need_save = False
            snapshots = []

            for zip_file in backup_dir.glob("*.zip"):
                zip_path_str = str(zip_file)

                try:
                    if zip_path_str in existing_paths:
                        existing = existing_paths[zip_path_str]
                        env_id_in_zip = self._get_env_id_from_zip(zip_file)
                        if env_id_in_zip != env_id:
                            continue
                        snapshots.append({
                            "filePath": existing["filePath"],
                            "name": existing["name"],
                            "backupOption": existing["backupOption"],
                            "note": existing.get("note", ""),
                            "createdAt": existing["createdAt"],
                            "fileSize": existing["fileSize"],
                        })
                    else:
                        extracted = self._extract_metadata_from_zip(zip_file)
                        if not extracted:
                            continue

                        env_id_in_zip = self._get_env_id_from_zip(zip_file)
                        if env_id_in_zip != env_id:
                            continue

                        metadata.setdefault("snapshots", []).append(extracted)
                        need_save = True
                        snapshots.append({
                            "filePath": extracted["filePath"],
                            "name": extracted["name"],
                            "backupOption": extracted["backupOption"],
                            "note": extracted.get("note", ""),
                            "createdAt": extracted["createdAt"],
                            "fileSize": extracted["fileSize"],
                        })
                        logger.info(f"[RescueController] 已迁移快照元数据: {zip_file.name}")

                except Exception as e:
                    logger.warning(
                        f"[RescueController] 处理 zip 文件失败: {zip_file.name}, 错误: {e}"
                    )
                    continue

            if need_save:
                self._save_metadata(metadata)
                logger.info(f"[RescueController] 元数据迁移完成，共迁移 {len([s for s in metadata.get('snapshots', []) if 'migratedAt' in s])} 个快照")

            snapshots.sort(key=lambda s: s["createdAt"], reverse=True)

            logger.info(
                f"[RescueController] 列出快照完成，"
                f"环境: {env_id}, 数量: {len(snapshots)}"
            )

            return {
                "success": True,
                "snapshots": snapshots,
                "error_message": None
            }

        except Exception as e:
            logger.error(
                f"[RescueController] 列出快照失败: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "snapshots": [],
                "error_message": f"列出快照失败: {str(e)}"
            }

    def _get_env_id_from_zip(self, zip_path: Path) -> Optional[str]:
        """
        从 zip 文件内获取 environment_id

        Args:
            zip_path: 快照 zip 文件路径

        Returns:
            environment_id 字符串，失败返回 None
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                if "snapshot_index.json" not in zf.namelist():
                    return None
                index_data = json.loads(
                    zf.read("snapshot_index.json").decode("utf-8")
                )
                return index_data.get("environment_id")
        except Exception:
            return None

    def rescue_delete_snapshot(self, snapshot_path: str) -> Dict:
        """
        删除指定的快照文件，同时移除外部元数据中的对应条目

        Args:
            snapshot_path: 快照 zip 文件的路径

        Returns:
            {success, error_message}
        """
        try:
            if not snapshot_path:
                return {
                    "success": False,
                    "error_message": "快照路径不能为空"
                }

            target = Path(snapshot_path)

            if not target.exists():
                return {
                    "success": False,
                    "error_message": f"快照文件不存在: {snapshot_path}"
                }

            if not target.is_file():
                return {
                    "success": False,
                    "error_message": f"指定路径不是文件: {snapshot_path}"
                }

            backup_dir = self._get_backup_dir()
            try:
                target.resolve().relative_to(backup_dir.resolve())
            except ValueError:
                return {
                    "success": False,
                    "error_message": "安全错误：不允许删除备份目录之外的文件"
                }

            target.unlink()

            metadata = self._load_metadata()
            snapshots = metadata.get("snapshots", [])
            original_count = len(snapshots)
            metadata["snapshots"] = [
                s for s in snapshots if s.get("filePath") != snapshot_path
            ]
            if len(metadata["snapshots"]) < original_count:
                self._save_metadata(metadata)
                logger.debug(
                    f"[RescueController] 已从元数据中移除快照记录: {snapshot_path}"
                )

            logger.info(
                f"[RescueController] 快照删除成功: {target.name}"
            )

            return {
                "success": True,
                "error_message": None
            }

        except PermissionError as e:
            logger.error(
                f"[RescueController] 删除快照权限不足: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "error_message": f"文件被占用或权限不足，无法删除: {str(e)}"
            }

        except FileNotFoundError:
            return {
                "success": False,
                "error_message": f"快照文件不存在: {snapshot_path}"
            }

        except OSError as e:
            logger.error(
                f"[RescueController] 删除快照系统错误: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "error_message": f"删除快照失败: {str(e)}"
            }

    def rescue_update_snapshot(self, snapshot_path: str, name: str, note: str) -> Dict:
        """
        更新快照元数据（name 和 note）

        通过外部元数据文件管理，不再重建 zip 文件。

        Args:
            snapshot_path: 快照 zip 文件路径
            name: 新的快照名称（1-50 字符）
            note: 新的备注信息（0-500 字符）

        Returns:
            {success, snapshot_info, error_message}
        """
        try:
            if not snapshot_path:
                return {
                    "success": False,
                    "snapshot_info": None,
                    "error_message": "快照路径不能为空"
                }

            if not name or len(name) < 1 or len(name) > 50:
                return {
                    "success": False,
                    "snapshot_info": None,
                    "error_message": "快照名称长度必须在 1 到 50 个字符之间"
                }

            if note is None:
                note = ""
            if len(note) > 500:
                return {
                    "success": False,
                    "snapshot_info": None,
                    "error_message": "备注长度不能超过 500 个字符"
                }

            target = Path(snapshot_path)

            if not target.exists():
                return {
                    "success": False,
                    "snapshot_info": None,
                    "error_message": f"快照文件不存在: {snapshot_path}"
                }

            if not target.is_file():
                return {
                    "success": False,
                    "snapshot_info": None,
                    "error_message": f"指定路径不是文件: {snapshot_path}"
                }

            backup_dir = self._get_backup_dir()
            try:
                target.resolve().relative_to(backup_dir.resolve())
            except ValueError:
                return {
                    "success": False,
                    "snapshot_info": None,
                    "error_message": "安全错误：不允许修改备份目录之外的文件"
                }

            metadata = self._load_metadata()
            snapshots = metadata.get("snapshots", [])

            found = None
            found_index = -1
            for i, s in enumerate(snapshots):
                if s.get("filePath") == snapshot_path:
                    found = s
                    found_index = i
                    break

            if found is None:
                extracted = self._extract_metadata_from_zip(target)
                if not extracted:
                    return {
                        "success": False,
                        "snapshot_info": None,
                        "error_message": "无法从快照文件中提取元数据"
                    }
                extracted["name"] = name
                extracted["note"] = note
                snapshots.append(extracted)
                found = extracted
            else:
                snapshots[found_index]["name"] = name
                snapshots[found_index]["note"] = note
                found = snapshots[found_index]

            metadata["snapshots"] = snapshots
            self._save_metadata(metadata)

            snapshot_info = {
                "filePath": str(target),
                "name": name,
                "backupOption": found.get("backupOption", ""),
                "note": note,
                "createdAt": found.get("createdAt", ""),
                "fileSize": found.get("fileSize", target.stat().st_size),
            }

            logger.info(
                f"[RescueController] 快照元数据更新成功: {target.name}"
            )

            return {
                "success": True,
                "snapshot_info": snapshot_info,
                "error_message": None,
            }

        except PermissionError as e:
            logger.error(
                f"[RescueController] 更新快照权限不足: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "snapshot_info": None,
                "error_message": f"文件被占用或权限不足，无法更新: {str(e)}"
            }

        except OSError as e:
            logger.error(
                f"[RescueController] 更新快照系统错误: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "snapshot_info": None,
                "error_message": f"更新快照失败: {str(e)}"
            }

        except Exception as e:
            logger.error(
                f"[RescueController] 更新快照失败: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "snapshot_info": None,
                "error_message": f"更新快照失败: {str(e)}"
            }

    def rescue_compute_diff(self, snapshot_path: str) -> Dict:
        """
        计算当前环境与快照之间的差异

        读取快照中的 snapshot_index.json，生成当前环境的临时索引，
        对比依赖和插件的差异。

        Args:
            snapshot_path: 快照 zip 文件的路径

        Returns:
            {success, diff_result, error_message}
            diff_result 格式:
            {
                "dependencies": {
                    "added": [{"name": str, "version": str}],    # 当前有、快照无 → 需卸载
                    "removed": [{"name": str, "version": str}],   # 快照有、当前无 → 需安装
                    "changed": [{"name": str, "current": str, "snapshot": str}]
                },
                "plugins": {
                    "added": [],    # 当前有、快照无 → 需删除
                    "removed": []   # 快照有、当前无 → 需恢复
                }
            }
        """
        try:
            if not snapshot_path:
                return {
                    "success": False,
                    "diff_result": None,
                    "error_message": "快照路径不能为空"
                }

            target = Path(snapshot_path)
            if not target.exists() or not target.is_file():
                return {
                    "success": False,
                    "diff_result": None,
                    "error_message": f"快照文件不存在: {snapshot_path}"
                }

            # === 读取快照中的 snapshot_index.json ===
            try:
                with zipfile.ZipFile(target, 'r') as zf:
                    if "snapshot_index.json" not in zf.namelist():
                        return {
                            "success": False,
                            "diff_result": None,
                            "error_message": "快照文件缺少 snapshot_index.json"
                        }
                    snapshot_index = json.loads(
                        zf.read("snapshot_index.json").decode("utf-8")
                    )
            except zipfile.BadZipFile:
                return {
                    "success": False,
                    "diff_result": None,
                    "error_message": "快照文件已损坏，无法读取"
                }

            # === 获取当前环境信息 ===
            env = self._get_current_env()
            if not env:
                return {
                    "success": False,
                    "diff_result": None,
                    "error_message": "无法获取当前环境信息，请确认已选中环境"
                }

            python_path = env.get("pythonPath")
            comfyui_path = env.get("comfyuiPath")

            # === 读取快照的 backup_option，决定对比范围 ===
            snapshot_backup_option = snapshot_index.get("backup_option", "all")
            compare_deps = snapshot_backup_option in ("deps_only", "all")
            compare_plugins = snapshot_backup_option in ("plugins_only", "all")

            # === 获取当前依赖列表 ===
            # 使用 PythonCommandBuilder 统一处理路径和命令构建
            current_deps = []
            if python_path and compare_deps:
                try:
                    builder = PythonCommandBuilder(python_path)
                    cmd = builder.pip_list()
                    result = builder.run(cmd, timeout=30, use_proxy=False)
                    
                    if result.returncode == 0 and result.stdout.strip():
                        current_deps = json.loads(result.stdout)
                except Exception as e:
                    logger.warning(f"[RescueController] pip list 执行失败: {e}")
                    current_deps = []

            # === 获取当前插件列表（扫描 custom_nodes）===
            current_plugins = []
            if comfyui_path and compare_plugins:
                custom_nodes_path = Path(comfyui_path) / "custom_nodes"
                if custom_nodes_path.exists() and custom_nodes_path.is_dir():
                    current_plugins = [
                        d.name for d in custom_nodes_path.iterdir()
                        if d.is_dir() and not d.name.startswith(".")
                    ]

            # === 计算依赖差异（仅当快照包含依赖信息时）===
            deps_added = []
            deps_removed = []
            deps_changed = []

            if compare_deps:
                # 构建依赖字典：{包名小写: 版本}
                current_deps_dict = {
                    dep.get("name", "").lower(): dep.get("version", "")
                    for dep in current_deps
                }
                snapshot_deps_dict = {
                    dep.get("name", "").lower(): dep.get("version", "")
                    for dep in snapshot_index.get("dependencies", [])
                }

                # 保留原始包名（用于显示）
                current_deps_names = {
                    dep.get("name", "").lower(): dep.get("name", "")
                    for dep in current_deps
                }
                snapshot_deps_names = {
                    dep.get("name", "").lower(): dep.get("name", "")
                    for dep in snapshot_index.get("dependencies", [])
                }

                current_keys = set(current_deps_dict.keys())
                snapshot_keys = set(snapshot_deps_dict.keys())

                # added: 当前有、快照无 → 需卸载
                deps_added = [
                    {
                        "name": current_deps_names.get(k, k),
                        "version": current_deps_dict[k]
                    }
                    for k in sorted(current_keys - snapshot_keys)
                ]

                # removed: 快照有、当前无 → 需安装
                deps_removed = [
                    {
                        "name": snapshot_deps_names.get(k, k),
                        "version": snapshot_deps_dict[k]
                    }
                    for k in sorted(snapshot_keys - current_keys)
                ]

                # changed: 两者都有但版本不同
                deps_changed = [
                    {
                        "name": current_deps_names.get(k, k),
                        "current": current_deps_dict[k],
                        "snapshot": snapshot_deps_dict[k]
                    }
                    for k in sorted(current_keys & snapshot_keys)
                    if current_deps_dict[k] != snapshot_deps_dict[k]
                ]

            # === 计算插件差异（仅当快照包含插件信息时）===
            plugins_added = []
            plugins_removed = []

            if compare_plugins:
                current_plugins_set = set(current_plugins)
                snapshot_plugins_set = set(snapshot_index.get("plugins", []))

                # added: 当前有、快照无 → 需删除
                plugins_added = sorted(current_plugins_set - snapshot_plugins_set)

                # removed: 快照有、当前无 → 需恢复
                plugins_removed = sorted(snapshot_plugins_set - current_plugins_set)

            diff_result = {
                "backup_option": snapshot_backup_option,
                "dependencies": {
                    "added": deps_added,
                    "removed": deps_removed,
                    "changed": deps_changed,
                },
                "plugins": {
                    "added": plugins_added,
                    "removed": plugins_removed,
                }
            }

            logger.info(
                f"[RescueController] 差异计算完成: "
                f"依赖 added={len(deps_added)}, removed={len(deps_removed)}, "
                f"changed={len(deps_changed)}, "
                f"插件 added={len(plugins_added)}, removed={len(plugins_removed)}"
            )

            return {
                "success": True,
                "diff_result": diff_result,
                "error_message": None,
            }

        except Exception as e:
            logger.error(
                f"[RescueController] 差异计算失败: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "diff_result": None,
                "error_message": f"差异计算失败: {str(e)}"
            }

    def rescue_smart_rollback(self, snapshot_path: str) -> Dict:
        """
        执行智能回滚

        基于差异对比结果，逐项恢复依赖和插件差异。
        依赖恢复通过 pip install/uninstall 实现，插件恢复通过解压/删除目录实现。
        单项失败不中断整体流程，最终返回完整的恢复报告。

        Args:
            snapshot_path: 快照 zip 文件的路径

        Returns:
            {success, report: {totalItems, succeeded, failed, failures[]}, error_message}
        """
        try:
            if not snapshot_path:
                return {
                    "success": False,
                    "report": None,
                    "error_message": "快照路径不能为空"
                }

            # === 调用 rescue_compute_diff 获取差异 ===
            diff_response = self.rescue_compute_diff(snapshot_path)
            if not diff_response.get("success"):
                return {
                    "success": False,
                    "report": None,
                    "error_message": diff_response.get("error_message", "差异计算失败")
                }

            diff_result = diff_response.get("diff_result", {})
            deps_diff = diff_result.get("dependencies", {})
            plugins_diff = diff_result.get("plugins", {})

            # === 获取环境信息 ===
            env = self._get_current_env()
            if not env:
                return {
                    "success": False,
                    "report": None,
                    "error_message": "无法获取当前环境信息，请确认已选中环境"
                }

            python_path = env.get("pythonPath")
            comfyui_path = env.get("comfyuiPath")

            # === 确定依赖目录路径 ===
            deps_dir = None
            if python_path:
                python_p = Path(python_path)
                python_dir = python_p.parent if python_p.is_file() else python_p
                if python_dir.name.lower() == "scripts":
                    deps_dir = python_dir.parent
                else:
                    deps_dir = python_dir  # python_embeded/ 本身

            # === 统计与跟踪 ===
            total_items = 0
            succeeded = 0
            failed = 0
            failures = []

            # 计算差异项
            deps_added = deps_diff.get("added", [])
            deps_removed = deps_diff.get("removed", [])
            deps_changed = deps_diff.get("changed", [])
            plugins_added = plugins_diff.get("added", [])
            plugins_removed = plugins_diff.get("removed", [])

            has_dep_diff = len(deps_added) + len(deps_removed) + len(deps_changed) > 0

            # 依赖整体算 1 个操作，插件每个单独计
            total_items = (
                (1 if has_dep_diff else 0)
                + len(plugins_added) + len(plugins_removed)
            )

            # === 依赖恢复：直接从快照解压 deps/ 覆盖 python 环境目录 ===
            if has_dep_diff:
                if not deps_dir:
                    failed += 1
                    failures.append({
                        "item": "依赖恢复",
                        "error": "Python 路径未配置，无法确定依赖目录"
                    })
                else:
                    try:
                        target_zip = Path(snapshot_path)
                        with zipfile.ZipFile(target_zip, 'r') as zf:
                            deps_files = [n for n in zf.namelist() if n.startswith("deps/")]
                            if not deps_files:
                                failed += 1
                                failures.append({
                                    "item": "依赖恢复",
                                    "error": "快照中不包含依赖目录备份（deps/），无法执行文件覆盖恢复"
                                })
                            else:
                                logger.info(
                                    f"[RescueController] 开始覆盖依赖目录: {deps_dir}, "
                                    f"共 {len(deps_files)} 个文件"
                                )
                                # 清空目标目录后解压覆盖
                                if deps_dir.exists():
                                    force_remove_directory(deps_dir, logger=logger)
                                deps_dir.mkdir(parents=True, exist_ok=True)

                                for file_path in deps_files:
                                    relative = file_path[len("deps/"):]
                                    if not relative:
                                        continue
                                    target_path = deps_dir / relative
                                    if file_path.endswith("/"):
                                        target_path.mkdir(parents=True, exist_ok=True)
                                    else:
                                        target_path.parent.mkdir(parents=True, exist_ok=True)
                                        with zf.open(file_path) as src, open(target_path, 'wb') as dst:
                                            dst.write(src.read())

                                succeeded += 1
                                logger.info("[RescueController] 依赖目录覆盖恢复完成")
                    except zipfile.BadZipFile:
                        failed += 1
                        failures.append({
                            "item": "依赖恢复",
                            "error": "快照文件已损坏，无法解压"
                        })
                    except Exception as e:
                        failed += 1
                        failures.append({
                            "item": "依赖恢复",
                            "error": str(e)
                        })
                        logger.error(f"[RescueController] 依赖覆盖恢复异常: {e}", exc_info=True)

            # === 插件恢复 ===
            plugins_dir = None
            if comfyui_path:
                plugins_dir = Path(comfyui_path) / "custom_nodes"

            # 删除新增的插件目录（当前有、快照无）
            for plugin_name in plugins_added:
                if not plugins_dir:
                    failed += 1
                    failures.append({
                        "item": f"删除插件 {plugin_name}",
                        "error": "ComfyUI 路径未配置"
                    })
                    continue

                plugin_path = plugins_dir / plugin_name
                try:
                    if plugin_path.exists() and plugin_path.is_dir():
                        success, error_msg = force_remove_directory(plugin_path, logger=logger)
                        if success:
                            succeeded += 1
                            logger.info(f"[RescueController] 删除插件成功: {plugin_name}")
                        else:
                            failed += 1
                            failures.append({
                                "item": f"删除插件 {plugin_name}",
                                "error": error_msg
                            })
                            logger.error(f"[RescueController] 删除插件失败: {plugin_name}, {error_msg}")
                    else:
                        succeeded += 1
                        logger.info(f"[RescueController] 插件目录已不存在，跳过: {plugin_name}")
                except Exception as e:
                    failed += 1
                    failures.append({
                        "item": f"删除插件 {plugin_name}",
                        "error": str(e)
                    })
                    logger.error(f"[RescueController] 删除插件异常: {plugin_name}, {e}")

            # 从 zip 恢复缺失的插件目录（快照有、当前无）
            if plugins_removed:
                target = Path(snapshot_path)
                try:
                    with zipfile.ZipFile(target, 'r') as zf:
                        for plugin_name in plugins_removed:
                            if not plugins_dir:
                                failed += 1
                                failures.append({
                                    "item": f"恢复插件 {plugin_name}",
                                    "error": "ComfyUI 路径未配置"
                                })
                                continue

                            try:
                                # 查找 zip 中对应插件的文件
                                prefix = f"plugins/{plugin_name}/"
                                plugin_files = [
                                    n for n in zf.namelist()
                                    if n.startswith(prefix)
                                ]

                                if not plugin_files:
                                    failed += 1
                                    failures.append({
                                        "item": f"恢复插件 {plugin_name}",
                                        "error": "快照中未找到该插件的备份文件"
                                    })
                                    continue

                                # 逐个解压文件到目标目录
                                for file_path in plugin_files:
                                    # 计算相对路径：去掉 "plugins/" 前缀
                                    relative = file_path[len("plugins/"):]
                                    if not relative:
                                        continue

                                    target_path = plugins_dir / relative

                                    # 如果是目录条目（以 / 结尾），创建目录
                                    if file_path.endswith("/"):
                                        target_path.mkdir(parents=True, exist_ok=True)
                                    else:
                                        # 确保父目录存在
                                        target_path.parent.mkdir(parents=True, exist_ok=True)
                                        # 解压文件
                                        with zf.open(file_path) as src, open(target_path, 'wb') as dst:
                                            dst.write(src.read())

                                succeeded += 1
                                logger.info(f"[RescueController] 恢复插件成功: {plugin_name}")

                            except Exception as e:
                                failed += 1
                                failures.append({
                                    "item": f"恢复插件 {plugin_name}",
                                    "error": str(e)
                                })
                                logger.error(f"[RescueController] 恢复插件异常: {plugin_name}, {e}")

                except zipfile.BadZipFile:
                    # zip 文件损坏，所有待恢复插件标记失败
                    for plugin_name in plugins_removed:
                        failed += 1
                        failures.append({
                            "item": f"恢复插件 {plugin_name}",
                            "error": "快照文件已损坏，无法解压"
                        })

            report = {
                "totalItems": total_items,
                "succeeded": succeeded,
                "failed": failed,
                "failures": failures,
            }

            logger.info(
                f"[RescueController] 智能回滚完成: "
                f"总计={total_items}, 成功={succeeded}, 失败={failed}"
            )

            return {
                "success": True,
                "report": report,
                "error_message": None,
            }

        except Exception as e:
            logger.error(
                f"[RescueController] 智能回滚失败: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "report": None,
                "error_message": f"智能回滚失败: {str(e)}"
            }

    def rescue_direct_restore(self, snapshot_path: str, restore_mode: str) -> Dict:
        """
        直接恢复模式

        从快照 zip 中解压对应目录，覆盖当前环境的依赖目录和/或插件目录。

        Args:
            snapshot_path: 快照 zip 文件的路径
            restore_mode: 恢复模式 "deps_only" | "plugins_only" | "all"

        Returns:
            {success, error_message}
        """
        try:
            # === 参数验证 ===
            if not snapshot_path:
                return {
                    "success": False,
                    "error_message": "快照路径不能为空"
                }

            if restore_mode not in ("deps_only", "plugins_only", "all"):
                return {
                    "success": False,
                    "error_message": f"无效的恢复模式: {restore_mode}"
                }

            target = Path(snapshot_path)
            if not target.exists() or not target.is_file():
                return {
                    "success": False,
                    "error_message": f"快照文件不存在: {snapshot_path}"
                }

            # === 获取环境信息 ===
            env = self._get_current_env()
            if not env:
                return {
                    "success": False,
                    "error_message": "无法获取当前环境信息，请确认已选中环境"
                }

            python_path = env.get("pythonPath")
            comfyui_path = env.get("comfyuiPath")

            # === 确定目标目录 ===
            deps_dir = None
            if python_path and restore_mode in ("deps_only", "all"):
                python_p = Path(python_path)
                python_dir = python_p.parent if python_p.is_file() else python_p
                if python_dir.name.lower() == "scripts":
                    deps_dir = python_dir.parent
                else:
                    deps_dir = python_dir  # python_embeded/ 本身

            plugins_dir = None
            if comfyui_path and restore_mode in ("plugins_only", "all"):
                plugins_dir = Path(comfyui_path) / "custom_nodes"

            # === 打开 zip 文件并解压 ===
            try:
                with zipfile.ZipFile(target, 'r') as zf:
                    all_names = zf.namelist()

                    # 恢复依赖目录
                    if restore_mode in ("deps_only", "all") and deps_dir:
                        deps_files = [n for n in all_names if n.startswith("deps/")]
                        if not deps_files:
                            if restore_mode == "deps_only":
                                return {
                                    "success": False,
                                    "error_message": "快照中不包含依赖目录备份"
                                }
                        else:
                            logger.info(f"[RescueController] 开始恢复依赖目录: {deps_dir}")
                            if deps_dir.exists():
                                force_remove_directory(deps_dir, logger=logger)
                            deps_dir.mkdir(parents=True, exist_ok=True)

                            for file_path in deps_files:
                                relative = file_path[len("deps/"):]
                                if not relative:
                                    continue

                                target_path = deps_dir / relative

                                if file_path.endswith("/"):
                                    target_path.mkdir(parents=True, exist_ok=True)
                                else:
                                    target_path.parent.mkdir(parents=True, exist_ok=True)
                                    with zf.open(file_path) as src, open(target_path, 'wb') as dst:
                                        dst.write(src.read())

                            logger.info("[RescueController] 依赖目录恢复完成")

                    # 恢复插件目录
                    if restore_mode in ("plugins_only", "all") and plugins_dir:
                        plugins_files = [n for n in all_names if n.startswith("plugins/")]
                        if not plugins_files:
                            if restore_mode == "plugins_only":
                                return {
                                    "success": False,
                                    "error_message": "快照中不包含插件目录备份"
                                }
                        else:
                            logger.info(f"[RescueController] 开始恢复插件目录: {plugins_dir}")
                            if plugins_dir.exists():
                                force_remove_directory(plugins_dir, logger=logger)
                            plugins_dir.mkdir(parents=True, exist_ok=True)

                            for file_path in plugins_files:
                                relative = file_path[len("plugins/"):]
                                if not relative:
                                    continue

                                target_path = plugins_dir / relative

                                if file_path.endswith("/"):
                                    target_path.mkdir(parents=True, exist_ok=True)
                                else:
                                    target_path.parent.mkdir(parents=True, exist_ok=True)
                                    with zf.open(file_path) as src, open(target_path, 'wb') as dst:
                                        dst.write(src.read())

                            logger.info("[RescueController] 插件目录恢复完成")

            except zipfile.BadZipFile:
                return {
                    "success": False,
                    "error_message": "快照文件已损坏，无法解压"
                }

            logger.info(
                f"[RescueController] 直接恢复完成: 模式={restore_mode}"
            )

            return {
                "success": True,
                "error_message": None,
            }

        except PermissionError as e:
            logger.error(
                f"[RescueController] 恢复权限不足: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "error_message": f"权限不足，无法恢复: {str(e)}"
            }

        except OSError as e:
            logger.error(
                f"[RescueController] 恢复系统错误: {str(e)}", exc_info=True
            )
            error_msg = "磁盘空间不足" if e.errno == 28 else f"系统错误: {str(e)}"
            return {
                "success": False,
                "error_message": error_msg
            }

        except Exception as e:
            logger.error(
                f"[RescueController] 直接恢复失败: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "error_message": f"直接恢复失败: {str(e)}"
            }


    def _add_directory_to_zip(self, zf: zipfile.ZipFile, source_dir: Path,
                              arc_prefix: str, include_git: bool = True) -> None:
        """
        将目录内容递归添加到 zip 文件中

        Args:
            zf: ZipFile 对象
            source_dir: 源目录路径
            arc_prefix: zip 内的目录前缀（如 "deps" 或 "plugins"）
            include_git: 是否包含 .git 目录
        """
        for root, dirs, files in os.walk(source_dir):
            root_path = Path(root)

            # 根据 include_git 参数过滤 .git 目录
            if not include_git:
                dirs[:] = [d for d in dirs if d != ".git"]
                # 跳过 .git 目录内的文件
                if ".git" in root_path.parts:
                    continue

            for file in files:
                file_path = root_path / file
                # 计算 zip 内的相对路径
                relative_path = file_path.relative_to(source_dir)
                arcname = f"{arc_prefix}/{relative_path}"
                try:
                    zf.write(file_path, arcname)
                except (PermissionError, OSError) as e:
                    logger.warning(
                        f"[RescueController] 跳过无法读取的文件: "
                        f"{file_path}, 错误: {e}"
                    )


    def _get_current_env(self) -> Optional[Dict]:
        """
        获取当前选中的环境配置

        Returns:
            环境配置字典（扁平化结构），如果未选中或获取失败则返回 None
            返回格式：
            {
                "id": "环境ID",
                "name": "环境名称",
                "alias": "环境别名",
                "path": "ComfyUI路径",
                "pythonPath": "Python路径",
                "pipPath": "pip路径",
                "comfyuiPath": "ComfyUI路径",
                "gitPath": "Git路径",
                "config": {...}
            }
        """
        if not self.environment_manager:
            logger.error("[RescueController] 环境管理器未初始化")
            return None

        try:
            # 获取当前环境 ID
            current_env_id = self.environment_manager.get_current_environment_id()

            if not current_env_id:
                logger.warning("[RescueController] 未选中任何环境")
                return None

            # 获取环境配置
            env_config = self.environment_manager.get_environment(current_env_id)

            if not env_config or not env_config.get("success"):
                logger.error(f"[RescueController] 获取环境配置失败: {current_env_id}")
                return None

            environment = env_config.get("environment")
            if not environment:
                logger.error(f"[RescueController] 环境数据为空: {current_env_id}")
                return None

            # 提取配置信息并扁平化
            config = environment.get("config", {})
            general = config.get("general", {})

            flattened_env = {
                "id": environment.get("id"),
                "name": environment.get("name"),
                "alias": environment.get("alias"),
                "path": environment.get("path"),
                "pythonPath": general.get("python_path"),
                "pipPath": general.get("pip_path"),
                "comfyuiPath": general.get("comfyui_path"),
                "gitPath": general.get("git_path"),
                "config": config,
            }

            logger.debug(
                f"[RescueController] 成功获取环境配置，"
                f"环境名称: {flattened_env.get('name')}"
            )
            return flattened_env

        except Exception as e:
            logger.error(f"[RescueController] 获取当前环境失败: {str(e)}", exc_info=True)
            return None

    def _get_backup_dir(self) -> Path:
        """
        获取备份目录路径，不存在时自动创建

        Returns:
            备份目录的 Path 对象（机器级用户数据根下的 backup/ 文件夹）
        """
        from backend.src.utils.paths import get_backup_dir
        backup_dir = get_backup_dir()

        if not backup_dir.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[RescueController] 已创建备份目录: {backup_dir}")

        return backup_dir

    def _get_metadata_file_path(self) -> Path:
        """
        获取快照元数据文件路径

        Returns:
            元数据文件的 Path 对象（data/snapshot_metadata.json）
        """
        from backend.src.utils.paths import get_data_dir
        data_dir = get_data_dir()

        if not data_dir.exists():
            data_dir.mkdir(parents=True, exist_ok=True)

        return data_dir / "snapshot_metadata.json"

    def _load_metadata(self) -> Dict:
        """
        加载快照元数据文件

        Returns:
            元数据字典，不存在则返回空结构 {"version": 1, "snapshots": []}
        """
        metadata_path = self._get_metadata_file_path()

        if not metadata_path.exists():
            return {"version": 1, "snapshots": []}

        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, dict) or "snapshots" not in data:
                    return {"version": 1, "snapshots": []}
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[RescueController] 元数据文件损坏，将重建: {e}")
            return {"version": 1, "snapshots": []}

    def _save_metadata(self, metadata: Dict) -> None:
        """
        原子写入快照元数据文件

        先写入临时文件，再替换目标文件，避免写入过程中崩溃导致数据丢失。

        Args:
            metadata: 元数据字典
        """
        import shutil

        metadata_path = self._get_metadata_file_path()
        temp_path = metadata_path.with_suffix('.tmp')

        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            shutil.move(str(temp_path), str(metadata_path))
            logger.debug(f"[RescueController] 元数据文件已保存: {metadata_path}")
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise e

    def _extract_metadata_from_zip(self, zip_path: Path) -> Optional[Dict]:
        """
        从 zip 文件内提取快照元数据

        Args:
            zip_path: 快照 zip 文件路径

        Returns:
            元数据字典，提取失败返回 None
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                if "snapshot_index.json" not in zf.namelist():
                    logger.warning(f"[RescueController] zip 文件缺少 snapshot_index.json: {zip_path.name}")
                    return None

                index_data = json.loads(
                    zf.read("snapshot_index.json").decode("utf-8")
                )

                now = datetime.now(timezone.utc).isoformat()

                return {
                    "filePath": str(zip_path),
                    "name": index_data.get("name", ""),
                    "backupOption": index_data.get("backup_option", ""),
                    "note": index_data.get("note", ""),
                    "createdAt": index_data.get("created_at", ""),
                    "fileSize": zip_path.stat().st_size,
                    "migratedAt": now,
                }
        except zipfile.BadZipFile:
            logger.warning(f"[RescueController] zip 文件损坏: {zip_path.name}")
            return None
        except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as e:
            logger.warning(f"[RescueController] zip 元数据解析失败: {zip_path.name}, {e}")
            return None
        except OSError as e:
            logger.warning(f"[RescueController] zip 文件读取失败: {zip_path.name}, {e}")
            return None
