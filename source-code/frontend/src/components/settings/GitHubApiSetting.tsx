/**
 * GitHub API 设置组件
 * 用于配置 GitHub Personal Access Token，提高 API 请求限制
 */

import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Input, Button } from '@/components/ui'
import { Switch } from '@/components/ui/Switch'
import { AlertCircle, Eye, EyeOff, ExternalLink, CheckCircle2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface GitHubApiSettingProps {
  enabled: boolean
  token: string
  onEnabledChange: (enabled: boolean) => void
  onTokenChange: (token: string) => void
  className?: string
}

export function GitHubApiSetting({
  enabled,
  token,
  onEnabledChange,
  onTokenChange,
  className
}: GitHubApiSettingProps) {
  const { t } = useTranslation()
  const [showToken, setShowToken] = useState(false)
  const [validationStatus, setValidationStatus] = useState<'none' | 'valid' | 'invalid'>('none')
  const [validationMessage, setValidationMessage] = useState('')

  useEffect(() => {
    if (token && token.length > 0) {
      if (token.startsWith('ghp_') || token.startsWith('github_pat_')) {
        setValidationStatus('valid')
        setValidationMessage('Token 格式正确')
      } else {
        setValidationStatus('invalid')
        setValidationMessage('Token 格式不正确，应以 ghp_ 或 github_pat_ 开头')
      }
    } else {
      setValidationStatus('none')
      setValidationMessage('')
    }
  }, [token])

  const handleTokenChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    onTokenChange(value)
  }

  const openGitHubTokenPage = () => {
    window.open('https://github.com/settings/tokens/new?description=Comfyui-Box&scopes=repo,read:user', '_blank')
  }

  return (
    <div className={cn('space-y-4', className)}>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium">{t("settings.enableGithubToken")}</label>
          <Switch
            checked={enabled}
            onCheckedChange={onEnabledChange}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          启用后可提高 GitHub API 请求限制（从 60次/小时 提升到 5000次/小时）
        </p>
      </div>

      {enabled && (
        <>
          <div className="space-y-2">
            <label className="text-sm font-medium">Personal Access Token</label>
            <div className="relative">
              <Input
                type={showToken ? 'text' : 'password'}
                value={token}
                onChange={handleTokenChange}
                placeholder={t("common.placeholder.githubToken")}
                className={cn(
                  'pr-10',
                  validationStatus === 'valid' && 'border-success focus:ring-success',
                  validationStatus === 'invalid' && 'border-danger focus:ring-danger'
                )}
              />
              <Button
                type="button"
                onClick={() => setShowToken(!showToken)}
                variant="ghost"
                size="icon"
                className="absolute right-2 top-1/2 -translate-y-1/2"
              >
                {showToken ? (
                  <EyeOff className="size-4" />
                ) : (
                  <Eye className="size-4" />
                )}
              </Button>
            </div>
            
            {validationStatus === 'valid' && (
              <div className="flex items-center gap-1 text-success">
                <CheckCircle2 className="size-3" />
                <span className="text-xs">{validationMessage}</span>
              </div>
            )}
            
            {validationStatus === 'invalid' && (
              <div className="flex items-center gap-1 text-danger">
                <AlertCircle className="size-3" />
                <span className="text-xs">{validationMessage}</span>
              </div>
            )}
          </div>

          <div className="rounded-md border border-primary/30 bg-primary/10 p-3">
            <div className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-primary" />
              <div className="space-y-2">
                <p className="text-sm text-primary">
                  如何获取 GitHub Personal Access Token：
                </p>
                <ol className="list-inside list-decimal space-y-1 text-xs text-primary">
                  <li>{t("settings.clickToCreateToken")}</li>
                  <li>{t("settings.fillTokenDesc")}</li>
                  <li>{t("settings.selectPermissions")}</li>
                  <li>{t('settings.generateAndCopyToken')}</li>
                </ol>
                <Button
                  type="button"
                  onClick={openGitHubTokenPage}
                  variant="link"
                  className="items-center gap-1 p-0 text-xs"
                >
                  <ExternalLink className="size-3" />
                  {t('settings.openGithubTokenPage')}
                </Button>
              </div>
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            Token 仅存储在本地配置文件中，不会上传到任何服务器。
          </p>
        </>
      )}
    </div>
  )
}
