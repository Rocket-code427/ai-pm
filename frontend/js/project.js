// 项目工作台逻辑 - AI-PM v0.2.0

const projectId = window.location.pathname.split('/').pop();
let projectData = null;
let currentStage = 'requirements';
let interviewSessionKey = null;
let interviewStep = 0;

// ============ 初始化 ============

document.addEventListener('DOMContentLoaded', () => {
    loadProject();
    loadStageFiles(currentStage);
    loadMeetings();
});

// ============ 会议纪要 ============

async function loadMeetings() {
    try {
        const response = await fetch(`/api/projects/${projectId}/files/meetings`);
        const data = await response.json();
        const container = document.getElementById('list-meetings');
        if (!container) return;
        
        if (!data.files || !data.files.length) {
            container.innerHTML = `
                <div class="text-center py-6 text-gray-400 bg-gray-50 rounded-lg border border-dashed border-gray-300">
                    <i class="fas fa-microphone-slash text-2xl mb-2"></i>
                    <p class="text-sm">暂无会议纪要，上传录音开始转录</p>
                </div>`;
            return;
        }
        
        const mdFiles = data.files.filter(f => f.name.endsWith('.md'));
        const cards = await Promise.all(mdFiles.map(async f => {
            const metaName = f.name.replace('.md', '.json');
            let meta = null;
            try {
                const metaResp = await fetch(`/api/projects/${projectId}/files/meetings/${encodeURIComponent(metaName)}`);
                if (metaResp.ok) meta = JSON.parse((await metaResp.json()).content);
            } catch (e) {}
            
            const typeColors = {
                '项目启动': 'bg-purple-100 text-purple-700', '需求评审': 'bg-blue-100 text-blue-700',
                'UI评审': 'bg-pink-100 text-pink-700', '技术方案评审': 'bg-orange-100 text-orange-700',
                '站会': 'bg-green-100 text-green-700', '复盘回顾': 'bg-gray-100 text-gray-700', '其他': 'bg-gray-100 text-gray-600'
            };
            const natureColors = { '推进': '🟢', '调整': '🟡', '纠偏': '🔴', '补充': '🔵', '信息同步': '⚪' };
            
            const mt = meta?.meeting_type || '其他';
            const nature = meta?.impact?.nature || '信息同步';
            
            return `
                <div class="bg-white rounded-lg border border-gray-200 hover:border-indigo-300 transition-all cursor-pointer" onclick="viewFile('meetings', '${f.name.replace(/'/g, "\\'")}')">
                    <div class="p-3">
                        <div class="flex items-center justify-between mb-2">
                            <div class="flex items-center gap-2">
                                <span class="px-2 py-0.5 rounded text-xs font-medium ${typeColors[mt] || typeColors['其他']}">${mt}</span>
                                <span class="text-xs text-gray-400">${natureColors[nature] || '⚪'} ${nature}</span>
                            </div>
                            <span class="text-xs text-gray-400">${formatDate(f.modified)}</span>
                        </div>
                        <p class="font-medium text-sm text-gray-800 mb-1">${f.name}</p>
                        ${meta?.theme ? `<p class="text-xs text-gray-500 mb-1.5">🎯 ${meta.theme}</p>` : ''}
                        ${meta?.impact?.summary ? `<p class="text-xs text-indigo-600 mb-1.5">📌 ${meta.impact.summary}</p>` : ''}
                        <div class="flex items-center gap-3 text-xs text-gray-400">
                            <span><i class="fas fa-ruler-combined mr-1"></i>影响: ${meta?.impact?.scope?.join('、') || '暂无'}</span>
                            <span>${formatFileSize(f.size)}</span>
                        </div>
                    </div>
                </div>`;
        }));
        container.innerHTML = cards.join('');
    } catch (error) { console.error('加载会议纪要失败:', error); }
}

// ============ 项目详情 ============

async function loadProject() {
    try {
        const response = await fetch(`/api/projects/${projectId}`);
        if (!response.ok) throw new Error('项目不存在');
        projectData = await response.json();
        
        document.getElementById('project-name').textContent = projectData.meta.name || projectId;
        document.getElementById('project-desc').textContent = projectData.meta.description || '暂无描述';
        document.getElementById('project-date').textContent = formatDate(projectData.meta.created_at);
        updateArtifactCounts(projectData.artifacts);
        updateAISidebar();
    } catch (error) {
        console.error('加载项目失败:', error);
        alert('项目不存在或加载失败');
    }
}

