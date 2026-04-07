// ==UserScript==
// @name         下载抖音视频至NAS (Open Source Edition)
// @name:en      Download Douyin Video to NAS
// @namespace    http://tampermonkey.net/
// @version      0.4.0
// @description  适配 FastAPI 后端：按钮实时同步后端任务状态 (Default Port 17650)
// @author       Kalo
// @match        *://www.douyin.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// @grant        GM_setClipboard
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // ============================================================
    // [User Configuration] 请根据你的部署情况修改以下两项
    // ============================================================

    // 1. 你的 NAS 服务器地址 (不需要带 /download 等后缀)
    // 默认后端端口契约是 APP_PORT=17650。
    // 如果是本地测试，通常是 http://localhost:17650
    // 如果是 NAS，请填写局域网 IP 或域名，例如 http://192.168.1.10:17650
    const NAS_SERVER_BASE_URL = 'http://localhost:17650';

    // 2. API Key (必须与后端 .env 文件中的 DY_API_KEY 保持一致)
    // 请确保修改此值，不要使用默认的示例 Key
    const MY_API_KEY = 'change_me_to_your_secure_key';

    // ============================================================
    // [End of Configuration] 以下代码通常无需修改
    // ============================================================

    const ENDPOINTS = {
        DOWNLOAD: `${NAS_SERVER_BASE_URL}/download`,
        TRANSCRIBE: `${NAS_SERVER_BASE_URL}/download_and_transcribe`,
        TASK_QUERY: `${NAS_SERVER_BASE_URL}/task`,
    };

    const API_KEY_HEADERS = ['X-API-KEY'];

    const VIDEO_PAGE_DETECTOR_SELECTOR = '[data-e2e="video-desc"]';
    const BTN_CONTAINER_ID = 'nas-download-btn-container';
    const TRANSCRIPT_PANEL_ID = 'nas-transcript-panel';

    const BUTTONS = [
        {
            id: 'nas-download-btn-only',
            defaultText: '下载到 NAS',
            busyText: '提交中...',
            successText: '已入队',
            errorText: '失败!',
            tooltip: '仅下载视频 (异步任务)',
            endpoint: ENDPOINTS.DOWNLOAD,
            mode: 'fire_and_forget',
        },
        {
            id: 'nas-download-transcribe-btn',
            defaultText: '下载+转录',
            busyText: '准备中...',
            successText: '完成',
            errorText: '失败!',
            tooltip: '下载并轮询等待转录结果',
            endpoint: ENDPOINTS.TRANSCRIBE,
            mode: 'poll_result',
        },
    ];

    // ... (样式代码保持不变，省略以节省空间) ...
    GM_addStyle(`
        #${BTN_CONTAINER_ID} { position: fixed; top: 100px; right: 20px; z-index: 99999; display: flex; flex-direction: column; gap: 10px; }
        #${BTN_CONTAINER_ID} button { background-color: #FE2C55; color: #fff; border: none; border-radius: 999px; width: 140px; height: 44px; font-size: 14px; font-weight: bold; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.2); display: flex; justify-content: center; align-items: center; text-align: center; padding: 0 12px; opacity: 0.25; transition: all 0.25s ease; }
        #${BTN_CONTAINER_ID} button:hover { opacity: 1; transform: translateY(-1px); }
        #${BTN_CONTAINER_ID} button.loading { cursor: progress; opacity: 1; background-color: #e02045; }
        #${BTN_CONTAINER_ID} button.success { background-color: #25c83e; opacity: 1; }
        #${BTN_CONTAINER_ID} button.error { background-color: #333; opacity: 1; }
        #${TRANSCRIPT_PANEL_ID} { position: fixed; bottom: 40px; right: 20px; width: 360px; max-height: 400px; background: rgba(0,0,0,0.85); color: #f5f5f5; padding: 16px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); backdrop-filter: blur(10px); display: flex; flex-direction: column; gap: 10px; z-index: 99999; border: 1px solid rgba(255,255,255,0.1); }
        #${TRANSCRIPT_PANEL_ID} .nas-transcript-header { display: flex; justify-content: space-between; align-items: center; font-weight: bold; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px; }
        #${TRANSCRIPT_PANEL_ID} .nas-transcript-close { border: none; background: transparent; color: #aaa; font-size: 20px; cursor: pointer; }
        #${TRANSCRIPT_PANEL_ID} .nas-transcript-close:hover { color: #fff; }
        #${TRANSCRIPT_PANEL_ID} pre { white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.5; margin: 0; background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; overflow-y: auto; max-height: 300px; user-select: text; }
        #${TRANSCRIPT_PANEL_ID} .nas-transcript-copy { font-size: 12px; color: #FE2C55; cursor: pointer; margin-top: 5px; text-align: right; }
    `);

    function buildHeaders(extra) {
        const headers = Object.assign({}, extra || {});
        API_KEY_HEADERS.forEach((name) => {
            headers[name] = MY_API_KEY;
        });
        return headers;
    }

    // ... (其余逻辑代码保持不变，引用 buildHeaders 即可) ...
    // 为确保完整性，以下是核心逻辑的简略引用
    function gmRequest(details) {
        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                ...details,
                onload: (res) => (res.status >= 200 && res.status < 300 ? resolve(res) : reject(res)),
                onerror: reject,
                ontimeout: () => reject(new Error('Timeout')),
            });
        });
    }

    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    async function handleButtonClick(btn, config) {
        if (btn.classList.contains('loading')) return;
        const videoId = extractActiveVideoId();
        if (!videoId) { alert('错误：无法获取当前视频 ID！'); return; }

        setButtonState(btn, 'loading', config.busyText);

        try {
            console.log(`[NAS] 提交任务至 ${config.endpoint}, 视频ID: ${videoId}`);
            const response = await gmRequest({
                method: 'POST',
                url: config.endpoint,
                headers: buildHeaders({ 'Content-Type': 'application/json' }),
                data: JSON.stringify({ video_id: videoId }),
            });

            const data = JSON.parse(response.responseText);
            const taskId = data.task_id;
            if (!taskId) throw new Error('服务器未返回 Task ID');

            if (data.message) btn.textContent = truncateText(data.message, 14);

            if (config.mode === 'poll_result') {
                const resultText = await pollTaskStatus(taskId, btn);
                setButtonState(btn, 'success', config.successText);
                renderTranscript(videoId, resultText);
            } else {
                setButtonState(btn, 'success', config.successText);
            }
        } catch (err) {
            console.error('[NAS Error]', err);
            setButtonState(btn, 'error', '出错');
            alert(`任务失败`); // 可根据需要展开错误详情
        } finally {
            setTimeout(() => {
                if (!btn) return;
                btn.className = '';
                btn.textContent = btn.dataset.defaultText;
            }, 3000);
        }
    }

    async function pollTaskStatus(taskId, btn) {
        const pollUrl = `${ENDPOINTS.TASK_QUERY}/${taskId}`;
        const TIMEOUT_MS = 10 * 60 * 1000;
        const start = Date.now();
        let lastMessage = '';

        while (Date.now() - start < TIMEOUT_MS) {
            await sleep(1000);
            try {
                const res = await gmRequest({ method: 'GET', url: pollUrl, headers: buildHeaders() });
                const job = JSON.parse(res.responseText);

                if (job.message && job.message !== lastMessage) {
                    lastMessage = job.message;
                    btn.textContent = truncateText(job.message, 14);
                }
                if (job.status === 'completed') return job.result;
                if (job.status === 'failed') throw new Error(job.message || '任务失败');
            } catch (err) {
                // 简单处理网络错误，继续重试
                if (err.status && err.status === 404) throw new Error("任务丢失");
            }
        }
        throw new Error('Timeout');
    }

    // DOM & UI Helpers
    function createOrRemoveButtons() {
        const targetElement = document.querySelector(VIDEO_PAGE_DETECTOR_SELECTOR);
        const container = document.getElementById(BTN_CONTAINER_ID);
        if (targetElement && !container) createDownloadButtons();
        else if (!targetElement && container) container.remove();
    }

    function createDownloadButtons() {
        const container = document.createElement('div');
        container.id = BTN_CONTAINER_ID;
        BUTTONS.forEach((config) => {
            const btn = document.createElement('button');
            btn.id = config.id;
            btn.textContent = config.defaultText;
            btn.dataset.defaultText = config.defaultText;
            btn.title = config.tooltip;
            btn.addEventListener('click', () => handleButtonClick(btn, config));
            container.appendChild(btn);
        });
        document.body.appendChild(container);
    }

    function setButtonState(btn, state, text) {
        if (!btn) return;
        btn.className = state;
        btn.textContent = text;
    }

    function truncateText(str, n) {
        if (!str) return '';
        let realLen = 0, out = '';
        for (const ch of str) {
            realLen += /[^\x00-\xff]/.test(ch) ? 2 : 1;
            if (realLen > n - 2) { out += '..'; break; }
            out += ch;
        }
        return out || str;
    }

    // =========================
    // 视频 ID 解析辅助函数
    // =========================

    function extractNumberId(str, minLen = 8) {
        if (!str) return null;
        const re = new RegExp(`\\d{${minLen},}`);
        const m = String(str).match(re);
        return m ? m[0] : null;
    }

    function findVideoIdInElement(root) {
        if (!root) return null;

        // 优先找 /video/xxxxxxxxxxxx 这种链接
        const linkSelectors = [
            'a[href*="/video/"]',
            'a[data-e2e="video-link"]',
        ];
        for (const sel of linkSelectors) {
            const a = root.querySelector(sel);
            if (a) {
                const href = a.getAttribute('href') || a.href || '';
                const m = href.match(/\/video\/(\d{8,})/);
                if (m) {
                    console.log(`[NAS] ID Source: Anchor Href (${m[1]})`);
                    return m[1];
                }
            }
        }

        // 常见挂载在元素上的 data-* 属性
        const attrNames = [
            'data-e2e-vid',
            'data-vid',
            'data-video-id',
            'data-aweme-id',
            'data-e2e-aweme-id',
        ];

        for (const name of attrNames) {
            if (root.hasAttribute && root.hasAttribute(name)) {
                const id = extractNumberId(root.getAttribute(name), 8);
                if (id) {
                    console.log(`[NAS] ID Source: Element Attribute ${name} (${id})`);
                    return id;
                }
            }
        }

        // 再从子节点里找这些属性
        const dataAttrSelector = [
            '[data-e2e-vid]',
            '[data-vid]',
            '[data-video-id]',
            '[data-aweme-id]',
            '[data-e2e-aweme-id]',
        ].join(',');

        const el = root.querySelector(dataAttrSelector);
        if (el) {
            for (const name of attrNames) {
                const id = extractNumberId(el.getAttribute(name), 8);
                if (id) {
                    console.log(`[NAS] ID Source: Child Attribute ${name} (${id})`);
                    return id;
                }
            }
        }

        return null;
    }

    // =========================
    // 合并后的 ID 提取主函数
    // =========================

    function extractActiveVideoId() {
        /**
         * 策略 0: 详情页路径 /video/xxxxxxxxxxxx
         * 这是最标准、也是最稳定的形式
         */
        const detailMatch = window.location.pathname.match(/\/video\/(\d{8,})/);
        if (detailMatch) {
            console.log(`[NAS] ID Source: Detail Path (${detailMatch[1]})`);
            return detailMatch[1];
        }

        /**
         * 策略 1: 优先检查 DOM 中被标记为 "Active" 的容器
         * 抖音通常会给当前播放的容器加 data-e2e="feed-active-video"
         * 这里的关键是取 dataset.id 而不是 data-e2e-vid
         */
        const activeFeed = document.querySelector('[data-e2e="feed-active-video"]');
        if (activeFeed && activeFeed.dataset && activeFeed.dataset.id) {
            console.log(`[NAS] ID Source: Active Feed Attribute (${activeFeed.dataset.id})`);
            return activeFeed.dataset.id;
        }

        /**
         * 策略 2: 针对弹窗/滑动模式 (Swiper)
         * 在个人主页点击视频进入的弹窗模式中，当前卡片通常有 .swiper-slide-active 类
         */
        const activeSlide = document.querySelector('.swiper-slide-active');
        if (activeSlide && activeSlide.dataset && activeSlide.dataset.id) {
            console.log(`[NAS] ID Source: Swiper Slide Active (${activeSlide.dataset.id})`);
            return activeSlide.dataset.id;
        }

        /**
         * 策略 3: URL 参数检查 (适用于直链访问或弹窗初次打开)
         * 只有当 URL 包含明确的 modal_id 且看起来像个长数字 ID 时才采信
         * 且：如果页面上有 swiper-slide-active，就以 DOM 为准，不信 URL
         * 防止用户在弹窗里划走了，但 URL 没变
         */
        const urlParams = new URLSearchParams(window.location.search);
        const rawModalId = urlParams.get('modal_id');
        const modalId = rawModalId && /^\d{15,}$/.test(rawModalId) ? rawModalId : null;
        if (modalId && !activeSlide) {
            console.log(`[NAS] ID Source: URL Modal Param (${modalId})`);
            return modalId;
        }

        /**
         * 策略 4: 视口中心 + feed-item 卡片 + 链接/属性解析
         * 适用于各种推荐流 / 搜索流 / 话题流 等
         */
        const centerX = window.innerWidth / 2;
        const centerY = window.innerHeight / 2;
        let centerEl = document.elementFromPoint(centerX, centerY);

        let feedItem = centerEl && centerEl.closest
            ? centerEl.closest('[data-e2e="feed-item"], [data-e2e="feed-active-video"]')
            : null;

        // 找不到就退回到第一个 feed-item
        if (!feedItem) {
            feedItem = document.querySelector('[data-e2e="feed-item"], [data-e2e="feed-active-video"]');
        }

        const idFromFeed = findVideoIdInElement(feedItem);
        if (idFromFeed) {
            return idFromFeed;
        }

        /**
         * 策略 5: 从整个 URL 中兜底提取一个“像样的长数字”
         * 某些特殊跳转或新页面结构，用这个作为最后的保险
         */
        const fallback = extractNumberId(window.location.href, 8);
        if (fallback) {
            console.log(`[NAS] ID Source: URL Fallback (${fallback})`);
            return fallback;
        }

        console.warn('[NAS] extractActiveVideoId: failed to resolve video id');
        return null;
    }


    function renderTranscript(videoId, text) {
        let panel = document.getElementById(TRANSCRIPT_PANEL_ID);
        if (!panel) {
            panel = document.createElement('div');
            panel.id = TRANSCRIPT_PANEL_ID;
            panel.innerHTML = `<div class="nas-transcript-header"><span>📝 转录结果</span><button class="nas-transcript-close">×</button></div><div style="font-size: 12px; color: #aaa; margin-bottom: 6px;">ID: <span class="nas-transcript-id"></span></div><pre class="nas-transcript-body"></pre><div class="nas-transcript-copy">点击复制</div>`;
            document.body.appendChild(panel);
            panel.querySelector('.nas-transcript-close').addEventListener('click', () => panel.remove());
            panel.querySelector('.nas-transcript-copy').addEventListener('click', () => {
                GM_setClipboard(panel.querySelector('.nas-transcript-body').textContent);
                alert('已复制到剪贴板');
            });
        }
        panel.querySelector('.nas-transcript-id').textContent = videoId;
        panel.querySelector('.nas-transcript-body').textContent = text;
    }

    const observer = new MutationObserver(createOrRemoveButtons);
    observer.observe(document.body, { childList: true, subtree: true });
    createOrRemoveButtons();
})();
