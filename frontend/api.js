/**
 * 투자거울: 백엔드 API 클라이언트 (api.js)
 * 모든 요청 직전에 인증 토큰(Firebase ID 토큰 또는 로컬 개발용 dev-token)을 받아 첨부합니다.
 */

const Api = {
  getBaseUrl() {
    return window.API_BASE_URL || '/api';
  },

  async getHeaders(isMultipart = false) {
    const headers = {};
    const token = window.Auth ? await window.Auth.getToken() : null;
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    if (!isMultipart) {
      headers['Content-Type'] = 'application/json';
    }
    return headers;
  },

  async request(endpoint, options = {}) {
    const url = `${this.getBaseUrl()}${endpoint}`;
    const isMultipart = options.body instanceof FormData;
    const config = {
      ...options,
      headers: {
        ...(await this.getHeaders(isMultipart)),
        ...(options.headers || {})
      }
    };

    try {
      const res = await fetch(url, config);

      if (res.status === 401 && endpoint !== '/health') {
        // 로그인이 만료되었거나 없음 → 로그인 화면으로
        window.store.setState({ isLoggedIn: false });
        if (window.Main && window.Main.showLogin) window.Main.showLogin('로그인이 필요해요.');
      }

      if (!res.ok) {
        let errMsg = `요청 실패 (HTTP ${res.status})`;
        try {
          const errData = await res.json();
          if (Array.isArray(errData.detail)) {
            // Pydantic 검증 오류 목록
            errMsg = errData.detail.map((d) => d.msg || JSON.stringify(d)).join(' / ');
          } else if (errData.detail) {
            errMsg = errData.detail;
          }
        } catch (_) {}
        const err = new Error(errMsg);
        err.status = res.status;
        throw err;
      }

      // Check if blob or json
      const contentType = res.headers.get('content-type');
      if (contentType && (contentType.includes('text/csv') || contentType.includes('application/octet-stream'))) {
        return await res.blob();
      }
      return await res.json();
    } catch (err) {
      console.error(`API Error [${endpoint}]:`, err);
      throw err;
    }
  },

  // Health
  checkHealth() {
    return this.request('/health', { method: 'GET' });
  },

  // Data
  getDataList(start, end) {
    const query = new URLSearchParams();
    if (start) query.append('start', start);
    if (end) query.append('end', end);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.request(`/data${qs}`, { method: 'GET' });
  },

  createData(payload) {
    return this.request('/data', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  updateData(id, payload) {
    return this.request(`/data/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  },

  deleteData(id) {
    return this.request(`/data/${id}`, { method: 'DELETE' });
  },

  getDataSummary() {
    return this.request('/data/summary', { method: 'GET' });
  },

  getDataStatistics() {
    return this.request('/data/statistics', { method: 'GET' });
  },

  syncMarketData() {
    return this.request('/data/sync', { method: 'POST' });
  },

  // Trades
  addTrade(dateId, payload) {
    return this.request(`/data/${dateId}/trades`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  updateTrade(dateId, tradeId, payload) {
    return this.request(`/data/${dateId}/trades/${tradeId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  },

  deleteTrade(dateId, tradeId) {
    return this.request(`/data/${dateId}/trades/${tradeId}`, {
      method: 'DELETE'
    });
  },

  // Conversations
  listConversations() {
    return this.request('/conversations', { method: 'GET' });
  },

  getConversation(id) {
    return this.request(`/conversations/${id}`, { method: 'GET' });
  },

  createConversation(payload) {
    return this.request('/conversations', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  deleteConversation(id) {
    return this.request(`/conversations/${id}`, { method: 'DELETE' });
  },

  // Chat
  sendChatMessage(message, conversationId = null) {
    return this.request('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: conversationId })
    });
  },

  // Review
  getPendingReviews() {
    return this.request('/review/pending', { method: 'GET' });
  },

  completeReview(tradeId, reviewType = '7d') {
    return this.request(`/review/${tradeId}/done?review_type=${reviewType}`, {
      method: 'POST'
    });
  },

  // Stocks
  getStockPrices(code, start, end) {
    const query = new URLSearchParams();
    if (start) query.append('start', start);
    if (end) query.append('end', end);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.request(`/stocks/${code}/prices${qs}`, { method: 'GET' });
  },

  // File & OCR
  parseTradeImage(file) {
    const fd = new FormData();
    fd.append('file', file);
    return this.request('/trades/parse-image', {
      method: 'POST',
      body: fd
    });
  },

  importTradeFile(file) {
    const fd = new FormData();
    fd.append('file', file);
    return this.request('/trades/import-file', {
      method: 'POST',
      body: fd
    });
  },

  /** 인증 헤더가 필요해서 링크 대신 fetch로 받아 저장합니다. */
  async downloadExport(format = 'csv') {
    const blob = await this.request(`/data/export?format=${format}`, { method: 'GET' });
    const data = blob instanceof Blob ? blob : new Blob([JSON.stringify(blob, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(data);
    const a = document.createElement('a');
    a.href = url;
    a.download = `investment_mirror_data.${format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }
};

window.Api = Api;
