// 로컬 개발용 설정. 배포(Vercel)에서는 scripts/build-config.js가 환경 변수로 이 파일을 다시 만듭니다.
// 백엔드가 프론트도 함께 내려주는 경우(python start.py)에는 같은 주소의 /api 를 씁니다.
if (typeof window.API_BASE_URL === 'undefined') {
  const servedByBackend = window.location.port === '8000';
  window.API_BASE_URL = servedByBackend ? '/api' : 'http://127.0.0.1:8000/api';
}

// Firebase 웹 앱 설정 (로컬에서 구글 로그인까지 시험할 때만 채우세요. DEV_MODE=true면 비워 둬도 됩니다)
if (typeof window.FIREBASE_WEB_CONFIG === 'undefined') {
  window.FIREBASE_WEB_CONFIG = {};
}
