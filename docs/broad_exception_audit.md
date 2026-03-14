# Broad Exception (except Exception) Audit

**Purpose:** §2.4 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Inventory broad `except Exception` in sensitive apps; replace with typed exceptions and structured logging. Nothing deferred.

**Status:** DONE — inventory complete; CI enforced via `scripts/lint_broad_except.py` and allowlist.

---

## 1. Sensitive apps inventory

### apps/api (§2.4 — Step 9, full app pass)
| File | Status | Notes |
|------|--------|--------|
| dashboard_api.py | DONE | All 6 dashboard views: (ImportError, AttributeError, TypeError, ValueError, ObjectDoesNotExist, DatabaseError) + logger.error + JsonResponse 500. Allowlist 0. |
| digital_id_api.py | DONE | Staff + children APIs: (ImportError, AttributeError, TypeError, ValueError, ObjectDoesNotExist, DatabaseError) + logger.exception. Allowlist 0. |
| ministry_connectors.py | DONE | HTTP response parse: (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError); outer: (OSError, ConnectionError, TimeoutError, ValueError, TypeError). Allowlist 0. |
| rate_limit.py | DONE | _throttle cache: (TypeError, ValueError, AttributeError); _check_tenant_quota_limit, _get_apicenter_quota_for_school, record_tenant_api_usage: (ImportError, AttributeError, TypeError, ValueError, DatabaseError); get_tenant_api_request_count: (TypeError, ValueError, AttributeError). Allowlist 0. |
| search_api.py | DONE | Read layer skip: (ImportError, AttributeError, TypeError, ValueError); per-type search: (ImportError, AttributeError, TypeError, ValueError, ObjectDoesNotExist, DatabaseError) + logger.error. Allowlist 0. |
| entity_api.py | DONE | Bulk create (StudentProfile, Classroom): (DRFValidationError, IntegrityError, DatabaseError, TypeError, ValueError, KeyError); noqa removed. Allowlist 0. |
| views_v1.py | — | No broad except; allowlist 0. |

### apps/dashboard (§2.4 — allowlist shrink)
| File | Status | Notes |
|------|--------|--------|
| admin_context.py | DONE | _query_action_queue: except Exception → except _ADMIN_WIDGET_QUERY_ERRORS (ImportError, AttributeError, TypeError, ValueError, KeyError, DatabaseError, OperationalError, ObjectDoesNotExist, NoReverseMatch, ImproperlyConfigured). Allowlist 0; lint_broad_except --strict pass. |

