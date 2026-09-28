import streamlit as st
import os
import sys

ROOT_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_PATH)

from app._theme import apply_theme, page_header, metric_row, badge
from app._graph import load_graph, render_graph, load_path, QUICK_ANALYSIS, filter_by_relations
from core.kg.neo4j_store import Neo4jStore
from core.kg.graph_query_service import GraphQueryService
from core.kg.review_manager import ReviewManager
from core.entity_registry import EntityRegistry
from core.knowledge import active_at, entity_candidates, find_conflicts, export_graph, _approved

apply_theme()

page_header("知识图谱探索台", "关系网络 · 生效时点 · 来源溯源 · 冲突审核")

# ---- Neo4j 连接状态 ----
neo4j_ok = False
try:
    neo4j_ok = Neo4jStore().is_connected()
except Exception:
    neo4j_ok = False

if neo4j_ok:
    try:
        _nstats = GraphQueryService().get_stats()
        st.markdown(
            badge("approved", f"● Neo4j Connected — database=neo4j · nodes={_nstats['node_count']} · relationships={_nstats['relation_count']}"),
            unsafe_allow_html=True,
        )
    except Exception:
        st.markdown(badge("approved", "● Neo4j Connected"), unsafe_allow_html=True)
else:
    st.markdown(badge("pending", "⚠ Neo4j 未连接（降级读取本地 JSONL 数据）"), unsafe_allow_html=True)

# ---- 视图模式（3 种）----
MODE_LABELS = {"all": "全部关系", "ai_preview": "AI 预审", "approved": "已审核知识"}
MODE_HINTS = {
    "all": "pending + ai_approved + ai_uncertain + approved（ai_rejected / rejected 不显示）",
    "ai_preview": "ai_approved + approved（AI 预审通过 + 人工通过，不含 uncertain）",
    "approved": "仅人工 approved —— 最高可信 Production KG",
}
st.session_state.setdefault("graph_mode", "all")
mode = st.radio(
    "视图模式", list(MODE_LABELS.keys()), format_func=lambda m: MODE_LABELS[m],
    horizontal=True, key="graph_mode",
)
st.caption(MODE_HINTS[mode])

# ---- 时点与实体别名：只改变展示，不改写来源断言 ----
as_of = st.date_input("图谱生效时点", value="today", key="kg_as_of",
                      help="按 [生效日, 失效日) 筛选关系；未标注日期的历史断言继续显示。")
g = load_graph(mode)
registry = EntityRegistry()
aliases = registry.mapping()
def resolve_id(cid):
    seen = set()
    while cid in aliases and cid not in seen:
        seen.add(cid)
        cid = aliases[cid]
    return cid
full_edges = []
for edge in g["edges"]:
    if active_at(edge, as_of.isoformat()):
        row = dict(edge)
        row["source"] = resolve_id(row["source"])
        row["target"] = resolve_id(row["target"])
        full_edges.append(row)
visible_ids = {cid for edge in full_edges for cid in (edge["source"], edge["target"])}
nodes_by_id = {}
for node in g["nodes"]:
    cid = resolve_id(node["id"])
    if cid in visible_ids and cid not in nodes_by_id:
        nodes_by_id[cid] = {**node, "id": cid}
full_nodes = list(nodes_by_id.values())
st.caption(f"时点 {as_of.isoformat()} · {len(full_nodes)} 实体 · {len(full_edges)} 关系 · 来源 {g.get('source','—')}")


# ---- 快捷分析 / Path Query（可覆盖当前显示）----
if "kg_view" not in st.session_state:
    st.session_state.kg_view = None  # None | ("quick", label, rels) | ("path", start, end)

ctl_c1, ctl_c2, ctl_c3 = st.columns([1, 1, 2])
with ctl_c1:
    if st.button("🔄 显示全图", use_container_width=True, key="kg_full"):
        st.session_state.kg_view = None
        st.rerun()

with st.expander("⚡ 快捷分析（按关系类型过滤，展示专业子图）"):
    qcols = st.columns(3)
    for i, (label, rels) in enumerate(QUICK_ANALYSIS.items()):
        if qcols[i % 3].button(label, key=f"qa_{label}", use_container_width=True):
            st.session_state.kg_view = ("quick", label, rels)
            st.rerun()

with st.expander("🔗 Path Query（两点间最短路径）"):
    node_opts = {n["id"]: f"{n['label']}（{n.get('type_label', n.get('type',''))}）" for n in full_nodes}
    if node_opts:
        pc1, pc2, pc3 = st.columns([2, 2, 1])
        with pc1:
            start_id = st.selectbox("起点", list(node_opts.keys()), format_func=lambda k: node_opts[k], key="pq_start")
        with pc2:
            end_id = st.selectbox("终点", list(node_opts.keys()), format_func=lambda k: node_opts[k], key="pq_end")
        with pc3:
            st.write("")
            st.write("")
            if st.button("🔍 查询路径", key="pq_go", use_container_width=True):
                st.session_state.kg_view = ("path", start_id, end_id)
                st.rerun()
    else:
        st.info("当前模式无可查询的实体节点。")

