(function () {
    const LEGACY_TOKEN_COOKIE = 'immersive_token';
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

    // Remove credentials created by the retired v1 browser authentication flow.
    eraseCookie(LEGACY_TOKEN_COOKIE);

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

        const response = await fetch('/v2/auth/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                username,
                return_to: window.location.pathname + window.location.search + window.location.hash,
            }),
        });
        if (!response.ok) {
            alert('Unable to start sign-in.');
            return;
        }
        const auth = await response.json();
        window.location.assign(auth.login_url);
    }

    async function logout() {
        const response = await fetch('/v2/auth/token', {method: 'DELETE'});
        if (!response.ok) {
            alert('Unable to sign out. Please try again.');
            return false;
        }
        alert('Signed out');
        return true;
    }

    window.ImmersiveAuth = {login, logout};

    document.addEventListener('DOMContentLoaded', function () {
        const button = document.getElementById('login-btn');
        if (!button) {
            return;
        }

        async function updateButton() {
            let authenticated = false;
            try {
                const response = await fetch('/v1/auth');
                authenticated = response.ok && (await response.json()).authenticated === true;
            } catch (_) {
                authenticated = false;
            }
            const label = button.querySelector('span');
            if (label) {
                label.textContent = authenticated ? 'Log out' : 'Login';
            }
            button.classList.toggle('secondary', authenticated);
            button.title = authenticated ? 'Sign out' : 'Sign in with Google';
            button.dataset.authenticated = authenticated ? 'true' : 'false';
        }

        button.addEventListener('click', async function () {
            if (button.dataset.authenticated === 'true') {
                await logout();
                await updateButton();
            } else {
                await login();
            }
        });
        updateButton();
    });
})();