### apps/schools
| File | Line(s) | Purpose | Verdict | Action |
|------|---------|---------|---------|--------|
| **repositories/health_repository.py** | — | **DONE** | **DONE** | check_table_exists, count_table_rows: (OperationalError, ProgrammingError, DatabaseError) + logger.debug; allowlist 0. |
| **models.py** | — | **DONE** | **DONE** | limits: (ImportError, AttributeError, TypeError, ValueError, DatabaseError) + logger.debug; _has_feature_fallback: (ImportError, AttributeError, TypeError, ValueError, KeyError, DatabaseError) + logger.debug; allowlist 0; lint_broad_except --strict pass. |
| **control_plane.py** | — | **DONE** | **DONE** | Rate limit cache: (ConnectionError, OSError, TypeError, ValueError, AttributeError); audit log: (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError, ImportError). Allowlist 0; lint_broad_except --strict pass. |
| **welcome_email.py** | — | **DONE** | **DONE** | Brand resolve: (ImportError, AttributeError, TypeError, ValueError, KeyError) + logger.debug; send: (OSError, SMTPException). Allowlist 0; lint_broad_except --strict pass. |
| **middleware.py** | — | **DONE** | **DONE** | _cache_get_optional/_cache_set_optional: (ImportError, AttributeError, TypeError, ConnectionError, ValueError, RuntimeError); SchoolDomain query: DatabaseError. Allowlist 0. |
| **super_views.py** | — | **DONE** | **DONE** | Already uses CONTROL_PLANE_METRIC_FAILURES, CONTROL_PLANE_AUDIT_FAILURES, NoReverseMatch, DatabaseError, etc.; no broad except. Allowlist 0. |
| **signup_views.py** | — | **DONE** | **DONE** | ValidationError (email); (ImportError, AttributeError, TypeError, ValueError) for funnel/Plan/ThemePack/policy; (OSError, ConnectionError, ValueError, TypeError) for send_mail; NoReverseMatch for reverse(); (json.JSONDecodeError, TypeError, AttributeError) for JSON parse. Allowlist 0. |
| **marketing_views.py** | — | **DONE** | **DONE** | All 8 broad excepts replaced with typed (NoReverseMatch, ValueError, TypeError, ImportError, DatabaseError, OperationalError, AttributeError, OSError). Allowlist 0; see BACKLOG §1 §2.4 and §5 "§2.4 schools marketing_views". |
| **onboarding_service.py** | — | **DONE** | **DONE** | _drop_tenant_schema: (DatabaseError, OperationalError, ProgrammingError, ImportError, AttributeError, TypeError); _run_tenant_migrations: (ImportError, DatabaseError, OperationalError, OSError, RuntimeError, TypeError, ValueError); _audit_log_public: (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError); ensure_tenant_client/provision_school_sync/domain sync: typed tuples. Allowlist 0. |
| **rls_context.py** | — | **DONE** | **DONE** | rls_school finally-block RESET: (OperationalError, ProgrammingError, DatabaseError) + logger.debug; matches rls_bypass pattern. Allowlist 0; lint_broad_except --strict pass. |
| **domain_sync.py** | — | **DONE** | **DONE** | is_runtime_domain_in_use: (ImportError, AttributeError, DatabaseError); ensure_tenant_client_for_school: (ImportError, AttributeError, DatabaseError); ensure_schooldomain_records_for_school sync_verified_schooldomain: (OSError, ConnectionError, DatabaseError, AttributeError, TypeError, ValueError) + logger.exception. Allowlist 0. |
| **dns_verification.py** | — | **DONE** | **DONE** | verify_domain_txt: (ImportError, OSError, ConnectionError, TimeoutError, UnicodeDecodeError, AttributeError, TypeError, ValueError); verify_and_activate_schooldomain sync: (OSError, ConnectionError, DatabaseError, AttributeError, TypeError, ValueError). Allowlist 0. |
| **tasks.py** | — | **DONE** | **DONE** | ImportError (kombu); _PROVISIONING_FAILURES (DatabaseError, IntegrityError, OSError, ConnectionError, ValueError, TypeError, AttributeError, ImportError, RuntimeError) for provision_school_sync + provision_school_task; (OSError, ConnectionError, DatabaseError, AttributeError, TypeError, ValueError) for sync_school_domains; (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError) for _record_school_event*; (ImportError, AttributeError, TypeError, ValueError, DatabaseError) for hydrate/sync_tenant_modules/persist_compiled_tenant_config; (TypeError, AttributeError, ValueError) for classroom_seed; (ImportError, AttributeError, TypeError, ValueError) for invalidate_policy_cache; (ImportError, AttributeError, ConnectionError, OSError, RuntimeError, TypeError, ValueError) for welcome_email_task.delay. Allowlist 0. |
| **management/commands/tenant_health_check.py** | — | **DONE** | **DONE** | No broad except; only `except ImportError` for django_tenants. Uses health_repository (check_table_exists, count_table_rows) with typed excepts. |
| **management/commands/verify_custom_domains.py** | — | **DONE** | **DONE** | invalidate_policy_cache (2): (ImportError, AttributeError, TypeError, ValueError) + logger.debug; allowlist 0. |
| Others (commands, tests, celery_tasks) | various | Commands/tests | keep (allowlist) | Per-file in allowlist |

