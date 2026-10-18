import io,json,tempfile,unittest,zipfile,os
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from core.wiki.platform import Platform,public_url
from core.wiki.service import WikiService
from core.wiki.worker import Worker
from core.wiki.routes import register
class PlatformTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);p=self.base/'data/vector_store';p.mkdir(parents=True)
  self.rows=[{'doc_id':'d1','chunk_id':'c1','title':'甲醇储存标准','text':'甲醇储存区域需要管理火源，保持通风。','page_start':1,'document_type':'标准','status':'ACTIVE'}]
  (p/'index_metadata.json').write_text(json.dumps(self.rows,ensure_ascii=False),encoding='utf-8')
  self.env=patch.dict(os.environ,{'CHEM_KB_BASE_DIR':str(self.base),'CHEM_KB_WIKI_ALLOW_LOCAL_GPU':'0'});self.env.start()
  self.service=WikiService(self.base/'wiki');self.p=Platform(self.service,self.base)
 def tearDown(self):self.env.stop();self.temp.cleanup()
 def topic(self,title='甲醇'):
  return self.p.create_topic({'title':title,'content':'甲醇属于有机物。','page_type':'chemical'})
 def test_source_summary_idempotent_and_exact_quotes(self):
  a=self.p.source_page('d1',self.rows);b=self.p.source_page('d1',self.rows)
  self.assertTrue(b['unchanged']);self.assertEqual(a['entity'],b['entity']);p=self.service.repo.read(a['entity']);self.assertTrue(p['validation']['ok']);self.assertIn(self.rows[0]['text'],p['markdown'])
 def test_cpu_ask_is_persisted_and_archive_idempotent(self):
  with patch.object(self.p,'remote',side_effect=AssertionError('must not infer')):
   a=self.p.ask({'question':'甲醇储存要求'});saved=self.p.archive(a['answer_id'],'甲醇储存专题');again=self.p.archive(a['answer_id'],'different')
  self.assertEqual(saved['entity'],again['entity']);p=self.service.repo.read(saved['entity']);self.assertFalse(self.service.detail(p['entity'])['is_published']);self.assertIn('甲醇储存',p['markdown']);self.assertEqual(len(self.p.conversation(a['conversation_id'])['answers']),1)
  with self.assertRaises(ValueError):self.service.publish(p['entity'],{'expected_revision':p['revision_id'],'reviewer':'test'})
 def test_drafts_opt_in_and_published_query_reuse(self):
  p=self.topic();self.assertEqual(self.p.search('甲醇'),[]);self.assertTrue(self.p.search('甲醇',True))
  self.service.review('甲醇',{'expected_revision':p['revision_id'],'section':'问答正文','reviewer':'test','review_status':'approved'})
  self.service.publish('甲醇',{'expected_revision':p['revision_id'],'reviewer':'test'})
  self.assertTrue(self.p.search('甲醇'));a=self.p.ask({'question':'甲醇','mode':'wiki'});self.assertEqual(a['wiki_refs'][0]['source_type'],'reviewed_wiki')
 def test_source_only_mode_excludes_wiki(self):
  self.topic();a=self.p.ask({'question':'甲醇','include_drafts':True,'mode':'sources'});self.assertEqual(a['wiki_refs'],[])
 def test_ingest_dedup_and_withdraw_does_not_delete_pages(self):
  a=self.p.ingest('test.md','甲醇储存资料。'.encode());b=self.p.ingest('test.md','甲醇储存资料。'.encode());self.assertTrue(b['deduplicated']);self.assertEqual(a['page']['revision'],b['page']['revision'])
  r=self.p.withdraw(a['id']);self.assertIn(a['page']['entity'],r['affected']);self.assertEqual(self.service.repo.entry(a['page']['entity'])['freshness'],'stale');self.assertTrue((self.p.root/'sources'/a['id']/'test.md').exists())
 def test_project_roundtrip_keeps_drafts_and_history(self):
  self.topic();a=self.p.ask({'question':'甲醇'});self.p.archive(a['answer_id'],'甲醇专题');blob=self.p.export()
  other=Platform(WikiService(self.base/'other'),self.base);r=other.restore(blob);self.assertEqual(r['restored'],2);self.assertEqual(r['published'],0);self.assertEqual(len(other.conversations()),1)
  self.assertEqual(other.restore(blob)['skipped'],2)
  with zipfile.ZipFile(io.BytesIO(blob)) as z:self.assertIn('wiki/index.md',z.namelist());self.assertNotIn('api_key',z.read('project.json').decode())
 def test_archive_traversal_rejected_before_writes(self):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('../outside','x');z.writestr('project.json','{}')
  with self.assertRaises(ValueError):self.p.restore(out.getvalue())
  self.assertEqual(self.service.repo.list(),[])
 def test_no_local_gpu_worker_load(self):
  w=Worker(self.service,resource_check=lambda:False)
  with patch('builtins.__import__',wraps=__import__) as imported:
   self.assertFalse(w.once())
   with self.assertRaises(RuntimeError):w.load()
  self.assertFalse(any(c.args[0]=='core.rag' for c in imported.call_args_list))
 def test_network_links_and_louvain(self):
  self.topic();self.p.create_topic({'title':'甲醇储运','content':'参考 [[甲醇]]。','page_type':'topic'})
  n=self.p.network();self.assertEqual(n['algorithm'],'louvain');self.assertEqual(n['edges'][0]['signals']['direct'],1)
 def test_lint_broken_link_is_explicit(self):
  self.p.create_topic({'title':'专题','content':'参考 [[不存在]]。'});self.assertTrue(any(f['type']=='broken_link' for f in self.p.lint()['findings']))
 def test_public_url_denies_internal_and_credentials(self):
  with self.assertRaises(ValueError):public_url('http://example.com')
  with self.assertRaises(ValueError):public_url('https://user:pass@example.com')
  with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
   with self.assertRaises(ValueError):public_url('https://example.com')
 def test_settings_redact_keys_and_export_gpu_disabled(self):
  with patch('core.wiki.platform.public_url',side_effect=lambda x:x):r=self.p.configure({'models':{'answer':{'base_url':'https://example.com/v1','model':'mock','api_key':'secret'}}})
  self.assertTrue(r['models']['answer']['key_configured']);self.assertNotIn('secret',json.dumps(r));self.assertFalse(r['local_gpu'])
 def test_missing_models_report_requirements_without_loading(self):
  with self.assertRaises(ValueError):self.p.embeddings()
  with self.assertRaises(ValueError):self.p.remote('ingest',[])
  self.assertEqual(self.p.summary()['minimum_target'],1)
 def test_external_blocks_preserved_on_human_edit(self):
  from test_wiki_external_sources import section
  p=self.service.create_draft('百科测试',[section()]);s=p['sections'][0]
  self.service.review('百科测试',{'expected_revision':p['revision_id'],'section':'基本概述','reviewer':'test','review_status':'modified','reviewed_content':s['content']+'\n\n编辑说明。','review_comment':'补充说明'})
  p=self.service.repo.read('百科测试');self.assertTrue(any(b['knowledge_source']=='external' for b in p['sections'][0]['knowledge_blocks']))
 def test_cpu_api_archive_workflow(self):
  app=Flask(__name__);register(app,self.base/'apiwiki');c=app.test_client()
  a=c.post('/api/wiki/platform/ask',json={'question':'甲醇'});self.assertEqual(a.status_code,200)
  r=c.post('/api/wiki/platform/answers/'+a.json['answer_id']+'/archive',json={'title':'专题'});self.assertEqual(r.status_code,201)
  self.assertEqual(c.get('/api/wiki/platform').json['entries'],1)
 def test_published_revision_remains_searchable_after_draft_update(self):
  p=self.topic();self.service.review('甲醇',{'expected_revision':p['revision_id'],'section':'问答正文','reviewer':'test','review_status':'approved'})
  self.service.publish('甲醇',{'expected_revision':p['revision_id'],'reviewer':'test'})
  self.p.commit('甲醇',[{'section':'问答正文','content':'新草稿乙醇描述','knowledge_blocks':[{'text':'新草稿乙醇描述','knowledge_source':'model_prior','evidence_ids':[]}]}],expected=p['revision_id'])
  self.assertEqual(self.p.search('甲醇')[0]['revision_id'],p['revision_id'])
 def test_two_step_remote_synthesis_preserves_evidence_and_creates_concept(self):
  page=self.p.source_page('d1',self.rows)
  with patch.object(self.p,'remote',side_effect=[json.dumps({'facts':['原文'],'concepts':['火源管理']}),json.dumps({'content':'需要管理火源。 [Wiki证据1]','concepts':[{'name':'火源管理','description':'管理点火源。'}]})]) as remote:
   r=self.p.synthesize(page['entity'])
  self.assertEqual(remote.call_count,2);self.assertEqual(r['created_concepts'],['火源管理']);self.assertFalse(r['automatic_approval']);self.assertTrue(self.service.repo.read(page['entity'])['validation']['ok'])
 def test_cpu_pdf_and_office_text_ingestion(self):
  import fitz
  doc=fitz.open();page=doc.new_page();page.insert_text((50,50),'Methanol chemical safety document.')
  a=self.p.ingest('methanol.pdf',doc.tobytes());self.assertGreater(a['chunks_count'],0)
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Methanol document.</w:t></w:r></w:p></w:body></w:document>')
  b=self.p.ingest('methanol.docx',out.getvalue());self.assertGreater(b['chunks_count'],0)
 def test_initializing_other_platform_preserves_live_task(self):
  import threading,time
  gate=threading.Event();t=self.p.task('test',lambda id:gate.wait(5),1)
  other=Platform(self.service,self.base);self.assertEqual(next(x for x in other.tasks() if x['id']==t['task_id'])['state'],'running');gate.set()
  for i in range(100):
   if next(x for x in other.tasks() if x['id']==t['task_id'])['state']!='running':break
   time.sleep(.01)
 def test_backlinks_and_two_hop_draft_retrieval(self):
  self.p.create_topic({'title':'第三页','content':'不同文字'})
  self.p.create_topic({'title':'第二页','content':'参考 [[第三页]]'})
  self.p.create_topic({'title':'甲醇','content':'甲醇 [[第二页]]'})
  self.assertEqual(self.p.links('第二页')['backlinks'],['甲醇'])
  a=self.p.ask({'question':'甲醇','include_drafts':True});self.assertIn('第三页',[h['entity'] for h in a['wiki_refs']])
 def test_watcher_imports_beyond_ten_files_and_retracts_deleted_source(self):
  from core.wiki.maintenance import watch_once
  folder=self.p.root/'incoming';folder.mkdir();seen={}
  for i in range(12):(folder/(str(i)+'.txt')).write_text('unique document '+str(i),encoding='utf-8')
  self.assertEqual(watch_once(self.p,folder,seen),10);self.assertEqual(watch_once(self.p,folder,seen),2)
  sid=seen['0.txt']['id'];(folder/'0.txt').unlink();watch_once(self.p,folder,seen)
  with self.p.connect() as db:self.assertEqual(db.execute('SELECT active FROM managed_sources WHERE id=?',(sid,)).fetchone()[0],0)
 def test_zero_history_budget_does_not_send_previous_turns_to_model(self):
  first=self.p.ask({'question':'甲醇'})
  with self.p.connect() as db:db.execute('INSERT OR REPLACE INTO config VALUES(1,?)',(json.dumps({**self.p.settings(True),'history_turns':0,'models':{'answer':{'base_url':'https://example.com','model':'mock'},'ingest':{},'embedding':{},'vision':{}}}),))
  with patch.object(self.p,'remote',return_value='资料不足。') as remote:self.p.ask({'question':'后续问题','conversation_id':first['conversation_id']})
  self.assertEqual(len(remote.call_args.args[1]),2)
if __name__=='__main__':unittest.main()
