/**
 * 数据目录设置组件
 *
 * 用户级数据（资产/提示词/工作流元数据/对话/密钥/配置/备份）保存在机器级
 * 用户数据根，可迁移、可清理；系统级产物随安装目录存在。
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Database, FolderOpen, HardDrive, RefreshCw, RotateCw, ShieldAlert, Trash2 } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent, Button, Progress } from '@/components/ui'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import type { UserDataMigrationStatus, UserDataStatus } from '@/types/bridge'
import { toast } from '@/utils/toast'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export function DataStorageSettings() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<UserDataStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [migrating, setMigrating] = useState(false)
  const [progress, setProgress] = useState<UserDataMigrationStatus | null>(null)
  const [pendingPath, setPendingPath] = useState<string | null>(null)
  const [showChangeDialog, setShowChangeDialog] = useState(false)
  const [showWipeDialog, setShowWipeDialog] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      if (!window.pywebview?.api) return
      const data = await window.pywebview.api.userdata_get_status()
      setStatus(data)
    } catch (error) {
      console.error('[数据目录] 加载状态失败:', error)
      toast.error(t('settings.storage.loadError'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const sourceLabel = (source: string) => {
    switch (source) {
      case 'env':
        return t('settings.storage.sourceEnv')
      case 'pointer':
        return t('settings.storage.sourcePointer')
      case 'default':
        return t('settings.storage.sourceDefault')
      default:
        return t('settings.storage.sourceFallback')
    }
  }

  const runMigration = async (sourceRoot: string, targetRoot?: string) => {
    if (!window.pywebview?.api) return null
    setMigrating(true)
    setResult(null)
    try {
      const start = await window.pywebview.api.userdata_start_migration(sourceRoot, targetRoot)
      if (!start.success) {
        toast.error(start.error || t('settings.storage.migrateFailed'))
        return null
      }
      let state: UserDataMigrationStatus | null = null
      while (true) {
        await sleep(600)
        state = await window.pywebview.api.userdata_migration_status()
        setProgress(state)
        if (!state.running) break
      }
      if (state?.result?.success) {
        const kv = state.result.key_verification
        const keyText = kv && kv.encrypted_keys > 0
          ? t('settings.storage.keyVerified', { decrypted: kv.decrypted, total: kv.encrypted_keys })
          : t('settings.storage.keySkipped')
        setResult(t('settings.storage.migrateSummary', {
          files: state.result.copied_files ?? 0,
          key: keyText,
        }))
        toast.success(t('settings.storage.migrateDone'))
      } else {
        toast.error(state?.result?.error || t('settings.storage.migrateFailed'))
      }
      await load()
      // 迁移会改动正在使用的数据文件，必须重启后生效
      setStatus((prev) => (prev ? { ...prev, restart_required: true } : prev))
      return state?.result ?? null
    } catch (error) {
      console.error('[数据目录] 迁移失败:', error)
      toast.error(t('settings.storage.migrateFailed'))
      return null
    } finally {
      setMigrating(false)
    }
  }

  const handleChangeDir = async () => {
    if (!window.pywebview?.api) return
    try {
      const response = await window.pywebview.api.browse_folder_for_shortcut()
      if (response.success && response.path) {
        setPendingPath(response.path)
        setShowChangeDialog(true)
      } else if (response.error_message) {
        toast.error(response.error_message)
      }
    } catch (error) {
      console.error('[数据目录] 选择目录失败:', error)
      toast.error(t('settings.storage.chooseFailed'))
    }
  }

  const confirmChangeDir = async (withData: boolean) => {
    if (!window.pywebview?.api || !pendingPath || !status) return
    setShowChangeDialog(false)
    if (withData) {
      const migration = await runMigration(status.root, pendingPath)
      if (!migration?.success) return
    }
    const changed = await window.pywebview.api.userdata_set_root(pendingPath, false)
    if (!changed.success) {
      toast.error(changed.error || t('settings.storage.changeFailed'))
      return
    }
    setPendingPath(null)
    toast.success(t('settings.storage.restarting'))
    await window.pywebview.api.userdata_restart_app()
  }

  const confirmWipe = async () => {
    setShowWipeDialog(false)
    if (!window.pywebview?.api) return
    const response = await window.pywebview.api.userdata_wipe_business()
    if (!response.success) {
      toast.error(response.error || t('settings.storage.wipeFailed'))
      return
    }
    toast.success(t('settings.storage.wipeQueued'))
    await window.pywebview.api.userdata_restart_app()
  }

  const handleCleanCache = async () => {
    if (!window.pywebview?.api) return
    const response = await window.pywebview.api.userdata_clean_cache(['cache', 'logs'])
    if (!response.success) {
      toast.error(t('settings.storage.cleanFailed'))
      return
    }
    const deleted = Object.values(response.deleted || {}).reduce((a, b) => a + b, 0)
    toast.success(t('settings.storage.cleanDone', { count: deleted }))
    await load()
  }

  const handleOpenFolder = async (path?: string) => {
    if (!window.pywebview?.api) return
    await window.pywebview.api.userdata_open_folder(path)
  }

  const counts = status?.counts
  const legacy = status?.legacy_sources?.[0]
  const percent = progress && progress.total > 0
    ? Math.min(100, Math.round((progress.done / progress.total) * 100))
    : 0

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">{t('settings.storage.title')}</h2>
        <p className="text-sm text-muted-foreground">{t('settings.storage.description')}</p>
      </div>

      {status?.restart_required && (
        <div className="flex items-center justify-between rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
          <span>{t('settings.storage.restartHint')}</span>
          <Button size="sm" onClick={() => window.pywebview?.api.userdata_restart_app()}>
            <RotateCw className="mr-1 size-4" />
            {t('settings.storage.restart')}
          </Button>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="size-4" />
            {t('settings.storage.locationTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <div className="break-all font-mono text-sm">{status?.root || t('common.loading')}</div>
              <div className="text-xs text-muted-foreground">
                {t('settings.storage.source')}: {sourceLabel(status?.source || '')}
                {status?.pointer_target ? ` · ${t('settings.storage.pointer')}: ${status.pointer_target}` : ''}
              </div>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button variant="outline" size="sm" onClick={() => handleOpenFolder()} disabled={loading}>
                <FolderOpen className="mr-1 size-4" />
                {t('settings.storage.openFolder')}
              </Button>
              <Button variant="outline" size="sm" onClick={load} disabled={loading || migrating}>
                <RefreshCw className="mr-1 size-4" />
                {t('settings.storage.refresh')}
              </Button>
              <Button size="sm" onClick={handleChangeDir} disabled={loading || migrating}>
                {t('settings.storage.changeDir')}
              </Button>
            </div>
          </div>

          {counts && (
            <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-3 lg:grid-cols-6">
              {[
                ['assets', counts.assets],
                ['categories', counts.categories],
                ['thumbnails', counts.thumbnails],
                ['promptImages', counts.prompt_images],
                ['workflows', counts.workflows_files],
                ['conversations', Math.max(0, counts.db_topics)],
              ].map(([key, value]) => (
                <div key={String(key)} className="rounded-md border border-border px-3 py-2">
                  <div className="text-xs text-muted-foreground">{t(`settings.storage.counts.${key}`)}</div>
                  <div className="font-semibold">{String(value)}</div>
                </div>
              ))}
            </div>
          )}

          {(migrating || progress) && (
            <div className="space-y-2 rounded-md border border-border p-3">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{t('settings.storage.migrating')} · {progress?.current || ''}</span>
                <span>{progress?.done ?? 0}/{progress?.total ?? 0} ({percent}%)</span>
              </div>
              <Progress value={percent} max={100} />
            </div>
          )}

          {result && (
            <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm">{result}</div>
          )}
        </CardContent>
      </Card>

      {legacy && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="size-4" />
              {t('settings.storage.legacyTitle')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">{t('settings.storage.legacyDesc')}</p>
            <div className="space-y-1 text-sm">
              <div className="break-all font-mono">{legacy.root}</div>
              <div className="text-xs text-muted-foreground">
                {t('settings.storage.legacyCounts', {
                  assets: legacy.counts.assets,
                  categories: legacy.counts.categories,
                  promptImages: legacy.counts.prompt_images,
                  workflows: legacy.counts.workflows_files,
                })}
              </div>
            </div>
            <Button size="sm" onClick={() => runMigration(legacy.root)} disabled={migrating}>
              {t('settings.storage.legacyMigrate')}
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Trash2 className="size-4" />
              {t('settings.storage.cacheTitle')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">{t('settings.storage.cacheDesc')}</p>
            <Button variant="outline" size="sm" onClick={handleCleanCache} disabled={loading || migrating}>
              {t('settings.storage.cleanCache')}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <ShieldAlert className="size-4" />
              {t('settings.storage.wipeTitle')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">{t('settings.storage.wipeDesc')}</p>
            <Button variant="destructive" size="sm" onClick={() => setShowWipeDialog(true)} disabled={loading || migrating}>
              {t('settings.storage.wipeButton')}
            </Button>
          </CardContent>
        </Card>
      </div>

      <AlertDialog open={showChangeDialog} onOpenChange={setShowChangeDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.storage.changeTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.storage.changeDesc', { path: pendingPath || '' })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => confirmChangeDir(false)}>
              {t('settings.storage.changeOnly')}
            </AlertDialogAction>
            <AlertDialogAction onClick={() => confirmChangeDir(true)}>
              {t('settings.storage.changeMigrate')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showWipeDialog} onOpenChange={setShowWipeDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.storage.wipeTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('settings.storage.wipeConfirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction className="bg-destructive text-destructive-foreground" onClick={confirmWipe}>
              {t('settings.storage.wipeConfirmButton')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
