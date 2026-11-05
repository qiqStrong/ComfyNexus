# 数据分层设计：用户级数据 / 系统级数据

> 状态：已实现（`backend/src/utils/paths.py` 为单一事实来源）
> 目标：换目录、换副本、重新 clone、重新解压安装，都能继续使用同一份用户数据；
> 缓存与业务数据有明确清理入口；系统级产物绝不写进用户数据区。

## 1. 问题

旧布局把用户数据写在项目目录内：

- 开发态：`source-code/data`、`source-code/backend/config`、`source-code/logs`、`source-code/lora_data`、`source-code/backup`
- 打包态：`<exe 同级>/data`、`<exe 同级>/config`、`<exe 同级>/logs` …

因此把项目目录改名、复制、重新 clone 或换安装位置后，新位置的程序看不到旧数据，表现为"数据丢了"。
打包到 `Program Files` 时，exe 同级目录通常不可写，还会导致启动失败或数据写不进去。

## 2. 目录方案

### 2.1 用户数据根（机器级、可迁移）

默认：

```
%LOCALAPPDATA%\Comfyui-Box\userdata\
├── data/                 # 业务数据
│   ├── gallery/assets.json
│   ├── gallery/thumbnails/*.webp
│   ├── prompt/{prompts,categories,metadata}.json + images/
│   ├── workflows/*.json
│   ├── system_prompts.json / active_system_prompts.json
│   ├── snapshot_metadata.json
│   ├── ai_assistant.db
│   └── secrets/ai_fernet.key
├── config/               # 用户配置（settings/environments/modules/lora/presets…）
├── backup/               # 救援快照
├── cache/                # 缓存（市场缓存、翻译缓存、扫描缓存…）
├── logs/                 # 运行日志（诊断，可清理）
├── lora_data/            # LoRA 扫描结果与预览（可重建）
├── .initialized          # 首启完成标记
└── .migrated-from-userdata.json  # 迁移记录（只在目标侧写）
```

选择 `%LOCALAPPDATA%` 而不是 `%APPDATA%` 的理由：

1. `%APPDATA%` 是漫游目录，域账户会同步到服务器，数据（缩略图、备份）体积大且无同步价值。
2. `%LOCALAPPDATA%` 是本地目录，符合"同一台电脑持续可用、不同电脑互不干扰"的需求。
3. WebView2 数据目录本来就在 `%LOCALAPPDATA%\Comfyui-Box\webview2`，与之一致。

### 2.2 项目目录只保留系统级产物

| 内容 | 开发态位置 | 打包态位置 | 说明 |
| --- | --- | --- | --- |
| 前端构建产物 `dist/` | `source-code/dist` | `_internal/dist` | 重新构建即可，不迁移 |
| 后端代码/资源 | `source-code/backend` | `_internal/backend` | 随安装包 |
| MinGit / models / VERSION / dev | `source-code/backend`、根目录 | `<exe>/tools`、根目录 | 随安装包 |
| `.venv`、`node_modules`、`build_scripts/打包产物_*` | 项目目录 | — | 开发/构建产物 |
| WebView2 缓存 | `%LOCALAPPDATA%\Comfyui-Box\webview2` | 同左 | 机器级缓存，可清空 |

## 3. 定位机制：机器级指针，而不是项目内相对路径

解析顺序（`paths.get_user_data_root()`）：

1. 环境变量 `COMFYUI_BOX_USERDATA`（绝对路径；测试/高级用户可覆盖）
2. 机器级指针文件 `%LOCALAPPDATA%\Comfyui-Box\userdata.location`（一行纯文本，绝对路径）
3. 默认目录 `%LOCALAPPDATA%\Comfyui-Box\userdata`

指针文件同时保证：

- 同一台机器上的**任意副本**都读同一份数据（指针不在项目目录里，复制/删除项目不会带走它）；
- 目录改名后重新选择即可继续使用（或使用"更改目录 → 迁移当前数据"）；
- 指针指向的目录不可写/不存在时，降级到默认目录，并在首启弹窗中提示"原数据目录不可用"，不会静默新建空库。

不使用"项目内相对路径"的原因：它把数据绑定在单个副本上，换副本即丢，正是本次要解决的问题。

## 4. 首启流程

1. 启动时解析用户数据根；若 `<root>/.initialized` 不存在 → 首启弹窗（`DataDirSetupDialog`）。
2. 弹窗展示当前目录（默认路径），两个动作：
   - **使用此目录**：写入 `.initialized`，关闭弹窗；
   - **选择其他目录**：调用系统目录选择（复用 `browse_folder_for_shortcut`），写入指针 + 标记，重启应用。