function updateArtifactCounts(artifacts) {
    // UI 统计合并原型 + 终稿
    const uiTotal = (artifacts.ui_prototype || 0) + (artifacts.ui_final || 0) + (artifacts.ui || 0);
    
    Object.keys(artifacts).forEach(key => {
        const el = document.getElementById(`count-${key}`);
        if (el) el.textContent = artifacts[key] || 0;
    });
    const uiEl = document.getElementById('count-ui');
    if (uiEl) uiEl.textContent = uiTotal;
}

// ============ 阶段切换 ============

function switchStage(stage) {
    currentStage = stage;
    document.querySelectorAll('.stage-btn').forEach(btn => {
        if (btn.dataset.stage === stage) {
            btn.classList.remove('bg-gray-200', 'text-gray-700');
            btn.classList.add('bg-blue-600', 'text-white');
        } else {
            btn.classList.remove('bg-blue-600', 'text-white');
            btn.classList.add('bg-gray-200', 'text-gray-700');
        }
    });
    document.querySelectorAll('.stage-content').forEach(content => content.classList.add('hidden'));
    document.getElementById(`stage-${stage}`).classList.remove('hidden');
    
    loadStageFiles(stage);
    
    // UI 阶段同时加载原型和终稿
    if (stage === 'ui') {
        loadStageFiles('ui_prototype');
        loadStageFiles('ui_final');
    }
}

// ============ 文件列表 ============

async function loadRequirementVersions(reqName) {
    try {
        const response = await fetch(`/api/projects/${projectId}/files/requirements/${encodeURIComponent(reqName)}/versions`);
        if (!response.ok) return [];
        const data = await response.json();
        return data.versions || [];
    } catch { return []; }
}

async function showDiffReport(reqName, v1, v2) {
    try {
        const response = await fetch(`/api/projects/${projectId}/files/requirements/${encodeURIComponent(reqName)}/diff-report?v1=${v1}&v2=${v2}`);
        if (!response.ok) throw new Error('获取差异报告失败');
        const data = await response.json();
        
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center';
        modal.innerHTML = `
            <div class="bg-white rounded-lg p-6 w-full max-w-4xl h-[85vh] flex flex-col">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="text-lg font-bold"><i class="fas fa-code-branch mr-2 text-blue-600"></i>版本差异：${reqName} (v${v1} → v${v2})</h3>
                    <button onclick="this.closest('.fixed').remove()" class="text-gray-500 hover:text-gray-700"><i class="fas fa-times"></i></button>
                </div>
                <div class="flex-1 overflow-y-auto bg-gray-50 rounded-lg p-4">
                    <pre class="whitespace-pre-wrap font-mono text-sm">${escapeHtml(data.content)}</pre>
                </div>
                <div class="flex justify-end mt-4">
                    <button onclick="this.closest('.fixed').remove()" class="px-4 py-2 text-gray-600">关闭</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
    } catch (e) { alert(e.message); }
}

async function loadStageFiles(stage) {
    try {
        const response = await fetch(`/api/projects/${projectId}/files/${stage}`);
        const data = await response.json();
        const container = document.getElementById(`list-${stage}`);
        if (!container) return;
        
        if (!data.files || !data.files.length) {
            container.innerHTML = `
                <div class="text-center py-6 text-gray-400 bg-gray-50 rounded-lg border border-dashed border-gray-300">
                    <i class="fas fa-folder-open text-xl mb-1"></i>
                    <p class="text-sm">暂无文件</p>
                </div>`;
            return;
        }
        
        // 需求文档特殊处理：过滤掉版本文件和差异报告，只显示主文件
        let displayFiles = data.files;
        if (stage === 'requirements') {
            displayFiles = data.files.filter(f => {
                // 过滤掉 .v1.md, .v2.md 等版本文件和 .diff.md 差异报告
                return !f.name.match(/\.v\d+\.md$/) && !f.name.endsWith('.diff.md');
            });
        }
        
        const cards = await Promise.all(displayFiles.map(async f => {
            let versionBadge = '';
            let diffButton = '';
            
            // 需求文档：加载版本信息
            if (stage === 'requirements') {
                const versions = await loadRequirementVersions(f.name);
                if (versions.length > 0) {
                    versionBadge = `<span class="ml-2 px-1.5 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">v${versions.length + 1}</span>`;
                    // 显示最新版本的差异按钮
                    const latestV = versions.length;
                    diffButton = `<button onclick="event.stopPropagation(); showDiffReport('${f.name.replace(/'/g, "\\'")}', ${latestV}, ${latestV + 1})" class="text-orange-600 hover:text-orange-800 text-sm ml-2" title="查看版本差异"><i class="fas fa-code-branch"></i></button>`;
                }
            }
            
            return `
            <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 cursor-pointer" onclick="viewFile('${stage}', '${f.name.replace(/'/g, "\\'")}')">
                <div class="flex items-center">
                    <i class="fas ${getFileIcon(f.name)} text-gray-400 mr-3"></i>
                    <div>
                        <p class="font-medium text-sm">${f.name}${versionBadge}</p>
                        <p class="text-xs text-gray-500">${formatFileSize(f.size)} · ${formatDate(f.modified)}</p>
                    </div>
                </div>
                <div class="space-x-2">
                    ${diffButton}
                    <button onclick="event.stopPropagation(); viewFile('${stage}', '${f.name.replace(/'/g, "\\'")}')" class="text-blue-600 hover:text-blue-800 text-sm"><i class="fas fa-eye"></i></button>
                    <button onclick="event.stopPropagation(); deleteFile('${stage}', '${f.name.replace(/'/g, "\\'")}')" class="text-red-600 hover:text-red-800 text-sm"><i class="fas fa-trash"></i></button>
                </div>
            </div>`;
        }));
        
        container.innerHTML = cards.join('');
    } catch (error) { console.error('加载文件失败:', error); }
}