### apps/accounts (§2.4 — Step 9, full app pass)
| File | Status | Notes |
|------|--------|--------|
| views.py | DONE | Already typed; allowlist 0. |
| views_migration.py | DONE | CSV/JSON: (UnicodeDecodeError, csv.Error, json.JSONDecodeError, …); run/apply: (ValueError, TypeError, KeyError, ImportError, AttributeError, RuntimeError). Allowlist 0. |
| views_oidc.py | DONE | JWT decode: (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError); token exchange: (OSError, ConnectionError, TimeoutError, …); session: (KeyError, TypeError, RuntimeError). Allowlist 0. |
| views_passkey.py | DONE | All four endpoints: (ValueError, TypeError, KeyError, json.JSONDecodeError, AttributeError). Allowlist 0. |
| views_mfa.py | DONE | otp_login + fromisoformat: (ValueError, TypeError, AttributeError, RuntimeError). Allowlist 0. |
| views_security.py | DONE | _user_has_mfa: (ImportError, AttributeError, TypeError). Allowlist 0. |
| views_onboarding.py | DONE | (AttributeError, TypeError, ValueError, DatabaseError). Allowlist 0. |
| views_delegation.py | DONE | Badge/send_mail: (ImportError, OSError, ConnectionError, AttributeError, TypeError); revoke: (ImportError, AttributeError, TypeError, ValueError). Allowlist 0. |
| middleware.py | DONE | resolve: Resolver404; MFA block: (ImportError, AttributeError, TypeError, ValueError); _is_mfa_verified: (ValueError, TypeError, AttributeError); ImpossibleTravel: (ValueError, TypeError, ImportError, AttributeError, OSError). Allowlist 0. |
| tasks.py | DONE | Email/revoke: (OSError, ConnectionError, AttributeError, TypeError), (ImportError, AttributeError, TypeError, ValueError); promotion_map: (ImportError, AttributeError, TypeError); carry_forward_arrears: (ValueError, TypeError, ImportError, AttributeError). Allowlist 0. |
| security_health.py | DONE | All checkers + get_weights + cache prefix + grace_period: (ImportError, AttributeError, TypeError, KeyError, ValueError). Allowlist 0. |
| templatetags/accounts_extras.py | DONE | _reset_db_state: (DatabaseError, TransactionManagementError); has_role/has_any_role: (DatabaseError, TransactionManagementError, AttributeError, TypeError). Allowlist 0. |
| pii_masking.py | DONE | mask_date: (TypeError, AttributeError, ValueError); can_show_pii: (ValueError, TypeError, AttributeError). Allowlist 0. |
| legacy_data_cleaner.py | DONE | detect + clean: (ImportError, AttributeError, TypeError, ValueError). Allowlist 0. |
| permissions.py | DONE | DatabaseError + (AttributeError, TypeError, ValueError, ImportError). Allowlist 0. |
| models.py | DONE | has_feature_permission rollback: (DatabaseError, TransactionManagementError). Allowlist 0. |
| management/commands/ensure_superuser.py | DONE | (DatabaseError, OSError) for table check; re-raise on other. Allowlist 0. |

### apps/finance (§2.4 — Step 9, full app pass)
| File | Status | Notes |
|------|--------|--------|
| security.py | DONE | Amount: (ValueError, TypeError, InvalidOperation); webhook log: (ValueError, TypeError, UnicodeDecodeError, DatabaseError, IntegrityError, ValidationError) + logger.error. Allowlist 0. |
| payment_validators.py | DONE | RefundValidator: (ValueError, TypeError, InvalidOperation). Allowlist 0. |
| notifications.py | DONE | _invoice_link: NoReverseMatch, ImproperlyConfigured; email send: (OSError, ConnectionError, ValueError, TypeError). Allowlist 0. |
| ocr_runtime.py | DONE | _credentials_file_exists: OSError, TypeError; pytesseract: ImportError. Allowlist 0. |
| signals.py | DONE | emit_platform_event + notify_guardians: (ImportError, AttributeError, TypeError, ValueError) + logger.debug. Allowlist 0. |
| admin.py | DONE | copy_fee_plan, resend_reminders, approve_selected, reject_selected, save_model void: typed (ValidationError, DatabaseError, IntegrityError, etc.) + debug log. Allowlist 0. |
| services.py | DONE | payment.created/invoice.created emit_event: (ImportError, AttributeError, TypeError, ValueError, KeyError) + debug; parent_finance_summary: (NoReverseMatch, ImproperlyConfigured, ObjectDoesNotExist, DatabaseError, AttributeError, TypeError, ValueError) + debug. Allowlist 0. |
| aid_services.py | DONE | _student_context: (ImportError, AttributeError, TypeError, ValueError); check_eligibility: (TypeError, ValueError, KeyError, AttributeError); webhook enqueue: (ImportError, AttributeError, TypeError, ValueError, ConnectionError, OSError); net_price_estimate: (ImportError, AttributeError, TypeError, ValueError). Allowlist 0. |
| fraud_detection.py | DONE | Date/amount validation: (ValueError, TypeError, AttributeError, InvalidOperation); image/EXIF/metadata: (OSError, IOError, AttributeError, TypeError, ValueError). Allowlist 0. |
| receipt_verification.py | DONE | OCR extraction: (ValueError, TypeError, OSError, UnicodeDecodeError); tesseract CLI: (OSError, IOError, ValueError, TypeError, UnicodeDecodeError) + debug. Allowlist 0. |
| payment_processors.py | DONE | Processor init: (ImportError, AttributeError, TypeError, ValueError, KeyError) + logger.warning. Allowlist 0. |
| bank_statement_import.py | DONE | Row processing: (ValueError, TypeError, DatabaseError, IntegrityError, ValidationError). Allowlist 0. |
| advanced_payments.py | DONE | record_payment: (DatabaseError, IntegrityError, ValidationError, ValueError, TypeError, AttributeError) + debug. Allowlist 0. |
| ohada_reports.py | DONE | _to_decimal: (ValueError, TypeError, InvalidOperation, ArithmeticError). Allowlist 0. |
| models.py | DONE | get_reminder_days_before / get_reminder_channels: (ImportError, AttributeError, TypeError, KeyError) + debug. Allowlist 0. |
| management/commands/verify_bank_deposits.py | DONE | Verify loop: (ValidationError, DatabaseError, IntegrityError, ValueError, TypeError, AttributeError). Allowlist 0. |

