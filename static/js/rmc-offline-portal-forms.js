/**
 * Portal/evals/finance forms: when offline (or forced queue), POST payloads via rmcOfflineEnqueue.
 * Server expects { action_type, payload: {...}, idempotency_key } — see offline-queue-client.js flush path.
 */
(function () {
  function cfg() {
    return window.SMS_OFFLINE_CONFIG || {};
  }

  function enabled() {
    var c = cfg();
    if (!c.formQueueEnabled) return false;
    if (typeof window.rmcOfflineEnqueue !== 'function') return false;
    return !!(c.offlineEnqueueUrl || c.offline_enqueue_url);
  }

  function toast(msg, kind) {
    try {
      if (window.bootstrap && bootstrap.Toast) {
        var el = document.createElement('div');
        el.className = 'toast align-items-center text-bg-' + (kind || 'info') + ' border-0 position-fixed bottom-0 end-0 m-3';
        el.setAttribute('role', 'alert');
        el.innerHTML = '<div class="d-flex"><div class="toast-body">' + msg + '</div></div>';
        document.body.appendChild(el);
        var t = new bootstrap.Toast(el, { delay: 4500 });
        t.show();
        el.addEventListener('hidden.bs.toast', function () { el.remove(); });
        return;
      }
    } catch (e) { /* fall through */ }
    window.alert(msg);
  }

  function wireAttendance(form) {
    form.addEventListener('submit', function (ev) {
      if (navigator.onLine || !enabled()) return;
      ev.preventDefault();
      var scope = (form.getAttribute('data-rmc-attendance-scope') || 'student').toLowerCase();
      var dateEl = form.querySelector('[name="date"]');
      var roomEl = form.querySelector('[name="classroom"]');
      var dateVal = dateEl ? dateEl.value : '';
      var roomVal = roomEl ? roomEl.value : '';
      if (!dateVal) {
        toast('Choose date before saving offline.', 'warning');
        return;
      }
      if (scope !== 'teacher' && !roomVal) {
        toast('Choose date and class before saving offline.', 'warning');
        return;
      }
      var selects = form.querySelectorAll('select[name^="status_"]');
      var n = 0;
      selects.forEach(function (sel) {
        var m = sel.name.match(/^status_(\d+)/);
        if (!m) return;
        var sid = m[1];
        var status = sel.value;
        var payload;
        var idem;
        if (scope === 'teacher') {
          idem = 'tatt-' + dateVal + '-' + sid;
          payload = {
            scope: 'teacher',
            teacher_profile_id: parseInt(sid, 10),
            date: dateVal,
            status: status,
          };
        } else {
          idem = 'att-' + roomVal + '-' + dateVal + '-' + sid;
          payload = {
            student_id: parseInt(sid, 10),
            classroom_id: parseInt(roomVal, 10),
            date: dateVal,
            status: status,
          };
        }
        window.rmcOfflineEnqueue({
          action_type: 'attendance',
          payload: payload,
          idempotency_key: idem,
        });
        n += 1;
      });
      toast('Queued ' + n + ' attendance row(s). Open Offline sync when you reconnect.', 'success');
    });
  }

  function parseMaybeNum(v) {
    if (v === '' || v === undefined || v === null) return null;
    var n = parseFloat(String(v).replace(',', '.'));
    return isNaN(n) ? null : n;
  }

  function wireGrading(form) {
    form.addEventListener('submit', function (ev) {
      if (navigator.onLine || !enabled()) return;
      var active = document.activeElement;
      if (active && active.getAttribute && active.getAttribute('name') === 'action' && active.value === 'submit_for_approval') {
        return;
      }
      ev.preventDefault();
      var sa = form.querySelector('[name="subject_assignment_id"]');
      var y = form.getAttribute('data-rmc-year-id');
      var t = form.getAttribute('data-rmc-term-id');
      if (!sa || !y || !t) {
        toast('Missing year/term context for offline marks.', 'warning');
        return;
      }
      var saId = parseInt(sa.value, 10);
      var yearId = parseInt(y, 10);
      var termId = parseInt(t, 10);
      var inputs = form.querySelectorAll(
        'input[name^="seq1_"], input[name^="seq2_"], input[name^="exam_"], input[name^="mock_"], input[name^="practical_"], input[name^="remarks_"]'
      );
      var byStudent = {};
      inputs.forEach(function (inp) {
        var mm = inp.name.match(/^(seq1|seq2|exam|mock|practical|remarks)_(\d+)$/);
        if (!mm) return;
        var field = mm[1];
        var sid = mm[2];
        if (!byStudent[sid]) byStudent[sid] = {};
        if (field === 'remarks') byStudent[sid].remarks = String(inp.value || '');
        else byStudent[sid][field + '_score'] = parseMaybeNum(inp.value);
      });
      var count = 0;
      Object.keys(byStudent).forEach(function (sid) {
        var row = byStudent[sid];
        var hasNum =
          row.seq1_score != null ||
          row.seq2_score != null ||
          row.exam_score != null ||
          row.mock_score != null ||
          row.practical_score != null ||
          (row.remarks && row.remarks.length);
        if (!hasNum) return;
        window.rmcOfflineEnqueue({
          action_type: 'grading',
          payload: {
            subject_assignment_id: saId,
            student_id: parseInt(sid, 10),
            academic_year_id: yearId,
            term_id: termId,
            seq1_score: row.seq1_score,
            seq2_score: row.seq2_score,
            exam_score: row.exam_score,
            mock_score: row.mock_score,
            practical_score: row.practical_score,
            remarks: row.remarks || '',
          },
          idempotency_key: 'grade-' + saId + '-' + sid + '-' + termId,
        });
        count += 1;
      });
      toast('Queued ' + count + ' offline mark row(s).', 'success');
    });
  }

  function wirePaymentReceipt(form) {
    form.addEventListener('submit', function (ev) {
      if (navigator.onLine || !enabled()) return;
      ev.preventDefault();
      var inv = form.getAttribute('data-rmc-invoice-id');
      var bal = form.getAttribute('data-rmc-invoice-balance') || '0';
      var pm = form.querySelector('[name="payment_method"]');
      var amt = form.querySelector('[name="uploaded_amount"]');
      var ref = form.querySelector('[name="transaction_reference"]');
      var notes = form.querySelector('[name="notes"]');
      var idemEl = form.querySelector('[name="idempotency_key"]');
      if (!inv || !pm || !pm.value) {
        toast('Select payment method before queueing offline.', 'warning');
        return;
      }
      var idem = (idemEl && idemEl.value) ? idemEl.value : ('offline-rcpt-' + inv + '-' + Date.now());
      if (idemEl) idemEl.value = idem;
      var amountStr = amt && amt.value ? amt.value : bal;
      window.rmcOfflineEnqueue({
        action_type: 'payment_receipt',
        payload: {
          invoice_id: parseInt(inv, 10),
          amount: amountStr,
          payment_method: pm.value,
          transaction_reference: ref ? ref.value : '',
          notes: (notes ? notes.value : '') + ' [offline_capture_no_file]',
          client_offline_id: idem.slice(0, 64),
        },
        idempotency_key: idem.slice(0, 128),
      });
      toast('Payment details queued (no file). Upload the receipt when you are online.', 'success');
    });
  }

  function wireNotesReport(form) {
    form.addEventListener('submit', function (ev) {
      var bodyEl = form.querySelector('[name="body"], textarea');
      var titleEl = form.querySelector('[name="title"]');
      var sidEl = form.querySelector('[name="student_id"]');
      var body = bodyEl ? String(bodyEl.value || '').trim() : '';
      if (!body) {
        ev.preventDefault();
        toast('Enter note text.', 'warning');
        return;
      }
      if (navigator.onLine) {
        ev.preventDefault();
        toast('When online, use your standard observation or report workflow. This box queues notes only while offline.', 'info');
        return;
      }
      if (!enabled()) {
        ev.preventDefault();
        toast('Offline queue URL not configured.', 'warning');
        return;
      }
      ev.preventDefault();
      window.rmcOfflineEnqueue({
        action_type: 'notes_report',
        payload: {
          body: body,
          title: titleEl ? String(titleEl.value || '') : '',
          student_id: sidEl && sidEl.value ? parseInt(sidEl.value, 10) : null,
          kind: 'quick_capture',
        },
        idempotency_key: 'note-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8),
      });
      toast('Note queued for sync.', 'success');
    });
  }

  function serializeFormFields(form) {
    var payload = {};
    var inputs = form.querySelectorAll('input, select, textarea');
    for (var i = 0; i < inputs.length; i++) {
      var el = inputs[i];
      var name = el.name;
      if (!name || name === 'csrfmiddlewaretoken') continue;
      if (el.type === 'checkbox') {
        payload[name] = el.checked;
      } else if (el.type === 'radio') {
        if (el.checked) payload[name] = el.value;
      } else if (el.value !== '') {
        payload[name] = el.value;
      }
    }
    return payload;
  }

  /**
   * Schoolops / finance / people POST forms that are not yet REST APIs:
   * queue a notes_report row with JSON body for staff replay on sync.
   */
  function wireFieldCapture(form) {
    form.addEventListener('submit', function (ev) {
      if (navigator.onLine || !enabled()) return;
      ev.preventDefault();
      var workflow = (form.getAttribute('data-rmc-offline-workflow') || 'field_capture').trim();
      var fields = serializeFormFields(form);
      if (!Object.keys(fields).length) {
        toast('Nothing to save offline — fill the form first.', 'warning');
        return;
      }
      var body = JSON.stringify({
        workflow: workflow,
        fields: fields,
        captured_at: new Date().toISOString(),
        page_path: global.location && global.location.pathname ? global.location.pathname : '',
      });
      var title = workflow.replace(/[_-]+/g, ' ').slice(0, 200);
      var idem = workflow + '-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
      window.rmcOfflineEnqueue({
        action_type: 'notes_report',
        payload: {
          body: body,
          title: title,
          kind: 'note',
        },
        idempotency_key: idem.slice(0, 128),
      });
      toast('Saved on this device — open Offline sync when you reconnect.', 'success');
    });
  }

  function wireHomeworkSubmission(form) {
    form.addEventListener('submit', function (ev) {
      if (navigator.onLine || !enabled()) return;
      ev.preventDefault();
      var hwEl = form.querySelector('[name="homework_id"]');
      var sidEl = form.querySelector('[name="student_id"]');
      var bodyEl = form.querySelector('[name="submission_text"], [name="body"], textarea');
      var homeworkId = hwEl ? String(hwEl.value || '').trim() : '';
      var studentId = sidEl && sidEl.value ? parseInt(sidEl.value, 10) : null;
      var body = bodyEl ? String(bodyEl.value || '').trim() : '';
      if (!homeworkId || !studentId || !body) {
        toast('Homework id, student, and submission text are required offline.', 'warning');
        return;
      }
      var idem = 'hw-' + homeworkId + '-' + studentId + '-' + Date.now();
      window.rmcOfflineEnqueue({
        action_type: 'homework_submission',
        payload: {
          homework_id: homeworkId,
          student_id: studentId,
          submission_text: body,
        },
        idempotency_key: idem.slice(0, 128),
      });
      toast('Homework queued for sync when you reconnect.', 'success');
    });
  }

  function wireSupportTicket(form) {
    form.addEventListener('submit', function (ev) {
      if (navigator.onLine || !enabled()) return;
      ev.preventDefault();
      var subjectEl = form.querySelector('[name="subject"]');
      var messageEl = form.querySelector('[name="message"]');
      var categoryEl = form.querySelector('[name="category"]');
      var subject = subjectEl ? String(subjectEl.value || '').trim() : '';
      var message = messageEl ? String(messageEl.value || '').trim() : '';
      if (!subject || !message) {
        toast('Enter subject and message before queueing offline.', 'warning');
        return;
      }
      var idem = 'support-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
      window.rmcOfflineEnqueue({
        action_type: 'support.ticket',
        payload: {
          subject: subject,
          message: message,
          category: categoryEl ? String(categoryEl.value || 'SUPPORT') : 'SUPPORT',
        },
        idempotency_key: idem,
      });
      toast('Support message queued. It will send when you reconnect.', 'success');
    });
  }

  function wireDonationCapture(form) {
    form.addEventListener('submit', function (ev) {
      if (navigator.onLine || !enabled()) return;
      ev.preventDefault();
      var nameEl = form.querySelector('[name="donor_name"]');
      var amountEl = form.querySelector('[name="amount"]');
      var donorName = nameEl ? String(nameEl.value || '').trim() : '';
      var amount = amountEl ? String(amountEl.value || '').trim() : '';
      if (!donorName || !amount) {
        toast('Donor name and amount are required offline.', 'warning');
        return;
      }
      var currencyEl = form.querySelector('[name="currency"]');
      var campaignEl = form.querySelector('[name="campaign_name"]');
      var notesEl = form.querySelector('[name="notes"]');
      // Mirror the payment-receipt capture: read a persisted key first and write
      // the generated one back into the hidden field, so a double-submit of this
      // same form reuses one key (enqueue dedupes) and the server receives a
      // non-empty client_offline_id to fold re-keyed replays onto the first gift.
      var idemEl = form.querySelector('[name="idempotency_key"]');
      var idem = (idemEl && idemEl.value)
        ? idemEl.value
        : ('don-' + donorName.toLowerCase().replace(/\s+/g, '-').slice(0, 40) + '-' + amount + '-' + Date.now());
      if (idemEl) idemEl.value = idem;
      window.rmcOfflineEnqueue({
        action_type: 'donation.intake',
        payload: {
          donor_name: donorName,
          amount: amount,
          currency: currencyEl ? String(currencyEl.value || 'USD') : 'USD',
          campaign_name: campaignEl ? String(campaignEl.value || '') : '',
          notes: notesEl ? String(notesEl.value || '') : '',
          client_offline_id: idem.slice(0, 64),
        },
        idempotency_key: idem.slice(0, 128),
      });
      toast('Donation saved on this device — it will sync when you reconnect.', 'success');
    });
  }

  function _mcBlobDb() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open('rmc-mc-offline-blobs', 1);
      req.onupgradeneeded = function (ev) {
        var db = ev.target.result;
        if (!db.objectStoreNames.contains('blobs')) {
          db.createObjectStore('blobs');
        }
      };
      req.onsuccess = function (ev) { resolve(ev.target.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function _csrfCookie() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function _stageMcBlobs(id, files, meta) {
    return _mcBlobDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction('blobs', 'readwrite');
        tx.objectStore('blobs').put({
          files: files,
          uploadUrl: meta && meta.uploadUrl ? meta.uploadUrl : '',
          label: meta && meta.label ? meta.label : '',
          created: Date.now(),
        }, id);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  function _flushMcBlobs() {
    if (!navigator.onLine) return;
    _mcBlobDb().then(function (db) {
      var tx = db.transaction('blobs', 'readonly');
      var store = tx.objectStore('blobs');
      var req = store.getAllKeys();
      req.onsuccess = function () {
        var keys = req.result || [];
        keys.forEach(function (key) {
          var getReq = store.get(key);
          getReq.onsuccess = function () {
            var row = getReq.result;
            if (!row || !row.files || !row.files.length) return;
            var form = document.querySelector('form[data-rmc-offline-form="migration_cloud_upload"]');
            var uploadUrl = (row.uploadUrl || (form && form.action) || '').trim();
            if (!uploadUrl) return;
            var fd = new FormData();
            var csrfEl = form && form.querySelector('[name="csrfmiddlewaretoken"]');
            var csrf = (csrfEl && csrfEl.value) || _csrfCookie();
            if (csrf) fd.append('csrfmiddlewaretoken', csrf);
            if (row.label) fd.append('label', row.label);
            for (var i = 0; i < row.files.length; i++) {
              fd.append('artifacts', row.files[i], row.files[i].name);
            }
            fetch(uploadUrl, {
              method: 'POST',
              body: fd,
              credentials: 'same-origin',
              headers: { 'X-Requested-With': 'XMLHttpRequest' },
            }).then(function (r) {
              if (!r.ok) return;
              var delTx = db.transaction('blobs', 'readwrite');
              delTx.objectStore('blobs').delete(key);
              toast('Offline Migration Cloud files uploaded.', 'success');
            }).catch(function () { /* retry on next online */ });
          };
        });
      };
    }).catch(function () { /* IDB unavailable */ });
  }

  function wireMigrationCloudUpload(form) {
    form.addEventListener('submit', function (ev) {
      if (navigator.onLine || !enabled()) return;
      var cfg = window.SMS_OFFLINE_CONFIG || {};
      if (cfg.migrationCloudUploadSyncEnabled === false) return;
      ev.preventDefault();
      var input = form.querySelector('input[type="file"][name="artifacts"]');
      if (!input || !input.files || !input.files.length) {
        toast('Choose at least one file to queue offline.', 'warning');
        return;
      }
      var files = Array.prototype.slice.call(input.files);
      var idem = 'mc-offline-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
      var labelEl = form.querySelector('[name="label"]');
      var label = labelEl ? String(labelEl.value || '') : '';
      _stageMcBlobs(idem, files, { uploadUrl: form.action || '', label: label }).then(function () {
        window.rmcOfflineEnqueue({
          action_type: 'migration_cloud_upload',
          payload: {
            filenames: files.map(function (f) { return f.name; }),
            sizes: files.map(function (f) { return f.size; }),
            label: label,
            client_offline_id: idem.slice(0, 64),
            pending_local_blobs: true,
          },
          idempotency_key: idem.slice(0, 128),
        });
        toast('Files saved on this device. They will upload when you reconnect.', 'success');
      }).catch(function () {
        toast('Could not store files offline on this device.', 'warning');
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('form[data-rmc-offline-form="attendance"]').forEach(wireAttendance);
    document.querySelectorAll('form[data-rmc-offline-form="grading"]').forEach(wireGrading);
    document.querySelectorAll('form[data-rmc-offline-form="payment_receipt"]').forEach(wirePaymentReceipt);
    document.querySelectorAll('form[data-rmc-offline-form="notes_report"]').forEach(wireNotesReport);
    document.querySelectorAll('form[data-rmc-offline-form="homework_submission"]').forEach(wireHomeworkSubmission);
    document.querySelectorAll('form[data-rmc-offline-form="support_ticket"]').forEach(wireSupportTicket);
    document.querySelectorAll('form[data-rmc-offline-form="field_capture"]').forEach(wireFieldCapture);
    document.querySelectorAll('form[data-rmc-offline-form="donation_capture"]').forEach(wireDonationCapture);
    document.querySelectorAll('form[data-rmc-offline-form="migration_cloud_upload"]').forEach(wireMigrationCloudUpload);
    window.addEventListener('online', _flushMcBlobs);
    if (navigator.onLine) {
      window.setTimeout(_flushMcBlobs, 1500);
    }
  });
})();
