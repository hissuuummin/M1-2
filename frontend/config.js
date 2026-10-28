// Runtime API Configuration
// Vercel deployment injects API_BASE_URL or defaults to localhost for development
if (typeof window.API_BASE_URL === 'undefined') {
  const isLocal =
    !window.location.hostname ||
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.protocol === 'file:';

  if (isLocal) {
    window.API_BASE_URL = 'http://127.0.0.1:8000/api';
  } else {
    // Production Render Backend URL fallback
    window.API_BASE_URL = 'https://investment-mirror-backend.onrender.com/api';
  }
}

// Optional Firebase Web Config for client Google Login
if (typeof window.FIREBASE_WEB_CONFIG === 'undefined') {
  window.FIREBASE_WEB_CONFIG = {
    apiKey: "",
    authDomain: "",
    projectId: "",
    storageBucket: "",
    messagingSenderId: "",
    appId: ""
  };
}