function getFileIcon(filename) {
    if (filename.endsWith('.md')) return 'fa-file-alt';
    if (filename.endsWith('.html')) return 'fa-html5';
    if (filename.endsWith('.js')) return 'fa-js';
    if (filename.endsWith('.py')) return 'fa-python';
    if (filename.endsWith('.mp3') || filename.endsWith('.wav')) return 'fa-music';
    return 'fa-file';
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('zh-CN');
}

// ============ 文件操作 ============

function uploadFile(stage) {
    const input = document.createElement('input');
    input.type = 'file';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const formData = new FormData();
        formData.append('file', file);
        formData.append('category', stage);
        try {
            const response = await fetch(`/api/projects/${projectId}/upload`, { method: 'POST', body: formData });
            if (response.ok) {
                loadStageFiles(stage);
                loadProject();
            } else alert('上传失败');
        } catch { alert('上传失败'); }
    };
    input.click();
}

async function viewFile(stage, filename) {
    try {
        const response = await fetch(`/api/projects/${projectId}/files/${stage}/${encodeURIComponent(filename)}`);
        if (!response.ok) throw new Error('读取失败');
        const data = await response.json();
        
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center';
        modal.innerHTML = `
            <div class="bg-white rounded-lg p-6 w-full max-w-3xl h-[80vh] flex flex-col">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="text-lg font-bold">${filename}</h3>
                    <button onclick="this.closest('.fixed').remove()" class="text-gray-500 hover:text-gray-700"><i class="fas fa-times"></i></button>
                </div>
                <div class="flex-1 overflow-y-auto">
                    <textarea id="file-editor" class="w-full h-full border rounded-lg p-3 font-mono text-sm resize-none" style="min-height: 400px">${escapeHtml(data.content)}</textarea>
                </div>
                <div class="flex justify-end space-x-3 mt-4">
                    <button onclick="this.closest('.fixed').remove()" class="px-4 py-2 text-gray-600">关闭</button>
                    <button onclick="saveFile('${stage}', '${filename.replace(/'/g, "\\'")}')" class="px-4 py-2 bg-blue-600 text-white rounded-lg">保存</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
    } catch { alert('读取文件失败'); }
}

function escapeHtml(text) {
    const div = document.createElement('div'); div.textContent = text; return div.innerHTML;
}

async function saveFile(stage, filename) {
    const editor = document.getElementById('file-editor');
    if (!editor) return;
    try {
        const formData = new FormData();
        formData.append('content', editor.value);
        const response = await fetch(`/api/projects/${projectId}/files/${stage}/${encodeURIComponent(filename)}`, { method: 'POST', body: formData });
        if (response.ok) alert('保存成功');
        else alert('保存失败');
    } catch { alert('保存失败'); }
}

async function deleteFile(stage, filename) {
    if (!confirm(`确定删除 ${filename} 吗？`)) return;
    try {
        const response = await fetch(`/api/projects/${projectId}/files/${stage}/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        if (response.ok) { loadStageFiles(stage); loadProject(); }
        else alert('删除失败');
    } catch { alert('删除失败'); }
}

