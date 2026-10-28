/**
 * 투자거울: 설정 컴포넌트 (settings.js)
 * 다크 모드 토글, API 서버 주소 확인, 인증 계정 정보 및 로그아웃
 */

const SettingsComponent = {
  render(container) {
    const state = window.store.getState();
    const isDark = state.theme === 'dark';

    container.innerHTML = `
      <div class="settings-container">
        <div class="settings-header">
          <h2>⚙️ 설정</h2>
          <p class="settings-subtitle">테마 설정 및 API 연동 상태, 계정 정보를 관리합니다.</p>
        </div>

        <div class="settings-card">
          <h3>화면 테마</h3>
          <div class="setting-row">
            <div>
              <strong>다크 모드 (Dark Mode)</strong>
              <p class="setting-desc">어두운 테마로 눈의 피로를 줄입니다.</p>
            </div>
            <button id="btn-toggle-theme" class="btn-outline btn-sm">
              ${isDark ? '☀️ 라이트 모드로 전환' : '🌙 다크 모드로 전환'}
            </button>
          </div>
        </div>

        <div class="settings-card">
          <h3>서버 및 API 연동 상태</h3>
          <div class="setting-row">
            <div>
              <strong>백엔드 API URL</strong>
              <p class="setting-desc">${window.Api.getBaseUrl()}</p>
            </div>
            <span class="status-badge ${state.serverStatus === 'online' ? 'status-online' : 'status-waking'}">
              ${state.serverStatus === 'online' ? '연결됨 (Online)' : '서버 확인 중...'}
            </span>
          </div>
        </div>

        <div class="settings-card">
          <h3>인증 계정</h3>
          <div class="setting-row">
            <div>
              <strong>로그인된 계정</strong>
              <p class="setting-desc">${state.user ? state.user.email : '로그인되지 않음'}</p>
            </div>
            <button id="btn-logout" class="btn-outline btn-danger btn-sm">
              로그아웃
            </button>
          </div>
        </div>
      </div>
    `;

    this.bindEvents(container);
  },

  bindEvents(container) {
    const themeBtn = container.querySelector('#btn-toggle-theme');
    if (themeBtn) {
      themeBtn.addEventListener('click', () => {
        const curr = window.store.getState().theme;
        const next = curr === 'dark' ? 'light' : 'dark';
        window.store.setState({ theme: next });
        this.render(container);
      });
    }

    const logoutBtn = container.querySelector('#btn-logout');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', () => {
        window.Auth.logout();
        alert('로그아웃되었습니다.');
        window.Main.switchTab('chat');
      });
    }
  }
};

window.SettingsComponent = SettingsComponent;