### apps/siteconfig
| File | Line(s) | Purpose | Verdict | Action |
|------|---------|---------|---------|--------|
| context_processors.py | — | OPTIONAL_CONTEXT_ERRORS / OPTIONAL_STORAGE_ERRORS (typed tuples); no broad except | DONE | allowlist 0. |
| **templatetags/feature_control.py** | — | **DONE** | **DONE** | feature_enabled: (ImportError, AttributeError, TypeError, ValueError, KeyError); allowlist 0. |
| **report_template_engine.py** | — | **DONE** | **DONE** | render_official_template_html: (TemplateSyntaxError, KeyError, ValueError, TypeError, AttributeError); allowlist 0. |
| **templatetags/region_format.py** | — | **DONE** | **DONE** | format_date: (TypeError, ValueError, AttributeError); format_date_tenant: (ImportError, AttributeError, TypeError, ValueError, KeyError); format_currency_tenant: (ImportError, AttributeError, TypeError, ValueError); allowlist 0. |
| workflow_engine.py | — | **DONE** | **DONE** | record_workflow_run: WORKFLOW_SOFT_FAILURES + logger.debug; allowlist 0. |
| **management/commands/check_branding_law.py** | — | **DONE** | **DONE** | read_text: (OSError, UnicodeDecodeError); allowlist 0. |
| **management/commands/compile_translations.py** | — | **DONE** | **DONE** | import: (OSError, ValueError, KeyError, TypeError); allowlist 0. |
| **management/commands/index_ai_knowledge.py** | — | **DONE** | **DONE** | _index_policy_bundles, _index_blueprint_packs, _index_workflow_packs, _index_report_templates: (ImportError, AttributeError, TypeError, ValueError, KeyError, DatabaseError, OperationalError, OSError) + logger.warning; AIMemoryService import added. Linter skips apps/siteconfig/management/. |
| **management/commands/recover_database.py** | — | **DONE** | **DONE** | backup: (OSError, PermissionError, shutil.Error); unlink: (OSError, PermissionError); migrate: (DatabaseError, OSError, PermissionError, SystemError) + logger.warning. Linter skips apps/siteconfig/management/. |
| **dashboard_views.py** | — | **DONE** | **DONE** | update_theme / update_accessibility_preferences: _DASHBOARD_PREF_ERRORS (ValueError, TypeError, KeyError, DatabaseError, IntegrityError, json.JSONDecodeError) + logger.exception/logger.warning; allowlist 0. |
| **views_dashboard_config.py** | — | **DONE** | **DONE** | workflow_hub: NoReverseMatch for automation_hub_url; get_blueprints: _OPTIONAL_HUB_ERRORS (ImportError, AttributeError, TypeError, ValueError, DatabaseError) + logger.debug for optional packs/manager_blueprints_url; allowlist 0. |
| **views.py** | — | **DONE** | **DONE** | theme/experience save redirect: NoReverseMatch for studio_os:experience → fallback to siteconfig:theme_colors + log_view_exception. Allowlist 0. |
| views / other commands | various | Optional features / reverse / format | keep (allowlist) | In allowlist |

### apps/people (§2.4 — management commands)
| File | Status | Notes |
|------|--------|------|
| **management/commands/attach_audit_triggers.py** | **DONE** | Single-schema and per-tenant attach: _AUDIT_TRIGGER_ERRORS (DatabaseError, OperationalError, ProgrammingError) + logger.warning; allowlist 0. |

