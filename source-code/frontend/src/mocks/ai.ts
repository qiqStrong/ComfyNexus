/**
 * AI助手 Mock 数据
 */

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export const mockChatHistory: ChatMessage[] = [
  {
    id: '1',
    role: 'assistant',
    content: '你好！我是 Comfyui-Box AI 助手。我可以帮助你分析日志、工作流和插件代码。有什么我可以帮助你的吗？',
    timestamp: '2024-01-21T10:00:00Z'
  },
  {
    id: '2',
    role: 'user',
    content: '我的 ComfyUI 启动失败了，能帮我看看日志吗？',
    timestamp: '2024-01-21T10:01:00Z'
  },
  {
    id: '3',
    role: 'assistant',
    content: '当然可以。根据日志分析，启动失败的原因是缺少必要的依赖包。建议你执行以下命令安装缺失的依赖：\n\n```bash\npip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118\n```\n\n安装完成后重新启动 ComfyUI 即可。',
    timestamp: '2024-01-21T10:01:30Z'
  }
]
