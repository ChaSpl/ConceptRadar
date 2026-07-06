        let cy = null;
        let sandboxNode = null;
        let sandboxEdges = [];
        let breathingIntervalId = null;
        let activeDomainId = null;
        let activeCategoryId = null;
        let activeDomainName = "All Domains";
        let activeCategoryName = "";
        let isClickNavigating = false;
        
        // List-view State Globals
        let currentViewMode = "list"; // "list" or "map" or "quadrant-list"
        let sortColumn = "name";      // "name", "novelty", "validation", "momentum"
        let sortDirection = "asc";    // "asc" or "desc"
        let userOverrodeSort = false; // True when user manually clicks a column header
        let expandedDomains = {};     // Maps domainId -> boolean
        let globalGraphElements = []; // Cached copy of elements from /api/graph
        let updateZoomView = null;    // Globally accessible view updater
        let activeQuadrants = [];     // Array of active quadrant filters: "established", "frontier", "noise", "speculative"
        let scoutedCategoryIds = null; // Set of parent_category_ids containing newly scouted nodes (null = inactive)
        const QUADRANT_NODE_LIMIT = 30;
        let baseZoomLevel = 1.0;          // Zoom level at which positions were originally calculated
        let semanticZoomTimer = null;     // Debounce timer for semantic zoom recalculation
        let suppressSemanticZoom = false;  // True during programmatic camera animations
        let savedZoomPan = null;           // Saved zoom/pan state before card opens

        // Display toast notification
        function showToast(message, isGold=false, durationMs=15000) {
            const toast = document.getElementById("toast");
            toast.innerText = message;
            if (isGold) {
                toast.style.border = "1px solid #f59e0b";
                toast.style.boxShadow = "var(--neon-glow-gold)";
            } else {
                toast.style.border = "1px solid #3b82f6";
                toast.style.boxShadow = "var(--neon-glow-blue)";
            }
            toast.classList.add("show");
            if (window.toastTimeout) clearTimeout(window.toastTimeout);
            window.toastTimeout = setTimeout(() => {
                toast.classList.remove("show");
            }, durationMs);
        }

        // Persistent error toast — stays until user explicitly dismisses via × button
        function showErrorBanner(message) {
            // Remove any existing error toast first
            const existing = document.getElementById("error-banner");
            if (existing) existing.remove();

            const toast = document.createElement("div");
            toast.id = "error-banner";
            toast.style.cssText = `
                position: fixed; bottom: 24px; left: 24px; z-index: 10000;
                max-width: 420px; min-width: 280px;
                background: linear-gradient(135deg, #1a0505, #2a0a0a);
                border: 1px solid rgba(239, 68, 68, 0.5);
                border-radius: 12px; color: #fecaca;
                padding: 14px 42px 14px 16px;
                font-family: 'Inter', sans-serif; font-size: 0.82rem; font-weight: 500;
                line-height: 1.5;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5), 0 0 15px rgba(239, 68, 68, 0.2);
                backdrop-filter: blur(12px);
                animation: slideUp 0.3s ease;
            `;
            toast.innerHTML = `
                <span style="margin-right: 6px; font-size: 1rem;">⚠️</span>
                ${message}
                <button onclick="dismissErrorBanner()" style="
                    position: absolute; top: 8px; right: 8px;
                    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
                    color: #fca5a5; font-size: 1.1rem; cursor: pointer;
                    line-height: 1; padding: 2px 7px; border-radius: 6px;
                    transition: all 0.2s;
                " onmouseover="this.style.background='rgba(255,255,255,0.15)'"
                   onmouseout="this.style.background='rgba(255,255,255,0.06)'">&times;</button>
            `;
            document.body.appendChild(toast);
        }

        function dismissErrorBanner() {
            const banner = document.getElementById("error-banner");
            if (banner) {
                banner.style.animation = "slideDown 0.25s ease forwards";
                banner.style.opacity = "0";
                banner.style.transform = "translateY(20px)";
                banner.style.transition = "opacity 0.25s, transform 0.25s";
                setTimeout(() => banner.remove(), 250);
            }
        }

        // Show/Hide loader
        function setLoader(show, text="Agent scouting...") {
            const loader = document.getElementById("loader-overlay");
            const loaderText = document.getElementById("loader-text");
            loaderText.innerHTML = text;
            if (show) {
                loader.classList.add("active");
            } else {
                loader.classList.remove("active");
            }
        }

        // Card-aware camera viewport reframing (balanced Goldilocks zoom)
        function refitCameraViewport(isCardOpen = false) {
            if (!cy || currentViewMode !== "map") return;
            
            let fitEles = null;
            if (activeQuadrants.length > 0) {
                fitEles = cy.nodes().filter(n => {
                    if (n.data('is_cluster_bubble')) return false;
                    const nov = (n.data('novelty') !== undefined && n.data('novelty') !== null) ? parseFloat(n.data('novelty')) : 0.5;
                    const val = (n.data('validation') !== undefined && n.data('validation') !== null) ? parseFloat(n.data('validation')) : 0.5;
                    
                    let matches = false;
                    activeQuadrants.forEach(aq => {
                        if (aq === 'established' && nov < 0.5 && val >= 0.5) matches = true;
                        if (aq === 'frontier' && nov >= 0.5 && val >= 0.5) matches = true;
                        if (aq === 'noise' && nov < 0.5 && val < 0.5) matches = true;
                        if (aq === 'speculative' && nov >= 0.5 && val < 0.5) matches = true;
                    });
                    return matches;
                });
            } else if (activeCategoryId) {
                fitEles = cy.nodes().filter(n => !n.data('is_cluster_bubble') && n.data('parent_category_id') === activeCategoryId);
            } else {
                fitEles = cy.nodes().filter(n => !n.data('is_cluster_bubble'));
            }

            if (fitEles && fitEles.length > 0) {
                const padRight = isCardOpen ? 440 : 80;
                const padLeft = 80;
                const padTop = 80;
                const padBottom = 80;
                
                const bb = fitEles.boundingBox();
                const w = cy.width();
                const h = cy.height();
                
                const clearW = Math.max(100, w - (padLeft + padRight));
                const clearH = Math.max(100, h - (padTop + padBottom));
                
                const bbW = Math.max(80, bb.w);
                const bbH = Math.max(80, bb.h);
                
                let targetZoom = Math.min(clearW / bbW, clearH / bbH) * 0.95;
                
                // Keep zoom in a comfortable range (min 0.65, max 1.15)
                targetZoom = Math.max(0.65, Math.min(targetZoom, 1.15));
                
                const bbCenterX = (bb.x1 + bb.x2) / 2;
                const bbCenterY = (bb.y1 + bb.y2) / 2;
                
                const targetCenterX = padLeft + clearW / 2;
                const targetCenterY = padTop + clearH / 2;
                
                const panX = targetCenterX - bbCenterX * targetZoom;
                const panY = targetCenterY - bbCenterY * targetZoom;
                
                // Save current viewport before adjusting for card
                if (isCardOpen) {
                    savedZoomPan = { zoom: cy.zoom(), pan: { ...cy.pan() } };
                }
                suppressSemanticZoom = true;
                cy.animate({
                    zoom: targetZoom,
                    pan: { x: panX, y: panY },
                    duration: 600,
                    easing: 'ease-out-cubic',
                    complete: function() { suppressSemanticZoom = false; }
                });
            }
        }

        // Navigate to newly ingested nodes: switch to map mode showing their parent categories
        // allScoutedIds: Set of all related node IDs (from server response).
        // trulyNewIds: Set of genuinely new inserts (subset of allScoutedIds). Orange highlight.
        // Remaining allScoutedIds get rose context highlight. Category siblings also get context.
        function navigateToNewNodes(allScoutedIds, trulyNewIds) {
            if (!cy) return;
            closeDetails(); // Clear any open detail card before showing scout results
            
            // Default trulyNewIds to allScoutedIds for backward compat
            if (!trulyNewIds) trulyNewIds = allScoutedIds;
            
            let targetNodes;
            if (allScoutedIds && allScoutedIds.size > 0) {
                // Find all scouted nodes in Cytoscape
                targetNodes = cy.nodes().filter(n => allScoutedIds.has(n.id()) && !n.data('is_cluster_bubble'));
                
                console.log(`[Scout Nav] Requested ${allScoutedIds.size} IDs (${trulyNewIds.size} new), found ${targetNodes.length} in Cytoscape`);
                if (targetNodes.length < allScoutedIds.size) {
                    const foundIds = new Set();
                    targetNodes.forEach(n => foundIds.add(n.id()));
                    const missing = [...allScoutedIds].filter(id => !foundIds.has(id));
                    console.log(`[Scout Nav] Missing IDs:`, missing);
                }
                
                // Clear ALL is_new and is_context flags first
                cy.nodes().forEach(n => {
                    n.data('is_new', false);
                    n.data('is_context', false);
                });
                
                // Three-tier visual marking:
                // 1. Truly new discoveries → is_new (orange breathing)
                // 2. Scouted/related but already existed → is_context (rose breathing) 
                // 3. Category siblings → visible but static (no animation, controlled by scoutedCategoryIds)
                targetNodes.forEach(n => {
                    if (trulyNewIds && trulyNewIds.size > 0 && trulyNewIds.has(n.id())) {
                        n.data('is_new', true);
                    } else {
                        n.data('is_context', true);
                    }
                });
            } else {
                // Fallback: use time-based is_new flag
                targetNodes = cy.nodes().filter(n => n.data('is_new') === true && !n.data('is_cluster_bubble'));
            }
            
            if (targetNodes.length === 0) return;
            
            // Collect categories ONLY from truly new nodes (not all scouted)
            // This prevents broad topics from expanding to 200+ nodes across many categories
            const catIds = new Set();
            targetNodes.forEach(n => {
                if (trulyNewIds && trulyNewIds.has(n.id())) {
                    const pcid = n.data('parent_category_id');
                    if (pcid) {
                        catIds.add(pcid);
                    } else {
                        console.warn(`[Scout Nav] Node ${n.id()} has no parent_category_id`);
                    }
                }
            });
            
            console.log(`[Scout Nav] Categories to show:`, [...catIds]);
            
            // NOTE: Category siblings are made visible via scoutedCategoryIds in updateZoomView
            // but are NOT marked is_context, so they don't breathe. Only target nodes animate.
            
            // Set category-scoped filter (drives visibility in updateZoomView)
            // If no truly new nodes, use sentinel to show ONLY directly matched nodes (no category expansion)
            scoutedCategoryIds = catIds.size > 0 ? catIds : new Set(['__direct_only__']);
            activeQuadrants = [];
            activeCategoryId = null;
            activeDomainId = null;
            currentViewMode = "map";
            
            // Show map, hide lists
            document.getElementById("cy").style.display = "block";
            document.getElementById("list-container").style.display = "none";
            const qc = document.getElementById("quadrant-container");
            if (qc) qc.style.display = "none";
            
            if (cy) cy.resize();
            // Reposition all nodes using actual container dimensions (container was likely hidden during renderGraph)
            window.dispatchEvent(new Event('resize'));
            if (updateZoomView) updateZoomView();
            renderListView();
            
            // Fit camera to all visible nodes (new + context siblings)
            setTimeout(() => {
                if (cy) {
                    cy.resize();
                    if (updateZoomView) updateZoomView();
                    const visibleNodes = cy.nodes().filter(n => n.style('display') === 'element' && !n.data('is_cluster_bubble'));
                    const newVisibleCount = visibleNodes.filter(n => n.data('is_new') === true).length;
                    const ctxVisibleCount = visibleNodes.filter(n => n.data('is_context') === true).length;
                    console.log(`[Scout Nav] Camera fit: ${visibleNodes.length} visible nodes (${newVisibleCount} new, ${ctxVisibleCount} context)`);
                    if (visibleNodes.length > 0) {
                        cy.fit(visibleNodes, 80);
                        // Cap zoom to avoid extreme close-up when few nodes
                        if (cy.zoom() > 1.5) {
                            cy.zoom(1.3);
                            cy.center(visibleNodes);
                        }
                        console.log(`[Scout Nav] Camera zoom after fit: ${cy.zoom().toFixed(3)}`);
                    }
                }
            }, 300);
        }

        // Close details panel & restore previous viewport
        function closeDetails() {
            document.getElementById("details-panel").classList.remove("open");
            if (savedZoomPan && cy) {
                suppressSemanticZoom = true;
                cy.animate({
                    zoom: savedZoomPan.zoom,
                    pan: savedZoomPan.pan,
                    duration: 400,
                    easing: 'ease-out-cubic',
                    complete: function() { suppressSemanticZoom = false; }
                });
                savedZoomPan = null;
            } else {
                refitCameraViewport(false);
            }
        }

        // Auto-close details card when user focuses any input field in the sidebar
        document.addEventListener("focusin", function(e) {
            const el = e.target;
            if ((el.tagName === "INPUT" || el.tagName === "TEXTAREA") &&
                el.closest(".sidebar")) {
                closeDetails();
            }
        });

        // Open details panel & shift camera to clear sidebar overlay
        function openDetails() {
            document.getElementById("details-panel").classList.add("open");
            refitCameraViewport(true);
        }

        // Lightweight Markdown parser to handle links, bold, bullet points, headers, and line breaks
        function parseMarkdown(text) {
            if (!text) return "";
            let html = text
                // Escape HTML tags to prevent XSS
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");
                
            // Markdown Links: [text](url) -> <a> tag
            html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" style="color: #818cf8; text-decoration: underline; font-weight: 500;">$1</a>');
            
            // Auto-link bare URLs (not already inside an href or <a> tag)
            html = html.replace(/(^|[^"=])(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" style="color: #818cf8; text-decoration: underline;">$2</a>');
            
            // Bold text **bold**
            html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
            
            // Horizontal rule (--- or ___)
            html = html.replace(/^\s*[-_]{3,}\s*$/gm, "<hr style='border: none; border-top: 1px solid rgba(255,255,255,0.1); margin: 0.6rem 0;'>");
            
            // Bullet list items (starting with - or *)
            html = html.replace(/^\s*[-*]\s+(.*?)$/gm, "<li>$1</li>");
            
            // Headers
            html = html.replace(/^\s*###\s+(.*?)$/gm, "<h4 style='margin-top: 0.6rem; margin-bottom: 0.3rem; font-weight: 700; color: #a78bfa;'>$1</h4>");
            html = html.replace(/^\s*##\s+(.*?)$/gm, "<h3 style='margin-top: 0.8rem; margin-bottom: 0.4rem; font-weight: 700; color: #fbbf24;'>$1</h3>");
            
            // Line breaks
            html = html.replace(/\n/g, "<br>");
            
            return html;
        }

        // Clear Sandbox Node session variable
        function clearSandboxIdea() {
            sandboxNode = null;
            sandboxEdges = [];
            
            // Clear input fields
            document.getElementById("sandbox-title").value = "";
            document.getElementById("sandbox-summary").value = "";
            document.getElementById("sandbox-attribute-check").checked = false;
            document.getElementById("sandbox-author-name").value = "";
            document.getElementById("sandbox-author-linkedin").value = "";
            document.getElementById("sandbox-author-email").value = "";
            document.getElementById("sandbox-attribution-fields").style.display = "none";
            
            // Toggle action buttons visibility
            document.getElementById("sandbox-initial-actions").style.display = "block";
            document.getElementById("sandbox-active-actions").style.display = "none";
            
            closeDetails();
            loadGraphData();
            showToast("Sandbox idea deleted. Zero trace left on server.");
        }

        // Fetch graph elements from backend
        async function fetchGraphElements() {
            try {
                const response = await fetch("/api/graph");
                return await response.json();
            } catch (err) {
                console.error("Error fetching graph data:", err);
                return [];
            }
        }

        // Map novelty and validation scores to coordinates
        function getCoordinates(novelty, validation, containerWidth, containerHeight) {
            let nov = parseFloat(novelty);
            let val = parseFloat(validation);
            if (isNaN(nov)) nov = 0.5;
            if (isNaN(val)) val = 0.5;
            
            const paddingX = 80;
            const paddingY = 80;
            const w = containerWidth - paddingX * 2;
            const h = containerHeight - paddingY * 2;
            
            const x = paddingX + (nov * w);
            // In screen coordinates Y=0 is TOP, so we must invert validation (Y = 1.0 - validation)
            const y = paddingY + ((1.0 - val) * h);
            
            return { x, y };
        }

        // Semantic Zoom: Spread overlapping nodes apart proportionally to zoom level.
        // Like Google Maps — zooming in reveals individual items that were stacked at overview zoom.
        function spreadNodesOnZoom() {
            if (!cy) return;
            if (currentViewMode !== 'map') return;
            if (suppressSemanticZoom) return;
            
            const zoom = cy.zoom();
            const container = document.getElementById('cy');
            const w = container.offsetWidth;
            const h = container.offsetHeight;
            if (w === 0 || h === 0) { console.log('[SemanticZoom] Container has no size'); return; }

            // Collect all leaf nodes with stored true positions
            const leafNodes = [];
            cy.nodes().forEach(n => {
                if (n.data('is_cluster_bubble') || n.data('is_domain_bubble')) return;
                if (n.data('trueX') === undefined || n.data('trueX') === null) return;
                // Check visibility: hidden nodes have display 'none'
                if (n.hidden()) return;
                leafNodes.push(n);
            });
            
            console.log(`[SemanticZoom] zoom=${zoom.toFixed(3)}, base=${baseZoomLevel.toFixed(3)}, leafNodes=${leafNodes.length}`);
            if (leafNodes.length < 2) return;

            // Scale factor: how much more to spread compared to base zoom
            const rawFactor = zoom / baseZoomLevel;
            const spreadFactor = Math.max(1.3, Math.sqrt(rawFactor));
            
            // Maximum pixels a node can move from its true position (grows gently with zoom)
            const maxDisplacement = 8 + spreadFactor * 10;

            // Build working array starting from true positions
            const items = leafNodes.map(n => {
                const mom = (n.data('momentum') !== undefined && n.data('momentum') !== null) ? parseFloat(n.data('momentum')) : 0.2;
                // Collision radius grows gently with zoom (sqrt scaling)
                const baseRadius = 5 + mom * 9;
                return {
                    node: n,
                    x: n.data('trueX'),
                    y: n.data('trueY'),
                    trueX: n.data('trueX'),
                    trueY: n.data('trueY'),
                    radius: baseRadius * spreadFactor,
                    nov: parseFloat(n.data('novelty')) || 0.5,
                    val: parseFloat(n.data('validation')) || 0.5
                };
            });

            // Run pairwise repulsion with zoom-scaled radii (fewer iterations = calmer)
            const iterations = Math.min(3, Math.ceil(spreadFactor));
            for (let iter = 0; iter < iterations; iter++) {
                for (let i = 0; i < items.length; i++) {
                    for (let j = i + 1; j < items.length; j++) {
                        const a = items[i], b = items[j];
                        const dx = b.x - a.x;
                        const dy = b.y - a.y;
                        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
                        const minDist = a.radius + b.radius + 3;
                        if (dist < minDist) {
                            const overlap = (minDist - dist) / 2;
                            const nx = dx / dist, ny = dy / dist;
                            a.x -= nx * overlap;
                            a.y -= ny * overlap;
                            b.x += nx * overlap;
                            b.y += ny * overlap;
                        }
                    }
                }
            }

            // Limit displacement from true position — keeps nodes close to home
            const midX = w / 2, midY = h / 2;
            items.forEach(({ node, x, y, trueX, trueY, nov, val }) => {
                let dx = x - trueX;
                let dy = y - trueY;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist > maxDisplacement) {
                    const scale = maxDisplacement / dist;
                    dx *= scale;
                    dy *= scale;
                }
                let finalX = trueX + dx;
                let finalY = trueY + dy;

                // Enforce quadrant boundaries — nodes must stay in their quadrant
                if (nov < 0.5) {
                    finalX = Math.min(finalX, midX - 2);
                } else {
                    finalX = Math.max(finalX, midX + 2);
                }
                if (val >= 0.5) {
                    finalY = Math.min(finalY, midY - 2);
                } else {
                    finalY = Math.max(finalY, midY + 2);
                }

                node.stop();
                node.unlock();
                node.animate({ position: { x: finalX, y: finalY } }, { 
                    duration: 350, 
                    easing: 'ease-out-cubic',
                    complete: function() { node.lock(); }
                });
            });
        }

        // Simple hash function to generate stable, vibrant HSL colors for clusters
        function getClusterColor(clusterId) {
            if (!clusterId) return '#cbd5e1'; // Fallback neutral slate for unclassified nodes
            
            let hash = 0;
            for (let i = 0; i < clusterId.length; i++) {
                hash = clusterId.charCodeAt(i) + ((hash << 5) - hash);
            }
            
            // Generate a hue between 0 and 360
            const hue = Math.abs(hash % 360);
            
            // Saturation 80%, Lightness 62% for bright visual aesthetics on dark backgrounds
            return `hsl(${hue}, 80%, 62%)`;
        }

        // Reset all filters and reload the full graph
        async function resetToFullMap() {
            closeDetails();
            scoutedCategoryIds = null;
            activeQuadrants = [];
            activeCategoryId = null;
            activeDomainId = null;
            activeDomainName = "All Domains";
            activeCategoryName = "";
            expandedDomains = {};
            await loadGraphData();
        }

        // Render Cytoscape Graph
        async function loadGraphData(resetCamera = false, preserveSelection = false) {
          try {
            const selectedNodes = cy ? cy.nodes(':selected') : null;
            const selectedNode = (selectedNodes && selectedNodes.length > 0) ? selectedNodes.filter(n => !n.data('is_cluster_bubble'))[0] : null;
            const selectedId = selectedNode ? selectedNode.id() : null;

            if (!preserveSelection) {
                closeDetails(); // Close node details sidebar before refreshing
            }
            
            const elements = await fetchGraphElements();
            globalGraphElements = elements;
            
            renderGraph(elements);
            
            if (resetCamera) {
                activeDomainId = null;
                activeCategoryId = null;
                activeDomainName = "All Domains";
                activeCategoryName = "";
                activeQuadrants = []; // Clear active quadrant filters on reset
                scoutedCategoryIds = null; // Clear scout category filter
                currentViewMode = "list"; // Default to list mode on load/reset
                expandedDomains = {};
                
                const cyContainer = document.getElementById("cy");
                const listContainer = document.getElementById("list-container");
                const conceptListContainer = document.getElementById("quadrant-container");
                
                if (cyContainer) cyContainer.style.display = "none";
                if (conceptListContainer) conceptListContainer.style.display = "none";
                if (listContainer) listContainer.style.display = "block";
            }
            
            renderListView();
            if (updateZoomView) updateZoomView();
            
            // Re-select the preserved node if applicable
            if (preserveSelection && selectedId) {
                setTimeout(() => {
                    const targetNode = cy.getElementById(selectedId);
                    if (targetNode.length > 0) {
                        targetNode.select();
                        displayNodeDetails(targetNode.data());
                    }
                }, 100);
            }
            
            // Dispatch a manual resize to ensure nodes are positioned using visible container dimensions
            window.dispatchEvent(new Event('resize'));
          } catch (err) {
              console.error("[ConceptRadar] loadGraphData error:", err);
              // Emergency fallback: ensure list view is visible even on crash
              currentViewMode = "list";
              const lc = document.getElementById("list-container");
              if (lc) lc.style.display = "block";
              renderListView();
          }
        }

        // Aggregate Domain and Category Metrics dynamically from document nodes
        function getAggregatedMetrics() {
            const domains = {};
            const categories = {};
            
            if (!globalGraphElements || !Array.isArray(globalGraphElements)) {
                return { domains: [], categories: {} };
            }
            
            // Extract bubbles and leaf nodes from cached elements
            const l1Bubbles = globalGraphElements.filter(el => el.group === "nodes" && el.data.is_domain_bubble);
            const l2Bubbles = globalGraphElements.filter(el => el.group === "nodes" && el.data.is_cluster_bubble);
            const leafNodes = globalGraphElements.filter(el => el.group === "nodes" && !el.data.is_cluster_bubble && !el.data.is_domain_bubble);
            
            // Initialize domains map
            l1Bubbles.forEach(d => {
                domains[d.data.id] = {
                    id: d.data.id,
                    name: d.data.label,
                    sumNovelty: 0,
                    sumValidation: 0,
                    sumMomentum: 0,
                    sumReach: 0,
                    count: 0,
                    categories: []
                };
            });
            
            // Initialize categories map
            l2Bubbles.forEach(c => {
                categories[c.data.id] = {
                    id: c.data.id,
                    name: c.data.label,
                    parentId: c.data.parent_domain_id,
                    sumNovelty: 0,
                    sumValidation: 0,
                    sumMomentum: 0,
                    sumReach: 0,
                    count: 0
                };
                
                // Link category to its parent domain
                if (domains[c.data.parent_domain_id]) {
                    domains[c.data.parent_domain_id].categories.push(c.data.id);
                }
            });
            
            // Aggregate metrics from Level 3 document nodes
            leafNodes.forEach(node => {
                const l3_nov = (node.data.novelty !== undefined && node.data.novelty !== null) ? parseFloat(node.data.novelty) : 0.5;
                const l3_val = (node.data.validation !== undefined && node.data.validation !== null) ? parseFloat(node.data.validation) : 0.5;
                const l3_mom = (node.data.momentum !== undefined && node.data.momentum !== null) ? parseFloat(node.data.momentum) : 0.5;
                const l3_reach = (node.data.reach !== undefined && node.data.reach !== null) ? parseFloat(node.data.reach) : 0.0;
                const catId = node.data.parent_category_id;
                // Derive domain_id from the category's parent
                const cat = categories[catId];
                const domId = cat ? cat.parentId : null;
                
                if (catId && categories[catId]) {
                    categories[catId].sumNovelty += l3_nov;
                    categories[catId].sumValidation += l3_val;
                    categories[catId].sumMomentum += l3_mom;
                    categories[catId].sumReach += l3_reach;
                    categories[catId].count += 1;
                }
                
                if (domId && domains[domId]) {
                    domains[domId].sumNovelty += l3_nov;
                    domains[domId].sumValidation += l3_val;
                    domains[domId].sumMomentum += l3_mom;
                    domains[domId].sumReach += l3_reach;
                    domains[domId].count += 1;
                }
            });
            
            // Finalize calculations
            const finalDomains = Object.values(domains).map(d => {
                const count = d.count || 1;
                return {
                    id: d.id,
                    name: d.name,
                    novelty: d.sumNovelty / count,
                    validation: d.sumValidation / count,
                    momentum: d.sumMomentum / count,
                    reach: d.sumReach / count,
                    count: d.count,
                    categoryIds: d.categories
                };
            });
            
            const finalCategories = {};
            Object.values(categories).forEach(c => {
                const count = c.count || 1;
                finalCategories[c.id] = {
                    id: c.id,
                    name: c.name,
                    parentId: c.parentId,
                    novelty: c.sumNovelty / count,
                    validation: c.sumValidation / count,
                    momentum: c.sumMomentum / count,
                    reach: c.sumReach / count,
                    count: c.count
                };
            });
            
            return { domains: finalDomains, categories: finalCategories };
        }

        // Render L1 and L2 expandable lists
        function renderListView() {
            const listContainer = document.getElementById("list-container");
            const listTableWrapper = document.getElementById("list-table-wrapper");
            
            if (currentViewMode !== "list") {
                listContainer.style.display = "none";
                return;
            }
            
            // Show list container
            listContainer.style.display = "block";
            
            // Reset title headers
            const titleHeader = listContainer.querySelector("h2");
            const subTitle = listContainer.querySelector("p");
            if (titleHeader) titleHeader.innerText = "Research Domains & Categories";
            if (subTitle) subTitle.innerText = "Click on a Domain to expand its Categories. Click on a Category to view its Topic Map Radar.";
            
            // Retrieve computed metrics
            const { domains, categories } = getAggregatedMetrics();
            
            // Sort domains
            domains.sort((a, b) => {
                let valA = a[sortColumn];
                let valB = b[sortColumn];
                
                if (sortColumn === "name") {
                    valA = a.name.toLowerCase();
                    valB = b.name.toLowerCase();
                }
                
                if (valA < valB) return sortDirection === "asc" ? -1 : 1;
                if (valA > valB) return sortDirection === "asc" ? 1 : -1;
                return 0;
            });
            
            let html = `
                <table class="radar-table">
                    <thead>
                        <tr>
                            <th onclick="toggleSort('name')" class="${sortColumn === 'name' ? (sortDirection === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">Domain / Category</th>
                            <th onclick="toggleSort('novelty')" class="${sortColumn === 'novelty' ? (sortDirection === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="width: 15%; text-align: center;">Novelty</th>
                            <th onclick="toggleSort('validation')" class="${sortColumn === 'validation' ? (sortDirection === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="width: 15%; text-align: center;">Validation</th>
                            <th onclick="toggleSort('momentum')" class="${sortColumn === 'momentum' ? (sortDirection === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="width: 13%; text-align: center;">Momentum</th>
                            <th onclick="toggleSort('reach')" class="${sortColumn === 'reach' ? (sortDirection === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="width: 13%; text-align: center;">Reach</th>
                            <th style="width: 8%; text-align: center;">Docs</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            if (domains.length === 0) {
                html += `
                    <tr>
                        <td colspan="6" style="text-align: center; padding: 30px; color: var(--text-secondary);">
                            No data available. Scout research topics to populate the map.
                        </td>
                    </tr>
                `;
            }
            
            domains.forEach(d => {
                // Expand domains by default so all topics are visible immediately
                // Domains start collapsed; user clicks chevron to expand
                const isExpanded = expandedDomains[d.id] === true;
                
                html += `
                    <tr class="row-domain ${isExpanded ? 'row-expanded' : ''}" onclick="toggleDomainExpand('${d.id}', event)">
                        <td>
                            <span class="chevron-icon">&#9654;</span>
                            ${d.name}
                        </td>
                        <td style="text-align: center;">
                            <span class="metric-badge" style="background: rgba(167, 139, 250, 0.15); color: #c084fc; border: 1px solid rgba(167, 139, 250, 0.3);">
                                ${d.novelty.toFixed(2)}
                            </span>
                        </td>
                        <td style="text-align: center;">
                            <span class="metric-badge" style="background: rgba(96, 165, 250, 0.15); color: #60a5fa; border: 1px solid rgba(96, 165, 250, 0.3);">
                                ${d.validation.toFixed(2)}
                            </span>
                        </td>
                        <td style="text-align: center;">
                            <span class="metric-badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3);">
                                ${d.momentum.toFixed(2)}
                            </span>
                        </td>
                        <td style="text-align: center;">
                            <span class="metric-badge" style="background: rgba(45, 212, 191, 0.15); color: #2dd4bf; border: 1px solid rgba(45, 212, 191, 0.3);">
                                ${d.reach.toFixed(2)}
                            </span>
                        </td>
                        <td style="text-align: center; color: var(--text-secondary); font-weight: 700;">
                            ${d.count}
                        </td>
                    </tr>
                `;
                
                if (isExpanded) {
                    const childCats = d.categoryIds.map(id => categories[id]).filter(Boolean);
                    
                    childCats.sort((a, b) => {
                        let valA = a[sortColumn];
                        let valB = b[sortColumn];
                        
                        if (sortColumn === "name") {
                            valA = a.name.toLowerCase();
                            valB = b.name.toLowerCase();
                        }
                        
                        if (valA < valB) return sortDirection === "asc" ? -1 : 1;
                        if (valA > valB) return sortDirection === "asc" ? 1 : -1;
                        return 0;
                    });
                    
                    if (childCats.length === 0) {
                        html += `
                            <tr class="row-category">
                                <td colspan="6" class="nested-category-cell" style="font-style: italic; color: var(--text-secondary); cursor: default;">
                                    No categories in this domain.
                                </td>
                            </tr>
                        `;
                    }
                    
                    childCats.forEach(c => {
                        html += `
                            <tr class="row-category" onclick="drillDownToCategoryMap('${d.id}', '${d.name}', '${c.id}', '${c.name}', event)">
                                <td class="nested-category-cell">
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right: 8px; vertical-align: middle;"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
                                    ${c.name}
                                </td>
                                <td style="text-align: center;">
                                    <span class="metric-badge" style="background: rgba(167, 139, 250, 0.1); color: #d8b4fe;">
                                        ${c.novelty.toFixed(2)}
                                    </span>
                                </td>
                                <td style="text-align: center;">
                                    <span class="metric-badge" style="background: rgba(96, 165, 250, 0.1); color: #93c5fd;">
                                        ${c.validation.toFixed(2)}
                                    </span>
                                </td>
                                <td style="text-align: center;">
                                    <span class="metric-badge" style="background: rgba(245, 158, 11, 0.1); color: #fde047;">
                                        ${c.momentum.toFixed(2)}
                                    </span>
                                </td>
                                <td style="text-align: center;">
                                    <span class="metric-badge" style="background: rgba(45, 212, 191, 0.1); color: #5eead4;">
                                        ${c.reach.toFixed(2)}
                                    </span>
                                </td>
                                <td style="text-align: center; color: var(--text-secondary);">
                                    ${c.count}
                                </td>
                            </tr>
                        `;
                    });
                }
            });
            
            html += `
                    </tbody>
                </table>
            `;
            
            listTableWrapper.innerHTML = html;
        }

        // Toggle sort columns
        function toggleSort(column) {
            userOverrodeSort = true; // User explicitly chose a sort
            if (sortColumn === column) {
                sortDirection = sortDirection === "asc" ? "desc" : "asc";
            } else {
                sortColumn = column;
                sortDirection = "desc";
            }
            if (currentViewMode === "quadrant-list") {
                renderConceptListView();
            } else {
                renderListView();
            }
        }

        // Helper to extract all document nodes belonging to active quadrants from global elements
        function getQuadrantNodes(quads) {
            if (!globalGraphElements || !quads || quads.length === 0) return [];
            
            const leafNodes = globalGraphElements.filter(el => el.group === "nodes" && !el.data.is_cluster_bubble && !el.data.is_domain_bubble);
            if (sandboxNode) {
                leafNodes.push(sandboxNode);
            }
            
            return leafNodes.filter(node => {
                const nov = (node.data.novelty !== undefined && node.data.novelty !== null) ? parseFloat(node.data.novelty) : 0.5;
                const val = (node.data.validation !== undefined && node.data.validation !== null) ? parseFloat(node.data.validation) : 0.5;
                
                let matches = false;
                quads.forEach(q => {
                    if (q === 'established' && nov < 0.5 && val >= 0.5) matches = true;
                    if (q === 'frontier' && nov >= 0.5 && val >= 0.5) matches = true;
                    if (q === 'noise' && nov < 0.5 && val < 0.5) matches = true;
                    if (q === 'speculative' && nov >= 0.5 && val < 0.5) matches = true;
                });
                return matches;
            });
        }

        // Switch View Mode between Map Radar Graph and Tabular Concept List
        async function switchQuadrantViewMode(mode) {
            closeDetails();
            currentViewMode = mode;
            if (mode === "map") {
                renderListView();
                renderConceptListView();
                document.getElementById("cy").style.display = "block";
                await loadGraphData(false, true);
                if (cy) {
                    cy.resize();
                    window.dispatchEvent(new Event('resize'));
                }
            } else {
                renderListView();
                renderConceptListView();
            }
            if (updateZoomView) updateZoomView();
        }
        function getQuadrantsLabel(quads) {
            if (!quads || quads.length === 0) return "No Quadrant Selected";
            if (quads.length === 4) return "All Quadrants Density Overview";
            
            const labels = [];
            quads.forEach(q => {
                if (q === 'established') labels.push("Established Field");
                else if (q === 'frontier') labels.push("New Frontier");
                else if (q === 'noise') labels.push("Noise/Hype");
                else if (q === 'speculative') labels.push("Speculative Opportunity");
            });
            
            if (labels.length === 1) return labels[0];
            if (labels.length === 2) return `${labels[0]} & ${labels[1]}`;
            return `${labels.slice(0, -1).join(', ')} & ${labels[labels.length - 1]}`;
        }

        // Display details panel by node ID to avoid HTML JSON escaping issues
        function displayNodeDetailsById(nodeId) {
            let node = null;
            if (cy) {
                const cyNode = cy.getElementById(nodeId);
                if (cyNode && cyNode.length > 0) {
                    node = cyNode.data();
                }
            }
            if (!node && globalGraphElements) {
                const found = globalGraphElements.find(el => el.group === "nodes" && el.data.id === nodeId);
                if (found) node = found.data;
            }
            if (!node && sandboxNode && sandboxNode.data.id === nodeId) {
                node = sandboxNode.data;
            }
            
            if (node) {
                displayNodeDetails(node);
            }
        }

        // Helper to extract all document nodes belonging to a category
        function getCategoryNodes(categoryId) {
            if (!globalGraphElements) return [];
            
            const leafNodes = globalGraphElements.filter(el => el.group === "nodes" && !el.data.is_cluster_bubble && !el.data.is_domain_bubble);
            if (sandboxNode) {
                leafNodes.push(sandboxNode);
            }
            
            return leafNodes.filter(node => node.data.parent_category_id === categoryId);
        }

        // Render a flat, sortable table for quadrant or category concept explorer
        function renderConceptListView() {
            const listContainer = document.getElementById("list-container");
            const listTableWrapper = document.getElementById("list-table-wrapper");
            
            if (currentViewMode !== "quadrant-list") {
                listContainer.style.display = "none";
                return;
            }
            
            listContainer.style.display = "block";
            
            let nodes = [];
            let listTitle = "Concept Explorer";
            
            if (activeQuadrants.length > 0) {
                nodes = getQuadrantNodes(activeQuadrants);
                listTitle = getQuadrantsLabel(activeQuadrants);
            } else if (activeCategoryId) {
                nodes = getCategoryNodes(activeCategoryId);
                listTitle = `${activeCategoryName} Concepts`;
            }
            
            // Smart default sort based on active quadrant(s)
            // Only auto-set if user hasn't manually clicked a column header
            if (activeQuadrants.length === 1 && !userOverrodeSort) {
                const quad = activeQuadrants[0];
                if (quad === 'established')  { sortColumn = "validation"; sortDirection = "desc"; }
                else if (quad === 'speculative')  { sortColumn = "novelty";    sortDirection = "desc"; }
                else if (quad === 'frontier')     { sortColumn = "_composite"; sortDirection = "desc"; }
                else if (quad === 'noise')        { sortColumn = "_composite"; sortDirection = "asc";  }
            }
            
            // Sort quadrant nodes
            nodes.sort((a, b) => {
                let valA, valB;
                
                if (sortColumn === "_composite") {
                    // Composite: novelty + validation
                    valA = (parseFloat(a.data.novelty) || 0) + (parseFloat(a.data.validation) || 0);
                    valB = (parseFloat(b.data.novelty) || 0) + (parseFloat(b.data.validation) || 0);
                } else if (sortColumn === "name") {
                    valA = (a.data.title || "").toLowerCase();
                    valB = (b.data.title || "").toLowerCase();
                } else {
                    valA = a.data[sortColumn];
                    valB = b.data[sortColumn];
                }
                
                if (typeof valA === 'string' && !isNaN(valA)) valA = parseFloat(valA);
                if (typeof valB === 'string' && !isNaN(valB)) valB = parseFloat(valB);
                
                if (valA < valB) return sortDirection === "asc" ? -1 : 1;
                if (valA > valB) return sortDirection === "asc" ? 1 : -1;
                return 0;
            });
            
            const titleHeader = listContainer.querySelector("h2");
            const subTitle = listContainer.querySelector("p");
            if (titleHeader) titleHeader.innerText = `${listTitle} (${nodes.length} Concepts)`;
            if (subTitle) subTitle.innerText = "Click on a concept row below to inspect its details and contradiction analysis.";
            
            let html = `
                <table class="radar-table">
                    <thead>
                        <tr>
                            <th onclick="toggleSort('name')" class="${sortColumn === 'name' ? (sortDirection === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">Concept Title</th>
                            <th style="width: 25%;">Category</th>
                            <th onclick="toggleSort('novelty')" class="${sortColumn === 'novelty' || sortColumn === '_composite' ? (sortDirection === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="width: 11%; text-align: center;">Novelty</th>
                            <th onclick="toggleSort('validation')" class="${sortColumn === 'validation' || sortColumn === '_composite' ? (sortDirection === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="width: 11%; text-align: center;">Validation</th>
                            <th onclick="toggleSort('momentum')" class="${sortColumn === 'momentum' ? (sortDirection === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="width: 11%; text-align: center;">Momentum</th>
                            <th onclick="toggleSort('reach')" class="${sortColumn === 'reach' ? (sortDirection === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="width: 11%; text-align: center;">Reach</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            if (nodes.length === 0) {
                html += `
                    <tr>
                        <td colspan="6" style="text-align: center; padding: 30px; color: var(--text-secondary);">
                            No data available in this view.
                        </td>
                    </tr>
                `;
            }
            
            nodes.forEach(node => {
                const nData = node.data;
                const nov = (nData.novelty !== undefined && nData.novelty !== null) ? parseFloat(nData.novelty) : 0.5;
                const val = (nData.validation !== undefined && nData.validation !== null) ? parseFloat(nData.validation) : 0.5;
                const mom = (nData.momentum !== undefined && nData.momentum !== null) ? parseFloat(nData.momentum) : 0.5;
                const rch = (nData.reach !== undefined && nData.reach !== null) ? parseFloat(nData.reach) : 0.0;
                
                html += `
                    <tr class="row-category" onclick="displayNodeDetailsById('${nData.id}')">
                        <td style="font-weight: 600; color: #fff;">
                            ${nData.title}
                        </td>
                        <td style="color: var(--text-secondary);">
                            ${(() => { const catBubble = globalGraphElements && globalGraphElements.find(el => el.data.id === nData.parent_category_id); return catBubble ? catBubble.data.label : 'Other Category'; })()}
                        </td>
                        <td style="text-align: center;">
                            <span class="metric-badge" style="background: rgba(167, 139, 250, 0.1); color: #d8b4fe;">
                                ${nov.toFixed(2)}
                            </span>
                        </td>
                        <td style="text-align: center;">
                            <span class="metric-badge" style="background: rgba(96, 165, 250, 0.1); color: #93c5fd;">
                                ${val.toFixed(2)}
                            </span>
                        </td>
                        <td style="text-align: center;">
                            <span class="metric-badge" style="background: rgba(245, 158, 11, 0.1); color: #fde047;">
                                ${mom.toFixed(2)}
                            </span>
                        </td>
                        <td style="text-align: center;">
                            <span class="metric-badge" style="background: rgba(45, 212, 191, 0.1); color: #5eead4;">
                                ${rch.toFixed(2)}
                            </span>
                        </td>
                    </tr>
                `;
            });
            
            html += `
                    </tbody>
                </table>
            `;
            
            listTableWrapper.innerHTML = html;
        }

        // Expand/Collapse Domain row handler
        function toggleDomainExpand(domainId, event) {
            expandedDomains[domainId] = expandedDomains[domainId] === false ? true : false;
            renderListView();
        }

        // Drill down to category map radar view
        function drillDownToCategoryMap(domainId, domainName, categoryId, categoryName, event) {
            if (event) event.stopPropagation();
            closeDetails();
            
            activeDomainId = domainId;
            activeDomainName = domainName;
            activeCategoryId = categoryId;
            activeCategoryName = categoryName;
            activeQuadrants = []; // Clear quadrant filters when drilling down a category
            scoutedCategoryIds = null; // Clear scout category filter
            
            // Always land on Map View FIRST
            currentViewMode = "map";
            
            renderListView(); // Hide main list
            renderConceptListView(); // Hide concept list
            
            document.getElementById("cy").style.display = "block";
            
            if (cy) {
                cy.resize(); // Force Cytoscape to recalculate container bounds!
            }
            
            // Dispatch a manual resize to calculate positions at current window size
            window.dispatchEvent(new Event('resize'));
            
            if (cy) {
                const catNodes = cy.nodes().filter(n => !n.data('is_cluster_bubble') && n.data('parent_category_id') === categoryId);
                if (catNodes.length > 0) {
                    cy.fit(catNodes, 80);
                    if (cy.zoom() > 1.3) {
                        cy.zoom(1.2);
                        cy.center();
                    }
                } else {
                    cy.fit(cy.nodes(), 80);
                }
            }
            
            if (updateZoomView) updateZoomView();
        }

        function renderGraph(elements) {
            if (breathingIntervalId) {
                clearInterval(breathingIntervalId);
                breathingIntervalId = null;
            }
            const container = document.getElementById("cy");
            const w = container.offsetWidth;
            const h = container.offsetHeight;

            // Defensive: filter orphan edges before Cytoscape init (prevents crash)
            const nodeIdSet = new Set(elements.filter(el => el.group === "nodes").map(el => el.data.id));
            elements = elements.filter(el => {
                if (el.group === "edges") {
                    return nodeIdSet.has(el.data.source) && nodeIdSet.has(el.data.target);
                }
                return true;
            });

            // Pre-process elements to attach their dynamic cluster HSL colors and bubble labels
            const nowMs = Date.now();
            elements.forEach(el => {
                if (el.group === "nodes") {
                    const cid = el.data.cluster_id || (el.data.is_cluster_bubble ? el.data.id : null);
                    el.data.color = getClusterColor(cid);
                    
                    if (el.data.is_cluster_bubble) {
                        el.data.label_with_count = `${el.data.title}\n[${el.data.content_size}]`;
                    }

                    // Mark nodes created within the last 3 minutes as "new" for orange highlight + front z-index
                    if (el.data.created_at && !el.data.is_cluster_bubble && !el.data.is_domain_bubble) {
                        try {
                            // Append 'Z' to force UTC parsing (server stores UTC ISO strings without suffix)
                            const tsStr = el.data.created_at.endsWith('Z') ? el.data.created_at : el.data.created_at + 'Z';
                            const createdMs = new Date(tsStr).getTime();
                            if (nowMs - createdMs < 180000) { // 180,000ms = 3 minutes
                                el.data.is_new = true;
                            }
                        } catch (e) { /* ignore bad timestamps */ }
                    }
                }
            });

            // Second pass: mark sibling nodes (same category as new nodes) as "context" for rose highlight
            // ONLY during active scout sessions — not for URL ingestion or sandbox ideas
            if (scoutedCategoryIds && scoutedCategoryIds.size > 0) {
                const newCategoryIds = new Set();
                elements.forEach(el => {
                    if (el.group === "nodes" && el.data.is_new && el.data.parent_category_id) {
                        newCategoryIds.add(el.data.parent_category_id);
                    }
                });
                if (newCategoryIds.size > 0) {
                    elements.forEach(el => {
                        if (el.group === "nodes" && !el.data.is_new && !el.data.is_cluster_bubble && !el.data.is_domain_bubble) {
                            if (el.data.parent_category_id && newCategoryIds.has(el.data.parent_category_id)) {
                                el.data.is_context = true;
                            }
                        }
                    });
                }
            }

            // Calculate dynamic circular coordinates and dynamic sizes for L1 and L2 bubbles
            const l1Bubbles = elements.filter(el => el.group === "nodes" && el.data.is_cluster_bubble && el.data.level === 1);
            const l2Bubbles = elements.filter(el => el.group === "nodes" && el.data.is_cluster_bubble && el.data.level === 2);
            
            const centerX = w / 2;
            const centerY = h / 2;

            // 1. Level 1 Domains positioning (via centroid coordinates)
            const N_L1 = l1Bubbles.length;
            const D_1 = Math.max(140, Math.min(240, (Math.min(w, h) * 0.6) / N_L1));
            const F_1 = Math.max(12, D_1 * 0.085);

            l1Bubbles.forEach((el, index) => {
                const nov = el.data.novelty !== undefined ? el.data.novelty : 0.5;
                const val = el.data.validation !== undefined ? el.data.validation : 0.5;
                el.position = getCoordinates(nov, val, w, h);
                el.data.dynamic_size = D_1;
                el.data.dynamic_font = F_1;
            });

            // 2. Level 2 Categories positioning (via centroid coordinates)
            const N_L2 = l2Bubbles.length;
            const D_2 = Math.max(110, Math.min(180, (Math.min(w, h) * 0.5) / (N_L2 || 1)));
            const F_2 = Math.max(11, D_2 * 0.085);

            l2Bubbles.forEach((el, index) => {
                const nov = el.data.novelty !== undefined ? el.data.novelty : 0.5;
                const val = el.data.validation !== undefined ? el.data.validation : 0.5;
                el.position = getCoordinates(nov, val, w, h);
                el.data.dynamic_size = D_2;
                el.data.dynamic_font = F_2;
            });
            if (sandboxNode) {
                sandboxNode.data.color = getClusterColor(sandboxNode.data.cluster_id);
            }

            // Collision avoidance: iterative pairwise repulsion based on momentum-derived node size.
            // Nodes stay near their true (novelty, validation) coordinates but spread apart
            // enough so overlapping dots remain individually visible and clickable.
            let nodesToPosition = elements.filter(el => el.group === "nodes" && !el.data.is_cluster_bubble);
            if (sandboxNode) {
                nodesToPosition.push(sandboxNode);
            }

            // When scout category filter is active, only run collision avoidance
            // on nodes in those categories — prevents hidden nodes from displacing visible ones
            if (scoutedCategoryIds && scoutedCategoryIds.size > 0) {
                nodesToPosition = nodesToPosition.filter(el =>
                    el.data.is_new || el.data.is_context ||
                    (el.data.parent_category_id && scoutedCategoryIds.has(el.data.parent_category_id))
                );
            }

            const activeClusterIds = Array.from(new Set(nodesToPosition.map(el => el.data.cluster_id).filter(Boolean))).sort();

            const positioned = nodesToPosition.map(el => {
                const coords = getCoordinates(el.data.novelty, el.data.validation, w, h);
                const mom = (el.data.momentum !== undefined && el.data.momentum !== null) ? parseFloat(el.data.momentum) : 0.2;
                const nodeRadius = 5 + mom * 15; // Maps momentum [0,1] to radius [5,20]
                return { el, x: coords.x, y: coords.y, trueX: coords.x, trueY: coords.y, radius: nodeRadius };
            });

            // Run 3 iterations of pairwise repulsion to resolve overlaps
            // After each iteration, spring nodes back toward their true X-position
            // to preserve novelty ordering on the X-axis
            for (let iter = 0; iter < 3; iter++) {
                for (let i = 0; i < positioned.length; i++) {
                    for (let j = i + 1; j < positioned.length; j++) {
                        const a = positioned[i], b = positioned[j];
                        const dx = b.x - a.x;
                        const dy = b.y - a.y;
                        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
                        const minDist = a.radius + b.radius + 4; // 4px padding between nodes
                        if (dist < minDist) {
                            const overlap = (minDist - dist) / 2;
                            const nx = dx / dist, ny = dy / dist;
                            a.x -= nx * overlap;
                            a.y -= ny * overlap;
                            b.x += nx * overlap;
                            b.y += ny * overlap;
                        }
                    }
                }
                // Spring-back: pull X 60% toward true novelty position to preserve ordering
                // Y is allowed to drift more freely since validation axis is less critical
                const springX = 0.6;
                for (const p of positioned) {
                    p.x = p.x + springX * (p.trueX - p.x);
                }
            }

            // Clamp to quadrant boundaries and assign final positions
            positioned.forEach(({ el, x, y }) => {
                const midX = w / 2;
                const midY = h / 2;
                const nov = el.data.novelty !== undefined ? parseFloat(el.data.novelty) : 0.5;
                const val = el.data.validation !== undefined ? parseFloat(el.data.validation) : 0.5;
                const paddingX = 80, paddingY = 80, margin = 15;

                if (nov < 0.5) {
                    x = Math.max(paddingX, Math.min(midX - margin, x));
                } else {
                    x = Math.max(midX + margin, Math.min(w - paddingX, x));
                }
                if (val >= 0.5) {
                    y = Math.max(paddingY, Math.min(midY - margin, y));
                } else {
                    y = Math.max(midY + margin, Math.min(h - paddingY, y));
                }

                el.position = { x, y };
                // Store true position for semantic zoom recalculation
                el.data.trueX = x;
                el.data.trueY = y;
                if (el.data.id === 'sandbox:idea') {
                    console.log("[DEBUG POSITION] Sandbox ID:", el.data.id);
                    console.log("[DEBUG POSITION] Sandbox Novelty:", el.data.novelty, "Validation:", el.data.validation);
                    console.log("[DEBUG POSITION] Sandbox Coordinates:", { x, y });
                    console.log("[DEBUG POSITION] Container dimensions w, h:", w, h);
                }
            });
            
            if (sandboxNode && !elements.includes(sandboxNode)) {
                elements.push(sandboxNode);
                
                // Inject sandbox edges as well
                if (sandboxEdges && sandboxEdges.length > 0) {
                    sandboxEdges.forEach(edge => {
                        if (!elements.includes(edge)) {
                            elements.push(edge);
                        }
                    });
                }
            }

            cy = cytoscape({
                container: container,
                elements: elements,
                style: [
                    {
                        selector: 'node',
                        style: {
                            'background-color': 'data(color)', // Dynamic cluster HSL color mapping
                            'label': '', // Remove static node labels from child dots to prevent clutter
                            'font-family': 'Inter',
                            'font-size': '10px',
                            'color': '#cbd5e1',
                            'text-margin-y': '6px',
                            'text-valign': 'bottom',
                            'text-halign': 'center',
                            'text-wrap': 'wrap',
                            'text-max-width': '120px',
                            'border-width': '2px',
                            'border-color': 'rgba(255,255,255,0.1)',
                            'z-compound-depth': 'orphan',
                            'transition-property': 'background-color, border-color, border-width',
                            'transition-duration': '0.3s'
                        }
                    },
                    {
                        // Size mapping scoped to leaf nodes (bubbles use dynamic_size instead)
                        selector: 'node[dot_size]',
                        style: {
                            'width': 'data(dot_size)',
                            'height': 'data(dot_size)'
                        }
                    },
                    {
                        selector: 'node[is_cluster_bubble]',
                        style: {
                            'width': 'data(dynamic_size)',
                            'height': 'data(dynamic_size)',
                            'background-color': 'data(color)',
                            'background-opacity': 0.15,
                            'border-width': '2.5px',
                            'border-color': 'data(color)',
                            'border-style': 'solid',
                            'shape': 'ellipse',
                            'label': 'data(label_with_count)',
                            'font-family': 'Outfit',
                            'font-weight': 'bold',
                            'font-size': 'data(dynamic_font)',
                            'color': 'data(color)',
                            'text-valign': 'center',
                            'text-halign': 'center',
                            'text-wrap': 'wrap',
                            'text-max-width': 'data(dynamic_size)',
                            'text-background-opacity': 0.85,
                            'text-background-color': '#090a16',
                            'text-background-padding': '4px 8px',
                            'text-background-shape': 'roundrectangle'
                        }
                    },
                    {
                        selector: 'node[source_type="sandbox"]',
                        style: {
                            'shape': 'star',
                            'width': 'data(dot_size)',
                            'height': 'data(dot_size)',
                            'background-color': '#f59e0b', // Amber-orange circle
                            'border-color': '#ffffff',
                            'border-width': '2.5px',
                            'border-style': 'dashed',
                            'transition-property': 'width, height',
                            'transition-duration': '0.3s'
                        }
                    },
                    {
                        selector: 'node[?is_analyzing]',
                        style: {
                            'border-color': '#fbbf24',
                            'border-style': 'double',
                            'border-width': '5px',
                            'z-index': 999
                        }
                    },
                    {
                        // Highlight newly scouted nodes in Neon Orange
                        selector: 'node[?is_new]',
                        style: {
                            'background-color': '#f97316',
                            'border-color': '#fdba74',
                            'border-width': '3px',
                            'z-index': 998
                        }
                    },
                    {
                        // Highlight scouted/related nodes in Rose/Coral with white border
                        selector: 'node[?is_context]',
                        style: {
                            'background-color': '#f43f5e',
                            'border-color': 'rgba(255,255,255,0.6)',
                            'border-width': '2.5px',
                            'z-index': 997
                        }
                    },
                    {
                        selector: 'edge',
                        style: {
                            'width': '2px',
                            'line-color': function(ele) {
                                const rel = ele.data('relationship_type');
                                if (rel === 'contradicts') return '#ef4444';
                                if (rel === 'depends_on') return '#10b981';
                                if (rel === 'extends') return '#8b5cf6';
                                if (rel === 'applies_to') return '#f59e0b';
                                if (rel === 'evaluates') return '#eab308';
                                if (rel === 'part_of') return '#06b6d4';
                                if (rel === 'similar_to') return 'rgba(255, 255, 255, 0.35)';
                                return 'rgba(255, 255, 255, 0.15)';
                            },
                            'line-style': function(ele) {
                                return ele.data('relationship_type') === 'contradicts' ? 'dashed' : 'solid';
                            },
                            'target-arrow-color': 'rgba(255,255,255,0.3)',
                            'target-arrow-shape': 'triangle',
                            'curve-style': 'bezier',
                            'opacity': 0.65
                        }
                    },
                    {
                        selector: 'node:selected',
                        style: {
                            'border-width': '3px',
                            'border-color': '#ffffff',
                            'color': '#ffffff',
                            'font-weight': 'bold'
                        }
                    },
                    {
                        // Dim style for interactive quadrant filtering
                        selector: '.dimmed',
                        style: {
                            'opacity': 0.12,
                            'transition-property': 'opacity',
                            'transition-duration': '0.2s'
                        }
                    },
                    {
                        // Dim style for out-of-focus zoom levels (depth-of-field effect)
                        selector: '.dimmed-context',
                        style: {
                            'opacity': 0.25,
                            'transition-property': 'opacity',
                            'transition-duration': '0.25s'
                        }
                    }
                ],
                layout: {
                    name: 'preset'
                },
                userZoomingEnabled: true,
                userPanningEnabled: true,
                boxSelectionEnabled: false,
                autoungrabify: true // Locks node dragging to keep fixed references to coordinates
            });

            // Programmatically lock all nodes
            cy.autoungrabify(true);
            cy.nodes().lock();

            // Continuous breathing animation for new, context, and analyzing nodes
            const startBreathingAnimation = () => {
                if (!cy) return;
                const targetNodes = cy.nodes().filter(n => n.data('is_new') === true || n.data('is_context') === true || n.data('is_analyzing') === true);
                targetNodes.forEach(n => {
                    const baseSize = parseFloat(n.data('dot_size')) || 20;
                    const expandSize = baseSize + 6;
                    n.animate({
                        style: { 'border-width': '5.5px', 'width': expandSize + 'px', 'height': expandSize + 'px' }
                    }, {
                        duration: 850
                    }).delay(100).animate({
                        style: { 'border-width': '2.5px', 'width': baseSize + 'px', 'height': baseSize + 'px' }
                    }, {
                        duration: 850
                    });
                });
            };
            setTimeout(startBreathingAnimation, 200);
            breathingIntervalId = setInterval(startBreathingAnimation, 2000);

            // Handle Zoom and Pan Events for dynamic viewport tracking
            const mapWrapper = document.getElementById("cy").parentElement;
            const miniGrid = document.querySelector(".mini-grid");
            const miniQuadrants = document.querySelectorAll(".mini-quadrant");

            updateZoomView = function() {
                const zoom = cy.zoom();
                const container = document.getElementById("cy");
                const w = container.offsetWidth;
                const h = container.offsetHeight;

                // Elements for breadcrumbs path tracker
                const domBreadcrumb = document.getElementById("breadcrumb-domain-link");
                const catBreadcrumb = document.getElementById("breadcrumb-category-link");
                const catBreadcrumbContainer = document.getElementById("breadcrumb-category-container");

                // Elements for quadrant grid overlays
                const bgGrid = document.querySelector(".quadrant-bg-grid");
                const lineH = document.querySelector(".quadrant-line-h");
                const lineV = document.querySelector(".quadrant-line-v");
                const quadLabels = document.querySelectorAll(".quadrant-name");

                // Manage View Toggle Bar visibility and count badge
                const toggleBar = document.getElementById("quadrant-view-toggle");
                const countBadge = document.getElementById("quadrant-count-text");
                const btnMap = document.getElementById("toggle-btn-map");
                const btnList = document.getElementById("toggle-btn-list");

                if (scoutedCategoryIds && scoutedCategoryIds.size > 0) {
                    if (toggleBar) toggleBar.style.display = "flex";
                    if (countBadge) {
                        const scoutNodes = cy.nodes().filter(n => !n.data('is_cluster_bubble') && n.data('parent_category_id') && scoutedCategoryIds.has(n.data('parent_category_id')));
                        const newCount = scoutNodes.filter(n => n.data('is_new') === true).length;
                        countBadge.innerText = `Scout Results | ${newCount} New + ${scoutNodes.length - newCount} Related`;
                    }
                } else if (activeQuadrants.length > 0 || activeCategoryId) {
                    if (toggleBar) toggleBar.style.display = "flex";
                    if (countBadge) {
                        if (activeQuadrants.length > 0) {
                            const qNodes = getQuadrantNodes(activeQuadrants);
                            const qLabel = getQuadrantsLabel(activeQuadrants);
                            countBadge.innerText = `${qLabel} | ${qNodes.length} ${qNodes.length === 1 ? 'Concept' : 'Concepts'}`;
                        } else if (activeCategoryId) {
                            const cNodes = getCategoryNodes(activeCategoryId);
                            countBadge.innerText = `${activeCategoryName} | ${cNodes.length} ${cNodes.length === 1 ? 'Concept' : 'Concepts'}`;
                        }
                    }
                } else if (toggleBar) {
                    toggleBar.style.display = "none";
                }

                if (currentViewMode === "map") {
                    if (btnMap) {
                        btnMap.style.background = "#3b82f6";
                        btnMap.style.color = "#fff";
                        btnMap.style.boxShadow = "0 2px 8px rgba(59,130,246,0.4)";
                    }
                    if (btnList) {
                        btnList.style.background = "transparent";
                        btnList.style.color = "#94a3b8";
                        btnList.style.boxShadow = "none";
                    }
                } else {
                    if (btnList) {
                        btnList.style.background = "#3b82f6";
                        btnList.style.color = "#fff";
                        btnList.style.boxShadow = "0 2px 8px rgba(59,130,246,0.4)";
                    }
                    if (btnMap) {
                        btnMap.style.background = "transparent";
                        btnMap.style.color = "#94a3b8";
                        btnMap.style.boxShadow = "none";
                    }
                }

                if (currentViewMode === "list" || currentViewMode === "quadrant-list") {
                    // Hide cytoscape canvas container
                    container.style.display = "none";
                    
                    // Hide quadrant grids and divider lines
                    if (bgGrid) bgGrid.style.opacity = "0";
                    if (lineH) lineH.style.opacity = "0";
                    if (lineV) lineV.style.opacity = "0";
                    quadLabels.forEach(lbl => lbl.style.opacity = "0");

                    // Set breadcrumbs trail
                    if (scoutedCategoryIds && scoutedCategoryIds.size > 0) {
                        if (domBreadcrumb) domBreadcrumb.innerText = "Scout Results";
                        if (catBreadcrumb) catBreadcrumb.innerText = "Related Topics";
                        if (catBreadcrumbContainer) catBreadcrumbContainer.style.display = "block";
                    } else if (activeQuadrants.length > 0) {
                        const quadName = getQuadrantsLabel(activeQuadrants);

                        if (domBreadcrumb) domBreadcrumb.innerText = "Quadrant Explorer";
                        if (catBreadcrumb) catBreadcrumb.innerText = quadName;
                        if (catBreadcrumbContainer) catBreadcrumbContainer.style.display = "block";
                    } else if (activeDomainId) {
                        if (domBreadcrumb) domBreadcrumb.innerText = activeDomainName;
                        if (catBreadcrumb) catBreadcrumb.innerText = "All Categories";
                        if (catBreadcrumbContainer) catBreadcrumbContainer.style.display = "block";
                    } else {
                        if (domBreadcrumb) domBreadcrumb.innerText = "All Domains";
                        if (catBreadcrumbContainer) catBreadcrumbContainer.style.display = "none";
                    }

                    // Manage mini grid highlights
                    if (activeQuadrants.length > 0) {
                        mapWrapper.classList.add("map-zoomed-in");
                        miniGrid.classList.add("zoomed-active");
                    } else {
                        mapWrapper.classList.remove("map-zoomed-in");
                        miniGrid.classList.remove("zoomed-active");
                    }

                    miniQuadrants.forEach(quad => {
                        if (activeQuadrants.includes(quad.getAttribute("data-quadrant"))) {
                            quad.classList.add("active-view");
                        } else {
                            quad.classList.remove("active-view");
                        }
                    });
                    
                    return;
                }

                // --- Map View Mode ---
                container.style.display = "block";

                // Get screen coordinates of the coordinate center (w/2, h/2 on the canvas) using standard projection math
                const panVal = cy.pan();
                const cx = (w / 2) * zoom + panVal.x;
                const cy_screen = (h / 2) * zoom + panVal.y;

                // Position divider lines
                if (lineH) lineH.style.top = `${cy_screen}px`;
                if (lineV) lineV.style.left = `${cx}px`;

                // Position backgrounds
                const bgEst = document.getElementById("bg-established");
                const bgFr = document.getElementById("bg-frontier");
                const bgNo = document.getElementById("bg-noise");
                const bgSp = document.getElementById("bg-speculative");

                if (bgEst) {
                    bgEst.style.left = '0';
                    bgEst.style.top = '0';
                    bgEst.style.width = `${cx}px`;
                    bgEst.style.height = `${cy_screen}px`;
                }
                if (bgFr) {
                    bgFr.style.left = `${cx}px`;
                    bgFr.style.top = '0';
                    bgFr.style.width = `${w - cx}px`;
                    bgFr.style.height = `${cy_screen}px`;
                }
                if (bgNo) {
                    bgNo.style.left = '0';
                    bgNo.style.top = `${cy_screen}px`;
                    bgNo.style.width = `${cx}px`;
                    bgNo.style.height = `${h - cy_screen}px`;
                }
                if (bgSp) {
                    bgSp.style.left = `${cx}px`;
                    bgSp.style.top = `${cy_screen}px`;
                    bgSp.style.width = `${w - cx}px`;
                    bgSp.style.height = `${h - cy_screen}px`;
                }

                // Position quadrant labels relative to the center intersections
                const lblEst = document.querySelector(".quad-established");
                const lblFr = document.querySelector(".quad-frontier");
                const lblNo = document.querySelector(".quad-noise");
                const lblSp = document.querySelector(".quad-speculative");

                if (lblEst) {
                    lblEst.style.top = `${cy_screen - 40}px`;
                    lblEst.style.left = `${cx - 180}px`;
                }
                if (lblFr) {
                    lblFr.style.top = `${cy_screen - 40}px`;
                    lblFr.style.left = `${cx + 40}px`;
                }
                if (lblNo) {
                    lblNo.style.top = `${cy_screen + 20}px`;
                    lblNo.style.left = `${cx - 180}px`;
                }
                if (lblSp) {
                    lblSp.style.top = `${cy_screen + 20}px`;
                    lblSp.style.left = `${cx + 40}px`;
                }

                // Ensure quadrant grids and divider lines are visible
                if (bgGrid) bgGrid.style.opacity = "1";
                if (lineH) lineH.style.opacity = "1";
                if (lineV) lineV.style.opacity = "1";
                quadLabels.forEach(lbl => lbl.style.opacity = "1");

                // Set breadcrumbs trail
                const selectedNodes = cy ? cy.nodes(':selected') : null;
                const selectedNode = (selectedNodes && selectedNodes.length > 0) ? selectedNodes.filter(n => !n.data('is_cluster_bubble'))[0] : null;
                const subBreadcrumbContainer = document.getElementById("breadcrumb-subcategory-container");
                const subBreadcrumbText = document.getElementById("breadcrumb-subcategory-text");

                if (selectedNode) {
                    const nodeData = selectedNode.data();
                    const domName = nodeData.domain_name || "All Domains";
                    const catName = nodeData.category_name || "";
                    const subName = nodeData.cluster_name || "";
                    
                    if (domBreadcrumb) domBreadcrumb.innerText = domName;
                    if (catBreadcrumb) catBreadcrumb.innerText = catName || subName;
                    
                    if (subBreadcrumbContainer && subBreadcrumbText && subName && catName) {
                        subBreadcrumbText.innerText = subName;
                        subBreadcrumbContainer.style.display = "inline";
                    } else if (subBreadcrumbContainer) {
                        subBreadcrumbContainer.style.display = "none";
                    }
                } else {
                    if (subBreadcrumbContainer) subBreadcrumbContainer.style.display = "none";
                    
                    if (scoutedCategoryIds && scoutedCategoryIds.size > 0) {
                        if (domBreadcrumb) domBreadcrumb.innerText = "Scout Results";
                        if (catBreadcrumb) catBreadcrumb.innerText = "Related Topics";
                    } else if (activeQuadrants.length > 0) {
                        const quadName = getQuadrantsLabel(activeQuadrants);

                        if (domBreadcrumb) domBreadcrumb.innerText = "Quadrant Explorer";
                        if (catBreadcrumb) catBreadcrumb.innerText = quadName;
                    } else {
                        if (domBreadcrumb) domBreadcrumb.innerText = activeDomainName;
                        if (catBreadcrumb) catBreadcrumb.innerText = activeCategoryName;
                    }
                }
                if (catBreadcrumbContainer) catBreadcrumbContainer.style.display = "block";

                // Filter nodes visibility - Level 3 document nodes only
                const allNodes = cy.nodes();
                allNodes.forEach(node => {
                    const isBubble = node.data('is_cluster_bubble');
                    if (!isBubble) {
                        if (scoutedCategoryIds && scoutedCategoryIds.size > 0) {
                            // Scout mode: always show target (is_new) nodes + nodes in scouted categories
                            if (node.data('is_new') || node.data('is_context') || 
                                (node.data('parent_category_id') && scoutedCategoryIds.has(node.data('parent_category_id')))) {
                                node.style('display', 'element');
                                node.removeClass('dimmed-context');
                            } else {
                                node.style('display', 'none');
                            }
                        } else if (activeQuadrants.length > 0) {
                            const nov = (node.data('novelty') !== undefined && node.data('novelty') !== null) ? parseFloat(node.data('novelty')) : 0.5;
                            const val = (node.data('validation') !== undefined && node.data('validation') !== null) ? parseFloat(node.data('validation')) : 0.5;
                            let inQuadrant = false;
                            
                            activeQuadrants.forEach(aq => {
                                if (aq === 'established' && nov < 0.5 && val >= 0.5) inQuadrant = true;
                                if (aq === 'frontier' && nov >= 0.5 && val >= 0.5) inQuadrant = true;
                                if (aq === 'noise' && nov < 0.5 && val < 0.5) inQuadrant = true;
                                if (aq === 'speculative' && nov >= 0.5 && val < 0.5) inQuadrant = true;
                            });
                            
                            if (inQuadrant) {
                                node.style('display', 'element');
                                node.removeClass('dimmed-context');
                            } else {
                                node.style('display', 'none');
                            }
                        } else {
                            // No filter active: show all nodes, or filter by active category
                            if (!activeCategoryId || node.id() === 'sandbox:idea' || node.data('parent_category_id') === activeCategoryId) {
                                node.style('display', 'element');
                                node.removeClass('dimmed-context');
                            } else {
                                node.style('display', 'none');
                            }
                        }
                    } else {
                        node.style('display', 'none');
                    }
                });
                
                // Show edges linking visible nodes
                cy.edges().forEach(edge => {
                    const s = cy.getElementById(edge.data('source'));
                    const t = cy.getElementById(edge.data('target'));
                    if (s.style('display') === 'element' && t.style('display') === 'element') {
                        edge.style('display', 'element');
                        edge.removeClass('dimmed-context');
                    } else {
                        edge.style('display', 'none');
                    }
                });

                // Sidebar Mini-Landscape Quadrant Tracking
                mapWrapper.classList.add("map-zoomed-in");
                miniGrid.classList.add("zoomed-active");
                
                miniQuadrants.forEach(quad => {
                    const qAttr = quad.getAttribute("data-quadrant");
                    if (activeQuadrants.includes(qAttr)) {
                        quad.classList.add("active-view");
                    } else if (activeQuadrants.length === 0) {
                        const extent = cy.extent();
                        const centerX = (extent.x1 + extent.x2) / 2;
                        const centerY = (extent.y1 + extent.y2) / 2;
                        
                        const midX = w / 2;
                        const midY = h / 2;
                        
                        let activeQuad = "";
                        if (centerX < midX && centerY < midY) {
                            activeQuad = "established";
                        } else if (centerX >= midX && centerY < midY) {
                            activeQuad = "frontier";
                        } else if (centerX < midX && centerY >= midY) {
                            activeQuad = "noise";
                        } else if (centerX >= midX && centerY >= midY) {
                            activeQuad = "speculative";
                        }
                        
                        if (qAttr === activeQuad) {
                            quad.classList.add("active-view");
                        } else {
                            quad.classList.remove("active-view");
                        }
                    } else {
                        quad.classList.remove("active-view");
                    }
                });
            }

            // Bind listeners for zoom and pan events
            cy.on("zoom pan", updateZoomView);

            // Semantic zoom: debounced node spreading on zoom change
            cy.on('zoom', function() {
                if (semanticZoomTimer) clearTimeout(semanticZoomTimer);
                semanticZoomTimer = setTimeout(spreadNodesOnZoom, 80);
            });
            
            // Fit camera viewport around Level 1 Domain bubbles on load (spacious overview)
            const l1Nodes = cy.nodes().filter(n => n.data('level') === 1);
            if (l1Nodes.length > 0) {
                cy.fit(l1Nodes, 40);
                if (cy.zoom() > 0.85) {
                    cy.zoom(0.80);
                    cy.center();
                }
            } else if (cy.nodes().length > 0) {
                cy.fit(cy.nodes(), 40);
                if (cy.zoom() > 0.85) {
                    cy.zoom(0.80);
                    cy.center();
                }
            }

            // Capture base zoom AFTER fit — use 70% of actual zoom so there's always
            // a minimum spread even at the overview level
            baseZoomLevel = (cy.zoom() || 0.5) * 0.7;
            
            // Run initial check
            if (updateZoomView) updateZoomView();

            // Clear suppress flag — any prior closeDetails animation was on the old cy instance
            suppressSemanticZoom = false;

            // Run semantic zoom once at startup so overlapping dots separate immediately
            setTimeout(spreadNodesOnZoom, 100);

            // Bind Breadcrumb Trail Navigation clicks to allow backtracking levels
            const domBreadcrumbLink = document.getElementById("breadcrumb-domain-link");
            const catBreadcrumbLink = document.getElementById("breadcrumb-category-link");
            
            if (domBreadcrumbLink) {
                domBreadcrumbLink.onclick = function(e) {
                    e.preventDefault();
                    closeDetails();
                    loadGraphData(true);
                };
            }
            
            if (catBreadcrumbLink) {
                catBreadcrumbLink.onclick = function(e) {
                    e.preventDefault();
                    closeDetails(); // Close card on navigation back
                    isClickNavigating = true;
                    
                    if (activeQuadrants.length > 0 || scoutedCategoryIds) {
                        activeQuadrants = [];
                        scoutedCategoryIds = null;
                        activeDomainId = null;
                        activeCategoryId = null;
                        currentViewMode = "list";
                        expandedDomains = {};
                    } else {
                        if (!activeDomainId) return;
                        activeCategoryId = null;
                        activeCategoryName = "";
                        currentViewMode = "list"; // Switch back to lists
                        expandedDomains = { [activeDomainId]: true }; // Keep this domain expanded!
                    }
                    
                    renderListView();
                    if (updateZoomView) updateZoomView();
                    isClickNavigating = false;
                };
            }

            // Node Single-Click (Tap) Event: Opens Details Panel
            cy.on('tap', 'node', function(evt) {
                const node = evt.target.data();
                if (node.is_cluster_bubble) {
                    return;
                }
                displayNodeDetails(node);
            });

            // Node Double-Click (Double-Tap) Event: Opens Link Directly
            cy.on('dbltap', 'node', function(evt) {
                const node = evt.target.data();
                if (node.is_cluster_bubble) return;
                if (node.url) {
                    window.open(node.url, '_blank');
                }
            });

        }

        // Fetch details of selected node
        async function displayNodeDetails(node) {
            const content = document.getElementById("details-content");
            const badgeClass = `badge badge-${node.source_type}`;
            const label = node.source_type.toUpperCase();
            
            // Resolve cluster_name from L2 category bubble if not already set
            if (!node.cluster_name && node.parent_category_id && globalGraphElements) {
                const catBubble = globalGraphElements.find(
                    el => el.data && el.data.id === node.parent_category_id && el.data.is_cluster_bubble
                );
                if (catBubble) {
                    node.cluster_name = catBubble.data.label || catBubble.data.title || "";
                }
            }
            if (!node.cluster_name) {
                node.cluster_name = "";
            }
            
            // Collect relationships/edges for this node
            const elements = cy.elements();
            const connectedEdges = cy.edges(`[source = "${node.id}"]`);
            
            let relationsHTML = "";
            if (connectedEdges.length > 0) {
                relationsHTML = `<div style="margin-top: 1rem;">`;
                connectedEdges.forEach(edge => {
                    const edgeData = edge.data();
                    const targetNode = cy.getElementById(edgeData.target).data();
                    const relType = edgeData.relationship_type || 'relates_to';
                    const badgeColors = {
                        'extends': '#8b5cf6', 'depends_on': '#10b981', 'part_of': '#06b6d4',
                        'similar_to': '#94a3b8', 'contradicts': '#ef4444', 'applies_to': '#f59e0b',
                        'evaluates': '#eab308', 'relates_to': '#64748b'
                    };
                    const badgeColor = badgeColors[relType] || '#64748b';
                    const badgeLabel = relType.toUpperCase().replace('_', ' ');
                    
                    relationsHTML += `
                        <div class="relation-item">
                            <div class="relation-hdr">
                                <span style="background: ${badgeColor}22; color: ${badgeColor}; border: 1px solid ${badgeColor}55; padding: 2px 8px; border-radius: 4px; font-size: 0.65rem; font-weight: 600; letter-spacing: 0.5px;">${badgeLabel}</span>
                                <span style="color: var(--text-secondary)">Similarity: ${(edgeData.similarity * 100).toFixed(0)}%</span>
                            </div>
                            <div style="font-size: 0.75rem; color: var(--text-primary); margin-top: 3px;">
                                Linked to: <strong>${targetNode.title.split(' - ')[0]}</strong>
                            </div>
                        </div>
                    `;
                });
                relationsHTML += `</div>`;
            }

            // Check if qualitative contradiction analysis exists
            let contradictionAnalysisHTML = "";
            if (node.contradiction_analysis) {
                contradictionAnalysisHTML = `
                    <div class="detail-section-title" style="margin-top: 1.5rem;">Agent Qualitative Evaluation</div>
                    <p class="detail-summary" style="margin-top: 0.5rem; color: var(--text-secondary); line-height: 1.6;">
                        ${node.is_analyzing 
                            ? `<span style="display: flex; align-items: center; gap: 8px; color: #fbbf24;"><svg class="animate-spin" style="width: 14px; height: 14px; border: 2px solid transparent; border-top-color: currentColor; border-radius: 50%; display: inline-block;" viewBox="0 0 24 24"></svg> Deep search, scraping literature, and running contradiction check in background...</span>`
                            : parseMarkdown(node.contradiction_analysis)}
                    </p>
                `;
            }
            const nov = (node.novelty !== undefined && node.novelty !== null) ? parseFloat(node.novelty) : 0.5;
            const val = (node.validation !== undefined && node.validation !== null) ? parseFloat(node.validation) : 0.5;
            const mom = (node.momentum !== undefined && node.momentum !== null) ? parseFloat(node.momentum) : 0.5;
            const reach = (node.reach !== undefined && node.reach !== null) ? parseFloat(node.reach) : 0.0;

            const novStr = node.is_analyzing ? `<span style="font-size: 0.85rem; color: #fbbf24; animation: pulse 1.2s infinite; font-weight: 600;">CALC...</span>` : nov.toFixed(2);
            const valStr = node.is_analyzing ? `<span style="font-size: 0.85rem; color: #fbbf24; animation: pulse 1.2s infinite; font-weight: 600;">CALC...</span>` : val.toFixed(2);
            const momStr = node.is_analyzing ? `<span style="font-size: 0.85rem; color: #fbbf24; animation: pulse 1.2s infinite; font-weight: 600;">CALC...</span>` : mom.toFixed(2);
            const reachStr = reach.toFixed(2);

            let refreshButtonHTML = '';
            if (node.id !== 'sandbox:idea') {
                // Format the scores_updated_at timestamp for display
                let lastUpdatedText = 'pending';
                if (node.scores_updated_at) {
                    try {
                        const d = new Date(node.scores_updated_at + 'Z');
                        const dd = String(d.getDate()).padStart(2, '0');
                        const mm = String(d.getMonth() + 1).padStart(2, '0');
                        const yyyy = d.getFullYear();
                        const hh = String(d.getHours()).padStart(2, '0');
                        const min = String(d.getMinutes()).padStart(2, '0');
                        lastUpdatedText = `${dd}/${mm}/${yyyy} ${hh}:${min}`;
                    } catch(e) { lastUpdatedText = 'unknown'; }
                }

                refreshButtonHTML = `
                    <button id="refresh-node-btn" class="btn" style="margin-top: 1rem; display: block; width: 100%; font-weight: 600; cursor: pointer; transition: all 0.3s ease; display: flex; align-items: center; justify-content: center; gap: 6px;" onclick="handleManualNodeRefresh('${node.id}')">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
                        Refresh Node
                    </button>
                    <div id="refresh-node-status" style="font-size: 0.68rem; text-align: center; margin-top: 0.25rem; color: var(--text-secondary); min-height: 12px;">Checking limits...</div>
                    <div style="font-size: 0.62rem; text-align: center; margin-top: 0.15rem; color: var(--text-secondary); opacity: 0.7;">Metrics last updated: ${lastUpdatedText}</div>
                `;
            }

            let attributionHTML = "";
            if (node.contact_name || node.contact_linkedin || node.contact_email) {
                attributionHTML = `
                    <div class="detail-section-title" style="margin-top: 1.5rem;">Concept Attribution</div>
                    <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 0.75rem; margin-top: 0.5rem; font-size: 0.82rem; display: flex; flex-direction: column; gap: 0.35rem;">
                        ${node.contact_name ? `<div style="color: var(--text-primary); font-weight: 600;"><span style="color: var(--text-secondary); font-weight: 400;">Pitched by:</span> ${node.contact_name}</div>` : ''}
                        ${node.contact_linkedin ? `<div><span style="color: var(--text-secondary);">LinkedIn:</span> <a href="${node.contact_linkedin.startsWith('http') ? node.contact_linkedin : 'https://' + node.contact_linkedin}" target="_blank" style="color: #60a5fa; text-decoration: none;">${node.contact_linkedin}</a></div>` : ''}
                        ${node.contact_email ? `<div><span style="color: var(--text-secondary);">Email:</span> <a href="mailto:${node.contact_email}" style="color: #60a5fa; text-decoration: none;">${node.contact_email}</a></div>` : ''}
                    </div>
                `;
            }

            // Document type display mapping
            const docTypeLabels = {
                "legislation": "\u{1F3DB}\uFE0F Legislation",
                "regulation": "\u{1F4DC} Regulation",
                "standard": "\u{1F3C5} Standard",
                "framework_official": "\u{1F4CB} Official Framework",
                "best_practice": "\u2705 Best Practice",
                "research_paper": "\u{1F4D1} Research",
                "blog_post": "\u{1F4F0} Blog/News",
                "tool": "\u{1F6E0}\uFE0F Tool",
                "youtube": "\u{1F3AC} YouTube",
                "idea": "\u{1F4A1} Idea",
                "other": "\u{1F4CC} Other"
            };
            const docTypeColors = {
                "legislation": "#fbbf24",
                "regulation": "#f59e0b",
                "standard": "#a78bfa",
                "framework_official": "#818cf8",
                "best_practice": "#34d399",
                "research_paper": "#94a3b8",
                "blog_post": "#64748b",
                "tool": "#60a5fa",
                "youtube": "#ff0000",
                "idea": "#fbbf24",
                "other": "#6b7280"
            };
            const docType = node.document_type || "other";
            const docTypeLabel = docTypeLabels[docType] || docTypeLabels["other"];
            const docTypeColor = docTypeColors[docType] || docTypeColors["other"];
            const docTypeBadge = `<span style="display: inline-block; font-size: 0.65rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background: ${docTypeColor}22; color: ${docTypeColor}; border: 1px solid ${docTypeColor}44; margin-left: 6px;">${docTypeLabel}</span>`;
            const crossDiscBadge = node.is_cross_disciplinary ? `<span style="display: inline-block; font-size: 0.65rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.35); margin-left: 6px;" title="Cross-Disciplinary: This concept bridges multiple research domains">🔀 Cross-Disciplinary</span>` : '';

            content.innerHTML = `
                <div class="detail-header">
                    <span class="${badgeClass}">${label}</span>${docTypeBadge}${crossDiscBadge}
                    <h2 class="detail-title">
                        ${node.url ? `<a href="${node.url}" target="_blank" style="color: inherit; text-decoration: none; border-bottom: 1.5px dashed rgba(255,255,255,0.3); transition: border-color 0.3s;" onmouseover="this.style.borderColor='white'" onmouseout="this.style.borderColor='rgba(255,255,255,0.3)'">${node.title}</a>` : node.title}
                    </h2>
                    <div class="detail-cluster" style="font-size: 0.78rem; line-height: 1.4; color: var(--text-secondary); margin-top: 6px;">
                        <strong style="color: var(--text-primary);">${node.cluster_name}</strong>
                    </div>
                    ${node.topic_name ? `<div style="display: flex; align-items: center; gap: 6px; margin-top: 5px; font-size: 0.72rem; color: var(--text-secondary);">
                        <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: ${getClusterColor(node.cluster_id)}; flex-shrink: 0;"></span>
                        Topic: <span style="color: ${getClusterColor(node.cluster_id)}; font-weight: 500;">${node.topic_name}</span>
                    </div>` : ''}
                </div>
                
                <div class="score-row">
                    <div class="score-card">
                        <div class="score-val">${novStr}</div>
                        <div class="score-label">Novelty</div>
                    </div>
                    <div class="score-card">
                        <div class="score-val">${valStr}</div>
                        <div class="score-label">Validation</div>
                    </div>
                    <div class="score-card">
                        <div class="score-val">${momStr}</div>
                        <div class="score-label">Momentum</div>
                    </div>
                    <div class="score-card">
                        <div class="score-val">${reachStr}</div>
                        <div class="score-label">Reach</div>
                    </div>
                </div>
                
                <div class="detail-section-title">Summary</div>
                <p class="detail-summary">${node.summary}</p>
                
                ${attributionHTML}
                ${contradictionAnalysisHTML}
                ${relationsHTML}
                
                ${node.url ? `
                    <a href="${node.url}" target="_blank" class="btn" style="margin-top: 1.5rem; display: block; text-align: center; text-decoration: none;">
                        Open Original Source
                    </a>
                ` : ''}
                
                ${refreshButtonHTML}
            `;
            
            openDetails();

            if (node.id !== 'sandbox:idea') {
                updateRefreshButtonStatus(node.id);
            }
        }

        // Reusable URL Ingest Helper
        async function ingestUrlDirect(url) {
            closeDetails();
            setLoader(true, `Agent is analyzing your source...<br><span style="font-size: 0.85rem; color: var(--text-secondary); display: block; margin-top: 0.5rem;">Scraping, scoring, and mapping to the research landscape.<br>This can take a few minutes. Please stand by.</span>`);

            try {
                const response = await fetch("/api/ingest-url", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ url: url })
                });

                const data = await response.json();
                
                // Check HTTP status OR explicit status field
                if (!response.ok || data.status === "failed") {
                    setLoader(false);
                    const msg = data.detail || "This webpage blocks automated scrapers or returned unreadable content and cannot be mapped.";
                    showErrorBanner(msg);
                    return;
                }

                showToast(data.message || "Source mapped successfully!", true);
                
                // Load graph data to register the new node element in Cytoscape
                await loadGraphData(false, true);
                
                const targetNode = cy ? cy.getElementById(data.node_id) : null;
                if (targetNode && targetNode.length > 0) {
                    const nodeData = targetNode.data();
                    const nov = (nodeData.novelty !== undefined && nodeData.novelty !== null) ? parseFloat(nodeData.novelty) : 0.5;
                    const val = (nodeData.validation !== undefined && nodeData.validation !== null) ? parseFloat(nodeData.validation) : 0.5;
                    
                    let quad = "frontier";
                    if (nov >= 0.5 && val >= 0.5) quad = "frontier";
                    else if (nov < 0.5 && val >= 0.5) quad = "established";
                    else if (nov >= 0.5 && val < 0.5) quad = "speculative";
                    else quad = "noise";
                    
                    // Set active quadrant filter so all nodes in this quadrant across all categories are displayed
                    activeQuadrants = [quad];
                    activeCategoryId = null;
                    activeDomainId = null;
                    currentViewMode = "map";
                    
                    // Ensure map container is visible BEFORE reloading so Cytoscape gets real dimensions
                    document.getElementById("cy").style.display = "block";
                    document.getElementById("list-container").style.display = "none";
                    const qc = document.getElementById("quadrant-container");
                    if (qc) qc.style.display = "none";
                    
                    await loadGraphData(false, true);
                    
                    // Force Cytoscape to recalculate container bounds after showing
                    if (cy) cy.resize();
                    
                    // Re-query Cytoscape to get the live, freshly rendered node instance
                    const liveTargetNode = cy ? cy.getElementById(data.node_id) : null;
                    if (liveTargetNode && liveTargetNode.length > 0) {
                        // Make sure the node is visible (not filtered out)
                        liveTargetNode.style('display', 'element');
                        liveTargetNode.removeClass('dimmed-context');
                        liveTargetNode.select();
                        displayNodeDetails(liveTargetNode.data());
                        
                        // Fit camera to the target node with generous padding
                        setTimeout(() => {
                            if (cy) {
                                cy.resize();
                                const visibleNodes = cy.nodes().filter(n => n.style('display') === 'element');
                                if (visibleNodes.length > 0) {
                                    cy.fit(visibleNodes, 80);
                                }
                            }
                        }, 150);
                        
                        // Eye-catcher scale pulse animation
                        const origW = liveTargetNode.style('width') || '22px';
                        const origH = liveTargetNode.style('height') || '22px';
                        liveTargetNode.animate({ style: { 'width': '42px', 'height': '42px', 'border-width': '6px' } }, { duration: 350 })
                            .delay(100)
                            .animate({ style: { 'width': origW, 'height': origH, 'border-width': '2px' } }, { duration: 350 });
                        
                        // 30-second continuous breathing highlight loop
                        animateNodeBorderBreathing(liveTargetNode, 30000);
                        refitCameraViewport(true);
                    }
                }

                // Hide loader only when graph, node highlight, card display, and camera framing are 100% ready
                setLoader(false);

            } catch (err) {
                console.error("URL Ingestion failed:", err);
                setLoader(false);
                showErrorBanner("Connection failed. Unable to reach the server or scrape the URL.");
            }
        }

        // Ingest URL source
        async function triggerIngestUrl(e) {
            e.preventDefault();
            const urlInput = document.getElementById("ingest-url");
            const url = urlInput.value.trim();
            if (!url) return;
            urlInput.value = ""; // Clear input immediately for next query
            await ingestUrlDirect(url);
        }

        /* ============================================================
         * DEACTIVATED: Manual Fallback Ingestion — Feature not implemented.
         * Manual ingestion bypasses the automated scoring/classification
         * pipeline and cannot guarantee consistency. All sources must go
         * through the automated Add Source or Scouting pipelines.
         * ============================================================ */
        // function closeManualFallbackModal() { ... }
        // async function submitManualFallback(e) { ... }

        // Ingest form submission
        async function triggerIngest(e) {
            e.preventDefault();
            const queryInput = document.getElementById("ingest-query");
            const query = queryInput.value.trim();
            if (!query) return;
            closeDetails();
            queryInput.value = ""; // Clear input immediately for next query

            // F10: Detect URL input and redirect to Add Source flow
            if (/^https?:\/\//i.test(query)) {
                showToast("URL detected — redirecting to Add Source.", true);
                await ingestUrlDirect(query);
                return;
            }

            setLoader(true, `Agent is scouting databases for '${query}'...<br><span style="font-size: 0.85rem; color: var(--text-secondary); display: block; margin-top: 0.5rem;">Discovering, scoring, and mapping relevant research.<br>This can take a few minutes. Please stand by.</span>`);
            
            try {
                const response = await fetch("/api/ingest", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ query: query, max_results: 4 })
                });
                
                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.detail || "Scouting request failed.");
                }
                
                const data = await response.json();
                await loadGraphData(false, true);
                setLoader(false);
                
                // Distinguish truly new nodes (orange) from all processed/related nodes (context)
                const allScoutedIds = new Set(data.node_ids || []);
                const trulyNewIds = new Set(data.new_node_ids || []);
                console.log(`[Scout] Server: ${allScoutedIds.size} total, ${trulyNewIds.size} truly new`);
                
                // Pre-compute category filter IMMEDIATELY so nodes are hidden before any render
                // Only use trulyNewIds for category scoping (not all scouted — too broad)
                const preCatIds = new Set();
                if (cy && trulyNewIds.size > 0) {
                    cy.nodes().forEach(n => {
                        if (trulyNewIds.has(n.id()) && n.data('parent_category_id')) {
                            preCatIds.add(n.data('parent_category_id'));
                        }
                    });
                }
                if (preCatIds.size > 0) {
                    scoutedCategoryIds = preCatIds;
                    currentViewMode = "map";
                    document.getElementById("cy").style.display = "block";
                    document.getElementById("list-container").style.display = "none";
                    const qc = document.getElementById("quadrant-container");
                    if (qc) qc.style.display = "none";
                    if (updateZoomView) updateZoomView();
                    console.log(`[Scout] Pre-set category filter: ${preCatIds.size} categories, hiding non-matching nodes`);
                } else {
                    // No new nodes (cached result): show only the directly scouted nodes, no category expansion
                    scoutedCategoryIds = new Set(['__direct_only__']);
                    currentViewMode = "map";
                    document.getElementById("cy").style.display = "block";
                    document.getElementById("list-container").style.display = "none";
                    const qc = document.getElementById("quadrant-container");
                    if (qc) qc.style.display = "none";
                    // Mark scouted nodes as is_context so they show through the filter
                    cy.nodes().forEach(n => {
                        if (allScoutedIds.has(n.id())) {
                            n.data('is_context', true);
                        }
                    });
                    if (updateZoomView) updateZoomView();
                    console.log(`[Scout] Cached result (0 new): showing ${allScoutedIds.size} directly matched nodes only`);
                }
                
                // Delay navigation for camera fit and animations (filter already applied above)
                setTimeout(() => {
                    navigateToNewNodes(allScoutedIds, trulyNewIds);
                    const newCount = trulyNewIds.size;
                    const existingCount = allScoutedIds.size - trulyNewIds.size;
                    if (data.status === "Cached") {
                        showToast(`Topic already scouted recently. Showing ${allScoutedIds.size} most related nodes.`, true, 10000);
                    } else if (newCount > 0) {
                        showToast(`${newCount} new finding${newCount !== 1 ? 's' : ''} discovered, ${existingCount} most related node${existingCount !== 1 ? 's' : ''} shown.`, true, 10000);
                    } else {
                        showToast(`No new findings. Showing ${existingCount} most related node${existingCount !== 1 ? 's' : ''}.`, true, 10000);
                    }
                }, 350);
            } catch (err) {
                console.error("Ingestion request failed:", err);
                setLoader(false);
                showToast(err.message || "Scouting request failed.");
            }
        }

        // Sandbox modal transfer state
        let tempSandboxTitle = "";
        let tempSandboxSummary = "";

        // Open sandbox declaration modal
        function openSandboxDeclarationModal(e) {
            if (e) e.preventDefault();
            const titleInput = document.getElementById("sandbox-title");
            const summaryInput = document.getElementById("sandbox-summary");
            const title = titleInput.value.trim();
            const summary = summaryInput.value.trim();
            
            if (!title || !summary) return;
            
            // Check description word length (>= 100 words)
            const wordCount = summary.split(/\s+/).filter(w => w.length > 0).length;
            if (wordCount < 100) {
                showToast(`Description is too short (${wordCount}/100 words). Please expand it to at least 100 words so the agent can evaluate it accurately without hallucinations.`, false);
                return;
            }
            
            tempSandboxTitle = title;
            tempSandboxSummary = summary;
            
            // Clear Sandbox input fields immediately for next pitch
            titleInput.value = "";
            summaryInput.value = "";
            
            document.getElementById("modal-sandbox-declare").classList.add("active");
        }

        // Close sandbox declaration modal
        function closeSandboxDeclarationModal() {
            document.getElementById("modal-sandbox-declare").classList.remove("active");
            document.getElementById("sandbox-pub-url").value = "";
        }

        // Submit sandbox declaration modal
        async function submitSandboxDeclaration(e) {
            e.preventDefault();
            const url = document.getElementById("sandbox-pub-url").value.trim();
            closeSandboxDeclarationModal();
            await analyzeIdeaActual(tempSandboxTitle, tempSandboxSummary, url || null);
        }

        // Wrapper compatibility function
        async function analyzeIdea(e) {
            openSandboxDeclarationModal(e);
        }

        // Actual Sandbox pitch analysis
        // Actual Sandbox pitch analysis
        async function analyzeIdeaActual(title, summary, url = null, silent = false) {
            closeDetails();
            // Instantly render a draft sandbox node on the map to give immediate feedback
            sandboxNode = {
                group: "nodes",
                data: {
                    id: "sandbox:idea",
                    title: `[Analyzing] ${title}`,
                    summary: summary,
                    source_type: "sandbox",
                    novelty: 0.5,
                    validation: url ? 0.45 : 0.1,
                    momentum: 0.3,
                    reach: 0.0,
                    dot_size: 17,
                    cluster_id: "general_ai",
                    cluster_name: "General AI",
                    category_id: "general_ai",
                    category_name: "General AI",
                    is_analyzing: true,
                    contradiction_analysis: "An agent is analyzing your idea against the research landscape. This can take a few minutes. Please stand by."
                }
            };
            sandboxEdges = [];

            // Switch view mode to map and reload graph immediately to render the draft node
            currentViewMode = "map";
            activeCategoryId = "general_ai";
            activeCategoryName = "General AI";
            activeDomainId = null;
            activeQuadrants = [];
            scoutedCategoryIds = null;

            await loadGraphData(false, true);

            // Select and display details for the analyzing draft node
            const draftNodeCy = cy ? cy.getElementById("sandbox:idea") : null;
            if (draftNodeCy && draftNodeCy.length > 0) {
                draftNodeCy.select();
                displayNodeDetails(sandboxNode.data);
                
                // Focus camera on the analyzing draft node
                cy.animate({
                    fit: { eles: draftNodeCy, padding: 120 },
                    duration: 800
                });
            }

            // Clean up sandbox inputs
            document.getElementById("sandbox-title").value = "";
            document.getElementById("sandbox-summary").value = "";
            document.getElementById("sandbox-pub-url").value = "";

            // Fire the heavy agent analysis asynchronously without blocking the UI
            fetch("/api/analyze-idea", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title, summary, url })
            })
            .then(async (response) => {
                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.detail || "Concept analysis failed.");
                }
                const data = await response.json();

                // Handle de-duplication redirection payload
                if (data && data.status === "redirected") {
                    sandboxNode = null;
                    sandboxEdges = [];
                    await loadGraphData();
                    
                    const match = data.matched_node;
                    showToast(`Source already mapped: "${match.title}"! Redirecting...`, true);
                    
                    activeCategoryId = match.category_id;
                    activeCategoryName = match.category_name;
                    
                    const targetNode = cy.getElementById(match.id);
                    if (targetNode.length > 0) {
                        targetNode.select();
                        displayNodeDetails(targetNode.data());
                        animateNodeBorderBreathing(targetNode, 30000);
                        
                        const catNodes = cy.nodes().filter(n => !n.data('is_cluster_bubble') && n.data('category_id') === match.category_id);
                        cy.animate({
                            fit: { eles: catNodes, padding: 80 },
                            duration: 900
                        });
                    }
                    return;
                }

                // Update the sandbox node with actual values returned by the agent
                sandboxNode = {
                    group: "nodes",
                    data: {
                        id: "sandbox:idea",
                        title: `[Sandbox] ${data.title}`,
                        summary: data.summary,
                        source_type: "sandbox",
                        novelty: data.novelty,
                        validation: data.validation,
                        momentum: data.momentum,
                        reach: data.reach || 0.0,
                        dot_size: Math.min(50, Math.round(10 + (data.momentum || 0.3) * 22 + (data.reach || 0) * 18)),
                        cluster_id: data.cluster_id,
                        cluster_name: data.cluster_name,
                        category_id: data.category_id || data.cluster_id,
                        category_name: data.category_name || data.cluster_name,
                        is_analyzing: false,
                        contradiction_analysis: data.contradiction_analysis
                    }
                };

                // Parse suggested edges
                sandboxEdges = [];
                if (data.suggested_edges && data.suggested_edges.length > 0) {
                    data.suggested_edges.forEach(e => {
                        sandboxEdges.push({
                            group: "edges",
                            data: {
                                id: `sandbox-edge-${e.target_id}`,
                                source: "sandbox:idea",
                                target: e.target_id,
                                relationship_type: e.relationship_type,
                                similarity: parseFloat(e.similarity) || 0.5,
                                reasoning: e.reasoning || ""
                            }
                        });
                    });
                }

                // Switch active views to place the node in its real category cluster
                activeCategoryId = data.category_id || data.cluster_id;
                activeCategoryName = data.category_name || data.cluster_name;

                await loadGraphData(false, true); // Preserve selection

                // Refresh details card and pulse only if the user is still looking at this sandbox idea
                const currentSelected = cy.nodes(':selected');
                if (currentSelected.length > 0 && currentSelected.id() === "sandbox:idea") {
                    displayNodeDetails(sandboxNode.data);
                    
                    const sandboxNodeCy = cy.getElementById("sandbox:idea");
                    if (sandboxNodeCy.length > 0) {
                        // Quick attention scale pulse
                        sandboxNodeCy.animate({
                            style: { 'width': '38px', 'height': '38px' }
                        }, { duration: 350 }).delay(100).animate({
                            style: { 'width': '24px', 'height': '24px' }
                        }, { duration: 350 });

                        // Focus camera on the category cluster and the star node
                        const catNodes = cy.nodes().filter(n => !n.data('is_cluster_bubble') && n.data('category_id') === activeCategoryId);
                        const fitNodes = catNodes.union(sandboxNodeCy);
                        cy.animate({
                            fit: { eles: fitNodes, padding: 80 },
                            duration: 900
                        });
                    }
                }

                // Enable active sandbox save actions
                document.getElementById("sandbox-initial-actions").style.display = "none";
                document.getElementById("sandbox-active-actions").style.display = "flex";

                if (data.scout_query) {
                    showToast(`Concept mapped! Auto-scouting started for: "${data.scout_query}"`, true);
                    startAutoScoutPolling();
                } else {
                    showToast("Concept mapped! Check the STAR node on the map.", true);
                }
            })
            .catch((err) => {
                console.error("Background sandbox analysis failed:", err);
                sandboxNode = null;
                sandboxEdges = [];
                loadGraphData();
                showToast(err.message || "Background analysis failed.");
            });
        }

        function toggleAttributionFields() {
            const check = document.getElementById("sandbox-attribute-check");
            const fields = document.getElementById("sandbox-attribution-fields");
            if (check.checked) {
                fields.style.display = "flex";
            } else {
                fields.style.display = "none";
            }
        }

        async function promoteSandboxIdea() {
            if (!sandboxNode) {
                showToast("No active sandbox idea to save.");
                return;
            }
            if (sandboxNode.data && sandboxNode.data.is_analyzing) {
                showToast("Concept is still being analyzed. Please wait until evaluation finishes.", true);
                return;
            }
            
            const isAttributed = document.getElementById("sandbox-attribute-check").checked;
            let name = null;
            let linkedin = null;
            let email = null;
            
            if (isAttributed) {
                name = document.getElementById("sandbox-author-name").value.trim();
                linkedin = document.getElementById("sandbox-author-linkedin").value.trim();
                email = document.getElementById("sandbox-author-email").value.trim();
                
                if (!name && !linkedin && !email) {
                    showToast("Attribution selected. Please fill in at least one contact field.");
                    return;
                }
            }
            
            setLoader(true, "Saving your concept permanently to the map...");
            
            try {
                const payload = {
                    title: sandboxNode.data.title.replace("[Sandbox] ", ""),
                    summary: sandboxNode.data.summary,
                    novelty: sandboxNode.data.novelty,
                    validation: sandboxNode.data.validation,
                    momentum: sandboxNode.data.momentum,
                    cluster_id: sandboxNode.data.cluster_id,
                    contact_name: name || null,
                    contact_linkedin: linkedin || null,
                    contact_email: email || null
                };
                
                const response = await fetch("/api/promote-idea", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                
                if (!response.ok) {
                    throw new Error("Failed to promote concept.");
                }
                
                // Clear sandbox state
                sandboxNode = null;
                
                // Clear input fields
                document.getElementById("sandbox-title").value = "";
                document.getElementById("sandbox-summary").value = "";
                document.getElementById("sandbox-attribute-check").checked = false;
                document.getElementById("sandbox-author-name").value = "";
                document.getElementById("sandbox-author-linkedin").value = "";
                document.getElementById("sandbox-author-email").value = "";
                document.getElementById("sandbox-attribution-fields").style.display = "none";
                
                // Reset action buttons
                document.getElementById("sandbox-initial-actions").style.display = "block";
                document.getElementById("sandbox-active-actions").style.display = "none";
                
                closeDetails();
                await loadGraphData();
                setLoader(false);
                showToast("Concept saved permanently! Refreshing radar map.", true);
            } catch (err) {
                console.error("Promoting idea failed:", err);
                setLoader(false);
                showToast(err.message || "Failed to promote concept.");
            }
        }

        let pollingInterval = null;
        let pollingAttempts = 0;
        let initialNodeCount = 0;

        function startAutoScoutPolling() {
            if (pollingInterval) clearInterval(pollingInterval);
            pollingAttempts = 0;
            initialNodeCount = cy ? cy.nodes().filter(n => !n.data('is_cluster_bubble') && n.data('id') !== 'sandbox:idea').length : 0;
            
            pollingInterval = setInterval(async () => {
                pollingAttempts++;
                if (pollingAttempts > 30) { // Poll for 30 attempts * 10 seconds = 300 seconds (5 minutes)
                    clearInterval(pollingInterval);
                    console.log("[ConceptRadar Polling] Reached max polling attempts (5 minutes). Stopping background checks.");
                    return;
                }
                
                try {
                    const elements = await fetchGraphElements();
                    const currentL3Count = elements.filter(el => el.group === "nodes" && !el.data.is_cluster_bubble).length;
                    if (currentL3Count > initialNodeCount) {
                        console.log(`[ConceptRadar Polling] Detected new nodes in DB (${currentL3Count} vs ${initialNodeCount}). Refreshing map!`);
                        clearInterval(pollingInterval);
                        await loadGraphData(false, true); // Preserve selection so the card remains open
                        
                        // Re-evaluate speculative sandbox concept silently against newly enriched database with a 3-minute delay
                        const sandboxNodeCy = cy ? cy.getElementById("sandbox:idea") : null;
                        if (sandboxNodeCy && tempSandboxTitle && tempSandboxSummary) {
                            setTimeout(async () => {
                                const checkNode = cy ? cy.getElementById("sandbox:idea") : null;
                                if (checkNode && tempSandboxTitle && tempSandboxSummary) {
                                    // Runs completely silently in the background
                                    await analyzeIdeaActual(tempSandboxTitle, tempSandboxSummary, null, true);
                                }
                            }, 180000);
                        }
                    }
                } catch (e) {
                    console.error("Error during auto-scout polling:", e);
                }
            }, 10000);
        }

        function animateNodeBorderBreathing(targetNode, durationMs = 30000) {
            if (!targetNode || targetNode.length === 0) return;
            const startTime = Date.now();
            const intervalTime = 1800; // 1.8 seconds per cycle
            
            const pulse = () => {
                // If Cytoscape is gone, node is removed, user selected another node, or time expired: stop.
                if (!cy || targetNode.removed() || !targetNode.selected() || (Date.now() - startTime > durationMs)) {
                    clearInterval(intervalId);
                    if (cy && !targetNode.removed()) {
                        // Reset to standard selected style
                        targetNode.animate({
                            style: {
                                'border-width': '3px',
                                'border-color': '#ffffff'
                            }
                        }, { duration: 300 });
                    }
                    return;
                }
                
                targetNode.animate({
                    style: {
                        'border-width': '7px',
                        'border-color': '#ffffff'
                    }
                }, {
                    duration: 800
                }).delay(100).animate({
                    style: {
                        'border-width': '3px',
                        'border-color': '#ffffff'
                    }
                }, {
                    duration: 800
                });
            };
            
            pulse();
            const intervalId = setInterval(pulse, intervalTime);
        }

        async function updateRefreshButtonStatus(nodeId) {
            const btn = document.getElementById("refresh-node-btn");
            const statusDiv = document.getElementById("refresh-node-status");
            if (!btn || !statusDiv) return;
            
            try {
                const response = await fetch(`/api/refresh-status/${encodeURIComponent(nodeId)}`);
                const data = await response.json();
                
                if (data.allowed === false) {
                    btn.disabled = true;
                    btn.style.opacity = "0.5";
                    btn.style.cursor = "not-allowed";
                    btn.title = data.reason;
                    statusDiv.innerText = data.reason;
                    statusDiv.style.color = "#ef4444"; // Red for locked
                } else {
                    btn.disabled = false;
                    btn.style.opacity = "1";
                    btn.style.cursor = "pointer";
                    btn.title = "";
                    statusDiv.innerText = `Refreshes remaining: ${data.refreshes_remaining} (max 3 per 14d)`;
                    statusDiv.style.color = "var(--text-secondary)";
                }
            } catch (e) {
                console.error("Error fetching refresh status:", e);
                statusDiv.innerText = "Error checking limit status.";
            }
        }
        
        async function handleManualNodeRefresh(nodeId) {
            const btn = document.getElementById("refresh-node-btn");
            const statusDiv = document.getElementById("refresh-node-status");
            if (!btn || btn.disabled) return;
            
            setLoader(true, "Re-evaluating concept against updated database...");
            
            try {
                const response = await fetch("/api/refresh-node", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ node_id: nodeId })
                });
                
                const data = await response.json();
                setLoader(false);
                
                if (!response.ok) {
                    showToast(data.detail || "Failed to refresh node.");
                    updateRefreshButtonStatus(nodeId);
                    return;
                }
                
                showToast("Node re-evaluated successfully!", true);
                
                // Reload graph to reflect new positions/scores
                await loadGraphData();
                
                // Reselect the node to show updated values in the sidebar card
                setTimeout(() => {
                    const targetNode = cy.getElementById(nodeId);
                    if (targetNode.length > 0) {
                        targetNode.select();
                        displayNodeDetails(targetNode.data());
                    }
                }, 200);
            } catch (e) {
                setLoader(false);
                console.error("Error refreshing node:", e);
                showToast("Failed to refresh node. Please check your connection.");
            }
        }

        function toggleRelationshipHelp(event) {
            if (event) event.stopPropagation();
            const panel = document.getElementById("relationship-help-panel");
            const btn = event.currentTarget;
            if (panel.style.display === "none") {
                panel.style.display = "block";
                btn.style.color = "#a78bfa";
            } else {
                panel.style.display = "none";
                btn.style.color = "rgba(255,255,255,0.4)";
            }
        }

        // Initial Load on page startup (F5)
        // When loaded as external script at end of body, DOMContentLoaded may have already fired
        function _initApp() {
            loadGraphData(true);

            // Clean up copied text on paste in sandbox title/description
            const sTitle = document.getElementById("sandbox-title");
            const sSummary = document.getElementById("sandbox-summary");
            
            if (sTitle) {
                sTitle.addEventListener("paste", function(e) {
                    e.preventDefault();
                    const text = (e.clipboardData || window.clipboardData).getData("text");
                    // Strip all newlines and multiple spaces for the Title
                    const cleaned = text.replace(/[\r\n]+/g, " ").replace(/\s\s+/g, " ").trim();
                    
                    // Insert at selection
                    const start = this.selectionStart;
                    const end = this.selectionEnd;
                    this.value = this.value.substring(0, start) + cleaned + this.value.substring(end);
                    this.selectionStart = this.selectionEnd = start + cleaned.length;
                    this.dispatchEvent(new Event("input"));
                });
            }
            
            if (sSummary) {
                sSummary.addEventListener("paste", function(e) {
                    e.preventDefault();
                    const text = (e.clipboardData || window.clipboardData).getData("text");
                    // Clean up: join single newlines (PDF wrapping), but keep double newlines (paragraphs)
                    let cleaned = text.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n");
                    cleaned = cleaned.split("\n\n").map(paragraph => {
                        return paragraph.replace(/\n/g, " ").replace(/\s\s+/g, " ").trim();
                    }).join("\n\n");
                    
                    // Insert at selection
                    const start = this.selectionStart;
                    const end = this.selectionEnd;
                    this.value = this.value.substring(0, start) + cleaned + this.value.substring(end);
                    this.selectionStart = this.selectionEnd = start + cleaned.length;
                    this.dispatchEvent(new Event("input"));
                });
            }

            // Reset to full graph when any input field gets focus
            document.querySelectorAll('input, textarea').forEach(field => {
                field.addEventListener('focus', () => resetToFullMap());
            });

            // Mini-Grid Quadrant Event Listeners (Registered once)
            document.querySelectorAll('.mini-quadrant').forEach(quad => {
                quad.style.cursor = 'pointer';
                
                quad.addEventListener('click', async function() {
                    closeDetails(); // Close card on quadrant filter change
                    const q = this.getAttribute('data-quadrant');
                    
                    // Toggle presence in activeQuadrants
                    const idx = activeQuadrants.indexOf(q);
                    if (idx > -1) {
                        activeQuadrants.splice(idx, 1);
                    } else {
                        activeQuadrants.push(q);
                    }
                    
                    activeCategoryId = null; 
                    activeDomainId = null;
                    userOverrodeSort = false; // Reset so smart default sort applies
                    
                    // Clear hover dimming classes immediately on click!
                    if (cy) {
                        cy.elements().removeClass('dimmed');
                    }
                    
                    if (activeQuadrants.length === 0) {
                        // Reset back to main domains list view
                        currentViewMode = "list";
                        renderListView();
                        if (updateZoomView) updateZoomView();
                        return;
                    }
                    
                    const nodes = getQuadrantNodes(activeQuadrants);
                    
                    // Always land on Map View FIRST when selecting any quadrant
                    currentViewMode = "map";
                    
                    renderListView(); // hides list view
                    renderConceptListView(); // hides concept list view
                    
                    document.getElementById("cy").style.display = "block";
                    
                    await loadGraphData(false, true); // Updates node display visibility for activeQuadrants
                    
                    if (cy) {
                        cy.resize(); // Force Cytoscape to recalculate container bounds!
                    }
                    
                    // Recalculate coordinates for map mode
                    window.dispatchEvent(new Event('resize'));
                    
                    // Fit to selected quadrant nodes
                    if (cy) {
                        const cyNodes = cy.nodes().filter(n => {
                            if (n.data('is_cluster_bubble')) return false;
                            const nov = (n.data('novelty') !== undefined && n.data('novelty') !== null) ? parseFloat(n.data('novelty')) : 0.5;
                            const val = (n.data('validation') !== undefined && n.data('validation') !== null) ? parseFloat(n.data('validation')) : 0.5;
                            
                            let matches = false;
                            activeQuadrants.forEach(aq => {
                                if (aq === 'established' && nov < 0.5 && val >= 0.5) matches = true;
                                if (aq === 'frontier' && nov >= 0.5 && val >= 0.5) matches = true;
                                if (aq === 'noise' && nov < 0.5 && val < 0.5) matches = true;
                                if (aq === 'speculative' && nov >= 0.5 && val < 0.5) matches = true;
                            });
                            return matches;
                        });
                        
                        if (cyNodes.length > 0) {
                            cy.fit(cyNodes, 80);
                            if (cy.zoom() > 1.3) {
                                cy.zoom(1.2);
                                cy.center();
                            }
                        } else {
                            cy.fit(cy.nodes(), 80);
                        }
                    }
                    
                    if (updateZoomView) updateZoomView();
                });

                quad.addEventListener('mouseenter', function() {
                    if (!cy || activeQuadrants.length > 0) return; // Skip hover dimming if active quadrant filter is set
                    
                    const q = this.getAttribute('data-quadrant');

                    cy.nodes().forEach(node => {
                        if (node.data('is_cluster_bubble')) return; // Ignore cluster bubbles
                        
                        const nov = node.data('novelty');
                        const val = node.data('validation');
                        if (nov === undefined || val === undefined) return;
                        
                        let matches = false;
                        if (q === 'established') matches = (nov < 0.5 && val >= 0.5);
                        else if (q === 'frontier') matches = (nov >= 0.5 && val >= 0.5);
                        else if (q === 'noise') matches = (nov < 0.5 && val < 0.5);
                        else if (q === 'speculative') matches = (nov >= 0.5 && val < 0.5);
                        
                        if (matches) {
                            node.removeClass('dimmed');
                        } else {
                            node.addClass('dimmed');
                        }
                    });
                    
                    // Dim edges to focus purely on selected quadrant nodes
                    cy.edges().addClass('dimmed');
                });
                
                quad.addEventListener('mouseleave', function() {
                    if (cy) cy.elements().removeClass('dimmed');
                });
            });
            
            // Adjust coordinates on window resize
            window.addEventListener("resize", () => {
                if (cy && currentViewMode === "map") {
                    const container = document.getElementById("cy");
                    const w = container.offsetWidth;
                    const h = container.offsetHeight;
                    if (w === 0 || h === 0) return;
                    
                    const centerX = w / 2;
                    const centerY = h / 2;
                    
                    const positionCounts = {};
                    
                    // Extract active cluster IDs present in the graph to calculate repulsion offsets
                    const activeClusterNodes = cy.nodes().filter(node => !node.data("is_cluster_bubble") && node.data("cluster_id"));
                    const activeClusterIds = Array.from(new Set(activeClusterNodes.map(node => node.data("cluster_id")))).sort();
                    
                    // Pre-calculate sizing metrics for virtual bubbles
                    const l1Nodes = cy.nodes().filter(node => node.data("is_cluster_bubble") && node.data("level") === 1);
                    const l2Nodes = cy.nodes().filter(node => node.data("is_cluster_bubble") && node.data("level") === 2);
                    
                    const N_L1 = l1Nodes.length;
                    const D_1 = Math.max(140, Math.min(240, (Math.min(w, h) * 0.6) / N_L1));
                    const F_1 = Math.max(12, D_1 * 0.085);
                    
                    l1Nodes.forEach((node) => {
                        const nov = node.data("novelty") !== undefined ? node.data("novelty") : 0.5;
                        const val = node.data("validation") !== undefined ? node.data("validation") : 0.5;
                        node.unlock();
                        node.position(getCoordinates(nov, val, w, h));
                        node.data('dynamic_size', D_1);
                        node.data('dynamic_font', F_1);
                        node.lock();
                    });
                    
                    // Group L2 categories
                    const N_L2 = l2Nodes.length;
                    const D_2 = Math.max(110, Math.min(180, (Math.min(w, h) * 0.5) / (N_L2 || 1)));
                    const F_2 = Math.max(11, D_2 * 0.085);
                    
                    l2Nodes.forEach((node) => {
                        const nov = node.data("novelty") !== undefined ? node.data("novelty") : 0.5;
                        const val = node.data("validation") !== undefined ? node.data("validation") : 0.5;
                        node.unlock();
                        node.position(getCoordinates(nov, val, w, h));
                        node.data('dynamic_size', D_2);
                        node.data('dynamic_font', F_2);
                        node.lock();
                    });
                    
                    // Position leaf (document) nodes with collision avoidance
                    const leafNodes = [];
                    cy.nodes().forEach(node => {
                        const isBubble = node.data("is_cluster_bubble");
                        if (isBubble) return;
                        
                        const nov = node.data("novelty");
                        const val = node.data("validation");
                        const cid = node.data("cluster_id");
                        
                        if (nov !== undefined && val !== undefined) {
                            let coords = getCoordinates(nov, val, w, h);
                            const mom = (node.data("momentum") !== undefined && node.data("momentum") !== null) ? parseFloat(node.data("momentum")) : 0.2;
                            const nodeRadius = 5 + mom * 15;
                            leafNodes.push({ node, x: coords.x, y: coords.y, trueX: coords.x, radius: nodeRadius, nov: parseFloat(nov), val: parseFloat(val) });
                        }
                    });

                    // Only run collision avoidance on VISIBLE nodes (skip hidden/filtered)
                    const visibleLeafNodes = leafNodes.filter(ln => ln.node.style('display') !== 'none');

                    // Run 3 iterations of pairwise repulsion with X spring-back
                    for (let iter = 0; iter < 3; iter++) {
                        for (let i = 0; i < visibleLeafNodes.length; i++) {
                            for (let j = i + 1; j < visibleLeafNodes.length; j++) {
                                const a = visibleLeafNodes[i], b = visibleLeafNodes[j];
                                const dx = b.x - a.x;
                                const dy = b.y - a.y;
                                const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
                                const minDist = a.radius + b.radius + 4;
                                if (dist < minDist) {
                                    const overlap = (minDist - dist) / 2;
                                    const nx = dx / dist, ny = dy / dist;
                                    a.x -= nx * overlap;
                                    a.y -= ny * overlap;
                                    b.x += nx * overlap;
                                    b.y += ny * overlap;
                                }
                            }
                        }
                        // Spring-back: pull X 60% toward true novelty position to preserve ordering
                        const springX = 0.6;
                        for (const p of visibleLeafNodes) {
                            p.x = p.x + springX * (p.trueX - p.x);
                        }
                    }

                    // Clamp to quadrant boundaries and apply positions
                    leafNodes.forEach(({ node, x, y, nov, val }) => {
                        const midX = w / 2;
                        const midY = h / 2;
                        const paddingX = 80, paddingY = 80, margin = 15;

                        if (nov < 0.5) {
                            x = Math.max(paddingX, Math.min(midX - margin, x));
                        } else {
                            x = Math.max(midX + margin, Math.min(w - paddingX, x));
                        }
                        if (val >= 0.5) {
                            y = Math.max(paddingY, Math.min(midY - margin, y));
                        } else {
                            y = Math.max(midY + margin, Math.min(h - paddingY, y));
                        }

                        node.unlock();
                        node.position({ x, y });
                        // Store true position for semantic zoom
                        node.data('trueX', x);
                        node.data('trueY', y);
                        node.lock();
                        if (node.id() === 'sandbox:idea') {
                            console.log("[DEBUG RESIZE POSITION] Sandbox ID:", node.id());
                            console.log("[DEBUG RESIZE POSITION] Sandbox Novelty:", nov, "Validation:", val);
                            console.log("[DEBUG RESIZE POSITION] Sandbox Coordinates:", { x, y });
                        }
                    });
                }
                // Re-apply visibility filters (scout category filter, quadrant filter, etc.)
                if (updateZoomView) updateZoomView();
            });
        }

        // Call immediately if DOM is ready, otherwise wait
        if (document.readyState === "loading") {
            window.addEventListener("DOMContentLoaded", _initApp);
        } else {
            _initApp();
        }