### apps/compliance (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| signals.py | DONE | post_save notify_audit_event: (ImportError, AttributeError, TypeError, ValueError); _bump_rules_version cache: (ValueError, TypeError, AttributeError, ConnectionError, OSError). Allowlist 0. |
| access_control.py | DONE | _access_control_prefix: (ImportError, AttributeError, TypeError, ValueError); check_ip_access table/query: (DatabaseError, OperationalError, ProgrammingError) + logger.debug; get_country_from_ip: (ImportError, AttributeError, TypeError, ValueError, OSError). Allowlist 0. |
| threat_detection.py | DONE | detect_threats config fallback: _THREAT_CONFIG_FALLBACK_ERRORS (DatabaseError, OperationalError, IntegrityError, AttributeError, TypeError, ValueError) + logger.debug; allowlist 0. |

### apps/evals (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| performance_optimization.py | DONE | _tenant_prefix: (ImportError, AttributeError, TypeError); allowlist 0; lint_broad_except --strict pass. |
| caching.py | DONE | get_cache_stats: (AttributeError, TypeError, ValueError, KeyError) + logger.debug; allowlist 0. |
| signals.py | DONE | create_audit_trail_and_convert_grades, handle_offline_sync_complete: _EVALS_AUDIT_FAILURES (DatabaseError, IntegrityError, ValidationError, AttributeError, TypeError, ValueError) + log_exception_with_context. Allowlist 0. |
| **notifications.py** | **DONE** | All 5 send paths: _EVALS_NOTIFICATION_SEND_ERRORS (OSError, ConnectionError, TimeoutError, SMTPException, ValueError, TypeError, AttributeError, KeyError) + log_exception_with_context. Allowlist 0. |
| notifications.py | DONE | All 5 send paths (grade_publication_email/sms, deadline_reminder, grade_approval_request_email, grade_approval_decision_email): broad except retained with log_exception_with_context(school_id/actor_id, extra=recipient/flow). Missing django.core.mail.send_mail import added. Allowlist 0. |
| validators.py | DONE | GradeValidator.validate_evaluation: outlier/jump/duplicate_remark use _EVAL_VALIDATION_DETECTION_ERRORS (TypeError, ValueError, ZeroDivisionError, AttributeError, KeyError, DatabaseError) + log_exception_with_context(school_id, extra: evaluation_id, section). Allowlist 0. |

### apps/studio_os (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| views.py | DONE | _resolve_legacy_urls + all reverse() and optional-context blocks: NoReverseMatch (or typed tuple for get_theme_colors_context, launch payload, control_audit, control_panel_html, messages.success). Allowlist 0; lint_broad_except --strict pass. |
| services.py | DONE | get_studio_recommendations launch payload: _STUDIO_SOFT_FAILURES (ImportError, AttributeError, TypeError, ValueError, KeyError, ObjectDoesNotExist, DatabaseError, NoReverseMatch) + logger.debug. Allowlist 0. |

### apps/brand_experience (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| design_studio.py | DONE | get_layout_metadata: (ImportError, AttributeError, TypeError, ValueError, KeyError); allowlist 0. |

### apps/academics (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| degree_audit.py | DONE | Eval credits loop: (ImportError, AttributeError, TypeError, ValueError, ObjectDoesNotExist, DatabaseError) + logger.debug; degree audit resilient if eval subsystem unavailable. Allowlist 0. |

### apps/automation (§2.4 sprint — Step 9)
| File | Status | Notes |
|------|--------|--------|
| models.py | DONE | Rollback run: (DatabaseError, IntegrityError, ValidationError, ValueError, TypeError) + logger.exception; result dict + mark_completed(FAILED) preserved; unexpected errors propagate. |

### apps/orchestration (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| runners.py | DONE | BaseOrchestrationRunner.execute: _ORCHESTRATION_RUN_ERRORS (DatabaseError, IntegrityError, ValueError, TypeError, AttributeError, ImportError, RuntimeError) + log_exception_with_context; compensate() same tuple + log. FeeFollowUpRunner/AdmissionsRunner/ReEnrollmentRunner.run_step: _ORCHESTRATION_STEP_QUERY_ERRORS (ImportError, DatabaseError, OperationalError, ProgrammingError, AttributeError, TypeError) + log_exception_with_context. run_workflow_simulation: _ORCHESTRATION_RUN_ERRORS + log. Allowlist 0. |

