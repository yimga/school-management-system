from django.test import SimpleTestCase

from apps.observability.logging_context import (
    RequestContextFilter,
    clear_request_logging_context,
    set_request_logging_context,
)


class LoggingContextHelperTests(SimpleTestCase):
    def test_clear_request_logging_context_resets_values(self):
        set_request_logging_context("req-1", "tenant-1", "user-1", school_id="9")
        clear_request_logging_context()

        record = type("Record", (), {})()
        RequestContextFilter().filter(record)

        self.assertEqual(record.request_id, "-")
        self.assertEqual(record.tenant_id, "-")
        self.assertEqual(record.user_id, "-")
        self.assertEqual(record.school_id, "-")
        self.assertEqual(record.http_method, "-")
        self.assertEqual(record.request_path, "-")
        self.assertEqual(record.remote_addr, "-")
        self.assertEqual(record.http_referer, "-")
        self.assertEqual(record.http_user_agent, "-")
        self.assertEqual(record.http_host, "-")
        self.assertEqual(record.content_type, "-")
        self.assertEqual(record.accept_language, "-")
        self.assertEqual(record.accept_encoding, "-")
        self.assertEqual(record.x_forwarded_for, "-")
        self.assertEqual(record.x_forwarded_proto, "-")
        self.assertEqual(record.x_forwarded_host, "-")
        self.assertEqual(record.content_length, "-")
        self.assertEqual(record.http_origin, "-")
        self.assertEqual(record.query_string, "-")
        self.assertEqual(record.server_protocol, "-")
        self.assertEqual(record.request_scheme, "-")
        self.assertEqual(record.server_name, "-")

    def test_clear_request_logging_context_resets_http_referer_after_prior_set(self):
        set_request_logging_context(http_referer="https://prior.example/from")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.http_referer, "-")

    def test_school_id_propagates_to_log_record(self):
        set_request_logging_context(school_id="42")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.school_id, "42")
        clear_request_logging_context()

    def test_http_method_propagates_to_log_record(self):
        set_request_logging_context(http_method="patch")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.http_method, "PATCH")
        clear_request_logging_context()

    def test_request_path_propagates_to_log_record(self):
        set_request_logging_context(request_path="/finance/invoices/")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.request_path, "/finance/invoices/")
        clear_request_logging_context()

    def test_remote_addr_propagates_to_log_record(self):
        set_request_logging_context(remote_addr="203.0.113.7")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.remote_addr, "203.0.113.7")
        clear_request_logging_context()

    def test_http_referer_propagates_to_log_record(self):
        set_request_logging_context(http_referer="https://app.example/prev")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.http_referer, "https://app.example/prev")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_http_user_agent_after_prior_set(self):
        set_request_logging_context(http_user_agent="Mozilla/5.0 (test)")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.http_user_agent, "-")

    def test_http_user_agent_propagates_to_log_record(self):
        set_request_logging_context(http_user_agent="RunMyCampus-QA/1.0")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.http_user_agent, "RunMyCampus-QA/1.0")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_content_type_after_prior_set(self):
        set_request_logging_context(content_type="application/json")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.content_type, "-")

    def test_content_type_propagates_to_log_record(self):
        set_request_logging_context(content_type="multipart/form-data; boundary=x")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.content_type, "multipart/form-data; boundary=x")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_http_host_after_prior_set(self):
        set_request_logging_context(http_host="manager.runmycampus.com")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.http_host, "-")

    def test_http_host_propagates_to_log_record(self):
        set_request_logging_context(http_host="tenant.example.com")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.http_host, "tenant.example.com")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_accept_language_after_prior_set(self):
        set_request_logging_context(accept_language="en-US,en;q=0.9")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.accept_language, "-")

    def test_accept_language_propagates_to_log_record(self):
        set_request_logging_context(accept_language="fr-CA,fr;q=0.8")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.accept_language, "fr-CA,fr;q=0.8")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_accept_encoding_after_prior_set(self):
        set_request_logging_context(accept_encoding="gzip, deflate, br")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.accept_encoding, "-")

    def test_accept_encoding_propagates_to_log_record(self):
        set_request_logging_context(accept_encoding="gzip, deflate")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.accept_encoding, "gzip, deflate")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_x_forwarded_for_after_prior_set(self):
        set_request_logging_context(x_forwarded_for="198.51.100.10, 10.0.0.1")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.x_forwarded_for, "-")

    def test_x_forwarded_for_propagates_to_log_record(self):
        set_request_logging_context(x_forwarded_for="203.0.113.5")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.x_forwarded_for, "203.0.113.5")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_x_forwarded_proto_after_prior_set(self):
        set_request_logging_context(x_forwarded_proto="HTTPS")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.x_forwarded_proto, "-")

    def test_x_forwarded_proto_propagates_to_log_record_lowercased(self):
        set_request_logging_context(x_forwarded_proto="HTTPS")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.x_forwarded_proto, "https")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_content_length_after_prior_set(self):
        set_request_logging_context(content_length="2048")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.content_length, "-")

    def test_content_length_strips_non_digits(self):
        set_request_logging_context(content_length="abc123def456")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.content_length, "123456")
        clear_request_logging_context()

    def test_content_length_propagates_digits_only(self):
        set_request_logging_context(content_length="4096")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.content_length, "4096")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_x_forwarded_host_after_prior_set(self):
        set_request_logging_context(x_forwarded_host="Manager.Example.COM")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.x_forwarded_host, "-")

    def test_x_forwarded_host_propagates_lowercased(self):
        set_request_logging_context(x_forwarded_host="Manager.RunMyCampus.COM")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.x_forwarded_host, "manager.runmycampus.com")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_http_origin_after_prior_set(self):
        set_request_logging_context(http_origin="https://tenant.example.com")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.http_origin, "-")

    def test_http_origin_propagates_to_log_record(self):
        set_request_logging_context(http_origin="https://app.runmycampus.com")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.http_origin, "https://app.runmycampus.com")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_query_string_after_prior_set(self):
        set_request_logging_context(query_string="page=2&q=test")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.query_string, "-")

    def test_query_string_propagates_to_log_record(self):
        set_request_logging_context(query_string="primary_sector=K12&q=demo")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.query_string, "primary_sector=K12&q=demo")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_server_protocol_after_prior_set(self):
        set_request_logging_context(server_protocol="HTTP/1.1")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.server_protocol, "-")

    def test_server_protocol_propagates_to_log_record(self):
        set_request_logging_context(server_protocol="HTTP/1.0")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.server_protocol, "HTTP/1.0")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_request_scheme_after_prior_set(self):
        set_request_logging_context(request_scheme="HTTPS")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.request_scheme, "-")

    def test_request_scheme_propagates_to_log_record_lowercased(self):
        set_request_logging_context(request_scheme="HTTPS")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.request_scheme, "https")
        clear_request_logging_context()

    def test_clear_request_logging_context_resets_server_name_after_prior_set(self):
        set_request_logging_context(server_name="manager.runmycampus.com")
        clear_request_logging_context()
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.server_name, "-")

    def test_server_name_propagates_to_log_record(self):
        set_request_logging_context(server_name="tenant.example.com")
        record = type("Record", (), {})()
        RequestContextFilter().filter(record)
        self.assertEqual(record.server_name, "tenant.example.com")
        clear_request_logging_context()
