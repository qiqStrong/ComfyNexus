/**
 * 首页相关类型定义
 */

/**
 * 系统监控数据类型
 */
export interface SystemMonitorData {
  // VRAM (GPU显存)
  vram: {
    used: number | null      // 使用百分比 (0-100)
    total: number            // 总容量 (GB)
    used_gb: number          // 已使用容量 (GB)
  }
  
  // 内存
  memory: {
    used: number | null      // 使用百分比 (0-100)
    total: number            // 总容量 (GB)
    used_gb: number          // 已使用容量 (GB)
  }
  
  // 虚拟内存
  virtual_memory: {
    used: number | null      // 使用百分比 (0-100)
    total: number            // 总容量 (GB)
    used_gb: number          // 已使用容量 (GB)
  }
  
  // CPU
  cpu: {
    usage: number | null     // CPU占用率 (0-100)
    power: number | null     // CPU功率 (W)
    temperature: number | null // CPU温度 (°C)
  }
  
  // GPU
  gpu: {
    usage: number | null     // GPU占用率 (0-100)
    power: number | null     // GPU功率 (W)
    temperature: number | null // GPU温度 (°C)
  }
}

/**
 * ComfyUI 状态类型
 */
export interface ComfyUIStatus {
  isRunning: boolean         // 是否正在运行
  isExternal?: boolean       // 是否是外部进程（不受 Comfyui-Box 管理）
  pid?: number               // 进程ID
  envId?: string             // 环境ID（运行时的环境）
  port?: number              // 运行端口
  portAvailable?: boolean    // 端口是否可用（服务是否真正启动完成）
  uptime?: number            // 运行时长 (秒)
  url?: string               // 访问URL
  wasStarted?: boolean       // 是否曾经启动过
  exitCode?: number | null   // 进程退出码
  processAlive?: boolean     // 进程是否存活
}

/**
 * 文件夹快捷方式类型
 */
export interface FolderShortcut {
  id: string                 // 唯一标识
  name: string               // 显示名称
  path: string               // 文件夹路径
  icon: string               // 图标名称 (Lucide图标)
  order: number              // 显示顺序
  isDefault: boolean         // 是否为默认文件夹 (默认文件夹不可删除)
  visible?: boolean          // 是否在首页显示 (默认为 true)
}

/**
 * 创作者类型
 */
export interface Creator {
  id: number                 // 创作者ID
  name: string               // 创作者名称
  avatar: string             // 头像URL
  description: string        // 描述
  link: string               // 主页链接
  platform: string           // 平台 (bilibili, youtube, github等)
}

/**
 * 监控项配置类型
 */
export interface MonitorItemConfig {
  key: string                // 数据键 (如 'vram', 'cpu.usage')
  label: string              // 显示标签
  unit: string               // 单位 (%, W, °C等)
  color: string              // 主题颜色
  icon: string               // 图标名称 (Lucide图标)
}

/**
 * 温度预警级别
 */
export type TemperatureLevel = 'normal' | 'warning' | 'danger'

/**
 * 文件夹快捷方式配置响应
 */
export interface FolderShortcutsResponse {
  success: boolean
  shortcuts?: FolderShortcut[]
  error_code?: number
  error_message?: string
}

/**
 * 文件夹操作响应
 */
export interface FolderOperationResponse {
  success: boolean
  error_code?: number
  error_message?: string
}

/**
 * 文件夹路径验证响应
 */
export interface FolderValidationResponse {
  success: boolean
  isValid?: boolean
  error_code?: number
  error_message?: string
}

/**
 * 文件夹浏览响应
 */
export interface FolderBrowseResponse {
  success: boolean
  path?: string | null
  error_code?: number
  error_message?: string
}

/**
 * 系统监控数据响应
 */
export interface SystemMonitorDataResponse {
  success: boolean
  data?: SystemMonitorData
  error_code?: number
  error_message?: string
}

/**
 * ComfyUI 状态响应
 */
export interface ComfyUIStatusResponse {
  success: boolean
  data?: ComfyUIStatus
  error_code?: number
  error_message?: string
}