### apps/platform_runtime (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| governor_limits.py | DONE | record_workflow_run/record_dashboard_refresh: (ValueError, TypeError, AttributeError, ConnectionError, OSError) + logger.debug; get_governor_usage_for_tenant: get_tenant_api_request_count (ImportError, AttributeError, TypeError, ValueError); cache.get (TypeError, AttributeError, ConnectionError, OSError). Allowlist 0. |

### apps/packages (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| engine.py | DONE | Optional emit_platform_event in apply + rollback: _EVENT_EMIT_ERRORS (ImportError, AttributeError, TypeError, ValueError, ConnectionError, OSError) + logger.debug; allowlist 0. |

### apps/dashboard (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| admin_context.py | DONE | _safe_reverse: _ADMIN_REVERSE_ERRORS (NoReverseMatch, ImproperlyConfigured, ValueError, TypeError); all widget query fns: _ADMIN_WIDGET_QUERY_ERRORS (ImportError, AttributeError, TypeError, ValueError, KeyError, DatabaseError, OperationalError, ObjectDoesNotExist, NoReverseMatch, ImproperlyConfigured) + logger.debug or log_view_exception. Allowlist 0. |

### apps/events (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| tasks.py | DONE | process_outbox_batch: except Exception → except _EVENT_OUTBOX_PROCESS_ERRORS (IntegrityError, OperationalError, DatabaseError, ValidationError, ValueError, TypeError, OSError, ObjectDoesNotExist, AttributeError, KeyError) + log_exception_with_context; allowlist 0. |
| webhooks.py | DONE | _default_http_post: HTTPError body decode → (OSError, UnicodeDecodeError, ValueError, TypeError); defensive urlopen branch → (OSError, TimeoutError, ValueError, TypeError); allowlist 0. |

### apps/billing (§2.4 — Step 9, full app pass)
| File | Status | Notes |
|------|--------|--------|
| entitlements.py | DONE | can/limits/usage: typed (ImportError, AttributeError, TypeError, ValueError, DatabaseError) + logger.debug; allowlist 0. |
| services.py | DONE | Payout: (ValueError, KeyError, TypeError, AttributeError, DatabaseError, ConnectionError, OSError) + logger.warning; allowlist 0. |
| admin.py | DONE | accept_quote: (ValidationError, ValueError, TypeError, DatabaseError, KeyError, AttributeError); allowlist 0. |

### apps/observability (§2.4 sprint — Step 9)
| File | Status | Notes |
|------|--------|--------|
| views.py | DONE | All broad excepts replaced with typed (ImportError, AttributeError, OSError, requests.RequestException, ValueError, KeyError, DatabaseError, IntegrityError, ValidationError, TypeError) + structured logging (logger.exception / logger.warning / logger.debug). |
| monitoring.py | DONE | Optional psutil → ImportError; memory/disk/CPU/cache fallbacks → OSError, AttributeError, TypeError, ValueError; SystemHealthMonitor get_* → same + logger.error. |
| middleware.py | DONE | Metrics record → (AttributeError, TypeError, ValueError) + debug log. |
| templatetags/admin_extras.py | DONE | model.objects.count() → DatabaseError, IntegrityError, ValueError; add_preserved_filters → ImportError, AttributeError, TypeError. |
| management/commands/synthetic_probe.py | DONE | reverse("ready") → NoReverseMatch, ImproperlyConfigured. |
| db_liveness.py | DONE | check_db_liveness: _DB_LIVENESS_ERRORS (DatabaseError, OperationalError, ProgrammingError, InterfaceError) + logger.warning; allowlist 0. |

### apps/requests (§2.4 sprint — Step 9)
| File | Status | Notes |
|------|--------|--------|
| tasks.py | DONE | Notification create → (IntegrityError, ValidationError, DatabaseError) + logger.warning; task body → (DatabaseError, IntegrityError, ValidationError, ValueError, TypeError) + logger.exception + re-raise. |
| services.py | DONE | GradeApprovalRequest filter → (DatabaseError, IntegrityError); target = None on failure. |

