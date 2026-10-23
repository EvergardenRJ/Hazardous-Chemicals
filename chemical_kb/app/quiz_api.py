"""Versioned learning sessions; no dependency on models or research datasets."""
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from flask import Blueprint, request, jsonify, g


def create_blueprint(content_dir, database):
    bp = Blueprint('quiz', __name__, url_prefix='/api/quiz')
    questions = json.loads((Path(content_dir) / 'questions.json').read_text(encoding='utf-8'))
    bank = {q['id']: q for q in questions}
    modules = json.loads((Path(content_dir) / 'modules.json').read_text(encoding='utf-8'))
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    @contextmanager
    def db():
        con = sqlite3.connect(database, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()
    with db() as con:
        con.executescript('''CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, question_id TEXT, version TEXT, reason TEXT, created REAL);''')

    @bp.before_request
    def owner():
        token = request.cookies.get('hazmat_learner', '')
        g.quiz_new_cookie = not (len(token) == 64 and all(c in '0123456789abcdef' for c in token))
        g.quiz_owner = secrets.token_hex(32) if g.quiz_new_cookie else token
        if request.method == 'POST':
            if (request.content_length or 0) > 20000:
                return jsonify(error='请求内容过大'), 413
            if not request.is_json:
                return jsonify(error='请使用 JSON 请求'), 415

    @bp.after_request
    def cookie(response):
        response.headers['Cache-Control'] = 'no-store'
        if g.get('quiz_new_cookie'):
            response.set_cookie('hazmat_learner', g.quiz_owner, httponly=True, samesite='Strict', secure=request.is_secure, max_age=30*86400)
        return response

    def public(q):
        return {k:v for k,v in q.items() if k not in ('answer','explanation','critical')}

    def feedback(q, answer):
        return {'correct': sorted(answer) == sorted(q['answer']), 'answer':q['answer'], 'explanation':q['explanation'], 'source_url':q['source_url'], 'source':q['source'], 'source_locator':q.get('source_locator',''), 'uncertain':answer == []}

    def render(s):
        result = {k:v for k,v in s.items() if k != 'questions'}
        result['total'] = len(s['questions'])
        result['questions'] = [public(q) for q in s['questions']]
        result['feedback'] = {str(i):feedback(s['questions'][i], a) for i,a in enumerate(s['answers']) if a is not None and (s['mode']=='learn' or s['finished'])}
        if s['finished']:
            result['score'] = sum(feedback(q,a or [])['correct'] for q,a in zip(s['questions'],s['answers']))
        return result

    def read(con, sid):
        row = con.execute('SELECT payload FROM sessions WHERE id=? AND owner=? AND created>?',(sid,g.quiz_owner,time.time()-30*86400)).fetchone()
        return json.loads(row['payload']) if row else None

    @bp.get('/catalog')
    def catalog():
        return jsonify(modules=[{**m,'count':sum(q['module']==m['id'] for q in questions)} for m in modules], total=len(questions), disclaimer='仅供学习参考，不替代产品 SDS、专业培训或现场处置要求。', sources=json.loads((Path(content_dir)/'sources.json').read_text(encoding='utf-8')))

    @bp.post('/sessions')
    def start():
        body = request.get_json()
        if not isinstance(body, dict): return jsonify(error='请求格式错误'),400
        mode=body.get('mode','learn')
        if mode not in ('learn','test'): return jsonify(error='不支持的答题模式'),400
        pool=[q for q in questions if body.get('module') in ('daily',q['module'])]
        ids=body.get('ids')
        if ids is not None:
            if not isinstance(ids,list) or len(ids)>100 or not all(isinstance(v,str) for v in ids):return jsonify(error='复习题列表无效'),400
            pool=[bank[i] for i in dict.fromkeys(ids) if i in bank]
        if not pool:return jsonify(error='暂无可用题目，请选择其他挑战'),400
        try: count=min(max(int(body.get('count',5)),1),20,len(pool))
        except (TypeError,ValueError):return jsonify(error='题量无效'),400
        with db() as con:
            con.execute('DELETE FROM sessions WHERE created<?',(time.time()-30*86400,))
            if con.execute('SELECT COUNT(*) FROM sessions WHERE owner=? AND created>?',(g.quiz_owner,time.time()-3600)).fetchone()[0]>=100:return jsonify(error='创建过于频繁，请稍后再试'),429
            selected=secrets.SystemRandom().sample(pool,count)
            selected=json.loads(json.dumps(selected))
            for q in selected:secrets.SystemRandom().shuffle(q['options'])
            sid=secrets.token_urlsafe(24)
            s={'id':sid,'mode':mode,'module':body.get('module','daily'),'questions':selected,'answers':[None]*count,'finished':False,'created':time.time(),'version':'20261022.1'}
            con.execute('INSERT INTO sessions VALUES(?,?,?,?)',(sid,g.quiz_owner,json.dumps(s),time.time()))
        return jsonify(render(s)),201

    @bp.get('/sessions/<sid>')
    def get_session(sid):
        with db() as con:s=read(con,sid)
        return (jsonify(render(s)),200) if s else (jsonify(error='会话不存在或已过期，请重新开始'),404)

    @bp.post('/sessions/<sid>/answer')
    def answer(sid):
        body=request.get_json()
        if not isinstance(body,dict):return jsonify(error='请求格式错误'),400
        i=body.get('index');a=body.get('answer')
        if type(i) is not int or not isinstance(a,list) or not all(isinstance(v,str) for v in a) or len(a)>8:return jsonify(error='答案格式无效'),400
        with db() as con:
            con.execute('BEGIN IMMEDIATE')
            s=read(con,sid)
            if not s:return jsonify(error='会话不存在或已过期'),404
            if not 0<=i<len(s['questions']):return jsonify(error='题号无效'),400
            if not set(a)<=set(o['id'] for o in s['questions'][i]['options']) or len(a)!=len(set(a)):return jsonify(error='选项无效'),400
            if s['answers'][i] is not None:
                if s['answers'][i] != a:return jsonify(error='已提交的答案不能更改'),409
                return jsonify(render(s))
            if s['finished']:return jsonify(error='会话已经结束'),409
            if any(v is None for v in s['answers'][:i]):return jsonify(error='请先完成前面的题目'),409
            s['answers'][i]=a
            s['finished']=all(v is not None for v in s['answers'])
            con.execute('UPDATE sessions SET payload=? WHERE id=?',(json.dumps(s),sid))
        return jsonify(render(s))

    @bp.post('/reports')
    def report():
        body=request.get_json()
        if not isinstance(body,dict):return jsonify(error='请求格式错误'),400
        qid=body.get('question_id','')
        if not isinstance(qid,str):return jsonify(error='题目编号无效'),400
        q=bank.get(qid);reason=body.get('reason','')
        if not q or not isinstance(reason,str) or not 3<=len(reason.strip())<=2000:return jsonify(error='请填写 3—2000 字的问题说明'),400
        with db() as con:
            if con.execute('SELECT COUNT(*) FROM reports WHERE created>?',(time.time()-60,)).fetchone()[0]>=30:return jsonify(error='提交过于频繁，请稍后再试'),429
            con.execute('INSERT INTO reports VALUES(?,?,?,?,?)',(secrets.token_hex(16),q['id'],q['version'],reason.strip(),time.time()))
        return jsonify(saved=True)

    @bp.delete('/sessions')
    def clear():
        with db() as con:con.execute('DELETE FROM sessions WHERE owner=?',(g.quiz_owner,))
        return jsonify(deleted=True)
    return bp


def register(app, root):
    app.register_blueprint(create_blueprint(Path(__file__).parent/'quiz_content', os.environ.get('CHEM_KB_QUIZ_DB',str(Path(root)/'data/quiz/sessions.sqlite'))))