3. 若检测到旧布局数据（项目内 `data/`、`config/`、`backup/`、`lora_data/` 且确有内容），弹窗额外显示"迁移旧数据"入口：
   - 后台迁移到当前根（带进度）；
   - 成功后写标记并重启。
4. 目录不可写 / 选择失败：返回错误提示，停留在首启弹窗；用户可改用默认目录。
   默认目录也不可写时，最后降级到 `%TEMP%\Comfyui-Box\userdata`（仍失败才报错）。

## 5. 一键迁移

入口：首启弹窗、设置 → 数据目录 → "迁移旧数据"/"更改目录（迁移当前数据）"。

步骤（`backend/src/core/userdata/manager.py`）：

1. 识别源目录：旧布局根（`<root>/data`、`<root>/backend/config` 或 `<root>/config`、`backup/`、`lora_data/`）。
2. 复制到目标根下暂存区 `.migrating-<id>/`（复制不移动，**源目录只读**）。
3. 暂存校验：资产数、分类数、缩略图数、提示词 JSON/图片数、工作流文件数、配置/备份/LoRA 文件数、数据库字节数与话题数、密钥 SHA-256。
4. 合并到目标：
   - 目标是全新空库（无资产/无对话/无提示词/无密钥/无备份）时覆盖空默认文件；
   - 目标已有数据时只补缺失文件，不覆盖。
5. 目标校验：计数一致（或至少齐全），并执行**密钥校验**：
   - 用目标 `data/secrets/ai_fernet.key` 解密 `ai_assistant.db` 中所有 `encrypted:` 开头的 API Key；
   - 有加密 Key 却缺密钥文件、或解密失败 → 判定迁移失败并回滚（否则用户迁移后 Key 永久不可用）。
6. 成功：在目标根写 `.migrated-from-userdata.json`（源路径、计数、密钥校验结果）。
7. 失败：回滚本次新建/覆盖的文件（暂存区删除），返回错误；已存在数据不受影响。
8. 旧目录处理：**保留且不做任何修改**（不删除、不写标记）。确认无误后由用户自行处理旧目录。

一致性校验字段（迁移前后）：

| 项 | 来源 | 说明 |
| --- | --- | --- |
| 资产数 / 分类数 | `data/gallery/assets.json` | 120 / 45（样本） |
| 缩略图 | `data/gallery/thumbnails` | 22 |
| 提示词 | `data/prompt/*.json`、`data/prompt/images` | JSON 3、图片 7（样本） |
| 工作流 | `data/workflows` | 3（样本） |
| 对话 | `data/ai_assistant.db` 的 `topics` 表 | 话题数 |
| API Key | `data/ai_assistant.db` 的 `api_configs.api_key` | 逐个解密验证 |
| 密钥 | `data/secrets/ai_fernet.key` | 存在性 + SHA-256 |

## 6. 清理入口

设置 → 数据目录：

- **清理缓存与日志**：删除 `<root>/cache`、`<root>/logs` 内容；可安全删除，下次启动重建。
- **清空业务数据**：删除 `<root>/data`、`config`、`backup`、`lora_data` 内容（含加密密钥、API Key、资产、提示词、工作流元数据、对话、配置、备份）。
  - 二次确认，文案明确"不可恢复"；
  - 为避免运行时文件句柄导致删除失败或数据回写，先写 `<root>/.wipe-request.json`，应用重启后在**任何数据模块初始化前**执行清空（`apply_pending_wipe`），随后进入空库。
- WebView2 缓存可手动删除 `%LOCALAPPDATA%\Comfyui-Box\webview2`（应用下次启动自动重建），不纳入业务数据清理，避免运行中句柄冲突。

## 7. 兼容旧安装

- 旧安装首次使用新版本时，`detect_legacy_sources()` 会检查安装根下是否存在**有内容**的旧布局目录（排除仅含随包默认文件的空壳），首启弹窗提示迁移。
- 不自动静默搬移用户数据；用户明确点击"迁移旧数据"才复制。
- 环境变量 `COMFYUI_BOX_USERDATA` 可让旧数据目录直接作为用户数据根（无需迁移）。
- 打包态若检测到 `_internal` 内的旧运行目录，启动时会搬到用户数据根（一次性，写 `.migration_completed` 于安装目录）。

## 8. 盘点表（旧 → 新）

