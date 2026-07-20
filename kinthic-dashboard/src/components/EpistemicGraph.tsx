"use client";

import { useState, useEffect, useRef, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { apiFetch } from '@/lib/api';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

interface GraphNode {
  id: string;
  type: string;
  content: string;
  status: string;
  x?: number;
  y?: number;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export default function EpistemicGraph() {
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [neighborIds, setNeighborIds] = useState<Set<string>>(new Set());
  const graphRef = useRef<any>(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await apiFetch('/api/graph');
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const json = await res.json();
      
      setData({
        nodes: json.nodes.map((n: any) => ({ ...n, id: n.node_id })),
        links: json.edges.map((e: any) => ({
          source: e.source_node_id,
          target: e.target_node_id,
          type: e.relation_type,
        }))
      });
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Adjust physics for Obsidian-style space
  useEffect(() => {
    if (!loading && !error && graphRef.current) {
      graphRef.current.d3Force('charge').strength(-400);
      graphRef.current.d3Force('link').distance(100);
    }
  }, [loading, error]);

  // Track neighbors of hovered node
  const handleNodeHover = (node: any) => {
    setHoveredNode(node);
    const neighbors = new Set<string>();
    if (node) {
      neighbors.add(node.id);
      data.links.forEach((link) => {
        const srcId = typeof link.source === 'object' ? link.source.id : link.source;
        const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
        if (srcId === node.id) neighbors.add(tgtId);
        if (tgtId === node.id) neighbors.add(srcId);
      });
    }
    setNeighborIds(neighbors);
  };

  const getNodeColor = (node: GraphNode) => {
    if (node.type === 'concept') return '#4A89FF'; // Blue (Primary)
    if (node.type === 'entity') return '#a657d9'; // Purple
    if (node.type === 'hypothesis') return '#6a9bcc'; // Slate Blue
    if (node.type === 'principle') return '#e2b34a'; // Gold
    return '#788c5d'; // Sage (Fact)
  };

  if (loading) return <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[#4A89FF] text-sm font-display font-semibold tracking-widest uppercase animate-pulse">Initializing Topology...</div>;
  if (error) return <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[#3B66EB] text-sm font-display font-semibold bg-[#1e1e1e] px-4 py-2 rounded-full border border-border-strong">Backend Offline: {error}</div>;

  return (
    <div className="w-full h-full relative bg-[#0d0d0d]">
      {/* Legend */}
      <div className="absolute top-4 left-4 z-10 bg-[#161616]/80 backdrop-blur-md border border-border-subtle p-3 rounded-lg flex flex-col gap-2 pointer-events-none select-none">
        <span className="text-[10px] font-display font-bold text-text-secondary uppercase tracking-widest mb-1">Topology Legend</span>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#4A89FF] shadow-[0_0_6px_#3B66EB]" />
          <span className="text-xs text-text-primary">Concept</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#a657d9] shadow-[0_0_6px_#a657d9]" />
          <span className="text-xs text-text-primary">Entity</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#6a9bcc] shadow-[0_0_6px_#6a9bcc]" />
          <span className="text-xs text-text-primary">Hypothesis</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#e2b34a] shadow-[0_0_6px_#e2b34a]" />
          <span className="text-xs text-text-primary">Principle</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#788c5d] shadow-[0_0_6px_#788c5d]" />
          <span className="text-xs text-text-primary">Fact</span>
        </div>
      </div>

      <ForceGraph2D
        ref={graphRef}
        graphData={data}
        onNodeHover={handleNodeHover}
        nodeRelSize={5}
        // Draw custom circular nodes with glow and clean text labels
        nodeCanvasObject={(node: any, ctx: any, globalScale: number) => {
          const color = getNodeColor(node);
          const isHovered = hoveredNode?.id === node.id;
          const isNeighbor = neighborIds.has(node.id);
          const isFaded = hoveredNode !== null && !isNeighbor;

          // 1. Draw glowing background ring for hovered/neighbor nodes
          if (isHovered) {
            ctx.shadowColor = color;
            ctx.shadowBlur = 15;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI, false);
            ctx.fill();
            ctx.shadowBlur = 0; // reset
          } else if (isNeighbor) {
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.arc(node.x, node.y, 7, 0, 2 * Math.PI, false);
            ctx.stroke();
          }

          // 2. Draw core node dot
          ctx.fillStyle = isFaded ? 'rgba(80, 80, 80, 0.3)' : color;
          ctx.beginPath();
          ctx.arc(node.x, node.y, 5, 0, 2 * Math.PI, false);
          ctx.fill();

          // 3. Draw clean floating labels (scale-dependent or on hover)
          const shouldShowLabel = globalScale > 1.2 || isHovered || isNeighbor;
          if (shouldShowLabel) {
            const labelText = node.content.length > 30 
              ? node.content.substring(0, 30) + '...' 
              : node.content;

            const fontSize = 10 / globalScale;
            ctx.font = `${isHovered ? '700' : '500'} ${fontSize}px var(--font-serif), serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';

            // Text color logic
            if (isHovered) {
              ctx.fillStyle = '#ffffff';
            } else if (isFaded) {
              ctx.fillStyle = 'rgba(150, 150, 150, 0.2)';
            } else {
              ctx.fillStyle = 'rgba(230, 230, 230, 0.85)';
            }

            // Draw text shadow for contrast
            ctx.shadowColor = '#000000';
            ctx.shadowBlur = 4;
            ctx.fillText(labelText, node.x, node.y + 8);
            ctx.shadowBlur = 0; // reset
          }
        }}
        // Clean Obsidian-style links
        linkColor={(link: any) => {
          if (hoveredNode) {
            const srcId = typeof link.source === 'object' ? link.source.id : link.source;
            const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
            const isRelated = srcId === hoveredNode.id || tgtId === hoveredNode.id;
            return isRelated ? 'rgba(255, 255, 255, 0.35)' : 'rgba(255, 255, 255, 0.03)';
          }
          return 'rgba(255, 255, 255, 0.08)';
        }}
        linkWidth={(link: any) => {
          if (hoveredNode) {
            const srcId = typeof link.source === 'object' ? link.source.id : link.source;
            const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
            return srcId === hoveredNode.id || tgtId === hoveredNode.id ? 2 : 0.8;
          }
          return 1.2;
        }}
        // Obsidian-style thought particles flowing down paths
        linkDirectionalParticles={(link: any) => {
          if (hoveredNode) {
            const srcId = typeof link.source === 'object' ? link.source.id : link.source;
            const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
            return srcId === hoveredNode.id || tgtId === hoveredNode.id ? 4 : 0;
          }
          return 2;
        }}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleSpeed={0.006}
        linkDirectionalParticleColor={() => '#ffffff'}
        enableNodeDrag={true}
        enableZoomInteraction={true}
        enablePanInteraction={true}
      />
    </div>
  );
}
