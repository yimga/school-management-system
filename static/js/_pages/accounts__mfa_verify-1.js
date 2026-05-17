(function(){
  var pageDataEl=document.getElementById("page-data-accounts__mfa_verify-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["accounts__mfa_verify-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
    function b64urlToBuf(b64) {
        b64 = b64.replace(/-/g, '+').replace(/_/g, '/');
        var pad = b64.length % 4;
        if (pad) b64 += (new Array(5 - pad)).join('=');
        var bin = atob(b64);
        var buf = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
        return buf.buffer;
    }
    function bufToB64url(buf) {
        var bin = '';
        var u8 = new Uint8Array(buf);
        for (var i = 0; i < u8.length; i++) bin += String.fromCharCode(u8[i]);
        return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }
    function getCookie(n) {
        var v = document.cookie.match('(^|;)\\s*' + n + '\\s*=\\s*([^;]+)');
        return v ? v.pop() : '';
    }
    var btn = document.getElementById('btn-use-passkey');
    var msg = document.getElementById('passkey-verify-msg');
    var nextUrl = ((window.__RMC_PAGE_DATA__["accounts__mfa_verify-1"] || {})["var_next_url_escapejs"]);
    if (btn && msg) {
        btn.addEventListener('click', function() {
            msg.textContent = 'Signing in with passkey…';
            msg.className = 'mt-2 small text-info';
            fetch(((window.__RMC_PAGE_DATA__["accounts__mfa_verify-1"] || {})["url_accounts_passkey_authentication_options"]), { method: 'GET', credentials: 'same-origin' })
                .then(function(r) { return r.json(); })
                .then(function(options) {
                    if (options.error) throw new Error(options.error);
                    options.challenge = b64urlToBuf(options.challenge);
                    if (options.allowCredentials) {
                        options.allowCredentials = options.allowCredentials.map(function(c) {
                            return { id: b64urlToBuf(c.id), type: c.type || 'public-key' };
                        });
                    }
                    return navigator.credentials.get({ publicKey: options });
                })
                .then(function(cred) {
                    if (!cred) throw new Error('No credential returned');
                    var payload = {
                        id: cred.id,
                        rawId: bufToB64url(cred.rawId),
                        type: cred.type,
                        response: {
                            clientDataJSON: bufToB64url(cred.response.clientDataJSON),
                            authenticatorData: bufToB64url(cred.response.authenticatorData),
                            signature: bufToB64url(cred.response.signature),
                            userHandle: cred.response.userHandle ? bufToB64url(cred.response.userHandle) : null
                        },
                        remember_device: document.getElementById('remember_device') && document.getElementById('remember_device').checked
                    };
                    return fetch(((window.__RMC_PAGE_DATA__["accounts__mfa_verify-1"] || {})["url_accounts_passkey_authentication_verify"]), {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken')
                        },
                        body: JSON.stringify(payload)
                    });
                })
                .then(function(r) { return r.json().then(function(j) { return { ok: r.ok, json: j }; }); })
                .then(function(o) {
                    if (o.ok && o.json.ok) {
                        msg.textContent = 'Verified. Redirecting…';
                        msg.className = 'mt-2 small text-success';
                        window.location.href = nextUrl || ((window.__RMC_PAGE_DATA__["accounts__mfa_verify-1"] || {})["url_accounts_redirect"]);
                    } else {
                        msg.textContent = o.json.error || 'Verification failed';
                        msg.className = 'mt-2 small text-danger';
                    }
                })
                .catch(function(e) {
                    msg.textContent = e.message || 'Passkey verification failed';
                    msg.className = 'mt-2 small text-danger';
                });
        });
    }
})();
})();
