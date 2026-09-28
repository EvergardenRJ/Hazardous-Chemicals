import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import SpriteText from 'three-spritetext';
import * as THREE from 'three';

export const TYPE_COLORS = {
  accident: '#ff887f', standard: '#64b5ff', regulation: '#9a8bff',
  chemical: '#64dfbd', equipment: '#70cfe5', enterprise: '#ffca82',
  causal_factor: '#f4b968', requirement: '#8caeff', clause: '#b09cff',
  measure: '#5bd1bd', process: '#91c9b8', site: '#9cb2c8',
  major_hazard_source: '#dcb47b', entity: '#9bb7cf'
};

function shortLabel(value) {
  const text = String(value || '');
  return text.length > 15 ? text.slice(0, 14) + '…' : text;
}

function nodeObject(node, selected, nearby, onPath, theme) {
  const color = TYPE_COLORS[node.type] || TYPE_COLORS.entity;
  const focused = selected === node.id || onPath;
  const dimmed = selected && node.id !== selected && !nearby.has(node.id) && !onPath;
  const group = new THREE.Group();
  const radius = node.type === 'accident' ? 6.8 : focused ? 6 : 4.7;
  const core = new THREE.Mesh(
    new THREE.SphereGeometry(radius, 24, 16),
    new THREE.MeshStandardMaterial({
      color: dimmed ? '#37536b' : color,
      emissive: dimmed ? '#11283b' : color,
      emissiveIntensity: focused ? 0.58 : 0.32,
      metalness: 0.22, roughness: 0.38
    })
  );
  group.add(core);
  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(radius * (focused ? 1.85 : 1.55), 18, 12),
    new THREE.MeshBasicMaterial({
      color, transparent: true, opacity: dimmed ? 0.025 : focused ? 0.18 : 0.075,
      depthWrite: false
    })
  );
  group.add(halo);
  if (!dimmed) {
    const label = new SpriteText(shortLabel(node.label));
    label.color = theme === 'light' ? (focused ? '#09253e' : '#284d68') : (focused ? '#ffffff' : '#c2d9e9');
    label.textHeight = focused ? 7 : 5.2;
    label.fontFace = 'IBM Plex Sans, Microsoft YaHei, sans-serif';
    label.fontWeight = focused ? 'bold' : 'normal';
    label.position.set(0, radius + 10, 0);
    group.add(label);
  }
  return group;
}

