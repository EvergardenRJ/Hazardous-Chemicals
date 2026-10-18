"""Small stdio MCP bridge to the authenticated CPU Wiki API."""
import json,os,sys,urllib.request
URL=os.environ.get('CHEM_KB_WIKI_API','http://127.0.0.1:8503').rstrip('/')
TOOLS=[{'name':'wiki_search','description':'Search published Wiki or original sources. No inference.','inputSchema':{'type':'object','properties':{'query':{'type':'string'},'mode':{'type':'string','enum':['wiki','sources']}},'required':['query']}}, {'name':'wiki_read','description':'Read a Wiki page and its exact source bindings.','inputSchema':{'type':'object','properties':{'entity':{'type':'string'}},'required':['entity']}}, {'name':'wiki_status','description':'Read corpus coverage and resource requirements.','inputSchema':{'type':'object','properties':{}}}, {'name':'wiki_archive_answer','description':'Archive an existing answer as a new Wiki draft. Requires user authorization to write.','inputSchema':{'type':'object','properties':{'answer_id':{'type':'string'},'title':{'type':'string'}},'required':['answer_id']}}]
def rpc(m):
    from urllib.parse import quote
    method=m['method'];params=m.get('params',{})
    if method=='initialize':return {'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'chemical-wiki-cpu','version':'1.0'}}
    if method=='ping':return {}
    if method=='tools/list':return {'tools':TOOLS}
    if method=='tools/call':
        a=params.get('arguments',{});name=params['name'];body=None
        if name=='wiki_search':path='/api/wiki/platform/search?q='+quote(a['query'])+'&mode='+quote(a.get('mode','wiki'))
        elif name=='wiki_read':path='/api/wiki/'+quote(a['entity'])
        elif name=='wiki_status':path='/api/wiki/platform'
        elif name=='wiki_archive_answer':path='/api/wiki/platform/answers/'+quote(a['answer_id'])+'/archive';body=json.dumps({'title':a.get('title')}).encode()
        else:raise ValueError('Unknown tool')
        headers={'Content-Type':'application/json'}
        if os.environ.get('CHEM_KB_API_KEY'):headers['X-API-Key']=os.environ['CHEM_KB_API_KEY']
        req=urllib.request.Request(URL+path,data=body,headers=headers)
        with urllib.request.urlopen(req,timeout=60) as r:result=json.load(r)
        return {'content':[{'type':'text','text':json.dumps(result,ensure_ascii=False)}]}
    raise ValueError('Unknown method')
def main():
    for line in sys.stdin:
        m=None
        try:
            m=json.loads(line)
            if 'id' not in m:continue
            result={'jsonrpc':'2.0','id':m['id'],'result':rpc(m)}
        except Exception as e:result={'jsonrpc':'2.0','id':m.get('id') if isinstance(m,dict) else None,'error':{'code':-32603,'message':str(e)}}
        print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
