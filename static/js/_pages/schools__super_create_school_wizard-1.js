(function(){
  var pageDataEl=document.getElementById("page-data-schools__super_create_school_wizard-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["schools__super_create_school_wizard-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
    (function () {
      var form = document.getElementById('wizard-form');
      var tabs = [document.getElementById('step1'), document.getElementById('step2'), document.getElementById('step3'), document.getElementById('step4')];
      var tabButtons = [document.getElementById('step1-tab'), document.getElementById('step2-tab'), document.getElementById('step3-tab'), document.getElementById('step4-tab')];
      var btnNext = document.getElementById('btn-next');
      var btnSubmit = document.getElementById('btn-submit');
      var successEl = document.getElementById('wizard-success');
      var errorEl = document.getElementById('wizard-error');
      var currentStep = 0;
      var totalSteps = 4;

      function showStep(i) {
        currentStep = i;
        tabs.forEach(function (t, j) {
          t.classList.toggle('show', j === i);
          t.classList.toggle('active', j === i);
        });
        tabButtons.forEach(function (b, j) {
          b.classList.toggle('active', j === i);
        });
        btnNext.classList.toggle('d-none', i === totalSteps - 1);
        btnSubmit.classList.toggle('d-none', i !== totalSteps - 1);
        var progressEl = document.getElementById('wizard-progress-text');
        if (progressEl) progressEl.textContent = 'Step ' + (i + 1) + ' of ' + totalSteps;
        if (i === 1 && typeof fetchPlansConfigurator === 'function') {
          var cc = document.getElementById('country_code') && document.getElementById('country_code').value;
          fetchPlansConfigurator(cc || '');
        }
      }

      btnNext.addEventListener('click', function () {
        if (currentStep < totalSteps - 1) showStep(currentStep + 1);
      });

      var skipBranding = document.getElementById('skip-branding');
      var skipDomain = document.getElementById('skip-domain');
      if (skipBranding) skipBranding.addEventListener('click', function () { showStep(3); });
      if (skipDomain) skipDomain.addEventListener('click', function () { document.getElementById('btn-submit').focus(); });

      form.addEventListener('submit', function (e) {
        e.preventDefault();
        successEl.classList.add('d-none');
        errorEl.classList.add('d-none');
        var name = document.getElementById('name').value.trim();
        var slug = document.getElementById('slug').value.trim().toLowerCase().replace(/\s+/g, '-');
        var subdomain = document.getElementById('subdomain').value.trim().toLowerCase() || slug;
        var contact_email = document.getElementById('contact_email').value.trim();
        var country_code = document.getElementById('country_code').value.trim().toUpperCase();
        var city_id = document.getElementById('city_id').value.trim();
        var region_code = document.getElementById('region_code').value.trim();
        var sub_system = document.getElementById('sub_system').value;
        var subdivision_id = (document.getElementById('subdivision_id') && document.getElementById('subdivision_id').value) ? document.getElementById('subdivision_id').value.trim() : '';
        var education_profile_code = document.getElementById('education_profile_code').value.trim();
        var primary_color = document.getElementById('primary_color').value;
        var accent_color = document.getElementById('accent_color').value;
        var theme_choice = (document.getElementById('theme_choice') && document.getElementById('theme_choice').value) ? document.getElementById('theme_choice').value : 'UNFOLD';
        var custom_domain = (document.getElementById('custom_domain') && document.getElementById('custom_domain').value) ? document.getElementById('custom_domain').value.trim() : '';
        var plan_id = (document.getElementById('plan_id') && document.getElementById('plan_id').value) ? document.getElementById('plan_id').value.trim() : '';
        var education_system_ids = [];
        var education_level_codes = [];
        var education_system_type_codes = [];
        var multiSel = document.getElementById('education_system_ids');
        var levelSel = document.getElementById('education_level_codes');
        var systemTypeSel = document.getElementById('education_system_type_codes');
        if (multiSel) {
          for (var i = 0; i < multiSel.options.length; i++) {
            if (multiSel.options[i].selected) education_system_ids.push(multiSel.options[i].value);
          }
        }
        if (levelSel) {
          for (var j = 0; j < levelSel.options.length; j++) {
            if (levelSel.options[j].selected) education_level_codes.push(levelSel.options[j].value);
          }
        }
        if (systemTypeSel) {
          for (var k = 0; k < systemTypeSel.options.length; k++) {
            if (systemTypeSel.options[k].selected) education_system_type_codes.push(systemTypeSel.options[k].value);
          }
        }
        var primarySectorEl = document.getElementById('primary_sector');
        if (primarySectorEl && primarySectorEl.value && education_system_type_codes.indexOf(primarySectorEl.value) === -1) {
          education_system_type_codes.unshift(primarySectorEl.value);
        }
        if (education_system_type_codes.length === 0) {
          errorEl.textContent = ((window.__RMC_PAGE_DATA__["schools__super_create_school_wizard-1"] || {})["trans_at_least_one_sector_primary_sector_or_education_system_types_is_required"]);
          errorEl.classList.remove('d-none');
          return;
        }
        if (education_profile_code && education_system_ids.indexOf(education_profile_code) === -1) {
          education_system_ids.unshift(education_profile_code);
        }
        var addons = [];
        document.querySelectorAll('#addons-list input[type="checkbox"]:checked').forEach(function (cb) { addons.push(cb.value); });
        var payload = {
          name: name,
          slug: slug,
          subdomain: subdomain,
          theme_choice: theme_choice,
          contact_email: contact_email,
          country_code: country_code,
          city_id: city_id,
          region_code: region_code,
          sub_system: sub_system,
          subdivision_id: subdivision_id,
          education_level_codes: education_level_codes,
          education_system_type_codes: education_system_type_codes,
          education_profile_code: education_profile_code,
          education_system_ids: education_system_ids,
          primary_color: primary_color,
          accent_color: accent_color,
          custom_domain: custom_domain
        };
        if (plan_id) payload.plan_id = plan_id;
        if (addons.length) payload.addons = addons;
        var parentSchoolIdEl = document.getElementById('parent_school_id');
        if (parentSchoolIdEl && parentSchoolIdEl.value) payload.parent_school_id = parentSchoolIdEl.value.trim();
        var csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
        fetch(((window.__RMC_PAGE_DATA__["schools__super_create_school_wizard-1"] || {})["url_super_api_create_school"]), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf
          },
          body: JSON.stringify(payload),
          credentials: 'same-origin'
        })
          .then(function (r) {
            return r.json().then(function (data) {
              if (r.ok) {
                var msg = 'School created. Provisioning started.';
                if (data.school_id) {
                  var editUrl = (form.getAttribute('data-edit-school-url-template') || '').replace('00000000-0000-0000-0000-000000000000', data.school_id);
                  var timelineTemplate = form.getAttribute('data-timeline-url-template') || '';
                  var timelineUrl = (data.timeline_url || '').trim();
                  if (!timelineUrl && timelineTemplate) {
                    timelineUrl = timelineTemplate.replace('00000000-0000-0000-0000-000000000000', data.school_id);
                  }
                  if (editUrl) {
                    msg += ' <a href="' + editUrl + '" class="alert-link">Edit school</a> (e.g. set logo, verify custom domain).';
                  }
                  if (timelineUrl) {
                    msg += ' <a href="' + timelineUrl + '" class="alert-link">View provisioning timeline</a>.';
                  }
                }
                successEl.innerHTML = msg;
                successEl.classList.remove('d-none');
                form.reset();
                showStep(0);
              } else {
                errorEl.textContent = (data.errors && data.errors.length) ? data.errors.join(' ') : (data.error || 'Request failed');
                errorEl.classList.remove('d-none');
              }
            });
          })
          .catch(function () {
            errorEl.textContent = 'Network error. Try again.';
            errorEl.classList.remove('d-none');
          });
      });

      document.getElementById('name').addEventListener('input', function () {
        var s = this.value.trim().toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
        if (!document.getElementById('slug').value) document.getElementById('slug').value = s;
        if (!document.getElementById('subdomain').value) document.getElementById('subdomain').value = s;
      });

      var countrySelect = document.getElementById('country_code');
      var citySelect = document.getElementById('city_id');
      var citySearch = document.getElementById('city_search');
      var regionCodeInput = document.getElementById('region_code');
      var timezonePreview = document.getElementById('timezone_preview');
      var citySearchUrl = form.getAttribute('data-city-search-url') || '';
      var profileSearchUrl = form.getAttribute('data-profile-search-url') || '';
      var provincesUrl = form.getAttribute('data-provinces-url') || '';
      var cityFetchToken = 0;
      var cityDebounce = null;
      var profileFetchToken = 0;

      function syncTimezonePreview() {
        if (!citySelect) return;
        var selectedOption = citySelect.options[citySelect.selectedIndex] || null;
        if (timezonePreview) timezonePreview.value = selectedOption ? (selectedOption.getAttribute('data-timezone') || '') : '';
      }

      function renderCityOptions(cities) {
        if (!citySelect) return;
        citySelect.innerHTML = '';
        if (!cities || !cities.length) {
          var emptyOpt = document.createElement('option');
          emptyOpt.value = '';
          emptyOpt.textContent = 'No matching cities';
          citySelect.appendChild(emptyOpt);
          syncTimezonePreview();
          return;
        }
        cities.forEach(function (city) {
          var opt = document.createElement('option');
          opt.value = String(city.id || '');
          opt.setAttribute('data-country', city.country_code_alpha2 || city.country_code || '');
          opt.setAttribute('data-country-alpha3', city.country_code || city.country_code_alpha3 || '');
          opt.setAttribute('data-timezone', city.timezone || '');
          opt.textContent = city.city || city.label || '';
          citySelect.appendChild(opt);
        });
        citySelect.selectedIndex = 0;
        syncTimezonePreview();
      }

      function syncStaticCities() {
        if (!countrySelect || !citySelect) return;
        var selectedCountry = countrySelect.value || '';
        var firstVisible = null;
        var selectedVisible = false;
        Array.prototype.forEach.call(citySelect.options, function (opt) {
          var visible = !selectedCountry || opt.getAttribute('data-country') === selectedCountry;
          opt.hidden = !visible;
          opt.disabled = !visible;
          if (visible && !firstVisible) firstVisible = opt;
          if (visible && opt.selected) selectedVisible = true;
        });
        if (!selectedVisible && firstVisible) firstVisible.selected = true;
        syncTimezonePreview();
      }

      function fetchCities(query) {
        if (!countrySelect || !citySelect || !citySearchUrl) {
          syncStaticCities();
          return;
        }
        var selectedCountry = (regionCodeInput && regionCodeInput.value ? regionCodeInput.value : countrySelect.value || '').toUpperCase();
        var q = (query || '').trim();
        var token = ++cityFetchToken;
        var url = citySearchUrl + '?country_code=' + encodeURIComponent(selectedCountry) + '&q=' + encodeURIComponent(q) + '&limit=160';
        fetch(url, { credentials: 'same-origin' })
          .then(function (resp) { return resp.ok ? resp.json() : null; })
          .then(function (data) {
            if (!data || token !== cityFetchToken) return;
            renderCityOptions(data.cities || []);
          })
          .catch(function () {
            if (token === cityFetchToken) syncStaticCities();
          });
      }

      function fetchProvinces(countryCode) {
        var provinceSelect = document.getElementById('subdivision_id');
        if (!provinceSelect || !provincesUrl) return;
        provinceSelect.innerHTML = '<option value="">— None —</option>';
        if (!countryCode) return;
        fetch(provincesUrl + '?country_code=' + encodeURIComponent(countryCode), { credentials: 'same-origin' })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) {
            (data.provinces || []).forEach(function (p) {
              var opt = document.createElement('option');
              opt.value = String(p.id);
              opt.textContent = p.name || p.code || '';
              provinceSelect.appendChild(opt);
            });
          });
      }

      function syncCities() {
        if (!countrySelect) return;
        var selectedCountry = countrySelect.value || '';
        var selectedOption = countrySelect.options[countrySelect.selectedIndex] || null;
        if (regionCodeInput) regionCodeInput.value = selectedOption ? (selectedOption.getAttribute('data-alpha3') || selectedCountry) : selectedCountry;
        fetchCities(citySearch ? citySearch.value : '');
        fetchProvinces(selectedCountry);
        fetchEducationProfiles();
        fetchPlansConfigurator(regionCodeInput ? regionCodeInput.value : selectedCountry);
      }

      var plansConfig = null;
      function fetchPlansConfigurator(countryCode) {
        var url = (form.getAttribute('data-plans-configurator-url') || '').trim();
        if (!url) return;
        url = url + (countryCode ? '?country_code=' + encodeURIComponent(countryCode) : '');
        fetch(url, { credentials: 'same-origin' })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) {
            plansConfig = data;
            var planSelect = document.getElementById('plan_id');
            var addonsList = document.getElementById('addons-list');
            var addonsContainer = document.getElementById('addons-container');
            if (!planSelect) return;
            planSelect.innerHTML = '<option value="">— None (set later) —</option>';
            (data.plans || []).forEach(function (p) {
              var opt = document.createElement('option');
              opt.value = String(p.id);
              opt.textContent = (p.name || p.slug || '') + (p.price_per_student != null ? ' (per student)' : '');
              planSelect.appendChild(opt);
            });
            addonsList.innerHTML = '';
            if (data.addons && data.addons.length) {
              addonsContainer.style.display = 'block';
              data.addons.forEach(function (a) {
                var label = document.createElement('label');
                label.className = 'd-block';
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.value = a.code || '';
                cb.className = 'form-check-input me-2';
                label.appendChild(cb);
                label.appendChild(document.createTextNode((a.name || a.code) + (a.price != null ? ' (+' + a.price + ')' : '')));
                addonsList.appendChild(label);
              });
            } else {
              addonsContainer.style.display = 'none';
            }
            updateEstimatedPrice();
          })
          .catch(function () { plansConfig = null; });
      }

      function updateEstimatedPrice() {
        var el = document.getElementById('estimated-price-display');
        if (!el || !plansConfig) {
          if (el) el.textContent = 'Select country and plan to see estimated price.';
          return;
        }
        var planId = (document.getElementById('plan_id') && document.getElementById('plan_id').value) || '';
        var students = parseInt(document.getElementById('estimated_students') && document.getElementById('estimated_students').value, 10) || 0;
        var mul = plansConfig.country_multiplier != null ? plansConfig.country_multiplier : 1;
        var total = 0;
        var plan = (plansConfig.plans || []).filter(function (p) { return String(p.id) === planId; })[0];
        if (plan) {
          if (plan.billing_model === 'PER_STUDENT' && plan.price_per_student != null) {
            total += students * plan.price_per_student * mul;
          } else if (plan.base_price != null) {
            total += plan.base_price * mul;
          }
        }
        document.querySelectorAll('#addons-list input[type="checkbox"]:checked').forEach(function (cb) {
          var addon = (plansConfig.addons || []).filter(function (a) { return a.code === cb.value; })[0];
          if (addon && addon.price != null) total += addon.price * mul;
        });
        el.textContent = total > 0 ? 'Estimated price (with PPP): ' + total.toFixed(2) : 'Select a plan to see estimated price.';
      }

      var planSelect = document.getElementById('plan_id');
      if (planSelect) {
        planSelect.addEventListener('change', updateEstimatedPrice);
      }
      document.getElementById('estimated_students').addEventListener('input', updateEstimatedPrice);
      document.getElementById('addons-list').addEventListener('change', updateEstimatedPrice);

      function renderEducationProfiles(profiles) {
        var select = document.getElementById('education_profile_code');
        var multiSel = document.getElementById('education_system_ids');
        var previous = select ? (select.value || '') : '';
        if (select) {
          select.innerHTML = '';
          var autoOption = document.createElement('option');
          autoOption.value = '';
          autoOption.textContent = 'Auto by Country and Sub-system (Recommended)';
          select.appendChild(autoOption);
        }
        if (multiSel) multiSel.innerHTML = '';
        (profiles || []).forEach(function(profile) {
          if (!profile || !profile.code) return;
          if (select) {
            var option = document.createElement('option');
            option.value = profile.code;
            option.textContent = profile.name + (profile.is_auto_generated ? ' (Auto pack)' : '');
            select.appendChild(option);
          }
          if (multiSel) {
            var mOpt = document.createElement('option');
            mOpt.value = profile.code;
            mOpt.textContent = profile.name + (profile.is_auto_generated ? ' (Auto)' : '');
            multiSel.appendChild(mOpt);
          }
        });
        if (select) {
          if (previous && Array.prototype.some.call(select.options, function(opt) { return opt.value === previous; })) {
            select.value = previous;
          } else {
            select.value = '';
          }
        }
      }

      function fetchEducationProfiles() {
        if (!countrySelect || !profileSearchUrl) return;
        var subSystemInput = document.getElementById('sub_system');
        var subSystem = subSystemInput ? (subSystemInput.value || 'EN') : 'EN';
        var selectedCountry = (countrySelect.value || '').toUpperCase();
        var provinceInput = document.getElementById('subdivision_id');
        var provinceId = provinceInput ? (provinceInput.value || '') : '';
        var token = ++profileFetchToken;
        var url = profileSearchUrl + '?country_code=' + encodeURIComponent(selectedCountry) + '&sub_system=' + encodeURIComponent(subSystem);
        if (provinceId) url += '&subdivision_id=' + encodeURIComponent(provinceId);
        fetch(url, { credentials: 'same-origin' })
          .then(function(resp) { return resp.ok ? resp.json() : null; })
          .then(function(data) {
            if (!data || token !== profileFetchToken) return;
            renderEducationProfiles(data.profiles || []);
          })
          .catch(function() {
            if (token === profileFetchToken) renderEducationProfiles([]);
          });
      }

      if (countrySelect) countrySelect.addEventListener('change', syncCities);
      if (citySelect) citySelect.addEventListener('change', syncTimezonePreview);
      var provinceSelect = document.getElementById('subdivision_id');
      if (provinceSelect) provinceSelect.addEventListener('change', fetchEducationProfiles);
      var profileSelect = document.getElementById('education_profile_code');
      if (profileSelect) {
        profileSelect.addEventListener('change', function() {
          var multiSel = document.getElementById('education_system_ids');
          if (!multiSel || !this.value) return;
          var opt = this.options[this.selectedIndex];
          var text = (opt && opt.textContent || '').toLowerCase();
          var code = (opt && opt.value || '').toLowerCase();
          var isTrade = text.indexOf('trade') >= 0 || text.indexOf('vocational') >= 0 || text.indexOf('technical') >= 0 || code.indexOf('trade') >= 0 || code.indexOf('voc') >= 0;
          if (isTrade) {
            for (var i = 0; i < multiSel.options.length; i++) {
              if (multiSel.options[i].value === this.value) {
                multiSel.options[i].selected = true;
                break;
              }
            }
          }
        });
      }
      var subSystemSelect = document.getElementById('sub_system');
      if (subSystemSelect) {
        subSystemSelect.addEventListener('change', function() {
          fetchEducationProfiles();
        });
      }
      if (citySearch) {
        citySearch.addEventListener('input', function () {
          clearTimeout(cityDebounce);
          cityDebounce = setTimeout(function () {
            fetchCities(citySearch.value || '');
          }, 220);
        });
      }
      syncCities();
    })();
  
})();
