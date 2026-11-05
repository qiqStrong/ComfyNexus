# 用户数据放在哪：一次讲清楚

> 目标：换目录、换副本、重新 clone、重新解压安装，同一台电脑上都能继续使用同一份用户数据；
> 缓存与业务数据有明确的清理入口；项目自身的产物绝不写进用户数据区。

---

## 一、切割逻辑：三条判据

判断一份文件属于"用户级数据"还是"系统级数据"，按下面顺序问三个问题：

1. **能否从别处重建？**
   能由程序重新生成（扫描、下载、翻译、构建）→ 缓存/系统级；不能（用户创作、对话、密钥）→ 用户级。
2. **重建代价有多大？**
   即使能重建，如果代价高（例如缩略图要从视频重新抽帧、LoRA 要重新扫描全盘），也按用户级对待，避免用户无意间丢掉"虽然可重建但很贵"的东西。
3. **删了还能不能找回？**
   删掉后无法从任何地方恢复（API Key、加密密钥、用户预设、救援备份）→ 必须留在用户数据区，并进入迁移清单。

**为什么按这个顺序**：先判断"是否可重建"最快排除系统产物；再看"重建代价"，避免把高成本缓存误判为可随意删除；最后用"能否找回"兜底，专门保护不可逆数据（尤其是加密密钥）。

---

## 二、举例：正反例各说清为什么

| 文件 | 判定 | 为什么 |
| --- | --- | --- |
| `data/gallery/assets.json` | **业务数据** | 记录用户导入的资产、分类、收藏。程序无法重新生成，删了等于用户作品库清空。 |
| `data/gallery/thumbnails/*.webp` | **缓存** | 可从原图/视频重新生成，但需要重新解码抽帧，代价不低；因此"可清理、但迁移时一起搬"，避免用户迁移后缩略图全空。 |
| `data/secrets/ai_fernet.key` | **最不能丢** | 它本身不是内容，而是解密 `ai_assistant.db` 中 API Key 的唯一钥匙。丢了以后所有 Key 永久无法解密，无法从别处重建。 |
| `build_scripts/打包产物_*` | **系统级** | 是构建输出，重新打包即可生成；与用户数据无关，项目目录删除时一起消失是正确行为。 |
| `logs/**` | **缓存/诊断** | 运行时可重新生成，删除不影响功能，只在排查问题时有用。 |
| `config/settings.json` | **业务配置** | 保存用户选择（语言、路径、行为偏好）。可从默认值重建，但会丢失用户设置，因此按用户级处理。 |

---

## 三、清单与保存路径

### 3.1 新的用户数据根

默认位置：`%LOCALAPPDATA%\Comfyui-Box\userdata`

```
%LOCALAPPDATA%\Comfyui-Box\userdata\
├── data\                 # 业务数据
│   ├── gallery\assets.json
│   ├── gallery\thumbnails\*.webp
│   ├── prompt\*.json + images\
│   ├── workflows\*.json
│   ├── system_prompts.json / active_system_prompts.json
│   ├── snapshot_metadata.json
│   ├── ai_assistant.db
│   └── secrets\ai_fernet.key
├── config\               # 用户配置（settings/environments/modules/lora/presets…）
├── backup\               # 救援快照
├── cache\                # 缓存（市场、翻译、扫描…）
├── logs\                 # 运行日志
├── lora_data\            # LoRA 扫描结果与预览
├── .initialized          # 首启完成标记
└── .migrated-from-userdata.json  # 迁移记录（只在目标侧写）
```

选择 `%LOCALAPPDATA%` 而不是 `%APPDATA%` 的理由：

1. `%APPDATA%` 是漫游目录，域账户会把它同步到服务器；缩略图和备份体积大，且没有同步价值。
2. `%LOCALAPPDATA%` 只在本机生效，符合"同一台电脑持续可用、不同电脑互不干扰"。
3. 应用的 WebView2 数据目录本来就在 `%LOCALAPPDATA%\Comfyui-Box\webview2`，与用户数据同源便于管理。

### 3.2 逐项清单（旧位置 → 新位置）

