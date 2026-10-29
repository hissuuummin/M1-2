/**
 * 투자거울: 중앙 상태 관리소 (store.js)
 * 상태는 store.js 한곳에서 관리하며, 상태가 변경될 때 구독자(화면 컴포넌트)에 알립니다.
 */

/**
 * 외부에서 온 글자(뉴스 제목, 파일에서 읽은 종목명, 메모 등)를 HTML에 넣기 전에 반드시 거칩니다.
 */
window.escapeHtml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

/** http(s) 링크만 허용 (javascript: 같은 링크 차단) */
window.safeUrl = (value) => {
  try {
    const u = new URL(String(value || ''));
    return (u.protocol === 'https:' || u.protocol === 'http:') ? u.href : '#';
  } catch (_) {
    return '#';
  }
};

const createStore = () => {
  let state = {
    // Auth & User (로그인 토큰은 브라우저 저장소에 남기지 않습니다)
    user: null,
    token: null,
    isLoggedIn: false,
    authMode: null, // 'dev' | 'firebase' (서버 /api/health 가 알려 줌)
    aiEnabled: false,

    // Navigation
    activeTab: 'chat', // 'chat', 'graph', 'review', 'data', 'history', 'settings'

    // Server Status & Cold-start
    serverStatus: 'checking', // 'checking', 'online', 'waking', 'offline'

    // Theme
    theme: (() => { try { return localStorage.getItem('im_theme') || 'dark'; } catch (_) { return 'dark'; } })(),

    // Data Store
    summary: null,
    statistics: null,
    records: [],
    conversations: [],
    currentConversationId: null,
    messages: [],

    // Interactive states
    pendingTrades: [], // Trades pending user confirmation
    pendingReviews: [],
    selectedStockCode: '005930',
    stockGraphData: null,
    isLoadingChat: false,
    errorMessage: null
  };

  const listeners = new Set();

  return {
    getState: () => state,
    setState: (partial) => {
      state = { ...state, ...partial };
      // Persist user & theme
      if (partial.theme) {
        try { localStorage.setItem('im_theme', partial.theme); } catch (_) {}
        document.documentElement.setAttribute('data-theme', partial.theme);
      }

      listeners.forEach((listener) => {
        try {
          listener(state);
        } catch (e) {
          console.error("Store listener error:", e);
        }
      });
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }
  };
};

window.store = createStore();
