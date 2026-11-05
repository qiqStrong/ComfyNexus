/**
 * 首次启动数据目录选择对话框
 *
 * 默认使用机器级用户数据根（%LOCALAPPDATA%\\Comfyui-Box\\userdata），
 * 允许选择其他目录；检测到旧布局数据时提示一键迁移（旧目录只读、保留）。
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Database, FolderOpen, HardDrive } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Button,
  Progress,
} from '@/components/ui'
import type { UserDataMigrationStatus, UserDataStatus } from '@/types/bridge'
import { toast } from '@/utils/toast'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export function DataDirSetupDialog() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<UserDataStatus | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<UserDataMigrationStatus | null>(null)

  const refresh = async (): Promise<UserDataStatus | null> => {
    if (!window.pywebview?.api) return null
    const data = await window.pywebview.api.userdata_get_status()
    setStatus(data)
    if (data.initialized) {
      setOpen(false)
    } else {
      setOpen(true)
    }
    return data
  }

  useEffect(() => {
    let cancelled = false
    const boot = async () => {
      // WebView 的 pywebview 注入可能稍晚于 React 挂载
      for (let attempt = 0; attempt < 10; attempt += 1) {
        if (window.pywebview?.api) break
        await sleep(300)
        if (cancelled) return
      }
      if (cancelled) return
      try {
        await refresh()
      } catch (error) {
        console.error('[首启数据目录] 读取状态失败:', error)
      }
    }
    boot()
    return () => {
      cancelled = true
    }
  }, [])

  const restart = async () => {
    await window.pywebview?.api.userdata_restart_app()
  }

  const handleInitialize = async (root?: string) => {
    if (!window.pywebview?.api) return
    setBusy(true)
    try {
      const result = await window.pywebview.api.userdata_initialize(root ?? null)
      if (!result.success) {
        toast.error(result.error || t('dataSetup.error'))
        return
      }
      setStatus(result)
      setOpen(false)
      if (result.restart_required) {
        toast.success(t('dataSetup.restarting'))
        await restart()
      }
    } catch (error) {
      console.error('[首启数据目录] 初始化失败:', error)
      toast.error(t('dataSetup.error'))
    } finally {
      setBusy(false)
    }
  }

  const handleChoose = async () => {
    if (!window.pywebview?.api) return
    const response = await window.pywebview.api.browse_folder_for_shortcut()
    if (response.success && response.path) {
      await handleInitialize(response.path)
    } else if (response.error_message) {
      toast.error(response.error_message)
    }
  }

  const handleMigrate = async () => {
    const legacy = status?.legacy_sources?.[0]
    if (!legacy || !window.pywebview?.api) return
    setBusy(true)
    try {
      const start = await window.pywebview.api.userdata_start_migration(legacy.root)
      if (!start.success) {
        toast.error(start.error || t('dataSetup.error'))
        return
      }
      let state: UserDataMigrationStatus | null = null
      while (true) {
        await sleep(600)
        state = await window.pywebview.api.userdata_migration_status()
        setProgress(state)
        if (!state.running) break
      }
      if (!state?.result?.success) {
        toast.error(state?.result?.error || t('dataSetup.error'))
        return
      }
      const initialized = await window.pywebview.api.userdata_initialize(null)
      if (!initialized.success) {
        toast.error(initialized.error || t('dataSetup.error'))
        return
      }
      toast.success(t('dataSetup.migrated'))
      await restart()
    } catch (error) {
      console.error('[首启数据目录] 迁移失败:', error)
      toast.error(t('dataSetup.error'))
    } finally {
      setBusy(false)
    }
  }

  const legacy = status?.legacy_sources?.[0]
  const percent = progress && progress.total > 0
    ? Math.min(100, Math.round((progress.done / progress.total) * 100))
    : 0

  return (
    <Dialog open={open} onOpenChange={() => undefined}>
      <DialogContent className="max-w-xl" onPointerDownOutside={(event) => event.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <HardDrive className="size-5" />
            {t('dataSetup.title')}
          </DialogTitle>
          <DialogDescription>{t('dataSetup.desc')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          <div className="space-y-1 rounded-md border border-border p-3">
            <div className="text-xs text-muted-foreground">{t('dataSetup.currentDir')}</div>
            <div className="break-all font-mono text-xs">{status?.root || '...'}</div>
            {status?.pointer_invalid && (
              <div className="text-xs text-amber-600">
                {t('dataSetup.pointerInvalid', { path: status.pointer_target || '' })}
              </div>
            )}
          </div>

          {legacy && (
            <div className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
              <div className="flex items-center gap-2 font-medium">
                <Database className="size-4" />
                {t('dataSetup.legacyFound')}
              </div>
              <div className="break-all font-mono text-xs">{legacy.root}</div>
              <div className="text-xs text-muted-foreground">
                {t('dataSetup.legacyDetail', {
                  assets: legacy.counts.assets,
                  categories: legacy.counts.categories,
                  promptImages: legacy.counts.prompt_images,
                  workflows: legacy.counts.workflows_files,
                })}
              </div>
              <Button size="sm" onClick={handleMigrate} disabled={busy}>
                {t('dataSetup.migrateOld')}
              </Button>
            </div>
          )}

          {(busy || progress) && progress && (
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{progress.current}</span>
                <span>{progress.done}/{progress.total} ({percent}%)</span>
              </div>
              <Progress value={percent} max={100} />
            </div>
          )}
        </div>

        <DialogFooter className="flex-wrap gap-2">
          <Button variant="outline" onClick={handleChoose} disabled={busy}>
            <FolderOpen className="mr-1 size-4" />
            {t('dataSetup.chooseOther')}
          </Button>
          <Button onClick={() => handleInitialize()} disabled={busy}>
            {t('dataSetup.useThis')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