| 路径 | 旧位置（开发态 / 打包态） | 新位置 | 分类 | 可重建 | 迁移必搬 | 可安全删除 |
| --- | --- | --- | --- | --- | --- | --- |
| `gallery/assets.json` | `source-code/data` / `<exe>/data` | `<userdata>/data` | 业务 | 否 | 是 | 否 |
| `gallery/thumbnails/*.webp` | 同上 | `<userdata>/data` | 业务（高成本缓存） | 可，但代价高 | 是 | 否 |
| `prompt/*.json`、`prompt/images` | 同上 | `<userdata>/data` | 业务 | 否 | 是 | 否 |
| `workflows/*.json` | 同上 | `<userdata>/data` | 业务 | 否 | 是 | 否 |
| `system_prompts.json`、`active_system_prompts.json` | 同上 | `<userdata>/data` | 业务 | 否 | 是 | 否 |
| `snapshot_metadata.json` | 同上 | `<userdata>/data` | 业务 | 否 | 是 | 否 |
| `ai_assistant.db` | 同上 | `<userdata>/data` | 业务（对话/API Key） | 否 | 是 | 否 |
| `secrets/ai_fernet.key` | 同上 | `<userdata>/data` | 业务（加密密钥） | 否 | **是** | 否 |
| `core_nodes.json` | 同上 | `<userdata>/data` | 缓存 | 是（重新扫描） | 否 | 是 |
| `settings.json` | `source-code/backend/config` / `<exe>/config` | `<userdata>/config` | 业务配置 | 可默认重建 | 是 | 否 |
| `environments.json`、`workflow_config.json`、`search_config.json`、`preset_index.json` | 同上 | `<userdata>/config` | 业务配置 | 否 | 是 | 否 |
| `modules.json`、`lora_config.json`、`folder_shortcuts.json` | 同上 | `<userdata>/config` | 业务配置 | 可重建（丢选择） | 是 | 否 |
| `presets/**` | 同上 | `<userdata>/config` | 业务 | 否 | 是 | 否 |
| `default_config.json` | 同上 | 项目内（随包） | 系统级 | 是 | 否 | 否 |
| `cache/**` | `source-code/cache` / `<exe>/cache` | `<userdata>/cache` | 缓存 | 是 | 否 | 是 |
| `logs/**` | `source-code/logs` / `<exe>/logs` | `<userdata>/logs` | 缓存/诊断 | 是 | 否 | 是 |
| `backup/*.zip` | `source-code/backup` / `<exe>/backup` | `<userdata>/backup` | 业务 | 否 | 是 | 否（确认后手动） |
| `lora_data/**` | `source-code/lora_data` / `<exe>/lora_data` | `<userdata>/lora_data` | 缓存 | 是（重新扫描） | 否 | 是 |
| `webview2` | `%LOCALAPPDATA%\Comfyui-Box\webview2` | 同左 | 缓存 | 是 | 否 | 是 |
| `dist/` | `source-code/dist` | `_internal/dist` | 系统级 | 是（构建） | 否 | 是（需重建） |
| `.venv`、`node_modules` | 项目目录 | — | 系统级 | 是（安装依赖） | 否 | 是 |
| `build_scripts/打包产物_*` | 项目目录 | — | 系统级 | 是（重新打包） | 否 | 是 |
| `MinGit-*`、`models/*.onnx`、`VERSION`、`dev` | 项目目录 | 随安装包 | 系统级 | 是 | 否 | 否 |
| `temp/` | 项目目录 | — | 系统级临时 | 是 | 否 | 是 |

分类汇总：业务数据/配置 13 项；缓存/诊断 5 项；系统级产物 6 项（合计 24 项）。
判为缓存的依据：内容可由程序重新生成，删除后功能不受损；缩略图虽然可重建，但成本高，因此归入"业务但可清理"并随迁移一起搬。

### 3.3 项目目录只保留系统级产物

前端 `dist/`、后端代码、构建产物、MinGit/models 等随安装包或构建生成，删除项目目录时一起消失；不会写入用户数据区。

---

## 四、迁移时做什么

入口：首启弹窗的"迁移旧数据"，设置页的"迁移到新目录 / 更改目录（迁移当前数据）"。

1. **源目录只读**：只读取旧布局根（`data`、`config` 或 `backend/config`、`backup`、`lora_data`），不删除、不写标记、不改文件。
2. **复制到暂存区**：在目标根下建 `.migrating-<id>/`，先复制到暂存，避免直接污染目标。
3. **校验源数据**：资产数、分类数、缩略图数、提示词 JSON/图片数、工作流文件数、配置/备份/LoRA 文件数、数据库字节数与话题数、密钥 SHA-256。
4. **合并策略**：目标为空库（无资产/对话/提示词/密钥/备份）时覆盖空默认文件；目标已有数据时只补缺失文件，不覆盖已有文件。
5. **复核**：目标计数应与源一致（或至少齐全），并执行密钥校验——用目标 `data/secrets/ai_fernet.key` 解密 `ai_assistant.db` 中所有 `encrypted:` 开头的 API Key；有加密 Key 却缺密钥或解密失败 → 判定失败。
6. **失败回滚**：删除本次新建/覆盖的文件与暂存区；目标原有数据不受影响。错误原因会返回给界面，可重试。
7. **成功后的指针**：迁移到新目录时，同时写入机器级指针，替换旧指针，确保下次启动进入新目录；旧目录保持原样，由用户自行决定是否删除。
8. **重启生效**：迁移/切换后当前进程不切换数据根，必须重启应用，避免运行中同时读写两套路径。

一致性校验字段（迁移前后）：

