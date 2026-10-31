(function () {
    const TOKEN_COOKIE = 'immersive_token';
    const USERNAME_COOKIE = 'immersive_username';
    const CONSENT_COOKIE = 'immersive_cookie_consent';

    function setCookie(name, value, days) {
        const secure = window.location.protocol === 'https:' ? '; Secure' : '';
        document.cookie = `${name}=${encodeURIComponent(value)}; max-age=${days * 86400}; path=/; SameSite=Lax${secure}`;
    }

    function getCookie(name) {
        for (const cookie of document.cookie.split(';')) {
            const [key, ...value] = cookie.trim().split('=');
            if (key === name) {
                return decodeURIComponent(value.join('='));
            }
        }
        return null;
    }

    function eraseCookie(name) {
        setCookie(name, '', 0);
    }

    function encodeBase64(value) {
        const bytes = new TextEncoder().encode(value);
        return btoa(String.fromCharCode(...bytes));
    }

    function toHex(bytes) {
        return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
    }

    function createToken() {
        return toHex(crypto.getRandomValues(new Uint8Array(32)));
    }

    async function hashToken(token) {
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
        return toHex(new Uint8Array(digest));
    }

    document.addEventListener('alpine:init', () => {
        let userRequest;

        Alpine.store('auth', {
            hasToken: Boolean(getCookie(TOKEN_COOKIE)),
            consentRequired: false,
            user: null,

            async loadUser(project) {
                if (!this.hasToken) return null;
                if (!userRequest) {
                    userRequest = fetch(`/v3/user/${encodeURIComponent(project)}/me`).then(async (response) => {
                        if (!response.ok) return null;
                        return (await response.json()).user;
                    });
                }

                try {
                    this.user = await userRequest;
                } catch {
                    this.user = null;
                }
                return this.user;
            },

            rememberConsent() {
                setCookie(CONSENT_COOKIE, 'yes', 365);
            },

            acceptConsent() {
                this.rememberConsent();
                this.consentRequired = false;
                this.login();
            },

            declineConsent() {
                this.consentRequired = false;
                window.location.replace('/');
            },

            async login() {
                if (!window.isSecureContext || !crypto.subtle) {
                    alert('Google sign-in requires a secure connection.');
                    return;
                }

                if (getCookie(CONSENT_COOKIE) !== 'yes') {
                    this.consentRequired = true;
                    return;
                }

                let username = getCookie(USERNAME_COOKIE);
                if (!username) {
                    username = window.prompt('Choose a display name')?.trim();
                    if (!username) return;
                    setCookie(USERNAME_COOKIE, username, 365);
                }

                let token = getCookie(TOKEN_COOKIE);
                if (!token) {
                    token = createToken();
                    setCookie(TOKEN_COOKIE, token, 365);
                    this.hasToken = true;
                }

                const state = {
                    username: encodeBase64(username),
                    token: encodeBase64(await hashToken(token)),
                    return_to: window.location.pathname + window.location.search + window.location.hash,
                };
                window.location.assign(`/v1/login?${new URLSearchParams({state: encodeBase64(JSON.stringify(state))})}`);
            },

            logout() {
                eraseCookie(TOKEN_COOKIE);
                window.location.reload();
            },
        });
    });

    const originalFetch = window.fetch;
    window.fetch = function (input, init = {}) {
        const headers = new Headers(init.headers ?? (input instanceof Request ? input.headers : undefined));
        const url = new URL(input instanceof Request ? input.url : input, window.location.href);
        if (url.origin === window.location.origin && !headers.has('Authorization')) {
            const token = getCookie(TOKEN_COOKIE);
            if (token) {
                headers.set('Authorization', `Bearer ${token}`);
            }
        }
        return originalFetch(input, {...init, headers});
    };
})();
