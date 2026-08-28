import json
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from project_openapi import build_inventory, extract_operations  # noqa: E402


def resource_operation(operation_id, action, group, version, kind):
    return {
        "operationId": operation_id,
        "tags": ["test"],
        "x-kubernetes-action": action,
        "x-kubernetes-group-version-kind": {"group": group, "version": version, "kind": kind},
    }


class OpenAPIProjectionTest(unittest.TestCase):
    def model(self):
        return {
            "swagger": "2.0",
            "paths": {
                "/api/v1/namespaces/{namespace}/configmaps/{name}": {
                    "get": resource_operation("readCoreV1NamespacedConfigMap", "get", "", "v1", "ConfigMap")
                },
                "/api/v1/configmaps": {
                    "get": resource_operation("listCoreV1ConfigMapForAllNamespaces", "list", "", "v1", "ConfigMap")
                },
                "/api/v1/nodes": {
                    "get": resource_operation("listCoreV1Node", "list", "", "v1", "Node")
                },
                "/api/v1/namespaces/{namespace}/pods/{name}/eviction": {
                    "post": resource_operation("createCoreV1NamespacedPodEviction", "post", "policy", "v1", "Eviction")
                },
                "/version/": {"get": {"operationId": "getCodeVersion", "tags": ["version"]}},
            },
        }

    def test_projects_scopes_and_endpoint_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory, "swagger.json")
            model = self.model()
            model_path.write_text(json.dumps(model), encoding="utf-8")
            inventory = build_inventory(model_path, model, "https://example.test/repo.git", "revision", "v1.0.0", "swagger.json")
        by_id = {operation["operationId"]: operation for operation in inventory["operations"]}
        self.assertEqual(by_id["readCoreV1NamespacedConfigMap"]["projection"]["scope"], "namespaced")
        self.assertEqual(by_id["listCoreV1ConfigMapForAllNamespaces"]["projection"]["scope"], "all_namespaces")
        self.assertEqual(by_id["listCoreV1Node"]["projection"]["scope"], "cluster")
        eviction = by_id["createCoreV1NamespacedPodEviction"]
        self.assertEqual(eviction["projection"]["verb"], "create")
        self.assertEqual(eviction["projection"]["apiGroup"], "")
        self.assertEqual(eviction["projection"]["resource"], "pods")
        self.assertEqual(eviction["projection"]["subresource"], "eviction")
        self.assertTrue(eviction["source"]["groupVersionKindDiffersFromEndpoint"])
        self.assertEqual(by_id["getCodeVersion"]["classification"], "non_resource")

    def test_rejects_partial_kubernetes_extensions(self):
        model = self.model()
        model["paths"]["/api/v1/nodes"]["get"].pop("x-kubernetes-group-version-kind")
        with self.assertRaisesRegex(ValueError, "must be present together"):
            extract_operations(model)

    def test_rejects_duplicate_operation_ids(self):
        model = self.model()
        model["paths"]["/version/"]["get"]["operationId"] = "listCoreV1Node"
        with self.assertRaisesRegex(ValueError, "duplicate operationId"):
            extract_operations(model)


if __name__ == "__main__":
    unittest.main()
