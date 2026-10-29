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

    // Bind Global Header & Nav Events
    this.bindGlobalEvents();

    // Subscribe to store updates
    window.store.subscribe((state) => {
      this.updateHeader(state);
    });

    // 1) 서버 깨우기 + 인증 방식 확인 (콜드스타트 안내 배너 표시)
    const health = await this.checkServerStatus();
    if (!health) {
      this.showLogin('서버에 연결하지 못했어요. 잠시 후 새로고침해 주세요.', false);
      return;
    }
    window.store.setState({ aiEnabled: !!health.ai_enabled });

    // 2) 로그인 확인 (배포: 구글 로그인 / 로컬 DEV_MODE: 바로 사용)
    const loggedIn = await window.Auth.init(health.auth_mode);
    if (!loggedIn) {
      this.showLogin();
      return;
    }
    await this.startApp();
  },

  async startApp() {
    this.hideLogin();
    await this.refreshData();
    this.switchTab('chat');
  },

  showLogin(message = '', showButton = true) {
    const overlay = document.getElementById('login-screen');
    if (!overlay) return;
    overlay.style.display = 'flex';
    const msg = overlay.querySelector('#login-message');
    if (msg) msg.textContent = message;
    const btn = overlay.querySelector('#btn-google-login');
    if (btn) {
      btn.style.display = showButton ? 'inline-flex' : 'none';
      btn.onclick = async () => {
        btn.disabled = true;
        try {
          await window.Auth.loginWithGoogle();
          await this.startApp();
        } catch (err) {
          if (msg) msg.textContent = `로그인하지 못했어요: ${err.message}`;
        } finally {
          btn.disabled = false;
        }
      };
    }
  },

  hideLogin() {
    const overlay = document.getElementById('login-screen');
    if (overlay) overlay.style.display = 'none';
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
    // Render 무료 서버는 잠들어 있으면 깨어나는 데 1분 가까이 걸릴 수 있어 여러 번 다시 시도합니다.
    window.store.setState({ serverStatus: 'waking' });
    for (let attempt = 0; attempt < 12; attempt += 1) {
      try {
        const health = await window.Api.checkHealth();
        window.store.setState({ serverStatus: 'online' });
        return health;
      } catch (e) {
        await new Promise((r) => setTimeout(r, 5000));
      }
    }
    window.store.setState({ serverStatus: 'offline' });
    return null;
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
        mode: res.mode || 'ai',
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
        content: `체결 내역 캡처에서 ${candidates.length}건을 읽었어요. AI가 읽은 값이라 틀릴 수 있으니, 아래 카드의 날짜·종목·수량·단가를 꼭 확인한 뒤 [기록 저장하기]를 눌러 주세요.`,
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
