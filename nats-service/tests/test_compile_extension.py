import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from compile_extension import build  # noqa: E402
from serialization import read_document  # noqa: E402


class NATSServiceExtensionCompilationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extension, cls.vocabulary = build(read_document(ROOT / "model/runtimeconditions.yaml"))
        cls.validator = Draft202012Validator(cls.extension["spec"]["schemas"][0]["schema"])

    def assert_valid_operation(self, operation):
        condition = {"kind": "nats", "interface": {"type": "service", "operations": [operation]}}
        self.assertEqual(list(self.validator.iter_errors(condition)), [])

    def test_compiles_exact_extension_coordinates(self):
        self.assertEqual(self.extension["metadata"]["id"], self.vocabulary["extension"]["id"])
        self.assertEqual(self.extension["metadata"]["version"], self.vocabulary["extension"]["version"])
        self.assertEqual(self.extension["metadata"]["semanticSha256"], self.vocabulary["extension"]["semanticSha256"])

    def test_accepts_each_adapter_actionable_form(self):
        self.assert_valid_operation({"resource": "connection", "action": "connect"})
        self.assert_valid_operation({"resource": "subject", "action": "request", "subject": "inventory.reserve"})
        self.assert_valid_operation({"resource": "stream", "action": "create", "name": "ORDERS", "subjects": ["orders.>"]})
        self.assert_valid_operation({"resource": "stream", "action": "publish", "subject": "orders.created"})
        self.assert_valid_operation({"resource": "consumer", "action": "consume", "stream": "ORDERS", "name": "worker"})
        self.assert_valid_operation({"resource": "key_value", "action": "write", "bucket": "profiles"})
        self.assert_valid_operation({"resource": "object_store", "action": "watch", "bucket": "configuration"})

    def test_rejects_open_resource_action_combinations(self):
        condition = {"kind": "nats", "interface": {"type": "service", "operations": [{"resource": "subject", "action": "write", "subject": "orders.created"}]}}
        self.assertTrue(list(self.validator.iter_errors(condition)))

    def test_rejects_one_operation_with_multiple_actions(self):
        condition = {"kind": "nats", "interface": {"type": "service", "operations": [{"resource": "key_value", "action": ["read", "write"], "bucket": "profiles"}]}}
        self.assertTrue(list(self.validator.iter_errors(condition)))


if __name__ == "__main__":
    unittest.main()
