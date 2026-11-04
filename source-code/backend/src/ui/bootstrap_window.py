"""
引导窗口模块

提供 Git 配置引导界面，用于首次启动时配置 Git。
"""

import sys
import os
import threading

# 必须在 import webview 之前初始化 .NET 8 coreclr 运行时
if sys.platform == "win32":
    from backend.src.utils.dotnet_runtime import init_dotnet
    init_dotnet()

import webview
from pathlib import Path
from typing import Optional, Callable

from backend.src.utils.git_manager import GitManager, GitMode, GitStatus
from backend.src.utils.mingit_downloader import MinGitDownloader, DownloadStatus
from backend.src.utils.paths import get_mingit_dir
from backend.src.utils.logger import get_logger
from .bootstrap_api import BootstrapAPI


def get_bootstrap_html() -> str:
    """获取引导窗口 HTML"""
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comfyui-Box - Git 配置</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body { overflow: hidden; height: 100%; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e4e4e7;
            
            /* 卡片样式 - 直角 */
            background: rgba(30, 30, 46, 0.95);
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.1);
            
            position: relative;
            width: 100%;
            height: 100%;
            
            /* 内容布局 */
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 32px;
        }
        .close-btn {
            position: absolute;
            top: 12px;
            right: 12px;
            width: 28px;
            height: 28px;
            background: rgba(255, 255, 255, 0.1);
            border: none;
            border-radius: 6px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
            z-index: 10;
        }
        .close-btn:hover {
            background: rgba(239, 68, 68, 0.8);
        }
        .close-btn svg {
            width: 16px;
            height: 16px;
            color: white;
        }
        .header { text-align: center; margin-bottom: 32px; }
        .logo {
            width: 64px; height: 64px;
            margin: 0 auto 16px;
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            border-radius: 16px;
            display: flex; align-items: center; justify-content: center;
            box-shadow: 0 8px 16px rgba(99, 102, 241, 0.3);
        }
        .logo svg {
            width: 36px;
            height: 36px;
            color: white;
        }
        .title {
            font-size: 24px; font-weight: 600; margin-bottom: 8px;
            background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .subtitle { font-size: 14px; color: #71717a; margin-bottom: 8px; }
        .status-message {
            font-size: 14px; color: #a1a1aa; text-align: center;
            padding: 12px; background: rgba(255, 255, 255, 0.05);
            border-radius: 8px; margin-bottom: 24px;
        }
        .status-message.success { color: #4ade80; background: rgba(74, 222, 128, 0.1); }
        .options { display: flex; flex-direction: column; gap: 12px; margin-bottom: 24px; }
        .option-btn {
            display: flex; align-items: center; gap: 16px;
            padding: 16px; background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px; cursor: pointer;
            transition: all 0.2s ease; text-align: left;
            color: inherit; width: 100%;
        }
        .option-btn:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(99, 102, 241, 0.5);
            transform: translateY(-2px);
        }
        .option-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .option-icon { font-size: 24px; width: 40px; text-align: center; }
        .option-content { flex: 1; }
        .option-title { font-size: 15px; font-weight: 500; margin-bottom: 4px; }
        .option-desc { font-size: 12px; color: #71717a; }
        .option-badge {
            font-size: 10px; padding: 2px 8px;
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            border-radius: 4px; color: white;
        }
        .progress-section { display: none; margin-bottom: 24px; }
        .progress-section.active { display: block; }
        .progress-bar {
            height: 8px; background: rgba(255, 255, 255, 0.1);
            border-radius: 4px; overflow: hidden; margin-bottom: 8px;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%);
            border-radius: 4px; transition: width 0.3s ease;
            width: 0%;
        }
        .progress-text { font-size: 12px; color: #71717a; text-align: center; }
        .error-message {
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(239, 68, 68, 0.95);
            border-radius: 8px;
            padding: 12px 20px;
            font-size: 13px;
            color: white;
            display: none;
            z-index: 100;
            max-width: 90%;
            text-align: center;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        }
        .error-message.active { display: block; }
        .buttons { display: flex; gap: 12px; }
        .btn {
            flex: 1; padding: 12px 24px;
            border: none; border-radius: 8px;
            font-size: 14px; font-weight: 500;
            cursor: pointer; transition: all 0.2s ease;
        }
        .btn-primary {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            color: white;
        }
        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
        }
        .btn-primary:disabled {
            opacity: 0.5; cursor: not-allowed;
            transform: none; box-shadow: none;
        }
        .btn-secondary {
            background: rgba(255, 255, 255, 0.1);
            color: #a1a1aa;
        }
        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.15);
            color: #e4e4e7;
        }
        .hidden { display: none !important; }
        
        /* 标题栏主容器 */
        .title-bar {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 48px;
            
            display: flex;
            justify-content: space-between;
            align-items: center;
            
            padding: 0 16px;
            box-sizing: border-box;
            z-index: 1000;
            
            -webkit-app-region: drag;
            user-select: none;
        }
        
        /* 标题文本样式 */
        .title-text {
            font-size: 14px;
            font-weight: 500;
            color: #e4e4e7;
        }
        
        /* 按钮控制区：必须防劫持 */
        .window-controls {
            -webkit-app-region: no-drag !important;
            display: flex;
            align-items: center;
        }
        
        /* 关闭按钮基础样式 */
        #close-btn {
            background: transparent;
            border: none;
            color: #a1a1aa;
            width: 32px;
            height: 32px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
        }
        
        /* 关闭按钮的悬浮效果 */
        #close-btn:hover {
            background-color: rgba(255, 60, 60, 0.8);
            color: white;
        }
        
        /* 四角手柄基础样式与防劫持 */
        .resize-handle {
            position: absolute;
            width: 15px;
            height: 15px;
            z-index: 9999;
            -webkit-app-region: no-drag !important;
        }
        
        /* 定位与鼠标样式 */
        .resize-handle.nw { top: 0; left: 0; cursor: nwse-resize; }
        .resize-handle.ne { top: 0; right: 0; cursor: nesw-resize; }
        .resize-handle.sw { bottom: 0; left: 0; cursor: nesw-resize; }
        .resize-handle.se { bottom: 0; right: 0; cursor: nwse-resize; }
        
        /* body 内容下移，避免被标题栏遮挡 */
        body {
            padding-top: 48px;
        }
    </style>
