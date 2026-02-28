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

    let selectedFile = null;
    let parsedEvents = [];
    let attendees = [];

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

        showLoading('Parsing PDF with AI (this may take a moment)...');

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

            html += `
            <div class="date-group">
                <div class="date-header">
                    <span class="date-label">${escapeHtml(displayDate)}</span>
                    <label class="date-toggle">
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

                html += `
                    <div class="event-item" data-child="${escapeHtml(childName)}">
                        <input type="checkbox" id="event-${event._index}" checked data-index="${event._index}">
                        <div class="event-details">
                            <div class="event-title">${escapeHtml(childName)}</div>
                            <div class="event-meta">
                                <span class="event-time-badge">${escapeHtml(timeStr)}</span>
                                <span class="event-location-badge">@ ${escapeHtml(locationCode)}</span>
                            </div>
                            ${locationFull ? `<div class="event-location-full">${escapeHtml(locationFull)}</div>` : ''}
                        </div>
                    </div>`;
            }

            html += `
                </div>
            </div>`;
        }

        eventsList.innerHTML = html;

        // Wire up per-date "All" toggles
        document.querySelectorAll('.date-group').forEach(group => {
            const toggle = group.querySelector('.date-select-all');
            const checkboxes = group.querySelectorAll('.event-item input[type="checkbox"]');

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
        document.querySelectorAll('#eventsList input[type="checkbox"]:checked').forEach(cb => {
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
