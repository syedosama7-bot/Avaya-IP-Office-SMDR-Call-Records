async function loadJourneyDiagram(callId, containerSelector, rowId = '') {
    let url = `/report/call_journey/json?call_id=${callId}`;
    if (rowId) url += `&row_id=${rowId}`;

    const res = await fetch(url);
    const data = await res.json();
    const legs = data.legs;
    const container = document.querySelector(containerSelector);
    if (!legs || !legs.length) {
        container.innerHTML = '<p class="text-center py-3 text-muted">No journey data available.</p>';
        return;
    }

    container.innerHTML = '';

    const nodeHeight = 200;    // extra tall to avoid any clipping
    const nodeWidth = 380;     // wider card for better readability
    const spacing = 40;
    const totalHeight = legs.length * (nodeHeight + spacing);

    const svg = d3.select(container)
        .append('svg')
        .attr('width', '100%')
        .attr('height', totalHeight + 20)
        .attr('viewBox', `0 0 820 ${totalHeight + 20}`);

    const g = svg.append('g').attr('transform', 'translate(20,10)');

    // ---------- Helper functions ----------

    function formatDevice(dev) {
        if (!dev) return '';
        if (dev.startsWith('E')) return 'Ext. ' + dev.substring(1);
        if (dev.startsWith('T')) return 'Line ' + dev.substring(1);
        if (dev.startsWith('V')) return 'System ' + dev.substring(1);
        return dev;
    }

    function deviceLabel(dev1, dev2) {
        const d1 = formatDevice(dev1);
        const d2 = formatDevice(dev2);
        if (d1 && d2) return `${d1} → ${d2}`;
        if (d1 || d2) return d1 || d2;
        return '';
    }

    function formatLeg(leg, idx, allLegs) {
        const isFirst = idx === 0;
        const isLast = idx === allLegs.length - 1;
        const direction = leg.direction;
        const callerDisplay = leg.caller || leg.p1_name || 'Unknown';
        const calledDisplay = leg.called || leg.p2_name || 'Unknown';

        let from = '', to = '';
        if (direction === 'Inbound') {
            from = callerDisplay;
            to = leg.p1_name || calledDisplay;
        } else {
            from = leg.p1_name || callerDisplay;
            to = leg.called || calledDisplay;
        }

        let transferBadge = '';
        if (idx > 0 && leg.p1_name !== allLegs[idx - 1].p1_name) {
            transferBadge = '<span class="badge bg-warning text-dark ms-1">TRANSFER</span>';
        }

        const startTime = leg.start_time || '';
        const timeNote = isFirst
            ? '<div class="text-muted" style="font-size:0.7rem;">📍 Original call start (all legs)</div>'
            : '<div class="text-muted" style="font-size:0.7rem;">📍 Same start time (SMDR)</div>';

        const ringInfo = leg.ring > 0 ? `<div>🔔 Ring: ${leg.ring}s</div>` : '';
        const durInfo = leg.duration && leg.duration !== '00:00:00' ? `<div>⏱ Talk: ${leg.duration}</div>` : '';
        const holdInfo = leg.hold > 0 ? `<div>⏸ Hold: ${leg.hold}s</div>` : '';
        const parkInfo = leg.park > 0 ? `<div>🅿 Park: ${leg.park}s</div>` : '';

        const devStr = deviceLabel(leg.p1_device, leg.p2_device);

        return `
            <div style="padding:12px 14px; box-sizing:border-box; height:100%; overflow:hidden;">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <div style="font-weight:600; font-size:0.9rem;">${startTime}</div>
                        ${timeNote}
                    </div>
                    <div>
                        ${isFirst ? '<span class="badge bg-success">START</span>' : ''}
                        ${isLast ? '<span class="badge bg-danger">ENDED</span>' : ''}
                        ${transferBadge}
                    </div>
                </div>
                <div class="mt-2">
                    <div class="fw-semibold" style="font-size:0.95rem;">📞 ${from} → ${to}</div>
                    <div class="small text-muted">${direction} · ${leg.internal ? 'Internal' : 'External'}</div>
                    ${devStr ? `<div class="small text-muted">${devStr}</div>` : ''}
                    <div class="mt-1" style="line-height:1.5;">
                        ${ringInfo}${durInfo}${holdInfo}${parkInfo}
                    </div>
                </div>
            </div>
        `;
    }

    // Draw connecting lines
    for (let i = 0; i < legs.length - 1; i++) {
        g.append('line')
            .attr('class', 'journey-line')
            .attr('x1', 400)
            .attr('y1', i * (nodeHeight + spacing) + nodeHeight)
            .attr('x2', 400)
            .attr('y2', (i + 1) * (nodeHeight + spacing))
            .attr('stroke-dasharray', '5,5');
    }

    // Draw nodes
    legs.forEach((leg, idx) => {
        const y = idx * (nodeHeight + spacing);
        const isInternal = leg.internal == 1;

        const fo = g.append('foreignObject')
            .attr('x', (800 - nodeWidth) / 2)
            .attr('y', y)
            .attr('width', nodeWidth)
            .attr('height', nodeHeight)
            .style('overflow', 'visible');   // important: don't clip content

        fo.append('xhtml:div')
            .attr('class', `journey-node ${isInternal ? 'internal' : 'external'}`)
            .html(formatLeg(leg, idx, legs));
    });
}