// ============ 会议纪要上传 ============

function uploadMeeting() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.mp3,.wav,.m4a,.ogg';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const statusDiv = document.getElementById('meeting-status');
        const statusText = document.getElementById('meeting-status-text');
        statusDiv.classList.remove('hidden');
        statusText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 正在转录，请稍候...';
        
        const formData = new FormData();
        formData.append('file', file);
        formData.append('auto_convert', 'true');
        
        try {
            const response = await fetch(`/api/projects/${projectId}/ai/transcribe`, { method: 'POST', body: formData });
            if (response.ok) {
                const result = await response.json();
                statusText.innerHTML = `<i class="fas fa-check mr-1"></i> 完成！生成 ${result.summary?.topics || 0} 议题, ${result.summary?.decisions || 0} 决策, ${result.summary?.todos || 0} 待办 ${result.summary?.llm_enhanced ? '(🤖 LLM增强)' : ''}`;
                loadMeetings();
                loadStageFiles('requirements');
                loadProject();
                setTimeout(() => statusDiv.classList.add('hidden'), 5000);
            } else {
                const error = await response.json();
                statusText.innerHTML = `<i class="fas fa-exclamation-triangle mr-1"></i> 失败: ${error.detail || '未知错误'}`;
            }
        } catch {
            statusText.innerHTML = '<i class="fas fa-exclamation-triangle mr-1"></i> 网络错误';
        }
    };
    input.click();
}

function uploadMeetingText() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.txt,.md,.markdown,.pdf,.docx,.doc';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const statusDiv = document.getElementById('meeting-status');
        const statusText = document.getElementById('meeting-status-text');
        statusDiv.classList.remove('hidden');
        statusText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 正在解析文字文档，请稍候...';
        
        const formData = new FormData();
        formData.append('file', file);
        formData.append('auto_convert', 'true');
        
        try {
            const response = await fetch(`/api/projects/${projectId}/ai/meeting-from-text`, { method: 'POST', body: formData });
            if (response.ok) {
                const result = await response.json();
                statusText.innerHTML = `<i class="fas fa-check mr-1"></i> 完成！生成 ${result.summary?.topics?.length || 0} 议题, ${result.summary?.decisions?.length || 0} 决策, ${result.summary?.todos?.length || 0} 待办 ${result.summary?.llm_enhanced ? '(🤖 LLM增强)' : ''}`;
                loadMeetings();
                loadStageFiles('requirements');
                loadProject();
                setTimeout(() => statusDiv.classList.add('hidden'), 5000);
            } else {
                const error = await response.json();
                statusText.innerHTML = `<i class="fas fa-exclamation-triangle mr-1"></i> 失败: ${error.detail || '未知错误'}`;
            }
        } catch {
            statusText.innerHTML = '<i class="fas fa-exclamation-triangle mr-1"></i> 网络错误';
        }
    };
    input.click();
}

// ============ 需求文档：文字文档→AI解析 ============

function uploadTextToRequirement() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.txt,.md,.markdown,.pdf,.docx,.doc';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const statusDiv = document.createElement('div');
        statusDiv.className = 'mb-4 bg-teal-50 border border-teal-200 rounded-lg p-3';
        statusDiv.innerHTML = '<p class="text-sm text-teal-700"><i class="fas fa-spinner fa-spin mr-1"></i> 正在解析文字文档为需求...</p>';
        const container = document.getElementById('stage-requirements');
        container.insertBefore(statusDiv, container.children[1]);
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch(`/api/projects/${projectId}/ai/requirement-from-text`, { method: 'POST', body: formData });
            if (response.ok) {
                const result = await response.json();
                statusDiv.innerHTML = `<p class="text-sm text-teal-700"><i class="fas fa-check mr-1"></i> 需求文档生成成功！已保存: ${result.requirement_file?.split('/').pop()}</p>`;
                loadStageFiles('requirements');
                loadProject();
                setTimeout(() => statusDiv.remove(), 5000);
            } else {
                const error = await response.json();
                statusDiv.innerHTML = `<p class="text-sm text-red-700"><i class="fas fa-exclamation-triangle mr-1"></i> 失败: ${error.detail || '未知错误'}</p>`;
            }
        } catch {
            statusDiv.innerHTML = '<p class="text-sm text-red-700"><i class="fas fa-exclamation-triangle mr-1"></i> 网络错误</p>';
        }
    };
    input.click();
}

// ============ PRD 从需求生成 ============

