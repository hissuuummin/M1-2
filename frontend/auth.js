/**
 * 투자거울: 인증 모듈 (auth.js)
 * Firebase Authentication 구글 로그인 및 로컬 개발용 테스트 로그인 지원
 */

const Auth = {
  init() {
    const state = window.store.getState();
    // Default to dev mode if token exists
    if (!state.token) {
      window.store.setState({ token: 'dev-token', isLoggedIn: true });
    }
  },

  async loginWithGoogle() {
    // If Firebase Web SDK is loaded and configured
    if (window.firebase && window.firebase.auth && window.FIREBASE_WEB_CONFIG && window.FIREBASE_WEB_CONFIG.apiKey) {
      try {
        if (!firebase.apps.length) {
          firebase.initializeApp(window.FIREBASE_WEB_CONFIG);
        }
        const provider = new firebase.auth.GoogleAuthProvider();
        const result = await firebase.auth().signInWithPopup(provider);
        const token = await result.user.getIdToken();
        const user = {
          email: result.user.email,
          name: result.user.displayName || result.user.email,
          photoURL: result.user.photoURL
        };
        window.store.setState({ token, user, isLoggedIn: true });
        return user;
      } catch (err) {
        console.error("Firebase Login Error:", err);
        alert(`구글 로그인 실패: ${err.message}\n로컬 테스트 모드로 전환합니다.`);
        this.loginWithDevMode();
      }
    } else {
      // Fast start in Dev Mode
      this.loginWithDevMode();
    }
  },

  loginWithDevMode(email = "tester@investment-mirror.local") {
    const user = {
      email: email,
      name: "테스터",
      is_dev: true
    };
    window.store.setState({
      token: "dev-token",
      user: user,
      isLoggedIn: true
    });
  },

  logout() {
    if (window.firebase && window.firebase.auth && firebase.apps.length) {
      firebase.auth().signOut().catch(() => {});
    }
    window.store.setState({
      token: null,
      user: null,
      isLoggedIn: false
    });
  }
};

window.Auth = Auth;