### apps/metadata (§2.4 sprint — Step 9)
| File | Status | Notes |
|------|--------|--------|
| changelog.py | DONE | record_metadata_changelog: MetadataChangeLog.objects.create → (DatabaseError, IntegrityError, ValidationError) + logger.warning (no silent pass). |
| lineage_api.py | DONE | get_unified_lineage field lookup: (FieldCatalogEntry.DoesNotExist, *_FIELD_LOOKUP_ERRORS) with log_exception_with_context on non-DoesNotExist; _FIELD_LOOKUP_ERRORS = AttributeError, DatabaseError, IntegrityError, ImportError, LookupError, TypeError, ValidationError, ValueError. Allowlist 0. |
| usage_registry.py | DONE | register_usage + get_lineage_consumers: METADATA_USAGE_SOFT_FAILURES; log_exception_with_context in both except blocks (extra: consumer_type/consumer_code/entity_code/field_name, entity_code/field_id). No allowlist entry (typed only). |

### apps/reports (§2.4 — structured logging rollout)
| File | Status | Notes |
|------|--------|--------|
| adhoc_runner.py | DONE | run_adhoc_report: _REPORT_RUN_ERRORS (DatabaseError, IntegrityError, ValidationError, TypeError, ValueError, KeyError, AttributeError, OSError, ImportError) + log_exception_with_context. Allowlist 0. |
| bi_services.py | DONE | ScheduledReportRunner.run_due_reports: _SCHEDULED_REPORT_RUN_ERRORS (same typed tuple) + log_exception_with_context. Allowlist 0. |
| services.py | DONE | notify_parent_report_blocked_by_debt: (OSError, ConnectionError, AttributeError, TypeError, ValueError, KeyError) + log_exception_with_context. _region_display_context: region lookup (ObjectDoesNotExist, DatabaseError, KeyError, TypeError, AttributeError); tenant locale/template_family (ImportError, AttributeError, TypeError, ValueError, KeyError, DatabaseError). All + log_exception_with_context. Allowlist 0. |
| views.py | DONE (logging) | Publish flow: AuditLog create + honor roll badge create — broad except retained with log_exception_with_context (request/school_id, extra: academic_year_id, term_id, student_id). Allowlist 2. |
| **weasy.py** | **DONE** | _load_weasyprint_html: _WEASYPRINT_LOAD_ERRORS (ImportError, ModuleNotFoundError, AttributeError, OSError) + re-raise RuntimeError. Allowlist 0. |

### apps/analytics (§2.4 — incremental)
| File | Status | Notes |
|------|--------|------|
| **services.py** | **DONE** | get_import_job_status: _IMPORT_JOB_STATUS_ERRORS (ObjectDoesNotExist, AttributeError, TypeError, ValueError); returns None on expected failures. Allowlist 0. |

### apps/policies (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|--------|
| rollback.py | DONE | set_active_policy_bundle: (ObjectDoesNotExist, DatabaseError, IntegrityError, ValueError, TypeError) + logger.debug; allowlist 0. |