async function generatePRD() {
    try {
        const response = await fetch(`/api/projects/${projectId}/files/requirements`);
        const data = await response.json();
        if (!data.files || !data.files.length) { alert('没有需求文件'); return; }
        
        const selected = await showRequirementSelector(data.files);
        if (!selected || !selected.length) return;
        
        const statusDiv = document.getElementById('prd-status');
        const statusText = document.getElementById('prd-status-text');
        statusDiv.classList.remove('hidden');
        statusText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 正在生成 PRD...';
        
        const formData = new FormData();
        formData.append('requirement_files', selected.join(','));
        
        const prdResponse = await fetch(`/api/projects/${projectId}/ai/generate-prd`, { method: 'POST', body: formData });
        if (prdResponse.ok) {
            const result = await prdResponse.json();
            statusText.innerHTML = `<i class="fas fa-check mr-1"></i> PRD 生成成功！基于 ${result.based_on?.length || 0} 个需求`;
            loadStageFiles('prd');
            loadProject();
            setTimeout(() => statusDiv.classList.add('hidden'), 3000);
        } else {
            const error = await prdResponse.json();
            statusText.innerHTML = `<i class="fas fa-exclamation-triangle mr-1"></i> 失败: ${error.detail || '未知错误'}`;
        }
    } catch { alert('生成 PRD 失败'); }
}

