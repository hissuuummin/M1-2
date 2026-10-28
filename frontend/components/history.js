/**
 * 투자거울: 대화 기록 컴포넌트 (history.js)
 * 이전 대화 세션 목록 조회, 대화 본문 불러오기, 대화 삭제 및 새 대화 시작
 */

const HistoryComponent = {
  async render(container) {
    container.innerHTML = `
      <div class="history-container">
        <div class="history-header">
          <div class="history-title-group">
            <h2>🕒 대화 기록</h2>
            <p class="history-subtitle">이전에 투자거울과 나눈 대화를 다시 불러와 복기 내용을 확인하거나 이어서 대화할 수 있습니다.</p>
          </div>
          <button class="btn-primary btn-sm" onclick="window.HistoryComponent.startNewChat()">
            + 새 대화 시작
          </button>
        </div>

        <div id="conversations-list-container" class="conversations-grid">
          <div class="loading-state">대화 기록을 불러오는 중입니다...</div>
        </div>
      </div>
    `;

    try {
      const list = await window.Api.listConversations();
      window.store.setState({ conversations: list });
      this.renderList(container, list);
    } catch (err) {
      container.querySelector('#conversations-list-container').innerHTML = `
        <div class="error-state">대화 목록을 불러오지 못했습니다: ${err.message}</div>
      `;
    }
  },

  renderList(container, list) {
    const listEl = container.querySelector('#conversations-list-container');
    if (!listEl) return;

    if (!list || list.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">💬</div>
          <h3>저장된 대화 기록이 없습니다.</h3>
          <p>AI 비서에게 질문을 남기면 대화 세션이 이곳에 자동으로 보관됩니다.</p>
          <button class="btn-primary btn-sm" onclick="window.Main.switchTab('chat')">첫 대화 시작하기</button>
        </div>
      `;
      return;
    }

    listEl.innerHTML = list.map((c) => {
      const activeId = window.store.getState().currentConversationId;
      const isActive = c.id === activeId;
      const dt = c.created_at ? c.created_at.substring(0, 10) : '';

      return `
        <div class="conversation-card ${isActive ? 'active-card' : ''}">
          <div class="card-top">
            <span class="conv-date">${dt}</span>
            <span class="conv-count">메시지 ${c.message_count}개</span>
          </div>
          <h4 class="conv-title">${c.title || '새 대화'}</h4>
          <div class="conv-actions">
            <button class="btn-primary btn-sm" onclick="window.HistoryComponent.loadConversation('${c.id}')">
              불러오기
            </button>
            <button class="btn-outline btn-sm btn-danger" onclick="window.HistoryComponent.deleteConversation('${c.id}')">
              삭제
            </button>
          </div>
        </div>
      `;
    }).join('');
  },

  async loadConversation(convId) {
    try {
      const conv = await window.Api.getConversation(convId);
      window.store.setState({
        currentConversationId: conv.id,
        messages: conv.messages || []
      });
      window.Main.switchTab('chat');
    } catch (err) {
      alert(`대화 불러오기 실패: ${err.message}`);
    }
  },

  async deleteConversation(convId) {
    if (!confirm('이 대화 기록을 삭제하시겠습니까?')) return;
    try {
      await window.Api.deleteConversation(convId);
      const list = await window.Api.listConversations();
      window.store.setState({ conversations: list });

      // If deleted current conversation, reset it
      if (window.store.getState().currentConversationId === convId) {
        window.store.setState({ currentConversationId: null, messages: [] });
      }

      const container = document.getElementById('tab-content');
      this.renderList(container, list);
    } catch (err) {
      alert(`삭제 실패: ${err.message}`);
    }
  },

  startNewChat() {
    window.store.setState({
      currentConversationId: null,
      messages: []
    });
    window.Main.switchTab('chat');
  }
};

window.HistoryComponent = HistoryComponent;
