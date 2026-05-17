(function(){
  var pageDataEl=document.getElementById("page-data-accounts__mfa_setup-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["accounts__mfa_setup-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
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
    function doAddPasskey(btnId, msgId) {
        var btn = document.getElementById(btnId);
        var msg = document.getElementById(msgId);
        if (!btn || !msg) return;
        btn.addEventListener('click', function() {
            msg.textContent = 'Requesting passkey registration…';
            msg.className = 'mt-2 small text-info';
            fetch(((window.__RMC_PAGE_DATA__["accounts__mfa_setup-1"] || {})["url_accounts_passkey_registration_options"]), { method: 'GET', credentials: 'same-origin' })
                .then(function(r) { return r.json(); })
                .then(function(options) {
                    if (options.error) throw new Error(options.error);
                    options.challenge = b64urlToBuf(options.challenge);
                    if (options.user && options.user.id) options.user.id = b64urlToBuf(options.user.id);
                    return navigator.credentials.create({ publicKey: options });
                })
                .then(function(cred) {
                    if (!cred) throw new Error('No credential returned');
                    var payload = {
                        id: cred.id,
                        rawId: bufToB64url(cred.rawId),
                        type: cred.type,
                        response: {
                            clientDataJSON: bufToB64url(cred.response.clientDataJSON),
                            attestationObject: bufToB64url(cred.response.attestationObject)
                        },
                        deviceName: 'Passkey'
                    };
                    return fetch(((window.__RMC_PAGE_DATA__["accounts__mfa_setup-1"] || {})["url_accounts_passkey_registration_verify"]), {
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
                        msg.textContent = 'Passkey added. Reloading…';
                        msg.className = 'mt-2 small text-success';
                        window.location.reload();
                    } else {
                        msg.textContent = o.json.error || 'Registration failed';
                        msg.className = 'mt-2 small text-danger';
                    }
                })
                .catch(function(e) {
                    msg.textContent = e.message || 'Passkey registration failed';
                    msg.className = 'mt-2 small text-danger';
                });
        });
    }
    doAddPasskey('btn-add-passkey', 'passkey-message');
    doAddPasskey('btn-add-passkey-first', 'passkey-message-first');
})();
})();
