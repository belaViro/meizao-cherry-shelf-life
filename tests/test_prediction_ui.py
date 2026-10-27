"""UI contracts: share the cherry theme without changing prediction form hooks."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from app import app

class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.nodes=[]; self.feed(html)
    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag,dict(attrs)))

class SharedPredictionStyleTests(unittest.TestCase):
    def setUp(self):
        self.client=app.test_client()

    def test_both_pages_use_same_theme_and_workspace_classes(self):
        urls=[]
        for path in ('/', '/tomato'):
            html=self.client.get(path).get_data(as_text=True)
            parsed=Elements(html)
            styles=[a['href'] for tag,a in parsed.nodes if tag=='link' and a.get('rel')=='stylesheet']
            theme=[s for s in styles if '/static/prediction.css?' in s]
            self.assertEqual(len(theme),1)
            urls.extend(theme)
            classes={c for _,a in parsed.nodes for c in a.get('class','').split()}
            for name in ('topbar-inner','page','hero','product-nav','workspace','panel-head','form-body','result-body','summary','metric','temp-button','submit'):
                self.assertIn(name,classes)
            self.assertNotIn('<style',html)
        self.assertEqual(urls[0],urls[1])
        with self.client.get(urls[0]) as response:
            self.assertEqual(response.status_code,200)

    def test_tomato_javascript_hooks_and_default_visibility(self):
        html=self.client.get('/tomato').get_data(as_text=True)
        parsed=Elements(html)
        ids=[a['id'] for _,a in parsed.nodes if 'id' in a]
        self.assertEqual(len(ids),len(set(ids)))
        script=(Path(__file__).resolve().parents[1]/'static/tomato.js').read_text(encoding='utf-8')
        for hook in re.findall(r"\$\('([^']+)'\)",script):self.assertIn(hook,ids)
        nodes={a['id']:a for _,a in parsed.nodes if 'id' in a}
        self.assertIn('hidden',nodes['result'])
        self.assertIn('hidden',nodes['error'])
        self.assertNotIn('hidden',nodes['emptyState'])
        self.assertEqual(nodes['temperature']['value'],'5')
        self.assertEqual(nodes['threshold']['value'],'10')
        self.assertIn('默认10%只是演示阈值',html)
        for asset in ('tomato.css','tomato.js'):
            with self.client.get('/static/'+asset) as response:
                self.assertEqual(response.status_code,200)

if __name__=='__main__':unittest.main()
