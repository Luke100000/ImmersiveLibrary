(function () {
    function setCookie(name, value, days) {
        let expires = "";
        if (days) {
            const date = new Date();
            date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
            expires = "; expires=" + date.toUTCString();
        }
        document.cookie = name + "=" + encodeURIComponent(value) + expires + "; path=/";
    }

    function getCookie(name) {
        const nameEQ = name + "=";
        const ca = document.cookie.split(';');
        for (let i = 0; i < ca.length; i++) {
            let c = ca[i];
            while (c.charAt(0) === ' ') c = c.substring(1, c.length);
            if (c.indexOf(nameEQ) === 0) return decodeURIComponent(c.substring(nameEQ.length, c.length));
        }
        return null;
    }

    function eraseCookie(name) {
        setCookie(name, "", -1);
    }

    async function loginPrompt() {
        const token = window.prompt("copy your immersive token here");
        if (!token || !token.trim().length) {
            return;
        }
        const trimmed = token.trim();
        try {
            const resp = await fetch('/v1/auth', {
                method: 'GET',
                headers: {
                    'Authorization': 'Bearer ' + trimmed,
                    'Accept': 'application/json'
                }
            });
            if (!resp.ok) {
                alert('Authentication check failed (' + resp.status + ').');
                return;
            }
            const data = await resp.json();
            if (data && data.authenticated === true) {
                setCookie('immersive_token', trimmed, 365);
                alert('Token saved');
                window.location.reload();
            } else {
                alert('Token not valid. Not saved.');
            }
        } catch (e) {
            alert('Network error while checking token.');
        }
    }

    function logout() {
        eraseCookie('immersive_token');
        alert('Token cleared');
    }

    // Wrap fetch to add Authorization header if token present, without overriding explicit header
    const origFetch = window.fetch;
    window.fetch = function (input, init) {
        init = init || {};
        const headers = new Headers(init.headers || {});
        // only set if not already set
        if (!headers.has('Authorization')) {
            const t = getCookie('immersive_token');
            if (t) {
                headers.set('Authorization', 'Bearer ' + t);
            }
        }
        init.headers = headers;
        return origFetch(input, init);
    };

    // Expose small API and ensure button hookup if present
    window.ImmersiveAuth = {loginPrompt, logout, getToken: () => getCookie('immersive_token')};

    // Auto-attach to a button with id login-btn if present
    document.addEventListener('DOMContentLoaded', function () {
        const btn = document.getElementById('login-btn');

        function updateBtn() {
            if (!btn) return;
            const has = !!getCookie('immersive_token');
            const span = btn.querySelector('span');
            if (span) {
                span.textContent = has ? 'Log out' : 'Login';
            }
            btn.classList.toggle('secondary', has);
            btn.title = has ? 'Token set' : 'Set immersive token';
        }

        if (btn) {
            btn.addEventListener('click', function () {
                const has = !!getCookie('immersive_token');
                if (has) {
                    logout();
                } else {
                    loginPrompt();
                }
                updateBtn();
            });
            updateBtn();
        }
        const logoutButton = document.getElementById('logout-btn');
        if (logoutButton) {
            logoutButton.addEventListener('click', function () {
                logout();
                updateBtn();
            });
        }
    });
})();
