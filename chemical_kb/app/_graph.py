# -*- coding: utf-8 -*-
"""知识图谱视图（v0.7）：Cytoscape.js + fcose 本地渲染 + 3 模式 + AI 预审状态 + 完整交互。

- 数据优先 Neo4j（graph_query_service），未连接时降级 JSONL。
- 统一节点/边结构（Cytoscape 就绪：id/source/target/type/color/shape/review_status）。
- review_status 五态：approved / ai_approved / ai_uncertain / ai_rejected / pending。
- Cytoscape.js + fcose 本地化到 app/static/，无 CDN；MiniMap 用自定义 canvas（无外部插件）。
"""
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
import networkx as nx

from core.kg.graph_builder import TYPE_COLORS, DEFAULT_COLOR, type_label
from core.kg.review_manager import ReviewManager
from core.kg.neo4j_store import Neo4jStore
from core.kg.graph_query_service import GraphQueryService

_BASE_DIR = Path(__file__).resolve().parent.parent
_STATIC = Path(__file__).resolve().parent / "static"
_AI_FILE = _BASE_DIR / "data" / "kg" / "review" / "ai_preview.jsonl"

NODE_SHAPES = {
    "standard": "round-rectangle", "regulation": "rectangle", "accident": "diamond",
    "chemical": "ellipse", "equipment": "hexagon", "enterprise": "round-rectangle",
    "causal_factor": "triangle", "requirement": "round-rectangle", "clause": "rectangle",
    "measure": "ellipse",
}
DEFAULT_SHAPE = "ellipse"

RELATION_GROUPS = {
    "事故因果": ["direct_cause", "indirect_cause", "leads_to"],
    "文档结构": ["derived_from", "has_clause", "parent_of", "defines", "references", "replaces"],
    "规范桥接": ["violates", "based_on", "applies_to", "governs"],
    "对象关系": ["involves_chemical", "involves_equipment", "involves_process",
               "contains", "used_in", "handles", "has_equipment", "operates_process",
               "located_at", "has_hazard_source", "hazard_of", "belongs_to_class"],
}

QUICK_ANALYSIS = {
    "事故因果链": ["direct_cause", "indirect_cause", "leads_to"],
    "事故→标准法规": ["violates", "derived_from", "has_clause", "based_on", "applies_to", "governs"],
    "化学品→历史事故": ["involves_chemical", "involves_equipment", "involves_process", "occurred_in", "occurred_at"],
    "化学品→安全要求": ["applies_to", "governs", "handles"],
    "设备→事故原因": ["involves_equipment", "direct_cause", "indirect_cause", "leads_to", "relates_to"],
    "整改措施→规范依据": ["based_on", "violates", "applies_to"],
}

_CAUSAL = {"direct_cause", "indirect_cause", "leads_to"}
_DOC_STRUCT = {"derived_from", "has_clause", "parent_of", "defines", "references", "replaces"}
_IMPORTANT_REL = _CAUSAL | {"violates", "applies_to", "derived_from",
                            "involves_chemical", "involves_equipment", "involves_process"}


# --------------------------------------------------------------------------- #
# 边样式：predicate 定颜色，review_status 定线型/透明度
# --------------------------------------------------------------------------- #
def _color_by_predicate(predicate):
    if predicate in _CAUSAL:
        return "#d1453b"
    if predicate == "violates":
        return "#c0392b"
    if predicate == "based_on":
        return "#2e9e6b"
    if predicate in _DOC_STRUCT:
        return "#9aa7b0"
    return "#b9c4ce"


def edge_style(predicate, review_status):
    """v0.7 五态边样式：approved 实线 / ai_approved 实线稍浅 / ai_uncertain 点划线 /
    pending 虚线低透明 / ai_rejected 不显示（由可见性过滤）。"""
    color = _color_by_predicate(predicate)
    rs = review_status or "pending"
    if rs == "approved":
        return {"lineColor": color, "lineStyle": "solid", "width": 2.0, "opacity": 0.9}
    if rs == "ai_approved":
        return {"lineColor": color, "lineStyle": "solid", "width": 2.0, "opacity": 0.55}
    if rs == "ai_uncertain":
        return {"lineColor": color, "lineStyle": "dotted", "width": 1.8, "opacity": 0.7}
    if rs == "pending":
        return {"lineColor": color, "lineStyle": "dashed", "width": 1.3, "opacity": 0.4}
    return {"lineColor": color, "lineStyle": "dashed", "width": 1.2, "opacity": 0.3}


