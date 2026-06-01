// 项目工作台逻辑

// 从 URL 获取项目 ID
const projectId = window.location.pathname.split('/').pop();

// 全局状态
let projectData = null;
let currentStage = 'requirements';

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadProject();
    loadStageFiles(currentStage);
    loadMeetings(); // 独立加载会议纪要
});

// 加载会议纪要（独立层级）- 从 JSON meta 读取类型和影响
async function loadMeetings() {
    try {
        // 获取文件列表
        const response = await fetch(`/api/projects/${projectId}/files/meetings`);
        const data = await response.json();
        
        const container = document.getElementById('list-meetings');
        if (!container) return;
        
        if (!data.files || !data.files.length) {
            container.innerHTML = `
                <div class="text-center py-6 text-gray-400 bg-gray-50 rounded-lg border border-dashed border-gray-300">
                    <i class="fas fa-microphone-slash text-2xl mb-2"></i>
                    <p class="text-sm">暂无会议纪要，上传录音开始转录</p>
                </div>
            `;
            return;
        }
        
        // 只处理 .md 文件，跳过 .json meta 文件
        const mdFiles = data.files.filter(f => f.name.endsWith('.md'));
        
        // 为每个会议纪要读取 meta JSON
        const cards = await Promise.all(mdFiles.map(async f => {
            // 尝试读取对应的 JSON meta 文件
            const metaName = f.name.replace('.md', '.json');
            let meta = null;
            try {
                const metaResp = await fetch(`/api/projects/${projectId}/files/meetings/${encodeURIComponent(metaName)}`);
                if (metaResp.ok) {
                    const metaData = await metaResp.json();
                    meta = JSON.parse(metaData.content);
                }
            } catch (e) {
                // meta 文件不存在或解析失败，忽略
            }
            
            // 类型标签颜色
            const typeColors = {
                '项目启动': 'bg-purple-100 text-purple-700',
                '需求评审': 'bg-blue-100 text-blue-700',
                'UI评审': 'bg-pink-100 text-pink-700',
                '技术方案评审': 'bg-orange-100 text-orange-700',
                '站会': 'bg-green-100 text-green-700',
                '复盘回顾': 'bg-gray-100 text-gray-700',
                '其他': 'bg-gray-100 text-gray-600'
            };
            
            // 影响性质颜色
            const natureColors = {
                '推进': '🟢',
                '调整': '🟡',
                '纠偏': '🔴',
                '补充': '🔵',
                '信息同步': '⚪'
            };
            
            const meetingType = meta?.meeting_type || '其他';
            const typeClass = typeColors[meetingType] || typeColors['其他'];
            const theme = meta?.theme || '';
            const impact = meta?.impact || {};
            const nature = impact.nature || '信息同步';
            const natureIcon = natureColors[nature] || '⚪';
            const scope = impact.scope?.length ? impact.scope.join('、') : '暂无';
            const impactSummary = impact.summary || '';
            
            return `
                <div class="bg-white rounded-lg border border-gray-200 hover:border-indigo-300 transition-all">
                    <div class="p-3 cursor-pointer" onclick="viewFile('meetings', '${f.name.replace(/'/g, "\\'")}')">
                        <div class="flex items-center justify-between mb-2">
                            <div class="flex items-center gap-2">
                                <span class="px-2 py-0.5 rounded text-xs font-medium ${typeClass}">
                                    ${meetingType}
                                </span>
                                <span class="text-xs text-gray-400">${natureIcon} ${nature}</span>
                            </div>
                            <span class="text-xs text-gray-400">${formatDate(f.modified)}</span>
                        </div>
                        <p class="font-medium text-sm text-gray-800 mb-1">${f.name}</p>
                        ${theme ? `<p class="text-xs text-gray-500 mb-1.5">🎯 ${theme}</p>` : ''}
                        ${impactSummary ? `<p class="text-xs text-indigo-600 mb-1.5">📌 ${impactSummary}</p>` : ''}
                        <div class="flex items-center gap-3 text-xs text-gray-400">
                            <span><i class="fas fa-ruler-combined mr-1"></i>影响: ${scope}</span>
                            <span>${formatFileSize(f.size)}</span>
                        </div>
                    </div>
                </div>
            `;
        }));
        
        container.innerHTML = cards.join('');
        
    } catch (error) {
        console.error('加载会议纪要失败:', error);
    }
}

// 加载项目详情
async function loadProject() {
    try {
        const response = await fetch(`/api/projects/${projectId}`);
        if (!response.ok) throw new Error('项目不存在');
        
        projectData = await response.json();
        
        // 更新页面信息
        document.getElementById('project-name').textContent = projectData.meta.name || projectId;
        document.getElementById('project-desc').textContent = projectData.meta.description || '暂无描述';
        document.getElementById('project-date').textContent = formatDate(projectData.meta.created_at);
        
        // 更新统计
        updateArtifactCounts(projectData.artifacts);
        
        // 更新 AI 侧边栏
        updateAISidebar();
        
    } catch (error) {
        console.error('加载项目失败:', error);
        alert('项目不存在或加载失败');
    }
}

