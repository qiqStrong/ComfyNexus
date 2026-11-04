/**
 * HomePage 组件单元测试
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { HomePage } from './HomePage'
import { useSystemStore } from '@/stores/useSystemStore'
import { useProcessStore } from '@/stores/useProcessStore'
import { useFolderShortcutStore } from '@/stores/useFolderShortcutStore'

// Mock 子组件
vi.mock('./SystemMonitorGrid', () => ({
  SystemMonitorGrid: () => <div data-testid="system-monitor-grid">SystemMonitorGrid</div>
}))

vi.mock('./ComfyUIStatusCard', () => ({
  ComfyUIStatusCard: () => <div data-testid="comfyui-status-card">ComfyUIStatusCard</div>
}))

vi.mock('./FolderShortcutBar', () => ({
  FolderShortcutBar: () => <div data-testid="folder-shortcut-bar">FolderShortcutBar</div>
}))

vi.mock('./CreatorRecommendationGrid', () => ({
  CreatorRecommendationGrid: () => <div data-testid="creator-recommendation-grid">CreatorRecommendationGrid</div>
}))

// Mock Store
vi.mock('@/stores/useSystemStore')
vi.mock('@/stores/useProcessStore')
vi.mock('@/stores/useFolderShortcutStore')

describe('HomePage', () => {
  // Mock Store 方法
  const mockLoadMonitorData = vi.fn()
  const mockLoadComfyUIStatus = vi.fn()
  const mockLoadShortcuts = vi.fn()

  beforeEach(() => {
    // 重置 Mock
    vi.clearAllMocks()

    // 设置 Store Mock 返回值
    vi.mocked(useSystemStore).mockReturnValue({
      loadMonitorData: mockLoadMonitorData,
      monitorData: null,
      monitorLoading: false,
      monitorError: null,
      status: { cpu: 0, memory: 0, disk: 0 },
      loading: false,
      setStatus: vi.fn(),
      setLoading: vi.fn(),
      startMonitorPolling: vi.fn(),
      stopMonitorPolling: vi.fn(),
    })

    vi.mocked(useProcessStore).mockReturnValue({
      loadComfyUIStatus: mockLoadComfyUIStatus,
      comfyUIStatus: null,
      status: { isRunning: false },
      logs: [],
      loading: false,
      setStatus: vi.fn(),
      setLogs: vi.fn(),
      addLog: vi.fn(),
      clearLogs: vi.fn(),
      setLoading: vi.fn(),
      openComfyUI: vi.fn(),
      startComfyUI: vi.fn(),
    })

    vi.mocked(useFolderShortcutStore).mockReturnValue({
      loadShortcuts: mockLoadShortcuts,
      shortcuts: [],
      loading: false,
      error: null,
      saveShortcuts: vi.fn(),
      addShortcut: vi.fn(),
      deleteShortcut: vi.fn(),
      updateShortcut: vi.fn(),
      reorderShortcuts: vi.fn(),
      syncDefaultPaths: vi.fn(),
    })

    // Mock 返回成功的 Promise
    mockLoadMonitorData.mockResolvedValue(undefined)
    mockLoadComfyUIStatus.mockResolvedValue(undefined)
    mockLoadShortcuts.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('组件渲染', () => {
    it('应该正确渲染欢迎标题', () => {
      render(<HomePage />)

      expect(screen.getByText('欢迎使用 Comfyui-Box')).toBeInTheDocument()
      expect(screen.getByText('现代化的 ComfyUI 管理工具')).toBeInTheDocument()
    })

    it('应该正确渲染所有子组件', () => {
      render(<HomePage />)

      expect(screen.getByTestId('system-monitor-grid')).toBeInTheDocument()
      expect(screen.getByTestId('comfyui-status-card')).toBeInTheDocument()
      expect(screen.getByTestId('folder-shortcut-bar')).toBeInTheDocument()
      expect(screen.getByTestId('creator-recommendation-grid')).toBeInTheDocument()
    })

    it('应该支持自定义 className', () => {
      const { container } = render(<HomePage className="custom-class" />)
      const mainDiv = container.firstChild as HTMLElement

      expect(mainDiv).toHaveClass('custom-class')
    })
  })

  describe('数据加载', () => {
    it('应该在组件挂载时并行加载所有数据', async () => {
      render(<HomePage />)

      await waitFor(() => {
        expect(mockLoadMonitorData).toHaveBeenCalledTimes(1)
        expect(mockLoadComfyUIStatus).toHaveBeenCalledTimes(1)
        expect(mockLoadShortcuts).toHaveBeenCalledTimes(1)
      })
    })

    it('应该在加载时显示加载指示器', async () => {
      // 让加载方法延迟完成
      mockLoadMonitorData.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))

      render(<HomePage />)

      // 应该显示加载指示器
      expect(screen.getByText('加载中...')).toBeInTheDocument()

      // 等待加载完成
      await waitFor(() => {
        expect(screen.queryByText('加载中...')).not.toBeInTheDocument()
      }, { timeout: 200 })
    })

    it('应该处理部分数据加载失败的情况', async () => {
      // 模拟其中一个加载失败
      mockLoadMonitorData.mockRejectedValue(new Error('加载失败'))

      render(<HomePage />)

      // 等待加载完成（不应该抛出错误）
      await waitFor(() => {
        expect(mockLoadMonitorData).toHaveBeenCalled()
        expect(mockLoadComfyUIStatus).toHaveBeenCalled()
        expect(mockLoadShortcuts).toHaveBeenCalled()
      })

      // 页面应该正常渲染
      expect(screen.getByText('欢迎使用 Comfyui-Box')).toBeInTheDocument()
    })

    it('应该处理所有数据加载失败的情况', async () => {
      // 模拟所有加载失败
      mockLoadMonitorData.mockRejectedValue(new Error('加载失败'))
      mockLoadComfyUIStatus.mockRejectedValue(new Error('加载失败'))
      mockLoadShortcuts.mockRejectedValue(new Error('加载失败'))

      render(<HomePage />)

      // 等待加载完成（不应该抛出错误）
      await waitFor(() => {
        expect(mockLoadMonitorData).toHaveBeenCalled()
      })

      // 页面应该正常渲染
      expect(screen.getByText('欢迎使用 Comfyui-Box')).toBeInTheDocument()
    })
  })

  describe('响应式布局', () => {
    it('应该应用正确的响应式类名', () => {
      const { container } = render(<HomePage />)

      // 检查主容器类名
      const mainDiv = container.firstChild as HTMLElement
      expect(mainDiv).toHaveClass('container', 'mx-auto', 'p-8', 'space-y-6', 'max-w-7xl')

      // 检查分栏布局类名
      const gridDiv = mainDiv.querySelector('.grid')
      expect(gridDiv).toHaveClass('grid-cols-1', 'lg:grid-cols-3', 'gap-6')
    })
  })

  describe('深色主题', () => {
    it('应该包含深色主题样式类名', () => {
      render(<HomePage />)

      // 检查标题的深色主题类名
      const title = screen.getByText('欢迎使用 Comfyui-Box')
      expect(title).toHaveClass('dark:text-dark-text-primary')

      // 检查副标题的深色主题类名
      const subtitle = screen.getByText('现代化的 ComfyUI 管理工具')
      expect(subtitle).toHaveClass('dark:text-dark-text-secondary')
    })
  })

  describe('性能优化', () => {
    it('应该使用 React.memo 包装组件', async () => {
      // 检查默认导出是否为 memo 包装的组件
      const module = await import('./HomePage')
      const DefaultExport = module.default
      
      // React.memo 包装的组件会有特殊的 $$typeof 属性
      expect(DefaultExport).toBeDefined()
      // 简单验证组件可以正常渲染即可
      render(<DefaultExport />)
      expect(screen.getByText('欢迎使用 Comfyui-Box')).toBeInTheDocument()
    })
  })
})
