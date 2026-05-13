async function loadJourneyDiagram(callId, containerSelector, rowId = '') {
    let url = `/report/call_journey/json?call_id=${callId}`;
    if (rowId) url += `&row_id=${rowId}`;

    const res = await fetch(url);
    const data = await res.json();
    const legs = data.legs;
    const container = document.querySelector(containerSelector);
    if (!legs || !legs.length) {
        container.innerHTML = '<p class="text-center py-4 text-muted"><i class="bi bi-diagram-3 fs-1 d-block mb-2"></i>No journey data available.</p>';
        return;
    }

    container.innerHTML = '';

    // ---------- Detect event type ----------
    function detectEvent(leg, idx, allLegs) {
        const isFirst = idx === 0;
        const isLast  = idx === allLegs.length - 1;
        const prev = idx > 0 ? allLegs[idx - 1] : null;

        if (isFirst) return { icon: 'bi-play-circle-fill', color: '#10b981', label: 'Start', desc: 'Call originated' };
        if (isLast)  return { icon: 'bi-stop-circle-fill', color: '#ef4444', label: 'End', desc: 'Call ended' };

        // Transfer: when Party1 changes from previous leg
        if (prev && (leg.p1_name !== prev.p1_name || leg.p1_device !== prev.p1_device)) {
            const to = leg.p1_name || leg.p1_device || 'another party';
            return { icon: 'bi-arrow-left-right', color: '#f59e0b', label: 'Transfer', desc: `Transferred to ${to}` };
        }

        // Hold detection
        if (leg.hold > 0) {
            return { icon: 'bi-pause-circle', color: '#8b5cf6', label: 'Hold', desc: `On hold for ${leg.hold}s` };
        }

        // Voicemail detection
        if (leg.p2_device && leg.p2_device.startsWith('V')) {
            return { icon: 'bi-voicemail', color: '#6366f1', label: 'Voicemail', desc: 'Call sent to voicemail' };
        }

        // Park detection
        if (leg.park > 0) {
            return { icon: 'bi-p-circle', color: '#14b8a6', label: 'Park', desc: `Parked for ${leg.park}s` };
        }

        return { icon: 'bi-chat-dots-fill', color: '#3b82f6', label: 'Connected', desc: 'Active conversation' };
    }

    // ---------- Format a single leg as a card ----------
    function formatLegCard(leg, idx, allLegs) {
        const direction = leg.direction || 'Outbound';
        const dirColor = direction === 'Inbound' ? '#10b981' : '#f59e0b';
        const dirIcon = direction === 'Inbound' ? 'bi-box-arrow-in-right' : 'bi-box-arrow-right';
        const caller = leg.caller || leg.p1_name || 'Unknown';
        const called = leg.called || leg.p2_name || 'Unknown';
        const fromName = direction === 'Inbound' ? caller : (leg.p1_name || caller);
        const toName   = direction === 'Inbound' ? (leg.p1_name || called) : called;
        const internalLabel = leg.internal ? 'Internal' : 'External';
        const startTime = leg.start_time || '—';
        const duration = leg.duration || '00:00:00';
        const ring = leg.ring || 0;
        const hold = leg.hold || 0;
        const park = leg.park || 0;

        const event = detectEvent(leg, idx, allLegs);
        const isTransfer = event.label === 'Transfer';

        return `
            <div class="journey-leg-card" style="padding:16px; animation: fadeIn 0.5s ease both; ${isTransfer ? 'border-left:4px solid #f59e0b;' : ''}">
                <!-- Event badge -->
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="d-flex align-items-center">
                        <div class="rounded-circle d-flex align-items-center justify-content-center me-2"
                             style="width:34px;height:34px;background:${event.color}20;color:${event.color};font-size:1.2rem;">
                            <i class="bi ${event.icon}"></i>
                        </div>
                        <div>
                            <div class="fw-semibold" style="font-size:0.9rem;color:${event.color}">${event.label}</div>
                            <div class="text-muted small">${event.desc}</div>
                        </div>
                    </div>
                    <span class="badge rounded-pill" style="background:${dirColor}20;color:${dirColor}">
                        <i class="bi ${dirIcon} me-1"></i>${direction}
                    </span>
                </div>

                <!-- Caller → Called -->
                <div class="d-flex align-items-center my-2">
                    <div class="rounded-pill bg-light px-3 py-1 fw-semibold text-dark me-2" style="font-size:0.85rem;">
                        <i class="bi bi-person-fill me-1"></i>${fromName}
                    </div>
                    <i class="bi bi-arrow-right text-muted mx-1"></i>
                    <div class="rounded-pill bg-light px-3 py-1 fw-semibold text-dark" style="font-size:0.85rem;">
                        <i class="bi bi-person-fill me-1"></i>${toName}
                    </div>
                </div>

                <!-- Device info -->
                <div class="text-muted small mb-2 d-flex flex-wrap align-items-center gap-2">
                    <span><i class="bi bi-diagram-2 me-1"></i>${internalLabel}</span>
                    <span>·</span>
                    <span>🕒 ${startTime}</span>
                    <span>·</span>
                    <span>⏱ ${duration}</span>
                    ${ring > 0 ? `<span>·</span><span>🔔 ${ring}s</span>` : ''}
                    ${hold > 0 ? `<span>·</span><span>⏸ ${hold}s</span>` : ''}
                    ${park > 0 ? `<span>·</span><span>🅿 ${park}s</span>` : ''}
                </div>
            </div>
        `;
    }

    // ---------- Determine if a transition from leg[i] to leg[i+1] is a transfer ----------
    function isTransferBetween(prev, curr) {
        return (prev.p1_name !== curr.p1_name) || (prev.p1_device !== curr.p1_device);
    }

    // ---------- Build the diagram ----------
    const nodeHeight = 210;
    const nodeWidth  = 480;
    const spacing    = 40;
    const totalHeight = legs.length * (nodeHeight + spacing) + 60;

    const svg = d3.select(container)
        .append('svg')
        .attr('width', '100%')
        .attr('height', totalHeight)
        .attr('viewBox', `0 0 900 ${totalHeight}`)
        .style('overflow', 'visible');

    // Defs
    const defs = svg.append('defs');

    // Drop shadow filter
    const filter = defs.append('filter').attr('id', 'cardShadow').attr('x', '-10%').attr('y', '-10%').attr('width', '130%').attr('height', '130%');
    filter.append('feDropShadow').attr('dx', 0).attr('dy', 3).attr('stdDeviation', 5).attr('flood-color', '#000000').attr('flood-opacity', 0.1);
    filter.append('feDropShadow').attr('dx', 0).attr('dy', 8).attr('stdDeviation', 10).attr('flood-color', '#000000').attr('flood-opacity', 0.06);

    // Gradient for left accent bar
    const accentGradient = defs.append('linearGradient').attr('id', 'cardAccent').attr('x1', '0%').attr('y1', '0%').attr('x2', '0%').attr('y2', '100%');
    accentGradient.append('stop').attr('offset', '0%').attr('stop-color', '#3b82f6');
    accentGradient.append('stop').attr('offset', '100%').attr('stop-color', '#8b5cf6');

    // Marker for normal arrows
    defs.append('marker')
        .attr('id', 'arrowNormal')
        .attr('viewBox', '0 0 10 10')
        .attr('refX', 5).attr('refY', 5)
        .attr('markerWidth', 6).attr('markerHeight', 6)
        .attr('orient', 'auto-start-reverse')
        .append('path')
        .attr('d', 'M 0 0 L 10 5 L 0 10 z')
        .attr('fill', '#cbd5e1');

    // Marker for transfer arrows
    defs.append('marker')
        .attr('id', 'arrowTransfer')
        .attr('viewBox', '0 0 10 10')
        .attr('refX', 5).attr('refY', 5)
        .attr('markerWidth', 7).attr('markerHeight', 7)
        .attr('orient', 'auto-start-reverse')
        .append('path')
        .attr('d', 'M 0 0 L 10 5 L 0 10 z')
        .attr('fill', '#f59e0b');

    const g = svg.append('g').attr('transform', 'translate(20,20)');

    // Draw connecting lines with transfer distinction
    for (let i = 0; i < legs.length - 1; i++) {
        const y1 = i * (nodeHeight + spacing) + nodeHeight + 10;
        const y2 = (i + 1) * (nodeHeight + spacing) - 10;
        const isTransfer = isTransferBetween(legs[i], legs[i + 1]);

        const line = g.append('line')
            .attr('x1', 450)
            .attr('y1', y1)
            .attr('x2', 450)
            .attr('y2', y2)
            .attr('stroke', isTransfer ? '#f59e0b' : '#cbd5e1')
            .attr('stroke-width', isTransfer ? 3 : 2)
            .attr('stroke-dasharray', isTransfer ? '8,4' : '6,4')
            .attr('opacity', isTransfer ? 1 : 0.6);

        // Arrow head
        g.append('polygon')
            .attr('points', `445,${y2-7} 450,${y2} 455,${y2-7}`)
            .attr('fill', isTransfer ? '#f59e0b' : '#cbd5e1')
            .attr('opacity', isTransfer ? 1 : 0.8);

        // Transfer label
        if (isTransfer) {
            g.append('text')
                .attr('x', 460)
                .attr('y', (y1 + y2) / 2 + 4)
                .attr('fill', '#f59e0b')
                .attr('font-size', '11px')
                .attr('font-family', 'Inter, sans-serif')
                .attr('font-weight', '600')
                .text('⤵ Transfer');
        }
    }

    // Render cards
    legs.forEach((leg, idx) => {
        const y = idx * (nodeHeight + spacing);

        // Background rect for the node (glass effect)
        g.append('rect')
            .attr('x', (900 - nodeWidth) / 2 - 20)
            .attr('y', y - 10)
            .attr('width', nodeWidth + 40)
            .attr('height', nodeHeight + 20)
            .attr('rx', 18)
            .attr('ry', 18)
            .attr('fill', '#ffffff')
            .attr('filter', 'url(#cardShadow)')
            .attr('opacity', 0.95)
            .attr('stroke', '#e2e8f0')
            .attr('stroke-width', 1);

        // Left accent bar
        g.append('rect')
            .attr('x', (900 - nodeWidth) / 2 - 20)
            .attr('y', y - 10)
            .attr('width', 5)
            .attr('height', nodeHeight + 20)
            .attr('rx', 3)
            .attr('fill', 'url(#cardAccent)')
            .attr('filter', 'url(#cardShadow)');

        const fo = g.append('foreignObject')
            .attr('x', (900 - nodeWidth) / 2)
            .attr('y', y)
            .attr('width', nodeWidth)
            .attr('height', nodeHeight)
            .style('overflow', 'visible');

        fo.append('xhtml:div')
            .html(formatLegCard(leg, idx, legs));
    });

    // Add CSS for animation and hover
    const style = document.createElement('style');
    style.textContent = `
        .journey-leg-card {
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            cursor: default;
        }
        .journey-leg-card:hover {
            transform: perspective(600px) rotateX(1deg) scale(1.02);
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    `;
    container.appendChild(style);
}