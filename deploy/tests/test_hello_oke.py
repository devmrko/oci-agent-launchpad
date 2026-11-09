import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('hello_oke', Path(__file__).parents[1] / 'render_hello_oke.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class HelloOkeTest(unittest.TestCase):
    def setUp(self):
        self.config = dict(namespace='demo', service_account='hello-agent', runtime_secret='runtime', image_pull_secret='pull', image='example.test/project/hello@sha256:' + 'a' * 64, model_region='example-region', model_compartment='example-compartment', model_name='example-model')

    def test_secret_projection_and_private_service(self):
        sa, dep, svc = m.render(self.config)
        pod = dep['spec']['template']['spec']
        secret = next(v['secret'] for v in pod['volumes'] if 'secret' in v)
        self.assertEqual({i['key'] for i in secret['items']}, {'demo-accounts.json', 'langfuse-url', 'langfuse-public-key', 'langfuse-secret-key'})
        self.assertEqual(pod['serviceAccountName'], 'hello-agent')
        self.assertEqual(sa['metadata']['name'], 'hello-agent')
        self.assertEqual(svc['spec']['type'], 'ClusterIP')
        self.assertTrue(pod['containers'][0]['securityContext']['readOnlyRootFilesystem'])
        self.assertFalse(any('persistentVolumeClaim' in v for v in pod['volumes']))

    def test_mutable_image_and_invalid_name_rejected(self):
        for key, value in [('image', 'example.test/hello:latest'), ('namespace', '../other')]:
            c = copy.deepcopy(self.config); c[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.render(c)

    def test_no_existing_workload_selector_reused(self):
        _, dep, svc = m.render(self.config)
        self.assertEqual(dep['metadata']['name'], 'hello-agent')
        self.assertEqual(svc['spec']['selector'], dep['spec']['selector']['matchLabels'])
        self.assertEqual(svc['spec']['selector'], {'app.kubernetes.io/name': 'hello-agent'})

if __name__ == '__main__': unittest.main()