// 更新产物统计
function updateArtifactCounts(artifacts) {
    Object.keys(artifacts).forEach(key => {
        const el = document.getElementById(`count-${key}`);
        if (el) el.textContent = artifacts[key] || 0;
    });
}

// 切换阶段
function switchStage(stage) {
    currentStage = stage;
    
    // 更新按钮样式
    document.querySelectorAll('.stage-btn').forEach(btn => {
        if (btn.dataset.stage === stage) {
            btn.classList.remove('bg-gray-200', 'text-gray-700');
            btn.classList.add('bg-blue-600', 'text-white');
        } else {
            btn.classList.remove('bg-blue-600', 'text-white');
            btn.classList.add('bg-gray-200', 'text-gray-700');
        }
    });
    
    // 显示对应内容
    document.querySelectorAll('.stage-content').forEach(content => {
        content.classList.add('hidden');
    });
    document.getElementById(`stage-${stage}`).classList.remove('hidden');
    
    // 加载文件列表
    loadStageFiles(stage);
}

// 加载阶段文件列表
async function loadStageFiles(stage) {
    try {
        const response = await fetch(`/api/projects/${projectId}/files/${stage}`);
        const data = await response.json();
        
        const container = document.getElementById(`list-${stage}`);
        if (!container) return;
        
        if (!data.files || !data.files.length) {
            container.innerHTML = `
                <div class="text-center py-10 text-gray-400">
                    <i class="fas fa-folder-open text-3xl mb-2"></i>
                    <p>暂无文件</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = data.files.map(f => `
            <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 cursor-pointer" onclick="viewFile('${stage}', '${f.name.replace(/'/g, "\\'")}')">
                <div class="flex items-center">
                    <i class="fas ${getFileIcon(f.name)} text-gray-400 mr-3"></i>
                    <div>
                        <p class="font-medium text-sm">${f.name}</p>
                        <p class="text-xs text-gray-500">${formatFileSize(f.size)} · ${formatDate(f.modified)}</p>
                    </div>
                </div>
                <div class="space-x-2">
                    <button onclick="event.stopPropagation(); viewFile('${stage}', '${f.name.replace(/'/g, "\\'")}')" class="text-blue-600 hover:text-blue-800 text-sm">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button onclick="event.stopPropagation(); deleteFile('${stage}', '${f.name.replace(/'/g, "\\'")}')" class="text-red-600 hover:text-red-800 text-sm">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('加载文件失败:', error);
    }
}

// 获取文件图标
function getFileIcon(filename) {
    if (filename.endsWith('.md')) return 'fa-file-alt';
    if (filename.endsWith('.html')) return 'fa-html5';
    if (filename.endsWith('.js')) return 'fa-js';
    if (filename.endsWith('.css')) return 'fa-css3';
    if (filename.endsWith('.json')) return 'fa-code';
    if (filename.endsWith('.py')) return 'fa-python';
    if (filename.endsWith('.mp3') || filename.endsWith('.wav')) return 'fa-music';
    return 'fa-file';
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// 格式化日期
function formatDate(dateStr) {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('zh-CN');
}

// 上传文件
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
            const response = await fetch(`/api/projects/${projectId}/upload`, {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                loadStageFiles(stage);
                loadProject(); // 刷新统计
            } else {
                alert('上传失败');
            }
        } catch (error) {
            console.error('上传失败:', error);
            alert('上传失败');
        }
    };
    input.click();
}

// 上传录音（会议纪要专用）- 调用 AI 转录
function uploadMeeting() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.mp3,.wav,.m4a,.ogg';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        // 显示状态
        const statusDiv = document.getElementById('meeting-status');
        const statusText = document.getElementById('meeting-status-text');
        statusDiv.classList.remove('hidden');
        statusText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 正在转录，请稍候...';
        
        // 调用后端转录 API
        const formData = new FormData();
        formData.append('file', file);
        formData.append('auto_convert', 'true');
        
        try {
            const response = await fetch(`/api/projects/${projectId}/ai/transcribe`, {
                method: 'POST',
                body: formData
            });
            
            if (response.ok) {
                const result = await response.json();
                statusText.innerHTML = `
                    <i class="fas fa-check mr-1"></i> 
                    完成！生成 ${result.summary?.topics || 0} 议题, 
                    ${result.summary?.decisions || 0} 决策, 
                    ${result.summary?.todos || 0} 待办
                    ${result.summary?.llm_enhanced ? '(🤖 LLM增强)' : ''}
                `;
                
                // 刷新会议纪要和需求列表
                loadMeetings();  // 独立刷新会议纪要（带类型标签）
                loadStageFiles('requirements');
                loadProject();
                
                // 3秒后隐藏状态
                setTimeout(() => statusDiv.classList.add('hidden'), 5000);
            } else {
                const error = await response.json();
                statusText.innerHTML = `<i class="fas fa-exclamation-triangle mr-1"></i> 失败: ${error.detail || '未知错误'}`;
                statusDiv.classList.remove('bg-blue-50', 'border-blue-200');
                statusDiv.classList.add('bg-red-50', 'border-red-200');
                statusText.classList.remove('text-blue-700');
                statusText.classList.add('text-red-700');
            }
        } catch (error) {
            console.error('处理录音失败:', error);
            statusText.innerHTML = '<i class="fas fa-exclamation-triangle mr-1"></i> 网络错误';
        }
    };
    input.click();
}

