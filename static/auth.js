(function () {
    const TOKEN_COOKIE = 'immersive_token';
    const USERNAME_COOKIE = 'immersive_username';
    const CONSENT_COOKIE = 'immersive_cookie_consent';

    function setCookie(name, value, days) {
        let expires = "";
        if (days) {
            const date = new Date();
            date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
            expires = "; expires=" + date.toUTCString();
        }
        document.cookie = name + "=" + encodeURIComponent(value) + expires
            + "; path=/; SameSite=Lax" + (window.location.protocol === 'https:' ? '; Secure' : '');
    }

    function getCookie(name) {
        const nameEQ = name + "=";
        for (let cookie of document.cookie.split(';')) {
            cookie = cookie.trim();
            if (cookie.startsWith(nameEQ)) {
                return decodeURIComponent(cookie.substring(nameEQ.length));
            }
        }
        return null;
    }

    function eraseCookie(name) {
        setCookie(name, "", -1);
    }

    function requestCookieConsent() {
        return new Promise((resolve) => {
            const dialog = document.createElement('div');
            dialog.className = 'consent-dialog';
            dialog.setAttribute('role', 'dialog');
            dialog.setAttribute('aria-modal', 'true');
            dialog.innerHTML = `
                <div class="consent-dialog__content">
                    <h2>Cookies and sign-in</h2>
                    <p>We use a necessary cookie to keep you signed in and Google Sign-In to authenticate you.</p>
                    <p>Read our <a href="/privacy">Privacy Notice</a> before continuing.</p>
                    <div class="consent-dialog__actions">
                        <button type="button" class="btn" data-consent="no">Leave</button>
                        <button type="button" class="btn" data-consent="yes">Accept and continue</button>
                    </div>
                </div>
            `;
            dialog.querySelector('[data-consent="yes"]').addEventListener('click', () => {
                setCookie(CONSENT_COOKIE, 'yes', 365);
                dialog.remove();
                resolve(true);
            });
            dialog.querySelector('[data-consent="no"]').addEventListener('click', () => {
                dialog.remove();
                resolve(false);
            });
            document.body.appendChild(dialog);
        });
    }

    function encodeBase64(value) {
        const bytes = new TextEncoder().encode(value);
        return btoa(String.fromCharCode(...bytes));
    }

    function createToken() {
        const bytes = crypto.getRandomValues(new Uint8Array(32));
        return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
    }

    async function hashToken(token) {
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
        return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
    }

    async function login() {
        if (!window.isSecureContext || !crypto.subtle) {
            alert('Google sign-in requires a secure connection.');
            return;
        }

        if (getCookie(CONSENT_COOKIE) !== 'yes') {
            if (!await requestCookieConsent()) {
                window.location.replace('/');
                return;
            }
        }

        let username = getCookie(USERNAME_COOKIE);
        if (!username) {
            username = window.prompt('Choose a display name');
            if (!username || !username.trim()) {
                return;
            }
            username = username.trim();
            setCookie(USERNAME_COOKIE, username, 365);
        }

        let token = getCookie(TOKEN_COOKIE);
        if (!token) {
            token = createToken();
            setCookie(TOKEN_COOKIE, token, 365);
        }

        const state = {
            username: encodeBase64(username),
            token: encodeBase64(await hashToken(token)),
            return_to: window.location.pathname + window.location.search + window.location.hash,
        };
        window.location.assign('/v1/login?state=' + encodeURIComponent(encodeBase64(JSON.stringify(state))));
    }

    function logout() {
        eraseCookie(TOKEN_COOKIE);
        alert('Signed out');
    }

    const originalFetch = window.fetch;
    window.fetch = function (input, init) {
        init = init || {};
        const headers = new Headers(
            init.headers || (input instanceof Request ? input.headers : undefined)
        );
        const url = new URL(input instanceof Request ? input.url : input, window.location.href);
        if (url.origin === window.location.origin && !headers.has('Authorization')) {
            const token = getCookie(TOKEN_COOKIE);
            if (token) {
                headers.set('Authorization', 'Bearer ' + token);
            }
        }
        init.headers = headers;
        return originalFetch(input, init);
    };

    window.ImmersiveAuth = {login, logout, getToken: () => getCookie(TOKEN_COOKIE)};

    document.addEventListener('DOMContentLoaded', function () {
        const button = document.getElementById('login-btn');
        if (!button) {
            return;
        }

        function updateButton() {
            const hasToken = !!getCookie(TOKEN_COOKIE);
            const label = button.querySelector('span');
            if (label) {
                label.textContent = hasToken ? 'Log out' : 'Login';
            }
            button.classList.toggle('secondary', hasToken);
            button.title = hasToken ? 'Sign out' : 'Sign in with Google';
        }

        button.addEventListener('click', function () {
            if (getCookie(TOKEN_COOKIE)) {
                logout();
                updateButton();
            } else {
                login();
            }
        });
        updateButton();
    });
})();
