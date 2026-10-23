import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from flask import Flask
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.quiz_api import create_blueprint


class QuizContract(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=Flask(__name__)
        self.app.register_blueprint(create_blueprint(Path(__file__).resolve().parents[1]/'app/quiz_content',Path(self.temp.name)/'quiz.sqlite'))
        self.client=self.app.test_client()
        self.client.get('/api/quiz/catalog')
    def tearDown(self):self.temp.cleanup()
    def start(self,mode='learn'):
        return self.client.post('/api/quiz/sessions',json={'module':'evidence','count':2,'mode':mode}).get_json()
    def test_hidden_answers_and_owner_isolation(self):
        s=self.start()
        self.assertEqual(s['feedback'],{})
        self.assertNotIn('answer',s['questions'][0])
        self.assertNotIn('explanation',s['questions'][0])
        self.assertEqual(self.app.test_client().get('/api/quiz/sessions/'+s['id']).status_code,404)
    def test_idempotent_submit_and_immutable_answer(self):
        s=self.start();url='/api/quiz/sessions/'+s['id']+'/answer'
        body={'index':0,'answer':['A']}
        a=self.client.post(url,json=body).get_json()
        b=self.client.post(url,json=body).get_json()
        self.assertEqual(a,b)
        self.assertIn('explanation',a['feedback']['0'])
        self.assertEqual(self.client.post(url,json={'index':0,'answer':['B']}).status_code,409)
        self.assertEqual(self.client.post(url,json={'index':0,'answer':['Z']}).status_code,400)
    def test_self_test_hides_until_finish(self):
        s=self.start('test');url='/api/quiz/sessions/'+s['id']+'/answer'
        self.assertEqual(self.client.post(url,json={'index':1,'answer':[]}).status_code,409)
        a=self.client.post(url,json={'index':0,'answer':[]}).get_json()
        self.assertEqual(a['feedback'],{})
        a=self.client.post(url,json={'index':1,'answer':[]}).get_json()
        self.assertTrue(a['finished']);self.assertEqual(a['score'],0)
        self.assertEqual(len(a['feedback']),2)
    def test_bad_shapes_and_cleanup(self):
        for bad in [[],None,'hello',3]:
            self.assertEqual(self.client.post('/api/quiz/sessions',json=bad).status_code in (400,415),True)
        s=self.start();self.assertEqual(self.client.delete('/api/quiz/sessions').status_code,200)
        self.assertEqual(self.client.get('/api/quiz/sessions/'+s['id']).status_code,404)
    def test_content_validity(self):
        qs=json.loads((Path(__file__).resolve().parents[1]/'app/quiz_content/questions.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(qs),490)
        self.assertEqual(len({q['id'] for q in qs}),len(qs))
        for q in qs:
            self.assertEqual(len(q['answer']),1)
            self.assertIn(q['answer'][0],[o['id'] for o in q['options']])
            self.assertTrue(q['explanation'].strip());self.assertTrue(q['source_url'].startswith('https://'))
    def test_reporting(self):
        self.assertEqual(self.client.post('/api/quiz/reports',json={'question_id':'learn-001','reason':'需要核对原文'}).status_code,200)
        self.assertEqual(self.client.post('/api/quiz/reports',json={'question_id':'not-real','reason':'不存在的题'}).status_code,400)

if __name__=='__main__':unittest.main(verbosity=2)
