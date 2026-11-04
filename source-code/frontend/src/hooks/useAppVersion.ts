import { useState, useEffect } from 'react'
import { bridgeService } from '@/services/bridge'

const DEFAULT_VERSION = 'V1.0.0'

function formatVersion(rawVersion: string): string {
  console.log('[formatVersion] rawVersion:', rawVersion)
  // 版本号已统一为大写 V 形态，直接展示原值，避免再拼一层 v 出现 vV1.0.0
  const trimmed = rawVersion.trim()
  return trimmed || DEFAULT_VERSION
}

export function useAppVersion(options?: { enabled?: boolean }) {
  const enabled = options?.enabled !== false
  const [rawVersion, setRawVersion] = useState<string>('')
  const [version, setVersion] = useState<string>(DEFAULT_VERSION)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  
  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    
    const fetchVersion = async () => {
      try {
        setLoading(true)
        console.log('[useAppVersion] 开始获取版本号...')
        const raw = await bridgeService.getAppVersion()
        console.log('[useAppVersion] 原始版本号:', raw)
        console.log('[useAppVersion] typeof raw:', typeof raw)
        setRawVersion(raw)
        const formatted = formatVersion(raw)
        console.log('[useAppVersion] 格式化版本号:', formatted)
        setVersion(formatted)
        setError(null)
      } catch (err) {
        console.error('[useAppVersion] 获取版本失败:', err)
        setError(err instanceof Error ? err : new Error('Unknown error'))
        setVersion(DEFAULT_VERSION)
      } finally {
        setLoading(false)
      }
    }
    
    fetchVersion()
  }, [enabled])
  return { version, rawVersion, loading, error }
}

export default useAppVersion
