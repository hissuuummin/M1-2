/**
 * Vercel 빌드 때 실행: 환경 변수로 config.js를 만듭니다.
 *   API_BASE_URL        예) https://investment-mirror-backend.onrender.com/api
 *   FIREBASE_WEB_CONFIG Firebase 콘솔 > 프로젝트 설정 > 웹 앱의 firebaseConfig (JSON 한 줄)
 * Firebase 웹 설정은 브라우저에 공개되는 값이라 비밀이 아닙니다. (보안은 서버의 토큰 검증 + ALLOWED_EMAIL)
 */
const fs = require('fs');
const path = require('path');

const apiBase = (process.env.API_BASE_URL || '').trim();
let firebaseConfig = {};
if (process.env.FIREBASE_WEB_CONFIG) {
  try {
    firebaseConfig = JSON.parse(process.env.FIREBASE_WEB_CONFIG);
  } catch (e) {
    console.error('FIREBASE_WEB_CONFIG is not valid JSON');
    process.exit(1);
  }
}
if (!apiBase) {
  console.error('API_BASE_URL is not set. Set it in Vercel > Project Settings > Environment Variables.');
  process.exit(1);
}

const out = `// 이 파일은 scripts/build-config.js가 배포 때 만든 파일입니다.
window.API_BASE_URL = ${JSON.stringify(apiBase)};
window.FIREBASE_WEB_CONFIG = ${JSON.stringify(firebaseConfig)};
`;
fs.writeFileSync(path.join(__dirname, '..', 'config.js'), out);
console.log('config.js generated for', apiBase);
