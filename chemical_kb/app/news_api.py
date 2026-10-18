from flask import Blueprint,jsonify,request
from core import news_store,news_content
news_bp=Blueprint('news',__name__)
@news_bp.get('/api/news/status')
def news_status(): return jsonify(news_store.status())
@news_bp.get('/api/news')
def news_list():
    try: return jsonify(news_store.list_articles(request.args))
    except (ValueError,TypeError): return jsonify(error='筛选日期或分页参数无效'),400
@news_bp.get('/api/news/<int:aid>')
def news_detail(aid):
    item=news_store.detail(aid)
    return jsonify(item) if item else (jsonify(error='新闻不存在'),404)
@news_bp.post('/api/news/sync')
def news_sync():
    if not news_store.CONFIG.exists(): return jsonify(error='同步连接尚未配置'),503
    started=news_store.sync_async()
    return jsonify(running=True,started=started),202

@news_bp.get('/api/news/<int:aid>/content')
def news_original_content(aid):
    item=news_content.content(aid,refresh=request.args.get('refresh')=='1')
    return jsonify(item) if item else (jsonify(error='新闻不存在'),404)