function showRequirementSelector(files) {
    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center';
        modal.id = 'req-selector-modal';
        modal.innerHTML = `
            <div class="bg-white rounded-lg p-6 w-full max-w-md max-h-[80vh] overflow-y-auto">
                <h3 class="text-lg font-bold mb-4">选择需求文件</h3>
                <div class="space-y-2 mb-4">
                    ${files.map(f => `
                        <label class="flex items-center p-3 bg-gray-50 rounded-lg cursor-pointer hover:bg-gray-100">
                            <input type="checkbox" value="${f.name}" class="mr-3 requirement-checkbox" checked>
                            <div>
                                <p class="font-medium text-sm">${f.name}</p>
                                <p class="text-xs text-gray-500">${formatFileSize(f.size)}</p>
                            </div>
                        </label>
                    `).join('')}
                </div>
                <div class="flex justify-end space-x-3">
                    <button onclick="document.getElementById('req-selector-modal').remove(); resolve([]);" class="px-4 py-2 text-gray-600">取消</button>
                    <button id="req-confirm-btn" class="px-4 py-2 bg-blue-600 text-white rounded-lg">确认</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
        document.getElementById('req-confirm-btn').onclick = () => {
            const selected = Array.from(modal.querySelectorAll('.requirement-checkbox:checked')).map(cb => cb.value);
            modal.remove();
            resolve(selected);
        };
    });
}

// ============ 访谈模式生成 PRD ============

function startInterviewPRD() {
    const modal = document.getElementById('interview-modal');
    const content = document.getElementById('interview-content');
    const inputArea = document.getElementById('interview-input-area');
    const doneArea = document.getElementById('interview-done-area');
    const input = document.getElementById('interview-input');
    const progress = document.getElementById('interview-progress');
    
    interviewSessionKey = null;
    interviewStep = 0;
    
    modal.classList.remove('hidden');
    inputArea.classList.remove('hidden');
    doneArea.classList.add('hidden');
    
    // 初始描述输入
    content.innerHTML = `
        <div class="text-sm text-gray-500 mb-4">
            <p class="font-bold mb-1">🎤 访谈模式</p>
            <p>通过 5 轮问答，AI 帮你对齐需求并生成 PRD。</p>
        </div>
        <div class="bg-purple-50 p-3 rounded-lg mb-2">
            <p class="text-sm font-bold text-purple-800 mb-1">Q1: 请描述你想要做什么功能？</p>
            <p class="text-xs text-purple-600">一句话描述需求背景和目标。</p>
        </div>`;
    input.placeholder = "例如：我们要做一个智能家居App，让用户可以远程控制家里的空调、灯光...";
    progress.textContent = '第 1 步：初始描述';
}

function closeInterview() {
    document.getElementById('interview-modal').classList.add('hidden');
    interviewSessionKey = null;
}

async function submitInterviewAnswer() {
    const input = document.getElementById('interview-input');
    const content = document.getElementById('interview-content');
    const progress = document.getElementById('interview-progress');
    const inputArea = document.getElementById('interview-input-area');
    const doneArea = document.getElementById('interview-done-area');
    
    const answer = input.value.trim();
    if (!answer) return;
    
    input.value = '';
    
    // 用户回答添加到对话
    content.innerHTML += `
        <div class="bg-gray-100 p-3 rounded-lg ml-4">
            <p class="text-sm text-gray-800">${escapeHtml(answer)}</p>
        </div>`;
    content.scrollTop = content.scrollHeight;
    
    // 第 0 步：提交初始描述，开始访谈
    if (interviewStep === 0) {
        progress.textContent = '提交中...';
        try {
            const formData = new FormData();
            formData.append('initial', answer);
            const response = await fetch(`/api/projects/${projectId}/ai/interview/start`, { method: 'POST', body: formData });
            if (!response.ok) throw new Error('启动失败');
            const result = await response.json();
            interviewSessionKey = result.session_key;
            interviewStep = 1;
            
            content.innerHTML += `
                <div class="bg-purple-50 p-3 rounded-lg mb-2">
                    <p class="text-sm font-bold text-purple-800 mb-1">${result.question}</p>
                </div>`;
            progress.textContent = result.progress;
            content.scrollTop = content.scrollHeight;
        } catch {
            content.innerHTML += `<p class="text-red-500 text-sm">启动访谈失败，请重试</p>`;
        }
        return;
    }
    
    // 第 1-5 步：回答问题
    progress.textContent = '思考中...';
    try {
        const formData = new FormData();
        formData.append('session_key', interviewSessionKey);
        formData.append('answer', answer);
        const response = await fetch(`/api/projects/${projectId}/ai/interview/answer`, { method: 'POST', body: formData });
        if (!response.ok) throw new Error('提交失败');
        const result = await response.json();
        
        if (result.status === 'completed') {
            // 访谈完成
            progress.textContent = '完成';
            content.innerHTML += `
                <div class="bg-green-50 p-3 rounded-lg mb-2 border border-green-200">
                    <p class="text-sm font-bold text-green-800 mb-1"><i class="fas fa-check-circle mr-1"></i>访谈完成！</p>
                    <p class="text-xs text-green-600">PRD 已生成: ${result.prd_file?.split('/').pop() || ''}</p>
                </div>`;
            inputArea.classList.add('hidden');
            doneArea.classList.remove('hidden');
            loadStageFiles('prd');
            loadProject();
        } else {
            interviewStep = result.step;
            content.innerHTML += `
                <div class="bg-purple-50 p-3 rounded-lg mb-2">
                    <p class="text-sm font-bold text-purple-800 mb-1">${result.question}</p>
                </div>`;
            progress.textContent = result.progress;
            content.scrollTop = content.scrollHeight;
        }
    } catch {
        content.innerHTML += `<p class="text-red-500 text-sm">提交失败，请重试</p>`;
    }
}

// ============ 文档直传生成 PRD ============

function uploadDocToPRD() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.md,.txt,.doc,.docx,.pdf';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const statusDiv = document.getElementById('prd-status');
        const statusText = document.getElementById('prd-status-text');
        statusDiv.classList.remove('hidden');
        statusText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 正在从文档生成 PRD...';
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch(`/api/projects/${projectId}/ai/generate-prd-from-docs`, { method: 'POST', body: formData });
            if (response.ok) {
                const result = await response.json();
                statusText.innerHTML = `<i class="fas fa-check mr-1"></i> PRD 从文档生成成功！`;
                loadStageFiles('prd');
                loadProject();
                setTimeout(() => statusDiv.classList.add('hidden'), 3000);
            } else {
                const error = await response.json();
                statusText.innerHTML = `<i class="fas fa-exclamation-triangle mr-1"></i> 失败: ${error.detail || '未知错误'}`;
            }
        } catch {
            statusText.innerHTML = '<i class="fas fa-exclamation-triangle mr-1"></i> 网络错误';
        }
    };
    input.click();
}

// ============ 飞书文档生成 PRD ============

function fetchFeishuToPRD() {
    document.getElementById('feishu-modal').classList.remove('hidden');
}

function closeFeishuModal() {
    document.getElementById('feishu-modal').classList.add('hidden');
}

async function submitFeishuPRD() {
    const token = document.getElementById('feishu-doc-token').value.trim();
    const name = document.getElementById('feishu-doc-name').value.trim() || '飞书文档';
    
    if (!token) { alert('请输入文档 Token'); return; }
    
    // 从 URL 中提取 token
    let docToken = token;
    if (token.includes('/')) {
        const match = token.match(//([a-zA-Z0-9]+)(?:\?|$)/);
        if (match) docToken = match[1];
    }
    
    const statusDiv = document.getElementById('prd-status');
    const statusText = document.getElementById('prd-status-text');
    statusDiv.classList.remove('hidden');
    statusText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 正在从飞书拉取并生成 PRD...';
    closeFeishuModal();
    
    try {
        const formData = new FormData();
        formData.append('doc_token', docToken);
        formData.append('doc_name', name);
        
        const response = await fetch(`/api/projects/${projectId}/ai/generate-prd-from-feishu`, { method: 'POST', body: formData });
        if (response.ok) {
            const result = await response.json();
            statusText.innerHTML = `<i class="fas fa-check mr-1"></i> PRD 从飞书生成成功！`;
            loadStageFiles('prd');
            loadProject();
            setTimeout(() => statusDiv.classList.add('hidden'), 3000);
        } else {
            const error = await response.json();
            statusText.innerHTML = `<i class="fas fa-exclamation-triangle mr-1"></i> 失败: ${error.detail || '未知错误'}`;
        }
    } catch {
        statusText.innerHTML = '<i class="fas fa-exclamation-triangle mr-1"></i> 网络错误';
    }
}

async function aiGenerate(stage) {
    alert(`${stage} 的 AI 生成功能开发中...`);
}

// ============ UI 原型生成 ============

async function generateUIPrototype() {
    // 获取 PRD 列表
    try {
        const response = await fetch(`/api/projects/${projectId}/files/prd`);
        const data = await response.json();
        if (!data.files || !data.files.length) { alert('没有 PRD 文件，请先生成 PRD'); return; }
        
        const prdFile = await showSingleFileSelector(data.files, '选择 PRD 文件');
        if (!prdFile) return;
        
        const statusDiv = document.getElementById('prd-status');
        const statusText = document.getElementById('prd-status-text');
        statusDiv.classList.remove('hidden');
        statusText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 正在从 PRD 生成 UI 原型...';
        
        const formData = new FormData();
        formData.append('prd_file', prdFile);
        
        const response2 = await fetch(`/api/projects/${projectId}/ai/generate-ui-prototype`, { method: 'POST', body: formData });
        if (response2.ok) {
            const result = await response2.json();
            statusText.innerHTML = `<i class="fas fa-check mr-1"></i> UI 原型生成成功！${result.html_file?.split('/').pop() || ''}`;
            loadStageFiles('ui_prototype');
            loadProject();
            setTimeout(() => statusDiv.classList.add('hidden'), 3000);
        } else {
            const error = await response2.json();
            statusText.innerHTML = `<i class="fas fa-exclamation-triangle mr-1"></i> 失败: ${error.detail || '未知错误'}`;
        }
    } catch { alert('生成 UI 原型失败'); }
}

function showSingleFileSelector(files, title) {
    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center';
        modal.innerHTML = `
            <div class="bg-white rounded-lg p-6 w-full max-w-md max-h-[80vh] overflow-y-auto">
                <h3 class="text-lg font-bold mb-4">${title}</h3>
                <div class="space-y-2 mb-4">
                    ${files.map(f => `
                        <label class="flex items-center p-3 bg-gray-50 rounded-lg cursor-pointer hover:bg-gray-100">
                            <input type="radio" name="file-select" value="${f.name}" class="mr-3" ${f === files[0] ? 'checked' : ''}>
                            <div>
                                <p class="font-medium text-sm">${f.name}</p>
                                <p class="text-xs text-gray-500">${formatFileSize(f.size)}</p>
                            </div>
                        </label>
                    `).join('')}
                </div>
                <div class="flex justify-end space-x-3">
                    <button onclick="this.closest('.fixed').remove(); window._fileSelectorResolve(null);" class="px-4 py-2 text-gray-600">取消</button>
                    <button id="file-sel-confirm" class="px-4 py-2 bg-blue-600 text-white rounded-lg">确认</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
        window._fileSelectorResolve = resolve;
        document.getElementById('file-sel-confirm').onclick = () => {
            const checked = modal.querySelector('input[name="file-select"]:checked');
            modal.remove();
            resolve(checked ? checked.value : null);
        };
    });
}

