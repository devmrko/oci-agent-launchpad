import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("connections", ROOT / "render_companion_connections.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConnectionBundleTests(unittest.TestCase):
    def config(self):
        config = json.loads((ROOT / "companion-connections.example.json").read_text())
        for field in ("tenancy", "user", "compartment"):
            config["scope"][field] = "ocid1." + field + ".oc1..synthetic"
        for app in config["apps"]:
            for dep in app["dependencies"]:
                dep["ocid"] = "ocid1." + module.PREFIX[dep["type"]] + ".oc1.ap-seoul-1.synthetic"
            if "oke" in app:
                app["oke"]["clusterId"] = app["dependencies"][0]["ocid"]
        return config

    def test_multiple_apps_match_current_companion_contract(self):
        output = {key: json.loads(value) for key, value in module.render(self.config()).items()}
        apps = output["agent-connections.json"]
        credentials = output["agent-credentials.json"]
        oke = output["oke-workloads.json"][0]
        self.assertEqual(len(apps), 2)
        self.assertEqual(len(credentials), 2)
        self.assertEqual(oke["appId"], apps[1]["id"])
        self.assertEqual(oke["clusterId"], apps[1]["dependencies"][0]["ocid"])
        for app, credential in zip(apps, credentials):
            self.assertEqual(app["credentialRef"], credential["id"])
            for field in module.SCOPE:
                self.assertEqual(app[field], credential[field])
            self.assertEqual(app["adapter"], "monitoring-http-v1")
        self.assertFalse(oke["inspectNodes"])

    def test_ids_stable_when_order_or_display_name_changes(self):
        c = self.config()
        first = json.loads(module.render(c)["agent-connections.json"])
        c["apps"][0]["name"] = "Renamed"
        c["apps"].reverse()
        second = json.loads(module.render(c)["agent-connections.json"])
        self.assertEqual(first[0]["id"], second[1]["id"])
        self.assertEqual(first[1]["id"], second[0]["id"])

    def test_explicit_existing_id_is_preserved(self):
        c = self.config(); c["apps"][1]["id"] = "1b0d01ca-d52f-4c96-af3e-789f73877436"
        self.assertEqual(json.loads(module.render(c)["oke-workloads.json"])[0]["appId"], c["apps"][1]["id"])

    def test_unresolved_or_secret_fields_rejected(self):
        with self.assertRaises(ValueError):
            module.render(json.loads((ROOT / "companion-connections.example.json").read_text()))
        c = self.config(); c["apps"][0]["token"] = "do-not-store"
        with self.assertRaises(ValueError): module.render(c)

    def test_wrong_dependency_type_and_cluster_mismatch(self):
        c = self.config(); c["apps"][0]["dependencies"][0]["type"] = "ADB"
        with self.assertRaises(ValueError): module.render(c)
        c = self.config(); c["apps"][1]["oke"]["clusterId"] += "other"
        with self.assertRaises(ValueError): module.render(c)

    def test_duplicate_keys_ids_and_dependencies(self):
        for mode in ("key", "id", "dependency"):
            c = self.config()
            if mode == "key": c["apps"][1]["key"] = c["apps"][0]["key"]
            if mode == "id":
                for app in c["apps"]: app["id"] = "11111111-1111-4111-8111-111111111111"
            if mode == "dependency": c["apps"][0]["dependencies"] *= 2
            with self.subTest(mode=mode), self.assertRaises(ValueError): module.render(c)

    def test_network_and_path_boundaries(self):
        for address in ("http://example.com", "http://127.0.0.1:8092?token=x", "http://user:pass@127.0.0.1:8092", "http://127.0.0.1:8092/private"):
            c = self.config(); c["apps"][0]["baseUrl"] = address
            with self.subTest(address=address), self.assertRaises(ValueError): module.render(c)
        c = self.config(); c["apps"][1]["oke"]["server"] = "http://127.0.0.1:16443"
        with self.assertRaises(ValueError): module.render(c)
        c = self.config(); c["apps"][0]["tokenFile"] = "/a/../secret"
        with self.assertRaises(ValueError): module.render(c)

    def test_files_are_private_and_existing_directory_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            module.write_bundle(self.config(), out)
            before = {p.name: p.read_bytes() for p in out.iterdir()}
            for p in out.iterdir(): self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError): module.write_bundle(self.config(), out)
            self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})

    def test_invalid_config_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            c = self.config(); c["apps"][1]["oke"]["inspectNodes"] = "true"
            with self.assertRaises(ValueError): module.write_bundle(c, out)
            self.assertFalse(out.exists())


if __name__ == "__main__": unittest.main()