</head>
<body>
    <div class="title-bar pywebview-drag-region">
        <div class="title-text">Comfyui-Box 配置引导</div>
        <div class="window-controls">
            <button id="close-btn">✕</button>
        </div>
    </div>
    
    <div class="resize-handle nw"></div>
    <div class="resize-handle ne"></div>
    <div class="resize-handle sw"></div>
    <div class="resize-handle se"></div>
    
    <div class="header">
            <div class="logo">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="6" y1="3" x2="6" y2="15"></line>
                    <circle cx="18" cy="6" r="3"></circle>
                    <circle cx="6" cy="18" r="3"></circle>
                    <path d="M18 9a9 9 0 0 1-9 9"></path>
                </svg>
            </div>
            <h1 class="title">Git 配置</h1>
            <p class="subtitle">Comfyui-Box 需要 Git 来管理插件</p>
        </div>
        
        <div class="status-message" id="statusMessage">检测中...</div>
        
        <div class="error-message" id="errorMessage"></div>
        
        <div class="options" id="optionsContainer">
            <button class="option-btn" id="btnDownload" onclick="startDownload()">
                <div class="option-icon">📥</div>
                <div class="option-content">
                    <div class="option-title">自动下载 MinGit <span class="option-badge">推荐</span></div>
                    <div class="option-desc">下载内置 Git 工具（约 70MB），无需额外安装</div>
                </div>
            </button>
            
            <button class="option-btn" id="btnSelectFile" onclick="selectGitExe()">
                <div class="option-icon">📁</div>
                <div class="option-content">
                    <div class="option-title">手动指定 Git</div>
                    <div class="option-desc">选择已安装的 git.exe 文件路径</div>
                </div>
            </button>
            
            <button class="option-btn hidden" id="btnSystemGit" onclick="useSystemGit()">
                <div class="option-icon">💻</div>
                <div class="option-content">
                    <div class="option-title">使用系统 Git</div>
                    <div class="option-desc" id="systemGitDesc">检测到系统已安装 Git</div>
                </div>
            </button>
        </div>
        
        <div class="progress-section" id="progressSection">
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            <div class="progress-text" id="progressText">准备下载...</div>
        </div>
        
        <div class="buttons">
            <button class="btn btn-secondary" id="btnCancel" onclick="cancelOperation()">取消</button>
            <button class="btn btn-primary hidden" id="btnContinue" onclick="continueStartup()">继续</button>
        </div>
    
    <script>
        let isCompleted = false;
        let hasSystemGit = false;
        
        async function init() {
            const status = await pywebview.api.check_git_status();
            updateStatus(status);
            
            if (status.has_system_git) {
                hasSystemGit = true;
                document.getElementById('btnSystemGit').classList.remove('hidden');
                document.getElementById('systemGitDesc').textContent = 
                    '检测到系统 Git: ' + status.system_git_version;
            }
            
            document.getElementById('btnSystemGit').addEventListener('click', useSystemGit);
            document.getElementById('btnCancel').addEventListener('click', cancelOperation);
            document.getElementById('close-btn').addEventListener('click', closeWindow);
            
            setupResizeHandles();
        }
        
        function closeWindow() {
            pywebview.api.close_window();
        }
        
        function setupResizeHandles() {
            const handles = document.querySelectorAll('.resize-handle');
            let isResizing = false;
            let isUpdating = false;
            let startMouseX, startMouseY;
            let startWinX, startWinY, startWidth, startHeight;
            let currentHandleType = '';

            handles.forEach(handle => {
                handle.addEventListener('mousedown', async (e) => {
                    if (!pywebview.api || !pywebview.api.get_window) return;
                    
                    isResizing = true;
                    
                    if (handle.classList.contains('nw')) currentHandleType = 'nw';
                    if (handle.classList.contains('ne')) currentHandleType = 'ne';
                    if (handle.classList.contains('sw')) currentHandleType = 'sw';
                    if (handle.classList.contains('se')) currentHandleType = 'se';

                    startMouseX = e.screenX / (window.devicePixelRatio || 1);
                    startMouseY = e.screenY / (window.devicePixelRatio || 1);
                    
                    const win = await pywebview.api.get_window();
                    startWinX = win.x;
                    startWinY = win.y;
                    startWidth = win.width;
                    startHeight = win.height;
                    
                    e.preventDefault();
                    e.stopPropagation();
                });
            });

            document.addEventListener('mousemove', (e) => {
                if (!isResizing || isUpdating) return;

                const dx = (e.screenX / (window.devicePixelRatio || 1)) - startMouseX;
                const dy = (e.screenY / (window.devicePixelRatio || 1)) - startMouseY;

                let newX = startWinX;
                let newY = startWinY;
                let newW = startWidth;
                let newH = startHeight;

                if (currentHandleType === 'se') {
                    newW = startWidth + dx;
                    newH = startHeight + dy;
                } else if (currentHandleType === 'sw') {
                    newX = startWinX + dx;
                    newW = startWidth - dx;
                    newH = startHeight + dy;
                } else if (currentHandleType === 'ne') {
                    newY = startWinY + dy;
                    newW = startWidth + dx;
                    newH = startHeight - dy;
                } else if (currentHandleType === 'nw') {
                    newX = startWinX + dx;
                    newY = startWinY + dy;
                    newW = startWidth - dx;
                    newH = startHeight - dy;
                }

                const MIN_WIDTH = 400;
                const MIN_HEIGHT = 500;

                if (newW < MIN_WIDTH) {
                    newW = MIN_WIDTH;
                    if (currentHandleType.includes('w')) {
                        newX = startWinX + (startWidth - MIN_WIDTH);
                    }
                }
                if (newH < MIN_HEIGHT) {
                    newH = MIN_HEIGHT;
                    if (currentHandleType.includes('n')) {
                        newY = startWinY + (startHeight - MIN_HEIGHT);
                    }
                }

                isUpdating = true;
                pywebview.api.set_window_bounds(newX, newY, newW, newH).then(() => {
                    isUpdating = false;
                });
            });

            document.addEventListener('mouseup', () => {
                isResizing = false;
                isUpdating = false;
            });
        }
        
        function updateStatus(status) {
            const statusEl = document.getElementById('statusMessage');
            statusEl.textContent = status.message;
            statusEl.className = 'status-message' + (status.available ? ' success' : '');
        }
        
        function showError(message) {
            const el = document.getElementById('errorMessage');
            el.textContent = message;
            el.classList.add('active');
            
            setTimeout(() => {
                el.classList.remove('active');
            }, 4000);
        }
        
        function hideError() {
            document.getElementById('errorMessage').classList.remove('active');
        }
        
        async function startDownload() {
            hideError();
            document.getElementById('optionsContainer').classList.add('hidden');
            document.getElementById('progressSection').classList.add('active');
            document.getElementById('btnCancel').disabled = true;
            
            try {
                await pywebview.api.start_download();
            } catch (e) {
                showError('下载失败: ' + e.message);
                resetUI();
            }
        }
        
        async function selectGitExe() {
            hideError();
            try {
                const result = await pywebview.api.select_git_exe();
                if (result.success) {
                    complete();
                } else if (result.message) {
                    showError(result.message);
                }
            } catch (e) {
                showError('选择文件失败: ' + e.message);
            }
        }
        
        async function useSystemGit() {
            hideError();
            try {
                const result = await pywebview.api.use_system_git();
                if (result.success) {
                    complete();
                } else {
                    showError(result.message);
                }
            } catch (e) {
                showError(e.message);
            }
        }
        
        function updateProgress(progress) {
            const fill = document.getElementById('progressFill');
            const text = document.getElementById('progressText');
            
            if (progress.total > 0) {
                const percent = Math.round((progress.current / progress.total) * 100);
                fill.style.width = percent + '%';
            }
            
            let message = progress.message;
            if (progress.from_cache) {
                message = '✓ 使用本地缓存文件';
            } else if (progress.resumed) {
                message = '↻ ' + message;
            }
            text.textContent = message;
            
            if (progress.status === 'completed') {
                complete();
            } else if (progress.status === 'failed') {
                showError(progress.error || '操作失败');
                resetUI();
            }
        }
        
        async function cancelOperation() {
            try {
                await pywebview.api.cancel_download();
            } catch (e) {}
            
            try {
                await pywebview.api.close_window();
            } catch (e) {
                window.close();
            }
        }
        
        function complete() {
            isCompleted = true;
            document.getElementById('progressSection').classList.add('hidden');
            document.getElementById('optionsContainer').classList.add('hidden');
            document.getElementById('statusMessage').textContent = 'Git 配置完成！';
            document.getElementById('statusMessage').classList.add('success');
            document.getElementById('btnCancel').classList.add('hidden');
            document.getElementById('btnContinue').classList.remove('hidden');
        }
        
        function resetUI() {
            document.getElementById('optionsContainer').classList.remove('hidden');
            document.getElementById('progressSection').classList.remove('active');
            document.getElementById('btnCancel').disabled = false;
        }
        
        async function continueStartup() {
            try {
                await pywebview.api.continue_startup();
            } catch (e) {
                showError('继续启动失败: ' + e.message);
            }
        }
        
        window.addEventListener('pywebviewready', init);
    </script>