def _visible(status, mode):
    if mode == "approved":
        return status == "approved"
    if mode == "ai_preview":
        return status in ("approved", "ai_approved")
    # all：pending + ai_approved + ai_uncertain + approved（ai_rejected / rejected 不显示）
    return status in ("approved", "ai_approved", "ai_uncertain", "pending")


def _effective_status(assertion_id, is_approved, ai_dec):
    if is_approved:
        return "approved"
    d = ai_dec.get(assertion_id, {}).get("decision", "")
    if d in ("ai_approved", "ai_rejected", "ai_uncertain"):
        return d
    return "pending"


# --------------------------------------------------------------------------- #
# AI 预审决定（ai_preview.jsonl）
# --------------------------------------------------------------------------- #
def _load_ai_decisions():
    if not _AI_FILE.exists():
        return {}
    out = {}
    with open(_AI_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            aid = r.get("assertion_id", "")
            if aid:
                out[aid] = r
    return out


def _node(cid, label, etype, a):
    return {
        "id": cid, "label": label or cid, "type": etype,
        "type_label": type_label(etype),
        "color": TYPE_COLORS.get(etype, DEFAULT_COLOR),
        "shape": NODE_SHAPES.get(etype, DEFAULT_SHAPE),
        "source_doc_id": a.get("source_doc_id", ""),
        "page": f"{a.get('page_start','')}-{a.get('page_end','')}",
        "section": a.get("section", ""),
    }


def _edge(a, sid, oid, pred, status):
    st = edge_style(pred, status)
    return {
        "id": a.get("assertion_id", "") or f"{sid}-{pred}-{oid}",
        "source": sid, "target": oid,
        "label": pred, "predicate": pred,
        "review_status": status,
        "confidence": a.get("confidence", ""),
        "assertion_type": a.get("assertion_type", ""),
        "source_doc_id": a.get("source_doc_id", ""),
        "source_chunk_id": a.get("source_chunk_id", ""),
        "page_start": a.get("page_start", ""),
        "page_end": a.get("page_end", ""),
        "source_text_quote": a.get("source_text_quote", ""),
        "valid_from": a.get("valid_from", ""), "valid_to": a.get("valid_to", ""),
        "recorded_at": a.get("recorded_at", ""),
        "lineColor": st["lineColor"], "lineStyle": st["lineStyle"],
        "width": st["width"], "opacity": st["opacity"],
        "important": 1 if pred in _IMPORTANT_REL else 0,
    }


def _load_jsonl(mode):
    mgr = ReviewManager()
    ai_dec = _load_ai_decisions()
    nodes, edges = {}, []

    def add(a, status):
        if not _visible(status, mode):
            return
        sid, oid = a.get("subject_id", ""), a.get("object_id", "")
        pred = a.get("predicate", "")
        if not sid or not pred:
            return
        if sid not in nodes:
            nodes[sid] = _node(sid, a.get("subject_label", sid), a.get("subject_type", ""), a)
        if a.get("object_kind") == "literal" or not oid:
            return
        if oid not in nodes:
            nodes[oid] = _node(oid, a.get("object_label", oid), a.get("object_type", ""), a)
        edges.append(_edge(a, sid, oid, pred, status))

    for r in mgr.get_reviewed():
        d = r.get("decision", "")
        a = r.get("original_assertion") if d == "approved" else (r.get("corrected_assertion") if d == "modified" else None)
        if isinstance(a, dict):
            add(a, "approved")
    for a in mgr.get_pending():
        add(a, _effective_status(a.get("assertion_id", ""), False, ai_dec))
    return {"nodes": list(nodes.values()), "edges": edges}


def _normalize_neo4j(g, ai_dec, mode):
    """把 graph_query_service 的中性结构（canonical_id/name/entity_type + _sub/_obj）转成 Cytoscape 就绪结构，
    并叠加 AI 预审决定 + 按模式过滤（节点只保留可见边的端点，避免孤立节点）。"""
    node_lookup = {n.get("canonical_id"): n for n in g.get("nodes", [])}
    edges = []
    for e in g.get("edges", []):
        sub, obj = e.get("_sub", ""), e.get("_obj", "")
        pred = e.get("predicate", "")
        if not sub or not pred:
            continue
        aid = e.get("assertion_id", "")
        raw = e.get("review_status", "")
        status = "approved" if raw == "approved" else _effective_status(aid, False, ai_dec)
        if not _visible(status, mode):
            continue
        edges.append(_edge(e, sub, obj, pred, status))
    nodes = {}
    for e in edges:
        for cid in (e["source"], e["target"]):
            if cid in nodes or cid not in node_lookup:
                continue
            n = node_lookup[cid]
            et = n.get("entity_type", "")
            nodes[cid] = {
                "id": cid, "label": n.get("name") or cid, "type": et,
                "type_label": type_label(et),
                "color": TYPE_COLORS.get(et, DEFAULT_COLOR),
                "shape": NODE_SHAPES.get(et, DEFAULT_SHAPE),
                "source_doc_id": "", "page": "", "section": "",
            }
    return {"nodes": list(nodes.values()), "edges": edges}


def _neo4j_available():
    try:
        return Neo4jStore().is_connected()
    except Exception:
        return False


def load_graph(mode="approved", center_id=None, hop=1):
    ai_dec = _load_ai_decisions()
    if _neo4j_available():
        try:
            svc = GraphQueryService()
            if center_id:
                g = svc.query_approved(center_id, hop) if mode == "approved" else svc.query_all(center_id, hop)
            else:
                g = svc.query_approved_all() if mode == "approved" else svc.query_all_all()
            g = _normalize_neo4j(g, ai_dec, mode)
            g["mode"], g["source"] = mode, "neo4j"
            return g
        except Exception:
            pass
    g = _load_jsonl(mode)
    g["mode"], g["source"] = mode, "jsonl"
    return g


# --------------------------------------------------------------------------- #
# 快捷分析 / 路径查询（networkx 降级，供页面调用）
# --------------------------------------------------------------------------- #
def filter_by_relations(nodes, edges, relation_types):
    rel = set(relation_types)
    sub_edges = [e for e in edges if e.get("predicate") in rel]
    involved = set()
    for e in sub_edges:
        involved.add(e["source"])
        involved.add(e["target"])
    sub_nodes = [n for n in nodes if n["id"] in involved]
    return {"nodes": sub_nodes, "edges": sub_edges}


def query_path_nx(nodes, edges, start_id, end_id, max_depth=6):
    G = nx.DiGraph()
    for n in nodes:
        G.add_node(n["id"])
    for e in edges:
        G.add_edge(e["source"], e["target"])
    if start_id not in G or end_id not in G:
        return {"found": False, "nodes": [], "edges": [], "reason": "起点/终点实体不存在"}
    try:
        path = nx.shortest_path(G, start_id, end_id)
    except nx.NetworkXNoPath:
        return {"found": False, "nodes": [], "edges": [], "reason": "两点之间无连通路径"}
    if len(path) - 1 > max_depth:
        return {"found": False, "nodes": [], "edges": [],
                "reason": f"路径深度 {len(path) - 1} 超过限制 {max_depth}"}
    node_map = {n["id"]: n for n in nodes}
    edge_map = {(e["source"], e["target"]): e for e in edges}
    sub_nodes = [node_map[nid] for nid in path if nid in node_map]
    sub_edges = []
    for i in range(len(path) - 1):
        e = edge_map.get((path[i], path[i + 1]))
        if e is None:
            e = edge_map.get((path[i + 1], path[i]))
        if e is not None:
            sub_edges.append(e)
    return {"found": True, "nodes": sub_nodes, "edges": sub_edges, "path": path}


def load_path(start_id, end_id, max_depth=5):
    """两点间最短路径：优先 Neo4j，降级 networkx（在 all 图上）。返回 Cytoscape 就绪结构。"""
    if _neo4j_available():
        try:
            r = GraphQueryService().query_path(start_id, end_id, max_depth)
            g = _normalize_neo4j({"nodes": r.get("nodes", []), "edges": r.get("edges", [])},
                                 _load_ai_decisions(), "all")
            g["found"] = bool(r.get("found"))
            g["path"] = r.get("path", [])
            g["source"] = "neo4j"
            if not g["found"]:
                g["reason"] = r.get("reason", "无路径")
            return g
        except Exception:
            pass
    g = _load_jsonl("all")
    r = query_path_nx(g["nodes"], g["edges"], start_id, end_id, max_depth)
    r["source"] = "networkx"
    return r


# --------------------------------------------------------------------------- #
# Cytoscape 渲染
# --------------------------------------------------------------------------- #
_TPL = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#091a27;}
  #wrap{display:flex;height:100vh;border:1px solid #31576a;border-radius:12px;overflow:hidden;}
  button:hover{border-color:#5dd5c5;background:#245364;}
  button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #f3b65c;outline-offset:2px;}
  @media(max-width:700px){#wrap{flex-direction:column}#panel{width:auto;max-height:38vh;border-left:0;border-top:1px solid #315467}#minimap{width:120px;height:90px}#zoomctl{bottom:105px}}
  #main{flex:1;display:flex;flex-direction:column;position:relative;}
  #toolbar{padding:8px 12px;background:#102b3b;border-bottom:1px solid #315467;display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:13px;color:#e6f4f3;}
  #graph{flex:1;background:#091a27;position:relative;}
  #minimap{position:absolute;left:10px;bottom:10px;width:180px;height:130px;background:#102b3b;border:1px solid #315467;border-radius:6px;z-index:5;overflow:hidden;}
  #minimap canvas{width:100%;height:100%;}
  #zoomctl{position:absolute;left:10px;bottom:150px;background:#102b3b;border:1px solid #315467;border-radius:6px;padding:4px;z-index:5;display:flex;flex-direction:column;gap:2px;align-items:center;font-size:12px;}
  #panel{width:330px;background:#102b3b;border-left:1px solid #315467;padding:14px;overflow:auto;display:none;font-size:13px;color:#e6f4f3;}
  #panel h4{margin:0 0 8px;font-size:15px;word-break:break-all;}
  .kv{margin:5px 0;line-height:1.5;}
  .kv b{color:#5c6b7a;font-weight:500;}
  .badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;margin-left:4px;}
  .b-approved{background:#e6f4ea;color:#1b6e33;} .b-ai{background:#e8f1fb;color:#1668c7;}
  .b-pending{background:#fdf3e0;color:#b26a00;} .b-uncertain{background:#f1eafb;color:#7b3fd0;}
  input,select,button{font-family:inherit;font-size:12px;padding:4px 8px;border:1px solid #426879;border-radius:6px;background:#17394a;color:#e6f4f3;}
  #tooltip{position:absolute;display:none;background:#14202e;color:#fff;padding:6px 10px;border-radius:6px;font-size:12px;z-index:9;pointer-events:none;max-width:260px;}
  #ctxmenu{position:absolute;display:none;background:#102b3b;border:1px solid #315467;border-radius:8px;z-index:10;box-shadow:0 2px 8px rgba(0,0,0,.12);padding:4px 0;}
  #ctxmenu div{padding:6px 16px;font-size:13px;cursor:pointer;}
  #ctxmenu div:hover{background:#f0f3f6;}
</style></head><body>
<div id="wrap">
  <div id="main">
    <div id="toolbar">
      <input id="search" placeholder="搜索实体(name/canonical_id)…" oninput="doSearch(this.value)">
      <select id="typefilter" onchange="applyFilters()"><option value="">类型:全部</option></select>
      <select id="relfilter" onchange="applyFilters()"><option value="">关系:全部</option></select>
      <select id="layout" onchange="applyLayout(this.value)">
        <option value="fcose" selected>fcose</option><option value="cose">cose</option><option value="breadthfirst">层级</option><option value="concentric">同心圆</option>
      </select>
      <button onclick="fit()">Fit</button>
      <button onclick="center()">Center</button>
      <button onclick="reset()">Reset</button>
    </div>
    <div id="graph"></div>
    <div id="minimap"><canvas id="mmcanvas" width="180" height="130"></canvas></div>
    <div id="zoomctl"><button onclick="zoom(1.2)">＋</button><span id="zoomval">100%</span><button onclick="zoom(0.8)">－</button></div>
    <div id="tooltip"></div>
    <div id="ctxmenu"></div>
  </div>
  <div id="panel"></div>
</div>
__CYTO_SCAPE__
__FCOSE__
<script>
var DATA = __GRAPH__;
function esc(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, function(ch) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];
  });
}
// 注册 fcose 布局插件（关键修复：不注册则 layout 失败、图空白；fcose 依赖 cose-base/layout-base，任一缺失则回退内置 cose）
var layoutName = 'fcose';
if (typeof cytoscapeFcose !== 'undefined') {
  try { cytoscape.use(cytoscapeFcose); } catch(e) { layoutName = 'cose'; }
} else { layoutName = 'cose'; }

var cy = cytoscape({
  container: document.getElementById('graph'),
  elements: DATA.elements,
  style: [
    {selector:'node', style:{
      'background-color':'data(color)','shape':'data(shape)','width':22,'height':22,
      'label':'data(label)','color':'#e4f0f1','font-size':11,'text-valign':'bottom','text-margin-y':5,
      'text-wrap':'ellipsis','text-max-width':70,'border-width':1,'border-color':'#9bd8d2'
    }},
    {selector:'edge', style:{
      'line-color':'data(lineColor)','line-style':'data(lineStyle)','width':'data(width)','opacity':'data(opacity)',
      'target-arrow-shape':'triangle','target-arrow-color':'data(lineColor)','arrow-scale':0.7,
      'curve-style':'bezier','label':'data(label)','font-size':9,'color':'#a9c7cf',
      'text-background-color':'#0a1d2b','text-background-opacity':0.9,'text-opacity':0
    }},
    {selector:'edge.important', style:{'text-opacity':0.75}},
    {selector:'edge.hovered, edge:selected', style:{'text-opacity':1}},
    {selector:':selected', style:{'border-width':3,'border-color':'#f59e0b'}},
    {selector:'.dim', style:{'opacity':0.18}},
    {selector:'.focus', style:{'opacity':1}}
  ],
  layout:{name:layoutName, animate:false, randomize:false},
  minZoom:0.2, maxZoom:4, wheelSensitivity:0.25
});

cy.on('zoom', function(){ document.getElementById('zoomval').textContent = Math.round(cy.zoom()*100)+'%'; });

(function(){
  var types={}; DATA.nodes.forEach(function(n){ types[n.type]=(n.type_label||n.type); });
  var tf=document.getElementById('typefilter');
  Object.keys(types).forEach(function(t){ var o=document.createElement('option'); o.value=t; o.textContent=types[t]; tf.appendChild(o); });
  var rels={}; DATA.edges.forEach(function(e){ rels[e.predicate]=1; });
  var rf=document.getElementById('relfilter');
  var groups=__GROUPS__;
  Object.keys(groups).forEach(function(g){ var o=document.createElement('option'); o.value='g:'+g; o.textContent='关系组:'+g; rf.appendChild(o); });
  Object.keys(rels).forEach(function(p){ var o=document.createElement('option'); o.value=p; o.textContent=p; rf.appendChild(o); });
})();

function applyFilters(){
  var t=document.getElementById('typefilter').value, r=document.getElementById('relfilter').value;
  cy.batch(function(){
    cy.elements().removeClass('dim');
    if(t){ cy.nodes().forEach(function(n){ if(n.data('type')!==t) n.addClass('dim'); }); }
    if(r){
      cy.edges().forEach(function(e){
        var ok=false;
        if(r.indexOf('g:')===0){ var g=r.slice(2); ok=(__GROUPS__[g]||[]).indexOf(e.data('predicate'))>=0; }
        else ok=(e.data('predicate')===r);
        if(!ok) e.addClass('dim');
      });
    }
  });
}

function showTooltip(html, x, y){ var t=document.getElementById('tooltip'); t.innerHTML=html; t.style.display='block'; t.style.left=(x+10)+'px'; t.style.top=(y+10)+'px'; }
function hideTooltip(){ document.getElementById('tooltip').style.display='none'; }

function nodeStats(n){
  var ce=n.connectedEdges(); var acc=0,std=0,reg=0,req=0,eq=0;
  ce.forEach(function(e){ var o=e.source()===n?e.target():e.source(); var t=o.data('type');
    if(t==='accident')acc++; if(t==='standard')std++; if(t==='regulation')reg++; if(t==='requirement')req++; if(t==='equipment')eq++; });
  return 'Degree '+n.degree()+' · 事故'+acc+' · 标准'+std+' · 法规'+reg;
}

cy.on('mouseover','node',function(evt){
  var n=evt.target;
  showTooltip('<b>'+esc(n.data('label'))+'</b><br>'+esc(n.data('type_label'))+'<br>'+esc(nodeStats(n)), evt.renderedPosition.x, evt.renderedPosition.y);
  cy.batch(function(){
    cy.elements().addClass('dim').removeClass('focus');
    n.closedNeighborhood().addClass('focus');
    n.addClass('focus');
  });
});
cy.on('mouseout','node',function(){ hideTooltip(); cy.elements().removeClass('dim').removeClass('focus'); });
cy.on('mouseover','edge',function(evt){
  var e=evt.target;
  showTooltip('<b>'+esc(e.data('predicate'))+'</b><br>'+esc(e.source().data('label'))+' → '+esc(e.target().data('label'))+'<br>conf '+esc(e.data('confidence'))+' · '+esc(e.data('review_status')), evt.renderedPosition.x, evt.renderedPosition.y);
  e.addClass('hovered');
});
cy.on('mouseout','edge',function(evt){ hideTooltip(); evt.target.removeClass('hovered'); });

function statusBadge(st){
  if(st==='approved') return '<span class="badge b-approved">approved</span>';
  if(st==='ai_approved') return '<span class="badge b-ai">ai_approved</span>';
  if(st==='ai_uncertain') return '<span class="badge b-uncertain">ai_uncertain</span>';
  return '<span class="badge b-pending">'+esc(st)+'</span>';
}
function showNodeDetails(n){
  var d=n.data(); var p=document.getElementById('panel'); p.style.display='block';
  var ce=n.connectedEdges(); var out={}; var inc={};
  ce.forEach(function(e){
    if(e.source()===n){ var k=e.data('predicate'); (out[k]=out[k]||[]).push(e.target().data('label')); }
    else { var k2=e.data('predicate'); (inc[k2]=inc[k2]||[]).push(e.source().data('label')); }
  });
  function fmt(obj){ var s=''; Object.keys(obj).forEach(function(k){ s+='<div class="kv"><b>'+esc(k)+'</b>: '+obj[k].map(esc).join('、')+'</div>'; }); return s||'<div class="kv">（无）</div>'; }
  p.innerHTML='<h4>'+esc(d.label)+statusBadge(d.review_status||'approved')+'</h4>'
    +'<div class="kv"><b>类型</b>: '+esc(d.type_label)+'</div>'
    +'<div class="kv"><b>canonical_id</b>: '+esc(d.id)+'</div>'
    +'<div class="kv"><b>Degree</b>: '+n.degree()+'</div>'
    +'<div class="kv"><b>来源</b>: '+esc(d.source_doc_id||'—')+' '+esc(d.page||'')+'</div>'
    +'<hr><b>出边</b>'+fmt(out)+'<hr><b>入边</b>'+fmt(inc);
}
function showEdgeDetails(e){
  var d=e.data(); var p=document.getElementById('panel'); p.style.display='block';
  var at = d.assertion_type==='inferred'?'推断关系':(d.assertion_type==='explicit'?'原文明确关系':(d.assertion_type||'—'));
  p.innerHTML='<h4>'+esc(d.predicate)+'</h4>'
    +'<div class="kv"><b>Subject</b>: '+esc(e.source().data('label'))+'</div>'
    +'<div class="kv"><b>Predicate</b>: '+esc(d.predicate)+'</div>'
    +'<div class="kv"><b>Object</b>: '+esc(e.target().data('label'))+'</div>'
    +'<div class="kv"><b>Confidence</b>: '+esc(d.confidence)+'</div>'
    +'<div class="kv"><b>Assertion Type</b>: '+esc(at)+'</div>'
    +'<div class="kv"><b>Review Status</b>: '+statusBadge(d.review_status)+'</div>'
    +'<div class="kv"><b>来源</b>: '+esc(d.source_doc_id||'—')+' p.'+esc(d.page_start||'')+'-'+esc(d.page_end||'')+'</div>'
    +'<div class="kv"><b>生效</b>: '+esc(d.valid_from||'未知')+' → '+esc(d.valid_to||'持续')+'</div>'
    +'<div class="kv"><b>记录时间</b>: '+esc(d.recorded_at||'—')+'</div>'
    +'<div class="kv"><b>Evidence</b>: '+esc(d.source_text_quote||'—')+'</div>';
}

cy.on('tap','node',function(evt){ showNodeDetails(evt.target); });
cy.on('tap','edge',function(evt){ showEdgeDetails(evt.target); });
cy.on('tap',function(evt){ if(evt.target===cy){ document.getElementById('panel').style.display='none'; cy.elements().removeClass('dim').removeClass('focus'); } });

cy.on('dbltap','node',function(evt){
  var n=evt.target;
  cy.batch(function(){ cy.elements().addClass('dim').removeClass('focus'); n.closedNeighborhood().addClass('focus'); n.addClass('focus'); });
  cy.animate({center:{eles:n}, zoom:1.6, duration:window.matchMedia('(prefers-reduced-motion: reduce)').matches?0:300});
});

cy.on('cxttap','node',function(evt){
  var n=evt.target; var m=document.getElementById('ctxmenu');
  m.innerHTML='<div>展开 1-hop</div><div>展开 2-hop</div><div>设为中心</div><div>隐藏节点</div>';
  var items=m.querySelectorAll('div'), id=n.id();
  items[0].onclick=function(){ expandHop(id,1); };
  items[1].onclick=function(){ expandHop(id,2); };
  items[2].onclick=function(){ setCenter(id); };
  items[3].onclick=function(){ hideNode(id); };
  m.style.display='block'; m.style.left=evt.renderedPosition.x+'px'; m.style.top=evt.renderedPosition.y+'px';
});
cy.on('tap',function(){ document.getElementById('ctxmenu').style.display='none'; });

function expandHop(id, hop){
  var n=cy.getElementById(id); var keep=n.closedNeighborhood();
  if(hop===2){ keep=keep.union(n.closedNeighborhood().nodes().closedNeighborhood()); }
  cy.batch(function(){ cy.elements().addClass('dim').removeClass('focus'); keep.addClass('focus'); });
  cy.animate({center:{eles:n}, zoom:1.6, duration:window.matchMedia('(prefers-reduced-motion: reduce)').matches?0:300});
}
function setCenter(id){ var n=cy.getElementById(id); cy.animate({center:{eles:n}, zoom:1.8, duration:300}); }
function hideNode(id){ cy.getElementById(id).addClass('dim'); }

function doSearch(q){
  q=(q||'').toLowerCase().trim();
  cy.elements().removeClass('dim').removeClass('focus');
  if(!q) return;
  var matches=cy.nodes().filter(function(n){ return (n.data('label')||'').toLowerCase().indexOf(q)>=0 || (n.data('id')||'').toLowerCase().indexOf(q)>=0; });
  if(matches.length===0) return;
  var n=matches[0];
  cy.batch(function(){ cy.elements().addClass('dim').removeClass('focus'); n.closedNeighborhood().addClass('focus'); n.addClass('focus'); });
  cy.animate({center:{eles:n}, zoom:1.6, duration:window.matchMedia('(prefers-reduced-motion: reduce)').matches?0:300});
  n.flashClass('focus', 1000);
  showNodeDetails(n);
}

function zoom(f){ cy.zoom(cy.zoom()*f); }
function fit(){ cy.fit(undefined, 30); }
function center(){ cy.center(); }
function reset(){ cy.layout({name: layoutName, animate:false}).run(); setTimeout(function(){ cy.fit(undefined, 30); }, 200); }
function applyLayout(name){ layoutName=name; cy.layout({name:name, animate:true}).run(); }

// ---- 自定义 MiniMap（canvas，无外部插件）----
var mmCanvas=document.getElementById('mmcanvas'), mmCtx=mmCanvas.getContext('2d');
var mmTransform=null;
function drawMinimap(){
  var W=mmCanvas.width, H=mmCanvas.height;
  mmCtx.clearRect(0,0,W,H);
  mmCtx.fillStyle='#fafbfc'; mmCtx.fillRect(0,0,W,H);
  var bb=cy.extent();
  if(bb.w===0 || bb.h===0) return;
  var pad=8;
  var s=Math.min((W-2*pad)/bb.w, (H-2*pad)/bb.h);
  var ox=pad-bb.x1*s, oy=pad-bb.y1*s;
  mmTransform={s:s,ox:ox,oy:oy};
  function tx(x){return x*s+ox;} function ty(y){return y*s+oy;}
  mmCtx.strokeStyle='#e3e8ee'; mmCtx.lineWidth=0.5;
  cy.edges().forEach(function(e){ var sp=e.source().position(), tp=e.target().position();
    mmCtx.beginPath(); mmCtx.moveTo(tx(sp.x),ty(sp.y)); mmCtx.lineTo(tx(tp.x),ty(tp.y)); mmCtx.stroke(); });
  cy.nodes().forEach(function(n){ var p=n.position();
    mmCtx.fillStyle=n.data('color')||'#9aa7b0';
    mmCtx.beginPath(); mmCtx.arc(tx(p.x),ty(p.y),2.2,0,Math.PI*2); mmCtx.fill(); });
  var pan=cy.pan(), zoom=cy.zoom();
  var vw=cy.width()/zoom, vh=cy.height()/zoom;
  var vx1=-pan.x/zoom, vy1=-pan.y/zoom;
  mmCtx.strokeStyle='#f59e0b'; mmCtx.lineWidth=1.2;
  mmCtx.strokeRect(tx(vx1),ty(vy1),vw*s,vh*s);
}
cy.on('render pan zoom layoutstop', drawMinimap);
mmCanvas.addEventListener('mousedown', function(evt){
  if(!mmTransform) return;
  var rect=mmCanvas.getBoundingClientRect();
  var cx=evt.clientX-rect.left, cyy=evt.clientY-rect.top;
  var mx=(cx-mmTransform.ox)/mmTransform.s, my=(cyy-mmTransform.oy)/mmTransform.s;
  var zoom=cy.zoom();
  cy.pan({x: cy.width()/2 - mx*zoom, y: cy.height()/2 - my*zoom});
  drawMinimap();
});

setTimeout(function(){ cy.fit(undefined, 30); drawMinimap(); }, 350);
</script>
</body></html>
"""


def _read_static(name):
    p = _STATIC / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def render_graph(nodes, edges, mode="approved", height=700):
    if not nodes:
        return
    elements = [{"data": n} for n in nodes] + [{"data": e} for e in edges]
    graph = {"nodes": nodes, "edges": edges, "elements": elements, "mode": mode}
    html = (_TPL
            .replace("__CYTO_SCAPE__", f"<script>{_read_static('cytoscape.min.js')}</script>")
            .replace("__FCOSE__",
                     f"<script>{_read_static('layout-base.js')}</script>"
                     f"<script>{_read_static('cose-base.js')}</script>"
                     f"<script>{_read_static('cytoscape-fcose.js')}</script>")
            .replace("__GRAPH__", json.dumps(graph, ensure_ascii=False).replace("<", "\\u003c"))
            .replace("__GROUPS__", json.dumps(RELATION_GROUPS, ensure_ascii=False)))
    components.html(html, height=height, scrolling=True)