function uploadDesign() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        alert('设计稿已选择，AI 生成 HTML 功能开发中...');
    };
    input.click();
}

// ============ 测试用例生成 ============

async function generateTestcases() {
    try {
        // 获取 PRD
        const prdResponse = await fetch(`/api/projects/${projectId}/files/prd`);
        const prdData = await prdResponse.json();
        if (!prdData.files || !prdData.files.length) { alert('没有 PRD 文件'); return; }
        const prdFile = await showSingleFileSelector(prdData.files, '选择 PRD 文件');
        if (!prdFile) return;
        
        // 可选：获取 UI 终稿
        let uiFile = '';
        const uiResponse = await fetch(`/api/projects/${projectId}/files/ui_final`);
        const uiData = await uiResponse.json();
        if (uiData.files && uiData.files.length) {
            const selected = await showSingleFileSelector(uiData.files, '选择 UI 终稿（可选）');
            if (selected) uiFile = selected;
        }
        
        const statusDiv = document.getElementById('prd-status');
        const statusText = document.getElementById('prd-status-text');
        statusDiv.classList.remove('hidden');
        statusText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 正在生成测试用例...';
        
        const formData = new FormData();
        formData.append('prd_file', prdFile);
        if (uiFile) formData.append('ui_file', uiFile);
        
        const response = await fetch(`/api/projects/${projectId}/ai/generate-testcases`, { method: 'POST', body: formData });
        if (response.ok) {
            const result = await response.json();
            statusText.innerHTML = `<i class="fas fa-check mr-1"></i> 测试用例生成成功！`;
            loadStageFiles('testcases');
            loadProject();
            setTimeout(() => statusDiv.classList.add('hidden'), 3000);
        } else {
            const error = await response.json();
            statusText.innerHTML = `<i class="fas fa-exclamation-triangle mr-1"></i> 失败: ${error.detail || '未知错误'}`;
        }
    } catch { alert('生成测试用例失败'); }
}