</body>
</html>'''


def show_bootstrap_window(git_manager: GitManager) -> bool:
    """
    显示 Git 配置引导窗口
    
    Args:
        git_manager: Git 管理器实例
        
    Returns:
        bool: 是否成功配置 Git
    """
    import traceback
    
    logger = get_logger()
    result = {'success': False}
    
    def on_complete(success: bool):
        try:
            logger.info(f"[Bootstrap] on_complete 回调：success={success}")
            result['success'] = success
        except Exception as e:
            logger.error(f"[Bootstrap] on_complete 回调异常：{e}")
            logger.debug(traceback.format_exc())
    
    api = BootstrapAPI(git_manager, on_complete)
    
    window = webview.create_window(
        title='Comfyui-Box - Git 配置',
        html=get_bootstrap_html(),
        width=500,
        height=720,
        resizable=True,
        frameless=True,
        easy_drag=False,
        js_api=api
    )
    
    api.set_window(window)
    
    try:
        logger.info("[Bootstrap] 开始启动窗口...")
        webview.start(debug=False, gui='edgechromium')
        logger.info(f"[Bootstrap] 窗口已关闭，result={result}")
    except Exception as e:
        logger.error(f"[Bootstrap] webview.start 异常：{e}")
        logger.debug(traceback.format_exc())
    
    return result['success']