| 项 | 来源 | 样本值 |
| --- | --- | --- |
| 资产数 / 分类数 | `data/gallery/assets.json` | 120 / 45 |
| 缩略图 | `data/gallery/thumbnails` | 22 |
| 提示词 | `data/prompt/*.json`、`data/prompt/images` | JSON 3、图片 7 |
| 工作流 | `data/workflows` | 3 |
| 对话 | `data/ai_assistant.db` 的 `topics` 表 | 2 |
| API Key | `data/ai_assistant.db` 的 `api_configs.api_key` | 逐个解密验证 |
| 密钥 | `data/secrets/ai_fernet.key` | 存在性 + SHA-256 |

---

## 五、用户能看到和能操作的东西

设置 → 数据目录，包含：

### 当前路径
只读展示用户数据根，可一键复制；显示来源：
- **默认目录**：`%LOCALAPPDATA%\Comfyui-Box\userdata`
- **用户指定目录**：由机器级指针指向
- **临时降级目录**：默认目录不可写时降级到 `%TEMP%\Comfyui-Box\userdata`，界面会用黄色提示条说明具体原因

### 按钮与后果

| 按钮 | 作用 | 是否重启 |
| --- | --- | --- |
| **复制路径** | 把当前数据根复制到剪贴板 | 否 |
| **打开目录** | 在资源管理器中打开当前数据根 | 否 |
| **刷新** | 重新读取计数、来源、旧安装检测结果 | 否 |
| **更改目录** | 选择新目录；弹窗提供"仅切换"或"迁移当前数据并切换"；若新目录已有数据会明确提示覆盖策略 | **是** |
| **迁移到新目录** | 选择新目录后直接执行"迁移当前数据 → 写入指针 → 重启" | **是** |
| **迁移旧数据**（检测到旧安装时出现） | 把项目内旧布局数据迁移到当前根，显示进度与结果 | 成功后重启 |
| **清理缓存与日志** | 删除 `cache/`、`logs/` 内容，下次启动自动重建 | 否 |
| **清空业务数据** | 二次确认后删除 `data/`、`config/`、`backup/`、`lora_data/` 内容（含密钥、API Key、资产、对话、配置、备份），**不可恢复**；重启后执行 | **是** |

迁移结果会展示：复制文件数、资产/分类/提示词图片/工作流数量、密钥校验结果；失败时显示原因，可重试。

---

## 附录：实现细节

### 定位顺序

1. 机器级指针文件 `%LOCALAPPDATA%\Comfyui-Box\userdata.location`（一行纯文本，绝对路径）
2. 默认目录 `%LOCALAPPDATA%\Comfyui-Box\userdata`
3. 默认目录不可写 → `%TEMP%\Comfyui-Box\userdata`，并把降级原因返回给 UI

指针失效（目录被移动/删除/不可写）时不会静默新建空库：回退默认目录并在界面提示原因。

不使用"项目内相对路径"的原因：它把数据绑定在单个项目副本上，换副本即丢，正是本次要解决的问题。指针在机器级目录，复制/删除项目都不会带走它。

### 指针文件格式

```
<绝对路径，一行，UTF-8>
```

写入时机：首启选择目录、设置页更改目录、迁移到新目录成功；均只写指针，不在当前进程切换数据根，重启后生效。

### 首启流程

1. 启动时解析用户数据根；`<root>/.initialized` 不存在 → 首启弹窗。
2. 弹窗展示当前目录与来源，两个动作：
   - **使用此目录**：写入 `.initialized`，关闭弹窗；
   - **选择其他目录**：系统目录选择，写指针 + 标记，重启应用。
3. 检测到旧布局有内容时，额外显示"迁移旧数据"入口（后台迁移，带进度）。
4. 选择失败/目录不可写：停留在弹窗并提示；仍可选择默认目录或临时降级目录。

### 代码入口

- `backend/src/utils/paths.py`：所有路径的唯一出口（`resolve_user_root`、`get_user_data_root`、`get_data_dir`、`get_config_dir`、`get_cache_dir`、`get_log_dir`、`get_backup_dir`、`get_lora_data_dir`、`get_webview2_dir`、旧布局候选）。
- `backend/src/core/userdata/manager.py`：状态、首启初始化、迁移、清理、待清空请求。
- `backend/src/bridge/api.py`：`userdata_*` 桥接 API。
- 前端：`components/settings/DataStorageSettings.tsx`（设置 → 数据目录）、`components/settings/DataDirSetupDialog.tsx`（首启弹窗）。
- 启动顺序：`main.py` 在单例检查后、任何数据模块初始化前执行 `apply_pending_wipe()`。

### 自动化测试注入

产品代码不读取进程环境变量。测试通过显式参数注入：`paths.resolve_user_root(override=<绝对路径>)`；数据层测试通过 monkeypatch 固定 `get_user_data_root` 返回值。