# ---- 计算实际显示数据 ----
view = st.session_state.kg_view
display_nodes, display_edges = full_nodes, full_edges
view_banner = None
if view is not None:
    kind = view[0]
    if kind == "quick":
        _, label, rels = view
        r = filter_by_relations(full_nodes, full_edges, rels)
        display_nodes, display_edges = r["nodes"], r["edges"]
        view_banner = f"⚡ 快捷分析「{label}」—— {len(display_nodes)} 节点 / {len(display_edges)} 关系"
    elif kind == "path":
        _, start_id, end_id = view
        r = load_path(start_id, end_id)
        if r.get("found"):
            display_nodes, display_edges = r["nodes"], r["edges"]
            hop = (r.get("path") or [])
            view_banner = f"🔗 路径 {start_id} → {end_id} —— {max(0, len(hop) - 1)} 跳 / {len(display_edges)} 关系（source={r.get('source','')}）"
        else:
            view_banner = f"🔗 路径未找到：{r.get('reason', '无路径')}（source={r.get('source','')}）"
            display_nodes, display_edges = [], []

if view_banner:
    st.info(view_banner)

# ---- 动态统计（基于全图）----
by_type = {}
for n in full_nodes:
    by_type[n.get("type", "other")] = by_type.get(n.get("type", "other"), 0) + 1
approved_edges = sum(1 for e in full_edges if e.get("review_status") == "approved")
ai_edges = sum(1 for e in full_edges if e.get("review_status") == "ai_approved")

metric_row([
    (len(full_nodes), "节点数"),
    (len(full_edges), "关系数"),
    (by_type.get("accident", 0), "Accident"),
    (by_type.get("standard", 0), "Standard"),
    (by_type.get("regulation", 0), "Regulation"),
    (by_type.get("chemical", 0), "Chemical"),
    (approved_edges, "Approved"),
    (ai_edges, "AI 预审"),
])

st.divider()

if not display_nodes:
    st.info(
        "当前视图无可展示数据。\n\n"
        "· 已审核知识：需在「KG 审核中心」approve 断言后才有数据。\n"
        "· 全部关系 / AI 预审：展示候选（pending/ai_*）与已审核断言，不同状态用线型/透明度区分。\n\n"
        "不伪造节点/关系。"
    )

st.caption(
    "交互：悬停节点高亮邻居 · 悬停/点击节点边看详情 · 双击节点聚焦 1-hop · 右键菜单 · "
    "滚轮缩放 · 拖动画布 · 顶部搜索/类型过滤/关系过滤/布局 · 左下角 MiniMap（点击可跳转）"
)
render_graph(display_nodes, display_edges, mode=mode, height=680)

# ---- 溯源导出与审查工作台 ----
st.subheader("溯源与质量审查")
reviews = ReviewManager()
reviewed = reviews.get_reviewed()
pending = reviews.get_pending()
approved = _approved(reviewed)
tab_export, tab_conflict, tab_entity = st.tabs(["图谱导出", "跨来源冲突", "全局实体去重"])
with tab_export:
    st.caption(f"仅导出人工审核通过的断言；时点 {as_of.isoformat()}；PROV-O 记录文档、片段、抽取活动和审核代理。")
    fmt = st.selectbox("导出格式", ["jsonld", "turtle", "graphml", "csv"],
                       format_func=lambda x: {"jsonld":"PROV-O JSON-LD", "turtle":"PROV-O Turtle",
                                               "graphml":"GraphML", "csv":"CSV"}[x])
    ext = {"jsonld":"jsonld","turtle":"ttl","graphml":"graphml","csv":"csv"}[fmt]
    st.download_button("下载图谱", data=export_graph(reviewed, fmt, as_of.isoformat()),
                       file_name=f"chemical_knowledge_{as_of.isoformat()}.{ext}",
                       mime={"jsonld":"application/ld+json","turtle":"text/turtle",
                             "graphml":"application/graphml+xml","csv":"text/csv"}[fmt])
with tab_conflict:
    conflicts = find_conflicts([registry.apply(a) for a in approved + pending])
    st.caption("同一主体与关系在生效区间重叠时，若不同来源指向不同对象，则列为待人工核实。")
    st.metric("待核实冲突", len(conflicts))
    if conflicts:
        st.dataframe(conflicts[:300], use_container_width=True, hide_index=True)
    else:
        st.info("当前断言中未发现符合该规则的冲突。")
with tab_entity:
    candidates = entity_candidates(approved + pending)
    st.caption("同类型且规范化名称一致的跨来源 ID 会列为候选；合并需人工审核，可撤销。")
    st.metric("重复实体候选", len(candidates))
    if candidates:
        st.dataframe(candidates[:300], use_container_width=True, hide_index=True)
        with st.form("entity_merge"):
            option = st.selectbox("候选实体", range(len(candidates)),
                                  format_func=lambda i: f"{candidates[i]['entity_type']} · {candidates[i]['normalized_label']} · {len(candidates[i]['canonical_ids'])} IDs")
            ids = candidates[option]["canonical_ids"]
            alias = st.selectbox("别名 ID", ids)
            canonical = st.selectbox("保留的全局 ID", ids)
            reviewer = st.text_input("审核人")
            if st.form_submit_button("确认合并", type="primary"):
                try:
                    registry.decide(alias, canonical, reviewer)
                    st.success("合并已记录；图谱视图将按全局 ID 汇总。")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    else:
        st.info("当前没有可建议的重复实体。")
    with st.expander("撤销实体合并"):
        aliases_now = registry.mapping()
        if aliases_now:
            alias_to_revoke = st.selectbox("别名", list(aliases_now))
            reviewer_revoke = st.text_input("撤销审核人")
            if st.button("撤销合并"):
                try:
                    registry.decide(alias_to_revoke, aliases_now[alias_to_revoke],
                                    reviewer_revoke, action="revoke")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

