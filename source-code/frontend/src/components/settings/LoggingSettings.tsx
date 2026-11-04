/**
 * 日志设置组件
 * 
 * 提供日志级别选择和配置功能
 */

import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { FileText, Info } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui'
import { LogLevel, configureLogger } from '@/utils/logger'

/**
 * 日志级别选项
 */
const LOG_LEVELS = [
  {
    value: 'DEBUG',
    label: 'DEBUG（调试）',
    description: '输出所有日志信息，包括详细的调试信息。适用于开发和问题排查。'
  },
  {
    value: 'INFO',
    label: 'INFO（信息）',
    description: '输出重要的业务操作信息。这是推荐的默认级别。'
  },
  {
    value: 'DEV',
    label: 'DEV（开发）',
    description: '只输出开发调试信息、警告和错误。适用于开发时临时调试，过滤 DEBUG 和 INFO 日志。'
  },
  {
    value: 'WARNING',
    label: 'WARNING（警告）',
    description: '只输出警告和错误信息。适用于生产环境。'
  },
  {
    value: 'ERROR',
    label: 'ERROR（错误）',
    description: '只输出错误信息。适用于只关注错误的场景。'
  }
]

interface LoggingSettingsProps {
  /** 当前日志级别 */
  currentLevel: string
  /** 日志级别变更回调 */
  onLevelChange: (level: string) => void
}

export function LoggingSettings({
  currentLevel, onLevelChange }: LoggingSettingsProps) {
  const { t } = useTranslation()
  const [selectedLevel, setSelectedLevel] = useState(currentLevel)
  const [selectedLevelInfo, setSelectedLevelInfo] = useState(
    LOG_LEVELS.find(l => l.value === currentLevel)
  )

  // 当外部传入的 currentLevel 变化时，同步更新本地状态
  useEffect(() => {
    setSelectedLevel(currentLevel)
    setSelectedLevelInfo(LOG_LEVELS.find(l => l.value === currentLevel))
  }, [currentLevel])

  const handleLevelChange = (newLevel: string) => {
    setSelectedLevel(newLevel)
    setSelectedLevelInfo(LOG_LEVELS.find(l => l.value === newLevel))
    onLevelChange(newLevel)

    // 同步更新前端日志系统
    const levelMap: Record<string, LogLevel> = {
      'DEBUG': LogLevel.DEBUG,
      'INFO': LogLevel.INFO,
      'DEV': LogLevel.DEV,
      'WARNING': LogLevel.WARN,
      'ERROR': LogLevel.ERROR
    }
    configureLogger({ level: levelMap[newLevel] || LogLevel.INFO })
  }

  return (
    <div className="space-y-4">
      {/* 日志级别选择 */}
      <div className="space-y-2">
        <label className="flex items-center gap-2 text-sm font-medium">
          <FileText className="size-4" />
          日志级别
        </label>
        <Select
          value={selectedLevel}
          onValueChange={(value) => handleLevelChange(value)}
        >
          <SelectTrigger>
            <SelectValue placeholder={t("common.placeholder.selectLogLevel")} />
          </SelectTrigger>
          <SelectContent>
            {LOG_LEVELS.map((level) => (
              <SelectItem key={level.value} value={level.value}>
                {level.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* 当前级别说明 */}
      {selectedLevelInfo && (
        <div className="flex gap-3 rounded-lg border border-primary/20 bg-primary/5 p-3">
          <Info className="mt-0.5 size-5 shrink-0 text-primary" />
          <div className="text-sm text-foreground">
            <div className="mb-1 font-medium">{selectedLevelInfo.label}</div>
            <div className="text-muted-foreground">
              {selectedLevelInfo.description}
            </div>
          </div>
        </div>
      )}

      {/* 日志文件说明 */}
      <div className="border-t border-border pt-4">
        <div className="space-y-2 text-sm">
          <div className="font-medium">{t("settings.logFileLocation")}</div>
          <div className="text-muted-foreground">
            <p>{t("settings.logFileSavedIn")} <code className="rounded bg-muted px-1 py-0.5">logs</code> {t('settings.folder')}</p>
            <p className="mt-1">{t("settings.fileNameFormat")}:<code className="rounded bg-muted px-1 py-0.5">comfyui-box_YYYYMMDD.log</code></p>
            <p className="mt-1">{t("settings.autoCleanLogs")}</p>
          </div>
        </div>
      </div>

      {/* 日志级别说明 */}
      <div className="border-t border-border pt-4">
        <div className="space-y-2 text-sm">
          <div className="font-medium">{t("settings.logLevelDesc")}</div>
          <div className="space-y-1 text-muted-foreground">
            <p><strong>DEBUG：</strong>{t('settings.logLevelDebug')}</p>
            <p><strong>INFO：</strong>{t('settings.logLevelInfo')}</p>
            <p><strong>DEV：</strong>开发调试级别，只显示 DEV、WARNING 和 ERROR 日志，适用于开发时临时调试。</p>
            <p><strong>WARNING：</strong>{t('settings.logLevelWarning')}</p>
            <p><strong>ERROR：</strong>{t('settings.logLevelError')}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