// AI 生成 PRD
async function generatePRD() {
    // 先获取需求列表
    try {
        const response = await fetch(`/api/projects/${projectId}/files/requirements`);
        const data = await response.json();
        
        if (!data.files || !data.files.length) {
            alert('没有需求文件，请先上传或生成需求');
            return;
        }
        
        // 显示选择对话框
        const selected = await showRequirementSelector(data.files);
        if (!selected || !selected.length) return;
        
        // 显示生成状态
        const statusDiv = document.getElementById('prd-status');
        const statusText = document.getElementById('prd-status-text');
        statusDiv.classList.remove('hidden');
        statusText.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> 正在生成 PRD，请稍候...';
        
        // 调用 PRD 生成 API
        const formData = new FormData();
        formData.append('requirement_files', selected.join(','));
        
        const prdResponse = await fetch(`/api/projects/${projectId}/ai/generate-prd`, {
            method: 'POST',
            body: formData
        });
        
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
    } catch (error) {
        console.error('生成 PRD 失败:', error);
        alert('生成 PRD 失败');
    }
}

// 显示需求选择对话框
function showRequirementSelector(files) {
    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center';
        modal.id = 'req-selector-modal';
        modal.innerHTML = `
            <div class="bg-white rounded-lg p-6 w-full max-w-md max-h-[80vh] overflow-y-auto">
                <h3 class="text-lg font-bold mb-4">选择需求文件</h3>
                <div class="space-y-2 mb-4" id="req-selector-list">
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
                    <button id="req-cancel-btn" class="px-4 py-2 text-gray-600">取消</button>
                    <button id="req-confirm-btn" class="px-4 py-2 bg-blue-600 text-white rounded-lg">确认</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // 绑定事件
        document.getElementById('req-cancel-btn').onclick = () => {
            modal.remove();
            resolve([]);
        };
        document.getElementById('req-confirm-btn').onclick = () => {
            const checkboxes = modal.querySelectorAll('.requirement-checkbox:checked');
            const selected = Array.from(checkboxes).map(cb => cb.value);
            modal.remove();
            resolve(selected);
        };
    });
}

// 查看文件内容
async function viewFile(stage, filename) {
    try {
        const encodedName = encodeURIComponent(filename);
        const response = await fetch(`/api/projects/${projectId}/files/${stage}/${encodedName}`);
        if (!response.ok) throw new Error('读取失败');
        
        const data = await response.json();
        
        // 显示内容对话框
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center';
        modal.innerHTML = `
            <div class="bg-white rounded-lg p-6 w-full max-w-3xl h-[80vh] flex flex-col">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="text-lg font-bold">${filename}</h3>
                    <button onclick="this.closest('.fixed').remove()" class="text-gray-500 hover:text-gray-700">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="flex-1 overflow-y-auto">
                    <textarea id="file-editor" class="w-full h-full border rounded-lg p-3 font-mono text-sm resize-none" style="min-height: 400px">${escapeHtml(data.content)}</textarea>
                </div>
                <div class="flex justify-end space-x-3 mt-4">
                    <button onclick="this.closest('.fixed').remove()" class="px-4 py-2 text-gray-600">关闭</button>
                    <button onclick="saveFile('${stage}', '${filename}')" class="px-4 py-2 bg-blue-600 text-white rounded-lg">保存</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    } catch (error) {
        console.error('读取文件失败:', error);
        alert('读取文件失败');
    }
}

// HTML 转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 保存文件
async function saveFile(stage, filename) {
    const editor = document.getElementById('file-editor');
    if (!editor) return;
    
    const content = editor.value;
    
    try {
        const formData = new FormData();
        formData.append('content', content);
        
        const encodedName = encodeURIComponent(filename);
        const response = await fetch(`/api/projects/${projectId}/files/${stage}/${encodedName}`, {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            alert('保存成功');
        } else {
            alert('保存失败');
        }
    } catch (error) {
        console.error('保存失败:', error);
        alert('保存失败');
    }
}

// 删除文件
async function deleteFile(stage, filename) {
    if (!confirm(`确定删除 ${filename} 吗？`)) return;
    alert('删除功能开发中...');
}

// 上传设计稿
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

// 执行自动化测试
function runAutomation() {
    alert('自动化测试执行功能开发中...');
}

// 显示 AI 助手
function showAIAssistant() {
    const sidebar = document.getElementById('ai-sidebar');
    sidebar.classList.toggle('translate-x-full');
}

// 显示项目设置
function showProjectSettings() {
    alert('项目设置功能开发中...');
}

// 更新 AI 侧边栏
function updateAISidebar() {
    // TODO: 加载历史方案推荐
    const suggestions = document.getElementById('history-suggestions');
    if (suggestions) {
        suggestions.innerHTML = `
            <li class="text-gray-400">暂无历史方案推荐</li>
            <li class="text-gray-400">知识库功能开发中...</li>
        `;
    }
}
