import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
from render_user_app_oke import render

class UserAppOkeTests(unittest.TestCase):
    def test_both_languages_preserve_application_contract(self):
        target = dict(namespace='user-agents', image='registry.example/agent@sha256:' + 'a'*64,
                      port=8080, working_directory='/app')
        for language in ('python', 'java'):
            app = json.loads((ROOT / 'examples/bring-your-agent' / language / 'app.json').read_text())
            objects = render(app, target)
            pod = objects[1]['spec']['template']['spec']
            container = pod['containers'][0]
            self.assertEqual(container['command'], [v.replace('{port}', '8080') for v in app['run']])
            self.assertEqual(container['readinessProbe']['httpGet']['path'], '/ready')
            self.assertFalse(pod['automountServiceAccountToken'])
            self.assertEqual(objects[2]['spec']['type'], 'ClusterIP')
            self.assertFalse(any('KEY' in v['name'] for v in container['env']))
            for change in ({'image':'agent:latest'}, {'namespace':'default'}, {'port':80}):
                with self.assertRaises(ValueError): render(app, dict(target, **change))

if __name__ == '__main__': unittest.main()
