import importlib.util
import base64
import json
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("bootstrap", Path(__file__).parents[1] / "docker/start.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.env = {"DATABASE_URL": "postgresql://demo:p%40ss%3A%22word@db.example:1234/defaultdb",
                    "PG_CA_CERT": "test-ca", "UI_PASSWORD": "a-long-test-password",
                    "PUBLIC_ORIGIN": "https://demo.example"}

    def test_credentials_are_decoded_and_safely_serialized(self):
        s = bootstrap.settings(self.env)
        config = json.loads(json.dumps(bootstrap.server_config(s)))
        sql = config["persistence"]["datastores"]["default"]["sql"]
        self.assertEqual(sql["password"], 'p@ss:"word')
        self.assertTrue(sql["tls"]["enabled"])
        self.assertTrue(sql["tls"]["enableHostVerification"])
        for service in config["services"].values():
            self.assertEqual(service["rpc"]["bindOnIP"], "127.0.0.1")

    def test_tls_cannot_be_disabled_on_runtime(self):
        self.env["PG_SSLMODE"] = "disable"
        with self.assertRaises(ValueError):
            bootstrap.settings(self.env)

    def test_missing_ca_fails_closed(self):
        self.env.pop("PG_CA_CERT")
        with self.assertRaises(ValueError):
            bootstrap.settings(self.env)

    def test_base64_ca_is_decoded_for_runtime(self):
        pem = "-----BEGIN CERTIFICATE-----\nexample\n-----END CERTIFICATE-----\n"
        self.env.pop("PG_CA_CERT")
        self.env["PG_CA_CERT_BASE64"] = base64.b64encode(pem.encode()).decode()
        self.assertEqual(bootstrap.settings(self.env)["ca_cert"], pem)

    def test_invalid_base64_ca_fails_closed(self):
        self.env["PG_CA_CERT_BASE64"] = "invalid!"
        with self.assertRaises(ValueError):
            bootstrap.settings(self.env)

    def test_ui_credentials_are_required(self):
        self.env["UI_PASSWORD"] = ""
        with self.assertRaises(ValueError):
            bootstrap.settings(self.env)

    def test_public_origin_requires_https(self):
        self.env["PUBLIC_ORIGIN"] = "http://demo.example"
        with self.assertRaises(ValueError):
            bootstrap.settings(self.env)

    def test_local_compose_can_use_plaintext_postgresql(self):
        self.env.update(LOCAL_DEVELOPMENT="true", PG_SSLMODE="disable", PUBLIC_ORIGIN="http://localhost:8080")
        self.assertFalse(bootstrap.settings(self.env)["tls"])


if __name__ == "__main__":
    unittest.main()