// ===================== Chat Functions =====================

let chatSessionId = null;

function toggleChat() {
    const panel = document.getElementById('chat-panel');
    const bubble = document.getElementById('chat-bubble');
    const isOpen = panel.classList.contains('open');
    
    if (isOpen) {
        panel.classList.remove('open');
        bubble.classList.remove('hidden');
    } else {
        panel.classList.add('open');
        bubble.classList.add('hidden');
        // Generate session ID on first open
        if (!chatSessionId) {
            chatSessionId = crypto.randomUUID();
        }
        document.getElementById('chat-input').focus();
    }
}

async function sendChatMessage(event) {
    event.preventDefault();
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;
    
    const messagesDiv = document.getElementById('chat-messages');
    
    // Add user message
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-message user-message';
    userMsg.innerHTML = `<div class="message-content">${escapeHtml(message)}</div>`;
    messagesDiv.appendChild(userMsg);
    
    input.value = '';
    input.disabled = true;
    document.querySelector('.chat-send-btn').disabled = true;
    
    // Add typing indicator
    const typing = document.createElement('div');
    typing.className = 'typing-indicator';
    typing.id = 'typing-indicator';
    typing.innerHTML = '<span>●</span><span>●</span><span>●</span>';
    messagesDiv.appendChild(typing);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message, session_id: chatSessionId })
        });
        
        // Remove typing indicator
        const typingEl = document.getElementById('typing-indicator');
        if (typingEl) typingEl.remove();
        
        if (!response.ok) {
            throw new Error('Chat request failed');
        }
        
        const data = await response.json();
        
        // Add agent response
        const agentMsg = document.createElement('div');
        agentMsg.className = 'chat-message agent-message';
        // Use parseMarkdown if available, otherwise basic escaping
        const formattedResponse = typeof parseMarkdown === 'function' 
            ? parseMarkdown(data.response) 
            : escapeHtml(data.response).replace(/\n/g, '<br>');
        agentMsg.innerHTML = `<div class="message-content">${formattedResponse}</div>`;
        messagesDiv.appendChild(agentMsg);
    } catch (error) {
        // Remove typing indicator
        const typingEl = document.getElementById('typing-indicator');
        if (typingEl) typingEl.remove();
        
        const errorMsg = document.createElement('div');
        errorMsg.className = 'chat-message agent-message';
        errorMsg.innerHTML = '<div class="message-content">Sorry, I encountered an error. Please try again.</div>';
        messagesDiv.appendChild(errorMsg);
    } finally {
        input.disabled = false;
        document.querySelector('.chat-send-btn').disabled = false;
        input.focus();
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
