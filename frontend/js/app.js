// AI-PM 主应用逻辑

// 全局状态
let projects = [];
let currentProject = null;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadProjects();
});

// 加载项目列表
async function loadProjects() {
    try {
        const response = await fetch('/api/projects');
        const data = await response.json();
        projects = data.projects || [];
        renderProjects();
        updateStats();
    } catch (error) {
        console.error('加载项目失败:', error);
        showError('加载项目失败，请检查服务是否运行');
    }
}

// 渲染项目列表
function renderProjects() {
    const container = document.getElementById('project-list');
    const emptyState = document.getElementById('empty-state');
    
    if (!projects.length) {
        container.innerHTML = '';
        emptyState.classList.remove('hidden');
        return;
    }
    
    emptyState.classList.add('hidden');
    container.innerHTML = projects.map(p => `
        <div class="project-card bg-white rounded-lg shadow-sm p-6 cursor-pointer" onclick="openProject('${p.id}')">
            <div class="flex justify-between items-start mb-3">
                <div class="flex items-center">
                    <div class="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center mr-3">
                        <i class="fas fa-project-diagram text-blue-600"></i>
                    </div>
                    <div>
                        <h3 class="font-bold text-gray-900">${p.name}</h3>
                        <p class="text-xs text-gray-500">${p.description || '暂无描述'}</p>
                    </div>
                </div>
                <span class="stage-badge ${p.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}">
                    ${p.status === 'active' ? '进行中' : '已归档'}
                </span>
            </div>
            <div class="flex items-center text-xs text-gray-500 mt-4">
                <span class="mr-4"><i class="far fa-calendar mr-1"></i>${formatDate(p.created_at)}</span>
                <span><i class="fas fa-file-alt mr-1"></i>${countArtifacts(p.id)} 个产物</span>
            </div>
        </div>
    `).join('');
}

// 更新统计
function updateStats() {
    document.getElementById('stat-total').textContent = projects.length;
    document.getElementById('stat-active').textContent = projects.filter(p => p.status === 'active').length;
    // 会议纪要和 PRD 数需要后端支持，暂时显示 0
    document.getElementById('stat-meetings').textContent = '0';
    document.getElementById('stat-prd').textContent = '0';
}

// 格式化日期
function formatDate(dateStr) {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('zh-CN');
}

// 统计产物数（简化）
function countArtifacts(projectId) {
    return 0; // 需要后端支持
}

// 打开项目
function openProject(projectId) {
    window.location.href = `/project/${projectId}`;
}

// 显示创建项目弹窗
function showCreateProject() {
    document.getElementById('create-modal').classList.remove('hidden');
}

// 隐藏创建项目弹窗
function hideCreateProject() {
    document.getElementById('create-modal').classList.add('hidden');
    document.getElementById('project-name').value = '';
    document.getElementById('project-desc').value = '';
}

// 创建项目
async function createProject() {
    const name = document.getElementById('project-name').value.trim();
    const desc = document.getElementById('project-desc').value.trim();
    
    if (!name) {
        alert('请输入项目名称');
        return;
    }
    
    try {
        const formData = new FormData();
        formData.append('name', name);
        formData.append('description', desc);
        
        const response = await fetch('/api/projects', {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            const data = await response.json();
            hideCreateProject();
            loadProjects();
            // 自动跳转到新项目
            setTimeout(() => openProject(data.id), 500);
        } else {
            const error = await response.json();
            alert('创建失败: ' + (error.detail || '未知错误'));
        }
    } catch (error) {
        console.error('创建项目失败:', error);
        alert('创建失败，请检查服务');
    }
}

// 显示 AI 状态
async function showAIStatus() {
    try {
        const response = await fetch('/api/ai/status');
        const status = await response.json();
        
        let msg = '🤖 AI 状态:\n\n';
        msg += `Whisper: ${status.whisper.installed ? '✅ 已安装' : '❌ 未安装'}\n`;
        if (status.whisper.model) msg += `  模型: ${status.whisper.model}\n`;
        msg += `\nOllama: ${status.ollama.available ? '✅ 可用' : '❌ 未检测'}\n`;
        if (status.ollama.models.length) msg += `  模型: ${status.ollama.models.join(', ')}\n`;
        msg += `\nAPI Key: ${status.api_key.configured ? '✅ 已配置' : '❌ 未配置'}\n`;
        if (status.api_key.provider) msg += `  提供商: ${status.api_key.provider}\n`;
        
        alert(msg);
    } catch (error) {
        alert('获取 AI 状态失败');
    }
}

// 显示设置
function showSettings() {
    alert('设置功能开发中...');
}

// AI 聊天面板
function toggleAIChat() {
    const panel = document.getElementById('ai-chat-panel');
    panel.classList.toggle('hidden');
}

function sendChat() {
    const input = document.getElementById('chat-input');
    const messages = document.getElementById('chat-messages');
    const text = input.value.trim();
    
    if (!text) return;
    
    // 添加用户消息
    messages.innerHTML += `
        <div class="bg-blue-100 p-3 rounded-lg text-sm ml-8">
            <p class="font-bold text-blue-800">你</p>
            <p>${text}</p>
        </div>
    `;
    
    input.value = '';
    messages.scrollTop = messages.scrollHeight;
    
    // 模拟 AI 回复（后续接入真实 API）
    setTimeout(() => {
        messages.innerHTML += `
            <div class="bg-gray-100 p-3 rounded-lg text-sm">
                <p class="font-bold text-gray-700">AI 助手</p>
                <p>收到！我正在思考...（AI 回复功能待接入）</p>
            </div>
        `;
        messages.scrollTop = messages.scrollHeight;
    }, 1000);
}

// 显示错误
function showError(msg) {
    console.error(msg);
}

// Enter 发送消息
document.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendChat();
        });
    }
});
