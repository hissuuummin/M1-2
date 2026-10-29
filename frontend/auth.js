/**
 * 투자거울: 인증 모듈 (auth.js)
 *
 * - 서버가 auth_mode='dev'(내 컴퓨터, DEV_MODE=true)라고 알려 주면 dev-token으로 바로 씁니다.
 * - auth_mode='firebase'(배포)이면 Firebase 구글 로그인을 거쳐야 합니다.
 *   ID 토큰은 1시간마다 만료되므로 요청할 때마다 getIdToken()으로 새로 받고, 브라우저 저장소에 넣지 않습니다.
 */

const FIREBASE_SDK_VERSION = '10.12.2';

const Auth = {
  _firebaseReady: null,

  async init(authMode) {
    // 예전 버전이 남겨 둔 토큰 정리
    try { localStorage.removeItem('im_token'); localStorage.removeItem('im_user'); } catch (_) {}

    window.store.setState({ authMode });

    if (authMode === 'dev') {
      window.store.setState({
        token: 'dev-token',
        user: { email: '로컬 개발 모드', name: '테스터', is_dev: true },
        isLoggedIn: true
      });
      return true;
    }

    const ready = await this.loadFirebase();
    if (!ready) return false;

    return new Promise((resolve) => {
      firebase.auth().onAuthStateChanged((user) => {
        if (user) {
          window.store.setState({
            user: { email: user.email, name: user.displayName || user.email },
            isLoggedIn: true
          });
          resolve(true);
        } else {
          window.store.setState({ user: null, isLoggedIn: false });
          resolve(false);
        }
      });
    });
  },

  loadScript(src) {
    return new Promise((resolve, reject) => {
      const el = document.createElement('script');
      el.src = src;
      el.onload = resolve;
      el.onerror = reject;
      document.head.appendChild(el);
    });
  },

  async loadFirebase() {
    if (this._firebaseReady !== null) return this._firebaseReady;
    const cfg = window.FIREBASE_WEB_CONFIG || {};
    if (!cfg.apiKey) {
      console.error('FIREBASE_WEB_CONFIG가 비어 있어 로그인할 수 없어요. README의 Vercel 설정을 확인하세요.');
      this._firebaseReady = false;
      return false;
    }
    try {
      const base = `https://www.gstatic.com/firebasejs/${FIREBASE_SDK_VERSION}`;
      await this.loadScript(`${base}/firebase-app-compat.js`);
      await this.loadScript(`${base}/firebase-auth-compat.js`);
      if (!firebase.apps.length) firebase.initializeApp(cfg);
      // 탭을 닫으면 로그인도 끝나도록 (공용 PC 대비)
      await firebase.auth().setPersistence(firebase.auth.Auth.Persistence.SESSION);
      this._firebaseReady = true;
    } catch (err) {
      console.error('Firebase SDK load failed:', err);
      this._firebaseReady = false;
    }
    return this._firebaseReady;
  },

  /** API 요청 직전에 호출. 만료된 토큰은 Firebase가 알아서 갱신합니다. */
  async getToken() {
    const state = window.store.getState();
    if (state.authMode === 'dev') return 'dev-token';
    if (window.firebase && firebase.apps && firebase.apps.length && firebase.auth().currentUser) {
      return firebase.auth().currentUser.getIdToken();
    }
    return null;
  },

  async loginWithGoogle() {
    const ready = await this.loadFirebase();
    if (!ready) {
      throw new Error('로그인 설정(FIREBASE_WEB_CONFIG)이 없어요.');
    }
    const provider = new firebase.auth.GoogleAuthProvider();
    const result = await firebase.auth().signInWithPopup(provider);
    window.store.setState({
      user: { email: result.user.email, name: result.user.displayName || result.user.email },
      isLoggedIn: true
    });
    return result.user;
  },

  async logout() {
    if (window.firebase && firebase.apps && firebase.apps.length) {
      try { await firebase.auth().signOut(); } catch (_) {}
    }
    window.store.setState({ token: null, user: null, isLoggedIn: false });
  }
};

window.Auth = Auth;
