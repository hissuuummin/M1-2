/**
 * 투자거울: 중앙 상태 관리소 (store.js)
 * 상태는 store.js 한곳에서 관리하며, 상태가 변경될 때 구독자(화면 컴포넌트)에 알립니다.
 */

const createStore = () => {
  let state = {
    // Auth & User
    user: JSON.parse(localStorage.getItem('im_user') || '{"email":"tester@investment-mirror.local","name":"테스터"}'),
    token: localStorage.getItem('im_token') || 'dev-token',
    isLoggedIn: true,

    // Navigation
    activeTab: 'chat', // 'chat', 'graph', 'review', 'data', 'history', 'settings'

    // Server Status & Cold-start
    serverStatus: 'checking', // 'checking', 'online', 'waking', 'offline'

    // Theme
    theme: localStorage.getItem('im_theme') || 'dark',

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
        localStorage.setItem('im_theme', partial.theme);
        document.documentElement.setAttribute('data-theme', partial.theme);
      }
      if (partial.token !== undefined) {
        if (partial.token) localStorage.setItem('im_token', partial.token);
        else localStorage.removeItem('im_token');
      }
      if (partial.user !== undefined) {
        if (partial.user) localStorage.setItem('im_user', JSON.stringify(partial.user));
        else localStorage.removeItem('im_user');
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
