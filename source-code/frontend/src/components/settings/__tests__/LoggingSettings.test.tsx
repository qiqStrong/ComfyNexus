/**
 * 日志设置组件集成测试
 * 
 * 测试日志设置界面的交互和前后端配置同步
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LoggingSettings } from '../LoggingSettings'

describe('LoggingSettings 组件', () => {
  const mockOnLevelChange = vi.fn()

  beforeEach(() => {
    mockOnLevelChange.mockClear()
  })

  it('应该渲染日志级别选择器', () => {
    render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    // 检查标题
    expect(screen.getByText('日志级别')).toBeInTheDocument()

    // 检查选择器
    const select = screen.getByRole('combobox')
    expect(select).toBeInTheDocument()
    expect(select).toHaveValue('INFO')
  })

  it('应该显示所有日志级别选项', () => {
    render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    const select = screen.getByRole('combobox')
    const options = select.querySelectorAll('option')

    expect(options).toHaveLength(4)
    expect(options[0]).toHaveTextContent('DEBUG（调试）')
    expect(options[1]).toHaveTextContent('INFO（信息）')
    expect(options[2]).toHaveTextContent('WARNING（警告）')
    expect(options[3]).toHaveTextContent('ERROR（错误）')
  })

  it('应该显示当前级别的说明', () => {
    render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    // 只检查说明文本，不检查标题（因为标题在select option中也有）
    expect(screen.getByText(/输出重要的业务操作信息/)).toBeInTheDocument()
  })

  it('切换日志级别时应该调用回调函数', async () => {
    render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'DEBUG' } })

    await waitFor(() => {
      expect(mockOnLevelChange).toHaveBeenCalledWith('DEBUG')
    })
  })

  it('切换到DEBUG级别应该显示DEBUG的说明', async () => {
    const { rerender } = render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'DEBUG' } })

    // 模拟父组件更新 currentLevel
    rerender(
      <LoggingSettings
        currentLevel="DEBUG"
        onLevelChange={mockOnLevelChange}
      />
    )

    await waitFor(() => {
      // 使用更精确的查询，查找说明区域中的文本
      expect(screen.getByText(/输出所有日志信息/)).toBeInTheDocument()
    })
  })

  it('切换到WARNING级别应该显示WARNING的说明', async () => {
    const { rerender } = render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'WARNING' } })

    rerender(
      <LoggingSettings
        currentLevel="WARNING"
        onLevelChange={mockOnLevelChange}
      />
    )

    await waitFor(() => {
      expect(screen.getByText(/只输出警告和错误信息/)).toBeInTheDocument()
    })
  })

  it('切换到ERROR级别应该显示ERROR的说明', async () => {
    const { rerender } = render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'ERROR' } })

    rerender(
      <LoggingSettings
        currentLevel="ERROR"
        onLevelChange={mockOnLevelChange}
      />
    )

    await waitFor(() => {
      expect(screen.getByText(/只输出错误信息/)).toBeInTheDocument()
    })
  })

  it('应该显示日志文件位置说明', () => {
    render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    expect(screen.getByText('日志文件位置')).toBeInTheDocument()
    expect(screen.getByText(/logs/)).toBeInTheDocument()
    expect(screen.getByText(/comfyui-box_YYYYMMDD.log/)).toBeInTheDocument()
    expect(screen.getByText(/30天前的日志文件/)).toBeInTheDocument()
  })

  it('应该显示日志级别说明', () => {
    render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    expect(screen.getByText('日志级别说明')).toBeInTheDocument()
    expect(screen.getByText(/DEBUG：/)).toBeInTheDocument()
    expect(screen.getByText(/INFO：/)).toBeInTheDocument()
    expect(screen.getByText(/WARNING：/)).toBeInTheDocument()
    expect(screen.getByText(/ERROR：/)).toBeInTheDocument()
  })

  it('外部更新currentLevel时应该同步更新组件状态', () => {
    const { rerender } = render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    const select = screen.getByRole('combobox')
    expect(select).toHaveValue('INFO')

    // 外部更新 currentLevel
    rerender(
      <LoggingSettings
        currentLevel="DEBUG"
        onLevelChange={mockOnLevelChange}
      />
    )

    expect(select).toHaveValue('DEBUG')
  })

  it('多次切换日志级别应该正确工作', async () => {
    const { rerender } = render(
      <LoggingSettings
        currentLevel="INFO"
        onLevelChange={mockOnLevelChange}
      />
    )

    const select = screen.getByRole('combobox')

    // 切换到 DEBUG
    fireEvent.change(select, { target: { value: 'DEBUG' } })
    await waitFor(() => {
      expect(mockOnLevelChange).toHaveBeenCalledWith('DEBUG')
    })

    rerender(
      <LoggingSettings
        currentLevel="DEBUG"
        onLevelChange={mockOnLevelChange}
      />
    )

    // 切换到 ERROR
    fireEvent.change(select, { target: { value: 'ERROR' } })
    await waitFor(() => {
      expect(mockOnLevelChange).toHaveBeenCalledWith('ERROR')
    })

    rerender(
      <LoggingSettings
        currentLevel="ERROR"
        onLevelChange={mockOnLevelChange}
      />
    )

    // 切换回 INFO
    fireEvent.change(select, { target: { value: 'INFO' } })
    await waitFor(() => {
      expect(mockOnLevelChange).toHaveBeenCalledWith('INFO')
    })

    expect(mockOnLevelChange).toHaveBeenCalledTimes(3)
  })
})
