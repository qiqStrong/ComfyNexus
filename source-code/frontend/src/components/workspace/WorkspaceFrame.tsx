/**
 * 工作台 iframe 容器
 * 
 * 新架构说明：
 * - ComfyUI 通过自定义节点桥接插件（Comfyui-Box_Bridge）与主窗口通信
 * - 不再需要反向代理，iframe 直接加载 ComfyUI
 * - WebSocket 直接连接到 ComfyUI（已启用 CORS）
 * - 图片下载通过桥接插件发送 postMessage 到主窗口
 */

import { memo, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import type { WorkspaceFrameProps } from '@/types/workspace'
import { useToast } from '@/hooks/useToast'

// 桥接插件消息类型
interface BridgeMessage {
  type: string
  data: {
    filename?: string
    imageUrl?: string
    [key: string]: unknown
  }
}

export const WorkspaceFrame = memo(({ url }: WorkspaceFrameProps) => {
  const { t } = useTranslation()
  const containerRef = useRef<HTMLDivElement>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const { success, error } = useToast()
  
  // ========== localStorage 同步脚本注入 ==========
  // 该 useEffect 负责将 localStorage 同步脚本注入到 ComfyUI iframe 中
  // 
  // 注意：由于现在是跨域 iframe，无法直接访问 contentDocument
  // 这个脚本注入需要通过桥接插件来实现，或者使用其他方式
  // 
  // 当前方案：通过桥接插件的消息机制同步设置
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return
    
    // 监听 iframe load 事件，发送设置同步请求
    const handleLoad = () => {
      console.log('[WorkspaceFrame] ComfyUI iframe 加载完成')
      
      // 发送设置同步请求到桥接插件
      // 注意：这需要桥接插件已经加载并监听消息
      setTimeout(() => {
        const settings: Record<string, string> = {}
        
        // 收集需要同步的设置
        const syncKeys = ['Comfy.Locale']
        const syncPrefixes = ['Comfy.', 'litegraph_']
        
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i)
          if (key) {
            if (syncKeys.includes(key) || syncPrefixes.some(p => key.startsWith(p))) {
              const value = localStorage.getItem(key)
              if (value) {
                settings[key] = value
              }
            }
          }
        }
        
        // 发送设置到桥接插件
        if (iframe.contentWindow) {
          iframe.contentWindow.postMessage({
            type: 'comfyui-box:set_settings',
            data: settings
          }, '*')
          
          console.log('[WorkspaceFrame] 已发送设置同步请求')
        }
      }, 2000) // 延迟 2 秒，确保桥接插件已加载
    }
    
    iframe.addEventListener('load', handleLoad)
    
    return () => {
      iframe.removeEventListener('load', handleLoad)
    }
  }, [])
  
  // ========== 桥接插件消息监听 ==========
  // 该 useEffect 负责监听来自桥接插件的 postMessage 消息
  useEffect(() => {
    const handleMessage = async (event: MessageEvent) => {
      // 验证消息格式
      if (!event.data || typeof event.data !== 'object') {
        return
      }
      
      const message = event.data as BridgeMessage
      const { type, data } = message
      
      // 处理不同类型的消息
      switch (type) {
        // 图片保存请求
        case 'comfyui-box:save_image':
          if (data.imageUrl && data.filename) {
            await handleSaveImage(data.imageUrl, data.filename)
          }
          break
          
        // 进度更新
        case 'comfyui-box:progress':
          console.debug('[WorkspaceFrame] 进度:', data)
          break
          
        // 执行完成
        case 'comfyui-box:executed':
          console.debug('[WorkspaceFrame] 执行完成:', data)
          break
          
        // 执行开始
        case 'comfyui-box:execution_start':
          console.debug('[WorkspaceFrame] 执行开始:', data)
          break
          
        // 执行错误
        case 'comfyui-box:execution_error':
          console.error('[WorkspaceFrame] 执行错误:', data)
          break
          
        // 心跳响应
        case 'comfyui-box:pong':
          console.debug('[WorkspaceFrame] 桥接插件已连接:', data)
          break
      }
    }
    
    // 处理图片保存
    const handleSaveImage = async (imageUrl: string, filename: string) => {
      console.log('[WorkspaceFrame] 收到图片保存请求:', filename)
      
      try {
        const result = await window.pywebview.api.save_image_with_dialog(
          imageUrl,
          filename
        )
        
        if (result.success) {
          const fileName = result.saved_path?.split(/[/\\]/).pop() || '图片'
          success(`${fileName} 已保存`, '保存成功', { duration: 1000 })
          
          // 通知桥接插件保存成功
          if (iframeRef.current?.contentWindow) {
            iframeRef.current.contentWindow.postMessage({
              type: 'comfyui-box:save_image_result',
              data: { success: true, saved_path: result.saved_path }
            }, '*')
          }
        } else {
          // 用户取消时静默处理
          if (result.error_code === 'USER_CANCELLED') {
            return
          }
          
          error(result.message || t('workspace.saveFailed'), t('workspace.saveFailed'))
          
          // 通知桥接插件保存失败
          if (iframeRef.current?.contentWindow) {
            iframeRef.current.contentWindow.postMessage({
              type: 'comfyui-box:save_image_result',
              data: { success: false, error: result.message }
            }, '*')
          }
        }
      } catch (err) {
        console.error('[WorkspaceFrame] 保存图片失败:', err)
        error('调用后端 API 失败，请重试', '系统错误')
      }
    }
    
    window.addEventListener('message', handleMessage)
    
    return () => {
      window.removeEventListener('message', handleMessage)
    }
  }, [success, error, t])
  
  return (
    <div 
      ref={containerRef}
      className="relative size-full bg-background"
    >
      {/* iframe - 直接加载 ComfyUI */}
      <iframe
        ref={iframeRef}
        src={url}
        className="size-full border-none"
        title="ComfyUI Workspace"
        allow="clipboard-read; clipboard-write; downloads"
      />
    </div>
  )
})

WorkspaceFrame.displayName = 'WorkspaceFrame'
