"""Flask endpoints for CPU Wiki workflows."""
import io,json
from pathlib import Path
from flask import jsonify,request,send_file
from .platform import Platform
from .repository import Conflict,NotFound

def register(app,service):
    platform=Platform(service);app.extensions['wiki_platform']=platform
    def guard(fn):
        def wrapped(*a,**k):
            try:return fn(*a,**k)
            except NotFound as e:return jsonify(error=str(e)),404
            except Conflict as e:return jsonify(error=str(e)),409
            except (ValueError,TypeError,KeyError,json.JSONDecodeError) as e:return jsonify(error=str(e)),400
        wrapped.__name__=fn.__name__;return wrapped
    def body():return request.get_json(silent=True) or {}
    @app.get('/api/wiki/platform')
    @guard
    def wp_summary():return jsonify(platform.summary())
    @app.route('/api/wiki/platform/settings',methods=['GET','POST'])
    @guard
    def wp_settings():return jsonify(platform.settings() if request.method=='GET' else platform.configure(body()))
    @app.get('/api/wiki/platform/tasks')
    def wp_tasks():return jsonify(tasks=platform.tasks())
    @app.post('/api/wiki/platform/sync')
    @guard
    def wp_sync():return jsonify(platform.sync()),202
    @app.post('/api/wiki/platform/topics')
    @guard
    def wp_topics():return jsonify(platform.create_topic(body())),201
    @app.post('/api/wiki/platform/ask')
    @guard
    def wp_ask():return jsonify(platform.ask(body()))
    @app.get('/api/wiki/platform/conversations')
    def wp_conversations():return jsonify(conversations=platform.conversations())
    @app.route('/api/wiki/platform/conversations/<id>',methods=['GET','POST'])
    @guard
    def wp_conversation(id):return jsonify(platform.conversation(id) if request.method=='GET' else platform.conversation_action(id,body().get('action'),body().get('title')))
    @app.post('/api/wiki/platform/answers/<id>/archive')
    @guard
    def wp_archive(id):return jsonify(platform.archive(id,body().get('title'))),201
    @app.get('/api/wiki/platform/search')
    @guard
    def wp_search():return jsonify(results=platform.search(request.args.get('q',''),request.args.get('drafts')=='1',request.args.get('mode','wiki')))
    @app.get('/api/wiki/platform/links')
    @guard
    def wp_links():return jsonify(platform.links(request.args['entity']))
    @app.get('/api/wiki/platform/network')
    @guard
    def wp_network():return jsonify(platform.network())
    @app.get('/api/wiki/platform/lint')
    @guard
    def wp_lint():return jsonify(platform.lint())
    @app.post('/api/wiki/platform/ingest')
    @guard
    def wp_ingest():
        f=request.files.get('file')
        if f:return jsonify(platform.ingest(f.filename,f.read(20*1024*1024+1))),201
        return jsonify(platform.ingest_url(body()['url'])),201
    @app.post('/api/wiki/platform/sources/<id>/withdraw')
    @guard
    def wp_withdraw(id):return jsonify(platform.withdraw(id))
    @app.post('/api/wiki/platform/research')
    @guard
    def wp_research():
        data=body()
        return jsonify(platform.research_local(data['topic']) if data.get('mode')=='sources' else platform.research(data['topic'])),201
    @app.post('/api/wiki/platform/synthesize')
    @guard
    def wp_synthesis():return jsonify(platform.synthesize(body()['entity']))
    @app.post('/api/wiki/platform/embeddings')
    @guard
    def wp_embeddings():return jsonify(platform.embeddings()),202
    @app.get('/api/wiki/platform/semantic')
    @guard
    def wp_semantic():return jsonify(results=platform.semantic(request.args.get('q','')))
    @app.post('/api/wiki/platform/vision')
    @guard
    def wp_vision():return jsonify(platform.describe_media(body()['entity'],body()['file']))
    @app.get('/api/wiki/platform/media/<file>')
    @guard
    def wp_media(file):
        target=(platform.root/'media'/file).resolve()
        if not target.is_relative_to(platform.root/'media') or not target.is_file():raise NotFound('图片不存在')
        return send_file(target)
    @app.get('/api/wiki/platform/export')
    @guard
    def wp_export():return send_file(io.BytesIO(platform.export()),mimetype='application/zip',as_attachment=True,download_name='chemical-wiki-project.zip')
    @app.post('/api/wiki/platform/import')
    @guard
    def wp_import():
        f=request.files.get('file')
        if not f:raise ValueError('请上传 Wiki 项目 ZIP')
        return jsonify(platform.restore(f.read(100*1024*1024+1)))
    return platform