### apps/portal (§2.4 — broad except replacement pass)
| File | Status | Notes |
|------|--------|--------|
| templatetags/portal_breadcrumb.py | DONE | split filter: (TypeError, AttributeError, ValueError); breadcrumb_label: (TypeError, AttributeError, ValueError). Allowlist 0. |
| views_parent_finance.py | DONE | reverse() fallback → (NoReverseMatch, ImproperlyConfigured) + logger.debug. |
| models_kb.py | DONE | article_count property → (DatabaseError, TypeError, AttributeError) + logger.debug. |
| views_documents.py | DONE | PDF conversion → (OSError, ValueError, TypeError) + logger.warning. |
| services.py | DONE | parent_completeness → (AttributeError, TypeError); upcoming_public_events_for_school → (ImportError, AttributeError, TypeError, ValueError, DatabaseError); slot_by_class_subject → (AttributeError, TypeError, ValueError); all + logger.debug. |
| views_kb.py | DONE | _get_kb_region: (ImportError, AttributeError, TypeError, KeyError) and (ImportError, OSError, ConnectionError, AttributeError, TypeError) + log_exception_with_context; kb_article_download_docx: (OSError, IOError, ValueError, TypeError) + log_exception_with_context. Allowlist 0. |
| views_ai_copilot.py | DONE | Cache: (AttributeError, OSError, RuntimeError, TypeError, ValueError); audit: DatabaseError + log_exception_with_context + request_context_for_log(request); request body: json.JSONDecodeError, (DatabaseError, OSError, RuntimeError, TypeError, ValueError). Allowlist 0. |
| **views_ai_gateway.py** | **DONE** | GATEWAY_VIEW_ERRORS (AttributeError, DatabaseError, ImportError, TypeError, ValueError, OSError, ConnectionError, RuntimeError, KeyError); _actor_roles: (AttributeError, DatabaseError, TypeError); _log_gateway_audit: (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError); all gateway view handlers use GATEWAY_VIEW_ERRORS after json.JSONDecodeError. Allowlist 0. |
| **views_parent.py** | **DONE** | parent_dashboard FormSignature stats: (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError) + log_view_exception. Allowlist 0. |
| **tasks.py** | **DONE** | generate_ai_response_async: (OSError, ConnectionError, TimeoutError, ValueError, TypeError, ImportError, AttributeError, KeyError, RuntimeError) + log_exception_with_context. Allowlist 0. |
| **forms.py** | **DONE** | LinkChildForm/StudentOnboardingForm: _FORM_POLICY_ERRORS (ImportError, AttributeError, TypeError, ValueError, KeyError) + logger.debug for apply_form_policy; payment_method choices: (DatabaseError, ObjectDoesNotExist, AttributeError, TypeError). Allowlist 0. |
| **ai_provider.py** | **DONE** | general_chat + get_workflow_clues + suggest_support_ticket_response: _AI_GATEWAY_INVOKE_ERRORS (OSError, ConnectionError, TimeoutError, ValueError, TypeError, KeyError, AttributeError, ImportError) + logger.warning. Allowlist 0. |
| **management/commands/import_docs_to_kb.py** | PARTIAL (logging) | Broad except retained in file-processing loop and markdown-conversion fallback; log_exception_with_context added in both blocks (extra: command, file). Rollout per BACKLOG §2e row 7. |
| **management/commands/generate_kb_odt.py** | PARTIAL (logging) | Broad except retained in article-conversion loop and odt_file.delete; log_exception_with_context added (extra: command, article_slug). Rollout per BACKLOG §2e row 7. |
| **management/commands/generate_regional_reports.py** | PARTIAL (logging) | Two broad excepts retained: per-student report loop and _send_report_email; log_exception_with_context added (school_id, extra: command, student_id, language). Allowlist 2. |
| **document_generation.py** | **DONE** | markdown_to_html: _MARKDOWN_CONVERT_ERRORS (TypeError, ValueError, KeyError, AttributeError, LookupError) + log_exception_with_context; fallback to _simple_markdown_to_html. Allowlist 0 (no entry needed; 0 broad except). |

### apps/marketplace (§2.4 — Step 9)
| File | Status | Notes |
|------|--------|------|
| **views.py** | **DONE** | Blueprint pack preview: _MARKETPLACE_PREVIEW_FAILURES; app sandbox embed: _embed_parse_errors (ValueError, TypeError, AttributeError, KeyError) for urlparse/origin. Allowlist 0. |

### apps/setup_studio (§2.4 — incremental)
| File | Status | Notes |
|------|--------|------|
| **services.py** | **DONE** | _safe_reverse: (NoReverseMatch, TypeError, ValueError); _school_surface_url: (ImportError, AttributeError, TypeError, ValueError, OSError, ConnectionError) for school_subdomain_fqdn; _rank_blueprints: (ImportError, AttributeError, TypeError) for BlueprintPack import. Allowlist 0. |

### apps/communication (§2.4 — incremental)
| File | Status | Notes |
|------|--------|------|
| **channels.py** | **DONE** | send_whatsapp: (requests.RequestException, OSError, ValueError, TypeError) + logger.exception; send_push: (OSError, ConnectionError, TimeoutError, ValueError, TypeError) + logger.exception. Allowlist 0. |

---

## 2. CI enforcement

- **Script:** `scripts/lint_broad_except.py --allowlist scripts/allowlists/broad_except_allowlist.json --strict`
- **Gate:** `scripts/pre_deploy_gate.sh` runs the above. New `except Exception` in sensitive apps must be allowlisted with reason.
- **Structured logging:** Where kept, ensure logger includes tenant/actor/route/school_id where available.

---

## 3. Completion gate (§2.4)

- [x] Broad exception inventory complete for api, schools, accounts, finance, siteconfig, evals, automation.
- [x] All current usages classified and allowlisted; CI blocks unlisted new usage.
- [x] Portal pass: views_parent_finance, models_kb, views_documents, services, views_kb — broad except replaced with typed + structured logging (see §portal above).
- [x] portal/views_ai_gateway DONE (GATEWAY_VIEW_ERRORS; allowlist 0). Future: remaining allowlisted files per backlog.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.4.*
