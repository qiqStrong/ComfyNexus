/**
 * 系统设置状态管理 Store
 */

import { create } from 'zustand'

interface VersionSettings {
  displayCount: number        // 默认显示数量
  showDevWarning: boolean     // 是否显示开发版警告
}

interface SystemSettings {
  // 通用设置
  configMode: 'preset' | 'advanced'
  autoUpdate: boolean
  comfyuiStartupAction?: 'workspace' | 'browser' | 'none'  // ComfyUI 启动后操作
  
  // 外观设置
  theme: 'light' | 'dark'
  windowSize: string
  
  // 语言设置
  language: string
  
  // 代理设置
  proxyEnabled: boolean
  proxyHost: string
  proxyPort: string
  
  // 插件管理设置
  gitConcurrency: number  // Git 并发数，默认 10，范围 1-32
  hideDisabledPlugins: boolean  // 是否隐藏禁用的插件，默认 false
  
  // 插件市场设置
  autoInstallDeps: boolean  // 是否自动安装依赖，默认 true
  
  // 日志设置
  logLevel?: string  // 日志级别：DEBUG/INFO/WARNING/ERROR
}

interface SettingsStore {
  // 版本管理设置（仍然使用 localStorage）
  versionSettings: VersionSettings
  
  // 系统设置（从后端加载）
  systemSettings: SystemSettings
  
  // 加载状态
  loading: boolean
  
  // 操作
  updateVersionSettings: (settings: Partial<VersionSettings>) => void
  updateSystemSettings: (settings: Partial<SystemSettings>) => Promise<void>
  loadSystemSettings: () => Promise<void>
  resetDevWarning: () => void
}