// ============ 自动化测试执行 ============

async function runAutomationTests() {
    // 先获取测试用例列表
    try {
        const response = await fetch(`/api/projects/${projectId}/files/testcases`);
        const data = await response.json();
        
        const select = document.getElementById('runtest-file-select');
        select.innerHTML = '';
        
        if (!data.files || !data.files.length) {
            select.innerHTML = '<option>请先上传或生成测试用例</option>';
        } else {
            data.files.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f.name;
                opt.textContent = f.name;
                select.appendChild(opt);
            });
        }
        
        document.getElementById('runtest-modal').classList.remove('hidden');
        document.getElementById('runtest-status').classList.add('hidden');
        document.getElementById('runtest-result').classList.add('hidden');
    } catch { alert('加载测试用例失败'); }
}

function closeRuntestModal() {
    document.getElementById('runtest-modal').classList.add('hidden');
}

async function submitRuntest() {
    const testFile = document.getElementById('runtest-file-select').value;
    const appUrl = document.getElementById('runtest-url').value;
    
    if (!testFile || testFile.includes('请先')) { alert('请选择测试文件'); return; }
    
    const statusDiv = document.getElementById('runtest-status');
    const statusText = document.getElementById('runtest-status-text');
    const resultDiv = document.getElementById('runtest-result');
    const output = document.getElementById('runtest-output');
    
    statusDiv.classList.remove('hidden');
    resultDiv.classList.add('hidden');
    statusText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 执行中，请稍候（可能需要几分钟）...';
    
    try {
        const formData = new FormData();
        formData.append('test_file', testFile);
        formData.append('app_url', appUrl);
        
        const response = await fetch(`/api/projects/${projectId}/ai/run-tests`, { method: 'POST', body: formData });
        const result = await response.json();
        
        statusDiv.classList.add('hidden');
        resultDiv.classList.remove('hidden');
        
        const success = result.success;
        output.innerHTML = `${success ? '✅ 测试通过' : '❌ 测试失败'} (exit: ${result.exit_code})\n\n${result.stdout_preview}\n\n${result.stderr_preview}`;
    } catch {
        statusText.innerHTML = '<i class="fas fa-exclamation-triangle mr-1"></i> 执行失败';
    }
}

// ============ 其他 ============

function showAIAssistant() {
    document.getElementById('ai-sidebar').classList.toggle('translate-x-full');
}

function showProjectSettings() {
    alert('项目设置功能开发中...');
}

function updateAISidebar() {
    const suggestions = document.getElementById('history-suggestions');
    if (suggestions) {
        suggestions.innerHTML = `
            <li class="text-gray-400">暂无历史方案推荐</li>
            <li class="text-gray-400">知识库功能开发中...</li>`;
    }
}

// Enter 发送访谈
function initInterviewEnter() {
    const input = document.getElementById('interview-input');
    if (input) {
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submitInterviewAnswer();
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', initInterviewEnter);
