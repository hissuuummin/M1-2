/**
 * 투자거울: 메인 애플리케이션 엔트리포인트 (main.js)
 * 탭 전환, 서버 헬스체크 및 콜드스타트 관리, 데이터 동기화
 */

const Main = {
  async init() {
    console.log("🚀 Initializing 투자거울 (Investment Mirror)...");

    // Apply saved theme
    const theme = window.store.getState().theme;
    document.documentElement.setAttribute('data-theme', theme);

    // Initialize Auth
    window.Auth.init();

    // Bind Global Header & Nav Events
    this.bindGlobalEvents();

    // Subscribe to store updates
    window.store.subscribe((state) => {
      this.updateHeader(state);
    });

    // Check backend health & cold-start
    await this.checkServerStatus();

    // Initial data refresh
    await this.refreshData();

    // Render initial tab (Chat)
    this.switchTab('chat');
  },

  bindGlobalEvents() {
    // Nav Tabs
    document.querySelectorAll('.nav-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        const target = tab.getAttribute('data-tab');
        this.switchTab(target);
      });
    });

    // Header theme toggle
    const themeBtn = document.getElementById('btn-header-theme');
    if (themeBtn) {
      themeBtn.addEventListener('click', () => {
        const curr = window.store.getState().theme;
        const next = curr === 'dark' ? 'light' : 'dark';
        window.store.setState({ theme: next });
      });
    }
  },

  updateHeader(state) {
    // Cold start notification banner
    const banner = document.getElementById('cold-start-banner');
    if (banner) {
      if (state.serverStatus === 'waking') {
        banner.style.display = 'block';
        banner.innerHTML = `
          <span>⏳ 서버를 깨우는 중이에요. 무료 호스팅 특성상 처음엔 30초~1분 정도 걸릴 수 있어요...</span>
        `;
      } else {
        banner.style.display = 'none';
      }
    }

    // Header theme icon
    const themeBtn = document.getElementById('btn-header-theme');
    if (themeBtn) {
      themeBtn.innerHTML = state.theme === 'dark' ? '☀️' : '🌙';
    }
  },

  async checkServerStatus() {
    window.store.setState({ serverStatus: 'waking' });
    try {
      await window.Api.checkHealth();
      window.store.setState({ serverStatus: 'online' });
    } catch (e) {
      console.warn("Backend still waking up or unreachable:", e);
      // Retry in 3 seconds if waking
      setTimeout(async () => {
        try {
          await window.Api.checkHealth();
          window.store.setState({ serverStatus: 'online' });
        } catch (_) {
          window.store.setState({ serverStatus: 'offline' });
        }
      }, 3000);
    }
  },

  async refreshData() {
    try {
      const [summary, records, pendingReviews] = await Promise.all([
        window.Api.getDataSummary().catch(() => null),
        window.Api.getDataList().catch(() => []),
        window.Api.getPendingReviews().catch(() => [])
      ]);

      window.store.setState({
        summary,
        records,
        pendingReviews
      });

      // Re-render current tab if it's chat or data
      const currentTab = window.store.getState().activeTab;
      if (currentTab === 'chat') {
        this.renderCurrentTab();
      }
    } catch (err) {
      console.error("Error refreshing data:", err);
    }
  },

  switchTab(tabName) {
    window.store.setState({ activeTab: tabName });

    // Update Tab UI
    document.querySelectorAll('.nav-tab').forEach((t) => {
      if (t.getAttribute('data-tab') === tabName) {
        t.classList.add('active');
      } else {
        t.classList.remove('active');
      }
    });

    this.renderCurrentTab();
  },

  renderCurrentTab() {
    const container = document.getElementById('tab-content');
    if (!container) return;

    const currentTab = window.store.getState().activeTab;

    switch (currentTab) {
      case 'chat':
        window.ChatComponent.render(container);
        break;
      case 'graph':
        window.GraphComponent.render(container);
        break;
      case 'review':
        window.ReviewComponent.render(container);
        break;
      case 'data':
        window.DataComponent.render(container);
        break;
      case 'history':
        window.HistoryComponent.render(container);
        break;
      case 'settings':
        window.SettingsComponent.render(container);
        break;
      default:
        window.ChatComponent.render(container);
    }
  },

  async sendChatMessage(text) {
    const state = window.store.getState();
    const currentMsgs = [...state.messages];

    // Add user message optimistically
    currentMsgs.push({
      role: 'user',
      content: text,
      created_at: new Date().toISOString()
    });

    window.store.setState({
      messages: currentMsgs,
      isLoadingChat: true
    });
    this.renderCurrentTab();

    try {
      const res = await window.Api.sendChatMessage(text, state.currentConversationId);

      const updatedMsgs = [...window.store.getState().messages];
      updatedMsgs.push({
        role: 'assistant',
        content: res.reply,
        sources: res.sources || [],
        created_at: new Date().toISOString()
      });

      // If pending trades were returned, queue them for confirmation
      const pendingTrades = [...(window.store.getState().pendingTrades || [])];
      if (res.pending_trades && res.pending_trades.length > 0) {
        pendingTrades.push(...res.pending_trades);
      }

      window.store.setState({
        messages: updatedMsgs,
        currentConversationId: res.conversation_id,
        pendingTrades: pendingTrades,
        isLoadingChat: false
      });

      this.renderCurrentTab();
    } catch (err) {
      console.error("Chat Error:", err);
      const updatedMsgs = [...window.store.getState().messages];
      updatedMsgs.push({
        role: 'assistant',
        content: `⚠️ 오류가 발생했습니다: ${err.message}`,
        created_at: new Date().toISOString()
      });
      window.store.setState({ messages: updatedMsgs, isLoadingChat: false });
      this.renderCurrentTab();
    }
  },

  async handleScreenshotUpload(file) {
    window.store.setState({ isLoadingChat: true });
    this.renderCurrentTab();

    try {
      const candidates = await window.Api.parseTradeImage(file);
      const pendingTrades = [...(window.store.getState().pendingTrades || []), ...candidates];
      const updatedMsgs = [...window.store.getState().messages];
      updatedMsgs.push({
        role: 'assistant',
        content: `체결 내역 캡처에서 ${candidates.length}건의 매매를 인식했어요! 아래 기록 카드의 수량과 단가를 확인하신 후 [기록 저장하기]를 눌러주세요.`,
        created_at: new Date().toISOString()
      });

      window.store.setState({
        messages: updatedMsgs,
        pendingTrades: pendingTrades,
        isLoadingChat: false
      });
      this.renderCurrentTab();
    } catch (err) {
      alert(`캡처 이미지 분석 실패: ${err.message}`);
      window.store.setState({ isLoadingChat: false });
      this.renderCurrentTab();
    }
  }
};

window.Main = Main;

document.addEventListener('DOMContentLoaded', () => {
  window.Main.init();
});
