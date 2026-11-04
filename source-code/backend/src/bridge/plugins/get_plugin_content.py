"""
Comfyui-Box Bridge 插件内容生成器

提供插件的 __init__.py 和 comfyui-box_bridge.js 的内容
"""

INIT_PY_CONTENT = '''"""
Comfyui-Box Bridge - ComfyUI 自定义节点桥接插件

功能：
1. 提供 JS 扩展，实现与 Comfyui-Box 主窗口的通信
2. 拦截图片下载，支持自定义保存路径
3. 同步实时预览和执行状态

注意：此文件由 Comfyui-Box 自动部署，请勿手动修改
"""

BRIDGE_PLUGIN_VERSION = "__BRIDGE_PLUGIN_VERSION__"
print("========== [Comfyui-Box Bridge v__BRIDGE_PLUGIN_VERSION__] ==========")

WEB_DIRECTORY = "./js"

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
'''

BRIDGE_PLUGIN_VERSION = "1.5.7"

INIT_PY_CONTENT = INIT_PY_CONTENT.replace("__BRIDGE_PLUGIN_VERSION__", BRIDGE_PLUGIN_VERSION)

BRIDGE_JS_CONTENT = '''/**
 * Comfyui-Box Bridge - 桥接脚本
 * 
 * 功能：
 * 1. 监听 ComfyUI 事件并转发给 Comfyui-Box 主窗口
 * 2. 拦截图片下载，支持自定义保存路径
 * 3. 提供 localStorage 同步功能
 * 4. 注入 electronAPI polyfill（桌面版兼容）
 * 
 * 注意：此文件由 Comfyui-Box 自动部署，请勿手动修改
 */

// ============================================
// Electron API Polyfill（桌面版兼容）
// ============================================
(function() {
    if (window.electronAPI) {
        console.log('[Comfyui-Box Bridge] electronAPI 已存在，跳过注入');
        return;
    }
    
    console.log('[Comfyui-Box Bridge] 注入 electronAPI polyfill（桌面版兼容）');
    
    window.electronAPI = {
        // 版本信息
        getComfyUIVersion: async () => {
            try {
                const response = await fetch('/system_stats');
                const data = await response.json();
                return data.system?.comfyui_version || 'unknown';
            } catch {
                return 'unknown';
            }
        },
        getElectronVersion: async () => 'N/A (Comfyui-Box)',
        isPackaged: async () => true,
        getBasePath: async () => '',
        getPlatform: () => navigator.platform,
        getModelConfigPath: async () => '',
        
        // 文件夹操作（空实现，避免报错）
        openLogsFolder: () => console.log('[Comfyui-Box Bridge] openLogsFolder not supported'),
        openModelsFolder: () => console.log('[Comfyui-Box Bridge] openModelsFolder not supported'),
        openOutputsFolder: () => console.log('[Comfyui-Box Bridge] openOutputsFolder not supported'),
        openInputsFolder: () => console.log('[Comfyui-Box Bridge] openInputsFolder not supported'),
        openCustomNodesFolder: () => console.log('[Comfyui-Box Bridge] openCustomNodesFolder not supported'),
        openDevTools: () => console.log('[Comfyui-Box Bridge] openDevTools not supported'),
        
        // Config 子对象
        Config: {
            getDetectedGpu: async () => null,
            setWindowStyle: async () => {},
            getWindowStyle: async () => ({})
        },
        
        // 其他方法
        getDetectedGpu: async () => null,
        setWindowStyle: async () => {},
        getWindowStyle: async () => ({}),
        getSystemPaths: async () => ({}),
        restartCore: async () => {},
        quit: async () => {},
        
        // DownloadManager 子对象
        DownloadManager: {
            onDownloadProgress: () => {},
            startDownload: async () => {},
            cancelDownload: async () => {},
            pauseDownload: async () => {},
            resumeDownload: async () => {},
            deleteModel: async () => {},
            getAllDownloads: async () => []
        },
        
        // Terminal 子对象
        Terminal: {
            write: async () => {},
            resize: async () => {},
            restore: async () => {},
            onOutput: () => () => {}
        },
        
        // Events 子对象
        Events: {
            trackEvent: () => {},
            incrementUserProperty: () => {}
        },
        
        // Validation 子对象
        Validation: {
            onUpdate: () => {},
            getStatus: async () => ({}),
            complete: async () => {},
            validateInstallation: async () => {},
            dispose: () => {}
        },
        
        // InstallStage 子对象
        InstallStage: {
            getCurrent: async () => '',
            onUpdate: () => () => {}
        },
        
        // uv 子对象
        uv: {
            installRequirements: async () => {},
            clearCache: async () => {},
            resetVenv: async () => {}
        },
        
        // Dialog 子对象
        Dialog: {
            clickButton: async () => {}
        },
        
        // 其他方法
        showDirectoryPicker: async () => null,
        checkForUpdates: async () => null,
        restartAndInstall: async () => {},
        isBlackwell: async () => false,
        setMetricsConsent: async () => {},
        startTroubleshooting: async () => {},
        disableCustomNodes: async () => {},
        canAccessUrl: async () => true
    };
})();

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// 插件版本
const PLUGIN_VERSION = "__BRIDGE_PLUGIN_VERSION__";

// 最后点击的图片信息（用于下载链接拦截）
let lastImageTarget = null;
let lastImageUrl = null;

// 最后右键点击的图片信息（用于 Save Image 菜单劫持）
let lastRightClickImageInfo = null;

app.registerExtension({
    name: "Comfyui-Box.Bridge",
    
    async setup() {
        console.log(`[Comfyui-Box Bridge] v${PLUGIN_VERSION} 初始化...`);
        
        // 1. 监听进度事件
        api.addEventListener("progress", (event) => {
            window.parent.postMessage({
                type: 'comfyui-box:progress',
                data: event.detail
            }, "*");
        });
        
        // 2. 监听执行完成事件
        api.addEventListener("executed", (event) => {
            window.parent.postMessage({
                type: 'comfyNexus:executed',
                data: event.detail
            }, "*");
        });
        
        // 3. 监听执行开始事件
        api.addEventListener("execution_start", (event) => {
            window.parent.postMessage({
                type: 'comfyui-box:execution_start',
                data: event.detail
            }, "*");
        });
        
        // 4. 监听执行错误事件
        api.addEventListener("execution_error", (event) => {
            window.parent.postMessage({
                type: 'comfyui-box:execution_error',
                data: event.detail
            }, "*");
        });
        
        // 5. 设置事件监听（合并 contextmenu 事件处理）
        _setupEventListeners();
        
        // 6. 监听来自主窗口的消息
        _setupMessageListener();
        
        // 7. 劫持 ComfyUI 右键菜单的 Save Image
        _setupLiteGraphSaveImageCallbackHijack();
        _setupSaveImageMenuHijack();
        
        console.log(`[Comfyui-Box Bridge] v${PLUGIN_VERSION} 初始化完成`);
    }
});

/**
 * 设置事件监听器（合并处理）
 */
function _setupEventListeners() {
    // LiteGraph 会在右键 mousedown 阶段生成菜单，必须提前记录图片信息。
    document.addEventListener('mousedown', (e) => {
        if (e.button === 2) {
            _captureImageContextTarget(e.target);
        }
    }, true);

    // 统一处理 contextmenu 事件
    document.addEventListener('contextmenu', (e) => {
        const target = e.target;

        _captureImageContextTarget(target);
    }, true);
    
    // 拦截下载链接点击
    document.addEventListener('click', (e) => {
        const target = e.target;
        
        // 1. 检查是否是下载按钮
        const button = target.tagName === 'BUTTON' ? target : target.closest('button');
        if (button) {
            const ariaLabel = button.getAttribute('aria-label');
            const title = button.getAttribute('title');
            const hasDownloadIcon = button.querySelector('[class*="lucide--download"]');
            
            // 检测是否是下载按钮（通过 aria-label、title 或图标）
            if (ariaLabel === '下载图片' || title === '下载图片' || 
                ariaLabel === 'Download Image' || title === 'Download Image' ||
                hasDownloadIcon) {
                
                // 阻止默认行为
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                
                // 获取图片信息
                let imageInfo = _getCurrentSaveImageInfo();
                
                if (!imageInfo) {
                    // 尝试获取当前显示的图片
                    const currentImg = document.querySelector('[role="img"] img');
                    if (currentImg) {
                        const src = currentImg.src.startsWith('/') 
                            ? window.location.origin + currentImg.src 
                            : currentImg.src;
                        imageInfo = {
                            imageUrl: src,
                            filename: currentImg.alt || src.split('/').pop().split('?')[0] || 'image.png'
                        };
                    }
                }
                
                if (imageInfo) {
                    console.log('[Comfyui-Box Bridge] 拦截下载按钮:', imageInfo);
                    
                    // 通知主窗口保存图片
                    window.parent.postMessage({
                        type: 'comfyui-box:save_image',
                        data: imageInfo
                    }, '*');
                }
                
                return;
            }
        }
        
        // 2. 检查是否是下载链接
        const link = target.tagName === 'A' ? target : target.closest('a');
        
        if (link && link.hasAttribute('download')) {
            const filename = link.getAttribute('download') || 'download';
            const isImage = /\\.(png|jpg|jpeg|gif|webp)$/i.test(filename);
            
            if (isImage && lastImageUrl) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                
                // 通知主窗口处理下载
                window.parent.postMessage({
                    type: 'comfyui-box:save_image',
                    data: {
                        filename: filename,
                        imageUrl: lastImageUrl
                    }
                }, "*");
                
                console.log(`[Comfyui-Box Bridge] 拦截图片下载: ${filename}`);
            }
        }
    }, true);
}

function _captureImageContextTarget(target) {
    if (!target) return;

    if (target.tagName === 'IMG' || target.tagName === 'CANVAS') {
        lastImageTarget = target;

        if (target.tagName === 'IMG') {
            lastImageUrl = target.src;
        } else if (target.tagName === 'CANVAS') {
            try {
                lastImageUrl = target.toDataURL('image/png');
            } catch (error) {
                lastImageUrl = null;
            }
        }
    }

    _recordImageInfo(target);
    _scheduleMenuChecks();
}

function _scheduleMenuChecks() {
    [0, 50, 150, 300, 500].forEach((delay) => {
        setTimeout(() => {
            _checkExistingMenus();
        }, delay);
    });
}

/**
 * 检查已存在的菜单（处理 MutationObserver 启动前菜单已存在的情况）
 */
function _checkExistingMenus() {
    // 检查 PrimeVue 菜单
    const primevueMenus = document.querySelectorAll('.p-contextmenu-root-list');
    for (const menu of primevueMenus) {
        _checkAndHijackSaveImageMenu(menu);
    }
    
    // 检查 LiteGraph 菜单
    const litegraphMenus = document.querySelectorAll('.litecontextmenu');
    for (const menu of litegraphMenus) {
        _checkAndHijackSaveImageMenu(menu);
    }
}

/**
 * 记录图片信息（用于 Save Image 菜单劫持）
 */
function _recordImageInfo(target) {
    const imageInfo = _getImageInfoFromElement(target);
    if (imageInfo) {
        lastRightClickImageInfo = imageInfo;
        console.log('[Comfyui-Box Bridge] 记录图片信息:', lastRightClickImageInfo);
    }
}

/**
 * 从元素解析图片信息，点击保存时也会实时调用，避免复用菜单保存到旧图片。
 */
function _getImageInfoFromElement(target) {
    if (!target) return null;

    let imgElement = null;
    let imageUrl = null;
    let filename = null;

    if (target.tagName === 'IMG') {
        imgElement = target;
    } else if (target.tagName === 'CANVAS') {
        try {
            imageUrl = target.toDataURL('image/png');
            filename = 'canvas.png';
        } catch (error) {
            return null;
        }
    } else if (target.closest?.('[role="img"]')) {
        const container = target.closest('[role="img"]');
        imgElement = container.querySelector('img');
    } else if (target.closest) {
        imgElement = target.closest('img');
    }

    if (imgElement && imgElement.src) {
        imageUrl = imgElement.src.startsWith('/')
            ? window.location.origin + imgElement.src
            : imgElement.src;
        filename = imgElement.alt || '';
    }

    if (!imageUrl) return null;

    if (!filename || filename === 'Node output') {
        try {
            const url = new URL(imageUrl);
            filename = url.searchParams.get('filename') || '';
        } catch (e) {
            filename = '';
        }
    }
    if (!filename) {
        filename = imageUrl.split('/').pop().split('?')[0] || 'image.png';
    }

    return { imageUrl, filename };
}

function _getCurrentSaveImageInfo() {
    return _getImageInfoFromElement(lastImageTarget) || lastRightClickImageInfo;
}

function _getImageInfoFromComfyNode(node) {
    if (!node?.imgs?.length) return null;

    let imageElement = null;
    if (node.imageIndex == null) {
        if (node.overIndex != null) imageElement = node.imgs[node.overIndex];
    } else {
        imageElement = node.imgs[node.imageIndex];
    }
    imageElement ||= node.imgs[0];
    return _getImageInfoFromElement(imageElement);
}

function _getImageInfoFromMenuContext(...contexts) {
    for (const context of contexts) {
        const imageInfo = _getImageInfoFromComfyNode(context)
            || _getImageInfoFromComfyNode(context?.node)
            || _getImageInfoFromComfyNode(context?.extra)
            || _getImageInfoFromComfyNode(context?.options?.node)
            || _getImageInfoFromComfyNode(context?.options?.extra);
        if (imageInfo) return imageInfo;
    }
    return null;
}

function _logSaveImageContextMiss(...contexts) {
    const describeContext = (context) => ({
        type: context?.constructor?.name || typeof context,
        keys: context && typeof context === 'object' ? Object.keys(context) : [],
        optionKeys: context?.options && typeof context.options === 'object' ? Object.keys(context.options) : [],
        hasNode: !!context?.node,
        hasExtra: !!context?.extra,
        hasOptionsExtra: !!context?.options?.extra,
        hasImgs: !!context?.imgs?.length || !!context?.node?.imgs?.length || !!context?.extra?.imgs?.length || !!context?.options?.extra?.imgs?.length
    });
    console.warn('[Comfyui-Box Bridge] Save Image 菜单点击时未找到图片信息', contexts.map(describeContext));
}

function _sendSaveImageRequest(imageInfo, logLabel) {
    if (!imageInfo) {
        _logSaveImageContextMiss();
        return false;
    }

    console.log(logLabel, imageInfo);
    window.parent.postMessage({
        type: 'comfyui-box:save_image',
        data: imageInfo
    }, '*');
    return true;
}

function _isSaveImageMenuItem(content, value) {
    const label = String(value?.content ?? value?.title ?? content ?? '').trim();
    return label === 'Save Image' || label === '保存图像';
}

function _setupLiteGraphSaveImageCallbackHijack(retryCount = 0) {
    const LiteGraph = window.LiteGraph;
    const contextMenuPrototype = LiteGraph?.ContextMenu?.prototype;
    if (!contextMenuPrototype?.addItem) {
        if (retryCount < 20) {
            setTimeout(() => _setupLiteGraphSaveImageCallbackHijack(retryCount + 1), 250);
        } else {
            console.warn('[Comfyui-Box Bridge] LiteGraph ContextMenu 未就绪，Save Image 回调劫持未安装');
        }
        return;
    }
    if (contextMenuPrototype.addItem.__comfyuiBoxHijacked) return;

    const originalAddItem = contextMenuPrototype.addItem;
    contextMenuPrototype.addItem = function(content, value, options) {
        if (_isSaveImageMenuItem(content, value) && value && typeof value === 'object') {
            const menuInstance = this;
            const capturedImageInfo = _getImageInfoFromMenuContext(options, menuInstance) || _getCurrentSaveImageInfo();
            const originalLabel = String(value.title ?? value.content ?? content ?? 'Save Image').trim();
            const patchedLabel = originalLabel === '保存图像' ? '保存图像 (Comfyui-Box)' : 'Save Image (Comfyui-Box)';
            value = {
                ...value,
                content: patchedLabel,
                title: patchedLabel,
                callback: (_item, menuOptions, clickEvent, menu, extra) => {
                    const imageInfo = _getImageInfoFromMenuContext(extra, menuOptions, menu, menuInstance, options)
                        || _getCurrentSaveImageInfo()
                        || capturedImageInfo;
                    if (!imageInfo) {
                        _logSaveImageContextMiss(extra, menuOptions, menu, menuInstance, options);
                        return;
                    }
                    _sendSaveImageRequest(imageInfo, '[Comfyui-Box Bridge] 拦截 Save Image (LiteGraph callback):');
                }
            };
            content = patchedLabel;
        }
        return originalAddItem.call(this, content, value, options);
    };
    contextMenuPrototype.addItem.__comfyuiBoxHijacked = true;
    console.log('[Comfyui-Box Bridge] LiteGraph Save Image 回调劫持已启动');
}

function _handleSaveImageMenuAction(e, fallbackImageInfo, logLabel, closeMenu) {
    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();

    const target = e.currentTarget || e.target;
    const currentImageInfo = _getCurrentSaveImageInfo();
    const saveImageInfo = currentImageInfo || fallbackImageInfo;
    if (!saveImageInfo) {
        console.warn('[Comfyui-Box Bridge] Save Image 菜单点击时未找到图片信息');
        return;
    }
    if (target?.dataset?.comfyuiBoxSaving === 'true') return;
    if (target?.dataset) target.dataset.comfyuiBoxSaving = 'true';

    _sendSaveImageRequest(saveImageInfo, logLabel);

    closeMenu?.();
}

/**
 * 劫持 ComfyUI 右键菜单的 Save Image
 */
function _setupSaveImageMenuHijack() {
    // 使用 MutationObserver 监听右键菜单的显示
    const menuObserver = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    // 检查是否是菜单或包含菜单
                    _checkAndHijackSaveImageMenu(node);
                }
            }
        }
    });
    
    // 启动观察器
    menuObserver.observe(document.body, {
        childList: true,
        subtree: true
    });
    
    console.log('[Comfyui-Box Bridge] Save Image 菜单劫持已启动');
}

/**
 * 检查并劫持 Save Image 菜单项（支持两种菜单系统）
 */
function _checkAndHijackSaveImageMenu(element) {
    // 查找右键菜单 - 支持两种菜单系统
    let menu = null;
    let menuType = null;
    
    // 优先检查 PrimeVue ContextMenu (Nodes 2.0)
    if (element.classList?.contains('p-contextmenu-root-list')) {
        menu = element;
        menuType = 'primevue';
    } else if (element.querySelector?.('.p-contextmenu-root-list')) {
        menu = element.querySelector('.p-contextmenu-root-list');
        menuType = 'primevue';
    }
    // 检查 LiteGraph Menu (传统模式)
    else if (element.classList?.contains('litecontextmenu')) {
        menu = element;
        menuType = 'litegraph';
    } else if (element.querySelector?.('.litecontextmenu')) {
        menu = element.querySelector('.litecontextmenu');
        menuType = 'litegraph';
    }
    
    if (!menu) return;
    
    // 根据菜单类型查找 "保存图像" 菜单项
    let saveImageItem = null;
    
    if (menuType === 'primevue') {
        // PrimeVue 菜单：使用 aria-label
        const menuItems = menu.querySelectorAll('.p-contextmenu-item');
        for (const item of menuItems) {
            const label = item.getAttribute('aria-label');
            if (label === 'Save Image' && !item.dataset.comfyuiBoxHijacked) {
                saveImageItem = item;
                break;
            }
        }
    } else if (menuType === 'litegraph') {
        // LiteGraph 菜单：检查文本内容
        const menuItems = menu.querySelectorAll('.litemenu-entry');
        for (const item of menuItems) {
            const text = item.textContent?.trim();
            // 支持中英文
            if ((text === '保存图像' || text === 'Save Image') && !item.dataset.comfyuiBoxHijacked) {
                saveImageItem = item;
                break;
            }
        }
    }
    
    if (!saveImageItem) return;
    
    // 标记为已处理
    saveImageItem.dataset.comfyuiBoxHijacked = 'true';
    
    // 获取图片信息
    let imageInfo = _getCurrentSaveImageInfo();
    
    if (!imageInfo) {
        // 尝试获取当前显示的图片
        const currentImg = document.querySelector('[role="img"] img');
        if (currentImg) {
            const src = currentImg.src.startsWith('/') 
                ? window.location.origin + currentImg.src 
                : currentImg.src;
            imageInfo = {
                imageUrl: src,
                filename: currentImg.alt || src.split('/').pop().split('?')[0] || 'image.png'
            };
        }
    }
    
    // 根据菜单类型调用不同的劫持函数
    if (menuType === 'primevue') {
        _hijackPrimeVueMenuItem(saveImageItem, imageInfo, menu);
    } else if (menuType === 'litegraph') {
        _hijackLiteGraphMenuItem(saveImageItem, imageInfo, menu);
    }
}

/**
 * 劫持 PrimeVue 菜单项 (Nodes 2.0)
 */
function _hijackPrimeVueMenuItem(item, imageInfo, menu) {
    const link = item.querySelector('.p-contextmenu-item-link');
    if (!link) return;
    
    // 克隆节点以移除原有事件监听器
    const newLink = link.cloneNode(true);
    link.parentNode.replaceChild(newLink, link);
    
    // 添加新的点击事件
    const handleMenuAction = (e) => _handleSaveImageMenuAction(
        e,
        imageInfo,
        '[Comfyui-Box Bridge] 拦截 Save Image (PrimeVue):',
        () => {
            const rootMenu = menu.closest('.p-contextmenu') || menu;
            if (rootMenu && rootMenu.remove) rootMenu.remove();
        }
    );
    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((eventName) => {
        newLink.addEventListener(eventName, handleMenuAction, true);
    });
    
    // 修改菜单项文本
    const textSpan = newLink.querySelector('.flex-1');
    if (textSpan) {
        textSpan.textContent = 'Save Image (Comfyui-Box)';
    }
    
    console.log('[Comfyui-Box Bridge] 已劫持 PrimeVue Save Image 菜单项');
}

/**
 * 劫持 LiteGraph 菜单项 (传统模式)
 */
function _hijackLiteGraphMenuItem(item, imageInfo, menu) {
    const originalValue = item.value;
    if (originalValue && typeof originalValue === 'object') {
        const capturedImageInfo = _getImageInfoFromMenuContext(menu, item, originalValue) || imageInfo;
        originalValue.callback = (_item, menuOptions, clickEvent, activeMenu, extra) => {
            const saveImageInfo = _getImageInfoFromMenuContext(extra, menuOptions, activeMenu, menu, item, originalValue)
                || _getCurrentSaveImageInfo()
                || capturedImageInfo;
            if (!saveImageInfo) {
                _logSaveImageContextMiss(extra, menuOptions, activeMenu, menu, item, originalValue);
                return;
            }
            _sendSaveImageRequest(saveImageInfo, '[Comfyui-Box Bridge] 拦截 保存图像 (LiteGraph DOM value):');
        };
        originalValue.content = originalValue.title = item.textContent?.trim() === '保存图像'
            ? '保存图像 (Comfyui-Box)'
            : 'Save Image (Comfyui-Box)';
    } else {
        const handleMenuAction = (e) => _handleSaveImageMenuAction(
            e,
            imageInfo,
            '[Comfyui-Box Bridge] 拦截 保存图像 (LiteGraph fallback):',
            () => {
                if (menu && menu.remove) menu.remove();
            }
        );
        item.addEventListener('click', handleMenuAction, true);
    }

    // 修改菜单项文本
    const originalText = item.textContent?.trim();
    if (originalText === '保存图像') {
        item.textContent = '保存图像 (Comfyui-Box)';
    } else {
        item.textContent = 'Save Image (Comfyui-Box)';
    }
    
    console.log('[Comfyui-Box Bridge] 已劫持 LiteGraph 保存图像菜单项');
}

/**
 * 设置消息监听器
 */
function _setupMessageListener() {
    window.addEventListener('message', (event) => {
        const { type, data } = event.data || {};
        
        switch (type) {
            case 'comfyui-box:get_settings':
                // 返回 localStorage 设置
                const settings = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    settings[key] = localStorage.getItem(key);
                }
                window.parent.postMessage({
                    type: 'comfyui-box:settings',
                    data: settings
                }, "*");
                break;
                
            case 'comfyui-box:set_settings':
                // 设置 localStorage
                if (data && typeof data === 'object') {
                    for (const [key, value] of Object.entries(data)) {
                        localStorage.setItem(key, value);
                    }
                }
                break;
                
            case 'comfyui-box:ping':
                // 心跳检测
                window.parent.postMessage({
                    type: 'comfyui-box:pong',
                    data: { version: PLUGIN_VERSION }
                }, "*");
                break;
                
            case 'comfyui-box:add_load_image_node':
                if (data && data.filename) {
                    try {
                        const LGraph = window.LiteGraph;
                        if (!LGraph) {
                            window.parent.postMessage({
                                type: 'comfyui-box:add_load_image_result',
                                data: { success: false, error: 'LiteGraph not available' }
                            }, "*");
                            break;
                        }
                        const node = LGraph.createNode("LoadImage");
                        if (node) {
                            const graphCanvas = app.canvas;
                            if (graphCanvas && graphCanvas.canvas) {
                                node.pos = [graphCanvas.canvas.width / 2 / graphCanvas.ds.scale - 100, graphCanvas.canvas.height / 2 / graphCanvas.ds.scale - 50];
                            } else {
                                node.pos = [100, 100];
                            }
                            app.graph.add(node);

                            if (node.widgets && node.widgets.length > 0) {
                                const imageWidget = node.widgets.find(w => w.name === 'image');
                                const targetWidget = imageWidget || node.widgets[0];
                                targetWidget.value = data.filename;
                                if (node.onWidgetChanged) {
                                    node.onWidgetChanged(targetWidget.name, data.filename, targetWidget.value);
                                }
                                if (targetWidget.callback) {
                                    targetWidget.callback(data.filename);
                                }
                            }

                            graphCanvas?.ds?.reset && graphCanvas.ds.reset();
                            graphCanvas?.setDirty && graphCanvas.setDirty(true, true);

                            window.parent.postMessage({
                                type: 'comfyui-box:add_load_image_result',
                                data: { success: true, filename: data.filename }
                            }, "*");
                        } else {
                            window.parent.postMessage({
                                type: 'comfyui-box:add_load_image_result',
                                data: { success: false, error: 'Failed to create LoadImage node' }
                            }, "*");
                        }
                    } catch (err) {
                        window.parent.postMessage({
                            type: 'comfyui-box:add_load_image_result',
                            data: { success: false, error: err.message }
                        }, "*");
                    }
                }
                break;
        }
    });
}
'''.replace("__BRIDGE_PLUGIN_VERSION__", BRIDGE_PLUGIN_VERSION)


def get_bridge_plugin_version():
    """
    获取桥接插件版本号

    Returns:
        str: 桥接插件版本号
    """
    return BRIDGE_PLUGIN_VERSION


def get_plugin_content():
    """
    获取插件内容
    
    Returns:
        tuple: (init_py_content, bridge_js_content)
    """
    return (INIT_PY_CONTENT, BRIDGE_JS_CONTENT)
