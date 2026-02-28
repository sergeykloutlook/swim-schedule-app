document.addEventListener('DOMContentLoaded', () => {
    // Elements
    const uploadArea = document.getElementById('uploadArea');
    const pdfInput = document.getElementById('pdfInput');
    const fileName = document.getElementById('fileName');
    const parseBtn = document.getElementById('parseBtn');
    const eventsSection = document.getElementById('eventsSection');
    const eventsList = document.getElementById('eventsList');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const deselectAllBtn = document.getElementById('deselectAllBtn');
    const attendeesSection = document.getElementById('attendeesSection');
    const attendeeEmail = document.getElementById('attendeeEmail');
    const addAttendeeBtn = document.getElementById('addAttendeeBtn');
    const attendeesList = document.getElementById('attendeesList');
    const sendSection = document.getElementById('sendSection');
    const sendBtn = document.getElementById('sendBtn');
    const resultsSection = document.getElementById('resultsSection');
    const resultsList = document.getElementById('resultsList');
    const loadingOverlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');

    const testUxBtn = document.getElementById('testUxBtn');

    const LOCATIONS = {
        MW: { name: "Mary Wayte Swimming Pool", address: "8815 SE 40th St, Mercer Island, WA 98040" },
        MICC: { name: "Mercer Island Country Club", address: "8700 SE 71st St, Mercer Island, WA 98040" },
        MIBC: { name: "Mercer Island Beach Club", address: "8326 Avalon Dr, Mercer Island, WA 98040" },
        PL: { name: "Phantom Lake Bath & Tennis Club", address: "15810 SE 24th St, Bellevue, WA 98008" },
    };

    let selectedFile = null;
    let parsedEvents = [];
    let attendees = [];

    // Test UX with synthetic data
    testUxBtn.addEventListener('click', () => {
        parsedEvents = [
            { child: "Nastya", team: "JUN2", date: "Jan 5, 2026", time: "5:00 PM - 8:00 PM", location_code: "MW", location_name: "Mary Wayte Swimming Pool", location_address: "8815 SE 40th St, Mercer Island, WA 98040", title: "Nastya @MW 5:00 PM - 8:00 PM DL", dl: true },
            { child: "Liza", team: "JUN1 R", date: "Jan 5, 2026", time: "5:00 PM - 6:30 PM", location_code: "MICC", location_name: "Mercer Island Country Club", location_address: "8700 SE 71st St, Mercer Island, WA 98040", title: "Liza @MICC 5:00 PM - 6:30 PM", dl: false },
            { child: "Kseniya", team: "JUN1 B", date: "Jan 5, 2026", time: "6:00 PM - 7:30 PM", location_code: "MICC", location_name: "Mercer Island Country Club", location_address: "8700 SE 71st St, Mercer Island, WA 98040", title: "Kseniya @MICC 6:00 PM - 7:30 PM", dl: false },
            { child: "Nastya", team: "JUN2", date: "Jan 6, 2026", time: "6:30 PM - 8:00 PM", location_code: "MW", location_name: "Mary Wayte Swimming Pool", location_address: "8815 SE 40th St, Mercer Island, WA 98040", title: "Nastya @MW 6:30 PM - 8:00 PM", dl: false },
            { child: "Liza", team: "JUN1 R", date: "Jan 6, 2026", time: "11:00 AM - 12:30 PM", location_code: "MICC", location_name: "Mercer Island Country Club", location_address: "8700 SE 71st St, Mercer Island, WA 98040", title: "Liza @MICC 11:00 AM - 12:30 PM", dl: false },
            { child: "Kseniya", team: "JUN1 B", date: "Jan 7, 2026", time: "6:00 PM - 7:30 PM", location_code: "PL", location_name: "Phantom Lake Bath & Tennis Club", location_address: "15810 SE 24th St, Bellevue, WA 98008", title: "Kseniya @PL 6:00 PM - 7:30 PM", dl: false },
            { child: "Nastya", team: "JUN2", date: "Jan 7, 2026", time: "5:30 PM - 8:00 PM", location_code: "MW", location_name: "Mary Wayte Swimming Pool", location_address: "8815 SE 40th St, Mercer Island, WA 98040", title: "Nastya @MW 5:30 PM - 8:00 PM DL", dl: true },
            { child: "Liza", team: "JUN1 R", date: "Jan 8, 2026", time: "5:00 PM - 6:30 PM", location_code: "MIBC", location_name: "Mercer Island Beach Club", location_address: "8326 Avalon Dr, Mercer Island, WA 98040", title: "Liza @MIBC 5:00 PM - 6:30 PM", dl: false },
        ];
        const mockMisalignments = [
            { date: "Jan 5, 2026", child: "Nastya", type: "time", opus_value: "5:00 PM - 8:00 PM", sonnet_value: "5:00 PM - 7:30 PM" },
            { date: "Jan 7, 2026", child: "Kseniya", type: "location_code", opus_value: "PL", sonnet_value: "MICC" },
            { date: "Jan 8, 2026", child: null, type: "missing_date", opus_value: "present", sonnet_value: "absent" },
        ];
        displayMisalignments(mockMisalignments);
        displayEvents(parsedEvents);
        eventsSection.style.display = 'block';
        attendeesSection.style.display = 'block';
        sendSection.style.display = 'block';
        eventsSection.scrollIntoView({ behavior: 'smooth' });
    });

    // Upload area click
    uploadArea.addEventListener('click', () => pdfInput.click());

    // Drag and drop
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type === 'application/pdf') {
            handleFileSelect(files[0]);
        }
    });

    // File input change
    pdfInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    function handleFileSelect(file) {
        selectedFile = file;
        fileName.textContent = file.name;
        parseBtn.disabled = false;
    }

    // Parse PDF
    parseBtn.addEventListener('click', async () => {
        if (!selectedFile) return;

        showLoading('Parsing PDF with dual-model verification (this may take a moment)...');

        const formData = new FormData();
        formData.append('file', selectedFile);

        try {
            const response = await fetch('/api/parse-pdf', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to parse PDF');
            }

            parsedEvents = data.events;
            displayMisalignments(data.misalignments || []);
            displayEvents(parsedEvents);
            eventsSection.style.display = 'block';
            attendeesSection.style.display = 'block';
            sendSection.style.display = 'block';

            // Scroll to events
            eventsSection.scrollIntoView({ behavior: 'smooth' });

        } catch (error) {
            alert('Error: ' + error.message);
        } finally {
            hideLoading();
        }
    });

    function displayMisalignments(misalignments) {
        const container = document.getElementById('verificationResult');
        if (!container) return;

        const errors = misalignments.filter(m => m.type === 'verification_error');
        const diffs = misalignments.filter(m => m.type !== 'verification_error');

        if (errors.length > 0) {
            container.innerHTML = `
                <div class="verification-warning">
                    <span class="verification-icon">&#9888;</span>
                    <span>Verification model (Sonnet) failed: ${escapeHtml(errors[0].error || 'Unknown error')}. Results shown are from Opus only.</span>
                </div>`;
            container.style.display = 'block';
            return;
        }

        if (diffs.length === 0) {
            container.innerHTML = `
                <div class="verification-ok">
                    <span class="verification-icon">&#10003;</span>
                    <span>Both models (Opus and Sonnet) agree on all parsed events.</span>
                </div>`;
            container.style.display = 'block';
            return;
        }

        const typeLabels = {
            'missing_date': 'Missing date',
            'missing_child': 'Missing child',
            'time': 'Time differs',
            'location_code': 'Location differs',
            'dl': 'DL flag differs',
        };

        let rows = diffs.map(m => {
            const typeLabel = typeLabels[m.type] || m.type;
            const child = m.child ? escapeHtml(m.child) : '(all)';
            const opusVal = m.opus_value != null ? escapeHtml(String(m.opus_value)) : '\u2014';
            const sonnetVal = m.sonnet_value != null ? escapeHtml(String(m.sonnet_value)) : '\u2014';
            return `<tr>
                <td>${escapeHtml(m.date)}</td>
                <td>${child}</td>
                <td>${escapeHtml(typeLabel)}</td>
                <td class="opus-val">${opusVal}</td>
                <td class="sonnet-val">${sonnetVal}</td>
            </tr>`;
        }).join('');

        container.innerHTML = `
            <div class="verification-mismatch">
                <div class="verification-mismatch-header">
                    <span class="verification-icon">&#9888;</span>
                    <span>${diffs.length} misalignment${diffs.length > 1 ? 's' : ''} found between Opus and Sonnet. Opus result is shown below.</span>
                </div>
                <table class="misalignment-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Child</th>
                            <th>Issue</th>
                            <th>Opus</th>
                            <th>Sonnet</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>`;
        container.style.display = 'block';
    }

    function displayEvents(events) {
        if (events.length === 0) {
            eventsList.innerHTML = '<p class="no-events">No events found for Nastya (JUN2), Kseniya (JUN1 B), or Liza (JUN1 R) in the PDF.</p>';
            return;
        }

        // Group events by date
        const grouped = {};
        events.forEach((event, index) => {
            const dateStr = event.date || 'Unknown Date';
            if (!grouped[dateStr]) grouped[dateStr] = [];
            grouped[dateStr].push({ ...event, _index: index });
        });

        let html = '';
        for (const [dateStr, dateEvents] of Object.entries(grouped)) {
            // Format date with day of week
            let displayDate = dateStr;
            try {
                const d = new Date(dateStr);
                if (!isNaN(d)) {
                    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
                    displayDate = `${days[d.getDay()]}, ${dateStr}`;
                }
            } catch (e) { /* keep original */ }

            // Summary of children for collapsed view
            const childSummary = dateEvents.map(e => e.child).join(', ');

            html += `
            <div class="date-group expanded">
                <div class="date-header">
                    <div class="date-header-left">
                        <span class="date-chevron">&#9660;</span>
                        <span class="date-label">${escapeHtml(displayDate)}</span>
                        <span class="date-summary">${escapeHtml(childSummary)}</span>
                    </div>
                    <label class="date-toggle" onclick="event.stopPropagation()">
                        <input type="checkbox" class="date-select-all" checked>
                        <span>All</span>
                    </label>
                </div>
                <div class="date-events">`;

            for (const event of dateEvents) {
                const childName = event.child || '';
                const locationCode = event.location_code || 'TBD';
                const timeStr = event.time || 'TBD';
                const locationFull = event.location_name && event.location_address
                    ? `${event.location_name}, ${event.location_address}`
                    : event.location_name || '';
                const hasDL = event.dl || false;

                html += `
                    <div class="event-card" data-child="${escapeHtml(childName)}">
                        <div class="event-card-header">
                            <input type="checkbox" id="event-${event._index}" checked data-index="${event._index}">
                            <span class="event-child-name">${escapeHtml(childName)}</span>
                            ${hasDL ? '<span class="event-dl-badge">DL</span>' : ''}
                        </div>
                        <div class="event-card-body">
                            <div class="event-card-row">
                                <span class="event-card-icon">&#128339;</span>
                                <input type="text" class="event-time-input" data-index="${event._index}" value="${escapeHtml(timeStr)}">
                            </div>
                            <div class="event-card-row">
                                <span class="event-card-icon">&#128205;</span>
                                <select class="event-location-select" data-index="${event._index}">
                                    ${Object.entries(LOCATIONS).map(([code, loc]) =>
                                        `<option value="${code}" ${code === locationCode ? 'selected' : ''}>${code} — ${loc.name}</option>`
                                    ).join('')}
                                </select>
                            </div>
                        </div>
                    </div>`;
            }

            html += `
                </div>
            </div>`;
        }

        eventsList.innerHTML = html;

        // Wire up collapsible date headers and toggles
        document.querySelectorAll('.date-group').forEach(group => {
            const header = group.querySelector('.date-header');
            const toggle = group.querySelector('.date-select-all');
            const checkboxes = group.querySelectorAll('.event-card input[type="checkbox"]');

            // Click header to expand/collapse
            header.addEventListener('click', () => {
                group.classList.toggle('expanded');
                group.classList.toggle('collapsed');
            });

            // "All" checkbox toggle
            toggle.addEventListener('change', () => {
                checkboxes.forEach(cb => cb.checked = toggle.checked);
            });

            // Keep toggle in sync when individual checkboxes change
            checkboxes.forEach(cb => {
                cb.addEventListener('change', () => {
                    toggle.checked = Array.from(checkboxes).every(c => c.checked);
                });
            });
        });

        // Wire up inline editing for time and location
        document.querySelectorAll('.event-time-input').forEach(input => {
            input.addEventListener('change', (e) => {
                const idx = parseInt(e.target.dataset.index);
                const ev = parsedEvents[idx];
                ev.time = e.target.value;
                ev.title = `${ev.child} @${ev.location_code} ${ev.time}${ev.dl ? ' DL' : ''}`;
            });
        });

        document.querySelectorAll('.event-location-select').forEach(select => {
            select.addEventListener('change', (e) => {
                const idx = parseInt(e.target.dataset.index);
                const code = e.target.value;
                const loc = LOCATIONS[code];
                const ev = parsedEvents[idx];
                ev.location_code = code;
                ev.location_name = loc ? loc.name : '';
                ev.location_address = loc ? loc.address : '';
                ev.title = `${ev.child} @${ev.location_code} ${ev.time}${ev.dl ? ' DL' : ''}`;
            });
        });
    }

    // Select/Deselect all
    selectAllBtn.addEventListener('click', () => {
        document.querySelectorAll('#eventsList input[type="checkbox"]').forEach(cb => cb.checked = true);
    });

    deselectAllBtn.addEventListener('click', () => {
        document.querySelectorAll('#eventsList input[type="checkbox"]').forEach(cb => cb.checked = false);
    });

    // Add attendee
    function addAttendee(email) {
        email = email.trim().toLowerCase();
        if (!email || !isValidEmail(email)) {
            alert('Please enter a valid email address');
            return;
        }
        if (attendees.includes(email)) {
            alert('Email already added');
            return;
        }

        attendees.push(email);
        renderAttendees();
        attendeeEmail.value = '';
    }

    addAttendeeBtn.addEventListener('click', () => addAttendee(attendeeEmail.value));

    attendeeEmail.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            addAttendee(attendeeEmail.value);
        }
    });

    function renderAttendees() {
        attendeesList.innerHTML = attendees.map((email, index) => `
            <span class="attendee-tag">
                ${escapeHtml(email)}
                <span class="attendee-remove" data-index="${index}">&times;</span>
            </span>
        `).join('');

        // Add remove handlers
        document.querySelectorAll('.attendee-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.index);
                attendees.splice(index, 1);
                renderAttendees();
            });
        });
    }

    // Send invites
    sendBtn.addEventListener('click', async () => {
        const selectedEvents = [];
        document.querySelectorAll('#eventsList .event-card input[type="checkbox"]:checked').forEach(cb => {
            const index = parseInt(cb.dataset.index);
            selectedEvents.push(parsedEvents[index]);
        });

        if (selectedEvents.length === 0) {
            alert('Please select at least one event');
            return;
        }

        if (attendees.length === 0) {
            alert('Please add at least one attendee');
            return;
        }

        showLoading('Sending calendar invites...');

        try {
            const response = await fetch('/api/send-invites', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    events: selectedEvents,
                    attendees: attendees
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to send invites');
            }

            displayResults(data.results);
            resultsSection.style.display = 'block';
            resultsSection.scrollIntoView({ behavior: 'smooth' });

        } catch (error) {
            alert('Error: ' + error.message);
        } finally {
            hideLoading();
        }
    });

    function displayResults(results) {
        resultsList.innerHTML = results.map(result => `
            <div class="result-item ${result.success ? 'success' : 'error'}">
                <span class="result-icon">${result.success ? '&#10003;' : '&#10007;'}</span>
                <div class="result-details">
                    <div class="result-title">${escapeHtml(result.event)}</div>
                    ${result.error ? `<div class="result-error">${escapeHtml(result.error)}</div>` : ''}
                </div>
            </div>
        `).join('');
    }

    // Utility functions
    function showLoading(text) {
        loadingText.textContent = text;
        loadingOverlay.style.display = 'flex';
    }

    function hideLoading() {
        loadingOverlay.style.display = 'none';
    }

    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});