export const useSettingsStore = create<SettingsStore>((set, get) => ({
  // 初始状态
  versionSettings: {
    displayCount: 20,
    showDevWarning: true,
  },
  
  systemSettings: {
    configMode: 'preset',
    autoUpdate: true,
    comfyuiStartupAction: 'workspace',  // 默认在工作台打开
    theme: 'light',
    windowSize: '1680x1080',
    language: 'zh-CN',
    proxyEnabled: false,
    proxyHost: '',
    proxyPort: '',
    gitConcurrency: 10,  // 默认并发数为 10
    hideDisabledPlugins: false,  // 默认显示所有插件
    autoInstallDeps: true,  // 默认自动安装依赖
    logLevel: 'INFO',  // 默认日志级别为 INFO
  },
  
  loading: false,
  
  // 更新版本设置（localStorage）
  updateVersionSettings: (settings) => {
    set((state) => ({
      versionSettings: {
        ...state.versionSettings,
        ...settings,
      },
    }))
    
    // 保存到 localStorage
    const newSettings = { ...get().versionSettings, ...settings }
    localStorage.setItem('comfyui-box-version-settings', JSON.stringify(newSettings))
  },
  
  // 更新系统设置（后端文件）
  updateSystemSettings: async (settings) => {
    try {
      if (!window.pywebview?.api) {
        console.error('[useSettingsStore] API 不可用')
        return
      }
      
      console.log('[useSettingsStore] 开始更新设置:', settings)
      
      // 构建更新数据
      const updates: Record<string, any> = {}
      
      if ('configMode' in settings || 'autoUpdate' in settings || 'comfyuiStartupAction' in settings) {
        updates.general = {}
        if ('configMode' in settings) updates.general.configMode = settings.configMode
        if ('autoUpdate' in settings) updates.general.autoUpdate = settings.autoUpdate
        if ('comfyuiStartupAction' in settings) updates.general.comfyuiStartupAction = settings.comfyuiStartupAction
      }
      
      if ('theme' in settings || 'windowSize' in settings) {
        updates.appearance = {}
        if ('theme' in settings) updates.appearance.theme = settings.theme
        if ('windowSize' in settings) updates.appearance.windowSize = settings.windowSize
      }
      
      if ('language' in settings) {
        updates.language = { current: settings.language }
      }
      
      if ('proxyEnabled' in settings || 'proxyHost' in settings || 'proxyPort' in settings) {
        updates.proxy = {}
        if ('proxyEnabled' in settings) updates.proxy.enabled = settings.proxyEnabled
        if ('proxyHost' in settings) updates.proxy.host = settings.proxyHost
        if ('proxyPort' in settings) updates.proxy.port = settings.proxyPort
      }
      
      if ('gitConcurrency' in settings || 'hideDisabledPlugins' in settings) {
        updates.pluginManagement = {}
        if ('gitConcurrency' in settings) updates.pluginManagement.gitConcurrency = settings.gitConcurrency
        if ('hideDisabledPlugins' in settings) updates.pluginManagement.hideDisabledPlugins = settings.hideDisabledPlugins
      }
      
      if ('autoInstallDeps' in settings) {
        updates.pluginMarketplace = {
          autoInstallDeps: settings.autoInstallDeps
        }
      }
      
      if ('logLevel' in settings) {
        updates.logging = {
          level: settings.logLevel
        }
      }
      
      console.log('[useSettingsStore] 发送到后端的更新数据:', updates)
      
      // 调用后端 API
      const result = await window.pywebview.api.update_settings(updates)
      
      console.log('[useSettingsStore] 后端返回结果:', result)
      
      if (result.success) {
        // 更新本地状态
        set((state) => ({
          systemSettings: {
            ...state.systemSettings,
            ...settings,
          },
        }))
        console.log('[useSettingsStore] 本地状态已更新')
      } else {
        console.error('[useSettingsStore] 更新设置失败:', result.message)
      }
    } catch (error) {
      console.error('[useSettingsStore] 更新设置失败:', error)
    }
  },
  
  // 从后端加载系统设置
  loadSystemSettings: async () => {
    try {
      set({ loading: true })
      
      if (!window.pywebview?.api) {
        console.error('[useSettingsStore] API 不可用')
        set({ loading: false })
        return
      }
      
      console.log('[useSettingsStore] 开始加载系统设置')
      
      const result = await window.pywebview.api.get_settings()
      
      console.log('[useSettingsStore] 后端返回的设置:', result)
      
      if (result.success && result.settings) {
        const settings = result.settings
        
        console.log('[useSettingsStore] pluginManagement 配置:', (settings as any).pluginManagement)
        console.log('[useSettingsStore] hideDisabledPlugins 值:', (settings as any).pluginManagement?.hideDisabledPlugins)
        
        // 转换后端格式到前端格式
        set({
          systemSettings: {
            configMode: settings.general?.configMode || 'preset',
            autoUpdate: settings.general?.autoUpdate !== false,
            comfyuiStartupAction: settings.general?.comfyuiStartupAction || 'workspace',
            theme: settings.appearance?.theme || 'light',
            windowSize: settings.appearance?.windowSize || '1680x1080',
            language: settings.language?.current || 'zh-CN',
            proxyEnabled: settings.proxy?.enabled || false,
            proxyHost: settings.proxy?.host || '',
            proxyPort: settings.proxy?.port || '',
            gitConcurrency: (settings as any).pluginManagement?.gitConcurrency ?? 10,
            hideDisabledPlugins: (settings as any).pluginManagement?.hideDisabledPlugins ?? false,
            autoInstallDeps: (settings as any).pluginMarketplace?.autoInstallDeps ?? true,
            logLevel: (settings as any).logging?.level || 'INFO',
          },
          loading: false,
        })
        
        console.log('[useSettingsStore] 系统设置加载完成')
      } else {
        console.error('[useSettingsStore] 加载设置失败:', result.message)
        set({ loading: false })
      }
      
      // 从 localStorage 加载版本设置
      const versionSettingsStr = localStorage.getItem('comfyui-box-version-settings')
      if (versionSettingsStr) {
        try {
          const versionSettings = JSON.parse(versionSettingsStr)
          set({ versionSettings })
        } catch (e) {
          console.error('[useSettingsStore] 解析版本设置失败:', e)
        }
      }
    } catch (error) {
      console.error('[useSettingsStore] 加载设置失败:', error)
      set({ loading: false })
    }
  },
  
  // 重置开发版警告（恢复显示）
  resetDevWarning: () => {
    set((state) => ({
      versionSettings: {
        ...state.versionSettings,
        showDevWarning: true,
      },
    }))
    
    // 保存到 localStorage
    const newSettings = { ...get().versionSettings, showDevWarning: true }
    localStorage.setItem('comfyui-box-version-settings', JSON.stringify(newSettings))
  },
}))