const GraphCanvas = forwardRef(function GraphCanvas(
  { nodes, edges, selection, focusId, highlighted, onSelect, theme }, ref
) {
  const element = useRef(null);
  const fgRef = useRef(null);
  const initialFit = useRef(false);
  const [size, setSize] = useState({ width: 640, height: 500 });
  const [hovered, setHovered] = useState('');
  const [webgl, setWebgl] = useState(true);
  const graphData = useMemo(() => ({
    nodes: nodes.map(n => ({ ...n })),
    links: edges.map(e => ({ ...e }))
  }), [nodes, edges]);
  const selectedId = selection?.kind === 'node' ? selection.id : '';
  const neighbors = useMemo(() => {
    const ids = new Set(selectedId ? [selectedId] : []);
    if (selectedId) edges.forEach(e => {
      if (e.source === selectedId) ids.add(e.target);
      if (e.target === selectedId) ids.add(e.source);
    });
    return ids;
  }, [edges, selectedId]);
  const pathNodes = useMemo(() => new Set(highlighted?.nodes || []), [highlighted]);
  const pathEdges = useMemo(() => new Set(highlighted?.edges || []), [highlighted]);
  useEffect(() => {
    if (!element.current) return;
    const observer = new ResizeObserver(entries => {
      const box = entries[0]?.contentRect;
      if (box) setSize({ width: Math.max(1, Math.round(box.width)),
                         height: Math.max(1, Math.round(box.height)) });
    });
    observer.observe(element.current);
    try {
      const canvas = document.createElement('canvas');
      setWebgl(Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl')));
    } catch { setWebgl(false); }
    return () => observer.disconnect();
  }, []);
  useEffect(() => { initialFit.current = false; }, [graphData]);
  const focus = useCallback(id => {
    const fg = fgRef.current;
    const node = graphData.nodes.find(n => n.id === id);
    if (!fg || !node || !Number.isFinite(node.x)) return;
    const distance = 105;
    const norm = Math.hypot(node.x, node.y, node.z) || 1;
    const ratio = 1 + distance / norm;
    fg.cameraPosition(
      { x: node.x * ratio, y: node.y * ratio, z: node.z * ratio },
      { x: node.x, y: node.y, z: node.z },
      window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 700
    );
  }, [graphData]);
  useEffect(() => { if (focusId) focus(focusId); }, [focusId, focus, graphData]);
  const fitView = useCallback((duration = 600) => {
    const fg = fgRef.current;
    if (!fg) return;
    const positioned = graphData.nodes.filter(n => [n.x, n.y, n.z].every(Number.isFinite));
    if (!positioned.length) return;
    const axes = ['x', 'y', 'z'];
    const bounds = Object.fromEntries(axes.map(axis => [axis, [
      Math.min(...positioned.map(n => n[axis])),
      Math.max(...positioned.map(n => n[axis]))
    ]]));
    const center = Object.fromEntries(axes.map(axis => [axis, (bounds[axis][0] + bounds[axis][1]) / 2]));
    const span = Math.max(...axes.map(axis => bounds[axis][1] - bounds[axis][0]), 55);
    const distance = Math.max(105, span * 1.40);
    fg.cameraPosition({
      x: center.x + distance * 0.10,
      y: center.y + distance * 0.07,
      z: center.z + distance
    }, center, duration);
  }, [graphData]);
  useEffect(() => {
    if (size.width < 2 || size.height < 2 || !graphData.nodes.length) return;
    const timer = window.setTimeout(() => {
      if (fgRef.current) { initialFit.current = true; fitView(800); }
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [graphData, size.width, size.height, fitView]);
  useEffect(() => {
    const controls = fgRef.current?.controls();
    if (controls) {
      controls.autoRotate = !selectedId;
      controls.autoRotateSpeed = 0.22;
    }
  }, [selectedId, graphData]);
  useImperativeHandle(ref, () => ({
    zoomIn: () => {
      const fg = fgRef.current;
      if (!fg) return;
      const camera = fg.camera();
      const target = fg.controls()?.target || { x: 0, y: 0, z: 0 };
      fg.cameraPosition({
        x: target.x + (camera.position.x - target.x) * 0.72,
        y: target.y + (camera.position.y - target.y) * 0.72,
        z: target.z + (camera.position.z - target.z) * 0.72
      }, target, 300);
    },
    zoomOut: () => {
      const fg = fgRef.current;
      if (!fg) return;
      const camera = fg.camera();
      const target = fg.controls()?.target || { x: 0, y: 0, z: 0 };
      fg.cameraPosition({
        x: target.x + (camera.position.x - target.x) * 1.38,
        y: target.y + (camera.position.y - target.y) * 1.38,
        z: target.z + (camera.position.z - target.z) * 1.38
      }, target, 300);
    },
    fit: () => fitView()
  }), [fitView]);

  if (!webgl) return <div className="canvas-message"><strong>浏览器未启用 WebGL</strong>
    <small>请开启硬件加速后刷新页面。左侧实体索引仍可查看来源与关系。</small></div>;
  return <div ref={element} className="force3d-canvas" role="img"
    aria-label="可拖动旋转、缩放和点击节点的三维知识图谱">
    <ForceGraph3D ref={fgRef} graphData={graphData}
      width={size.width} height={size.height}
      backgroundColor={theme === 'light' ? '#e8f2f8' : '#091a2b'} showNavInfo={false} controlType="orbit" numDimensions={3}
      nodeThreeObject={node => nodeObject(node, selectedId || hovered, neighbors,
                                        pathNodes.has(node.id), theme)}
      nodeLabel={() => ''}
      linkColor={link => {
        if (pathEdges.has(link.id)) return '#ffc77b';
        const source = typeof link.source === 'object' ? link.source.id : link.source;
        const target = typeof link.target === 'object' ? link.target.id : link.target;
        if (selectedId && source !== selectedId && target !== selectedId) return theme === 'light' ? '#c4d7e3' : '#1e3447';
        return link.status === 'approved' ? (theme === 'light' ? '#6695b4' : '#5b9ac4') : '#b68d5b';
      }}
      linkOpacity={0.68} linkWidth={link => pathEdges.has(link.id) ? 2.3 : 1}
      linkDirectionalParticles={link => pathEdges.has(link.id) ? 4 : 1}
      linkDirectionalParticleWidth={link => pathEdges.has(link.id) ? 2.8 : 1.3}
      linkDirectionalParticleSpeed={0.004}
      onNodeHover={node => setHovered(node?.id || '')}
      onNodeClick={node => { onSelect({ kind: 'node', id: node.id }); focus(node.id); }}
      onLinkClick={link => onSelect({ kind: 'edge', id: link.id })}
      onBackgroundClick={() => onSelect(null)}
      onEngineStop={() => {
        if (!initialFit.current && fgRef.current) {
          initialFit.current = true;
          fitView();
        }
      }}
      d3AlphaDecay={0.035} d3VelocityDecay={0.3}
      enableNodeDrag={false}
    />
  </div>;
});

export default GraphCanvas;