| 路径 | 旧实际位置（开发 / 打包） | 分类 | 可从别处重建 | 迁移必搬 | 可安全删除 |
| --- | --- | --- | --- | --- | --- |
| `data/gallery/assets.json` | `source-code/data` / `<exe>/data` | 业务 | 否 | 是 | 否 |
| `data/gallery/thumbnails/*.webp` | 同上 | 业务 | 可从源视频重建但成本高 | 是 | 否 |
| `data/prompt/*.json`、`data/prompt/images` | 同上 | 业务 | 否（用户创作） | 是 | 否 |
| `data/workflows/*.json` | 同上 | 业务 | 否（仅元数据，源工作流在 ComfyUI） | 是 | 否 |
| `data/system_prompts.json`、`active_system_prompts.json` | 同上 | 业务 | 否 | 是 | 否 |
| `data/snapshot_metadata.json` | 同上 | 业务（快照索引） | 否 | 是 | 否 |
| `data/ai_assistant.db` | 同上 | 业务（对话/API Key） | 否 | 是 | 否 |
| `data/secrets/ai_fernet.key` | 同上 | 业务（加密密钥） | 否；丢失则 API Key 不可解 | **是** | 否 |
| `data/core_nodes.json` | 同上 | 缓存（核心节点扫描结果） | 是（重新扫描） | 否 | 是 |
| `backend/config/settings.json` | `source-code/backend/config` / `<exe>/config` | 业务配置 | 可默认重建 | 是 | 否 |
| `config/environments.json`、`workflow_config.json`、`search_config.json`、`preset_index.json` | 同上 | 业务配置 | 否（用户环境路径/预设索引） | 是 | 否 |
| `config/modules.json`、`lora_config.json`、`folder_shortcuts.json` | 同上 | 业务配置 | 可重建（会丢用户选择） | 是 | 否 |
| `config/presets/**` | 同上 | 业务（用户预设） | 否 | 是 | 否 |
| `backend/config/default_config.json` | 同上 | 系统级（随包默认） | 是（随包） | 否 | 否 |
| `cache/**`（marketplace/translations…） | `source-code/cache` / `<exe>/cache` | 缓存 | 是 | 否 | 是 |
| `logs/**` | `source-code/logs` / `<exe>/logs` | 缓存/诊断 | 是（重新运行） | 否 | 是 |
| `backup/*.zip` | `source-code/backup` / `<exe>/backup` | 业务（救援快照） | 否 | 是 | 否（确认后手动） |
| `lora_data/**` | `source-code/lora_data` / `<exe>/lora_data` | 缓存（扫描+预览） | 是（重新扫描） | 否 | 是 |
| `%LOCALAPPDATA%\Comfyui-Box\webview2` | 同左 | 缓存 | 是 | 否 | 是（不迁移） |
| `dist/` | `source-code/dist` | 系统级 | 是（`npm run build`） | 否 | 是（应用需重建） |
| `backend/.venv`、`.venv`、`frontend/node_modules` | 项目目录 | 系统级 | 是（安装依赖） | 否 | 是 |
| `build_scripts/打包产物_*` | 项目目录 | 系统级 | 是（重新打包） | 否 | 是 |
| `backend/MinGit-*`、`backend/models/*.onnx`、`VERSION`、`dev` | 项目目录 | 系统级 | 是（随包） | 否 | 否 |
| `temp/` | 项目目录 | 系统级临时 | 是 | 否 | 是 |

分类汇总：业务数据/配置 13 项；缓存/诊断 5 项；系统级产物 6 项（合计 24 项）。
判为缓存的依据：内容可由程序重新生成（扫描/下载/翻译/日志），删除后功能不受损。

## 9. 代码入口

- `backend/src/utils/paths.py`：所有路径的唯一出口（`get_user_data_root`、`get_data_dir`、`get_config_dir`、`get_cache_dir`、`get_log_dir`、`get_backup_dir`、`get_lora_data_dir`、`get_webview2_dir`、旧布局候选）。
- `backend/src/core/userdata/manager.py`：状态、首启初始化、迁移、清理、待清空请求。
- `backend/src/bridge/api.py`：`userdata_*` 桥接 API。
- 前端：`components/settings/DataStorageSettings.tsx`（设置 → 数据目录）、`components/settings/DataDirSetupDialog.tsx`（首启弹窗）。
- 启动顺序：`main.py` 在单例检查后、任何数据模块初始化前执行 `apply_pending_wipe()`。
