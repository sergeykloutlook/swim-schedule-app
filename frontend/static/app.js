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

        showLoading('Parsing PDF...');

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
            eventsList.innerHTML = '<p style="color: #666; text-align: center;">No events found for Nastya (JUN2), Kseniya (JUN1 B), or Liza (JUN1 R) in the PDF.</p>';
            return;
        }

        // Display only events for our kids with proper format
        eventsList.innerHTML = events.map((event, index) => {
            const childName = event.child || '';
            const locationCode = event.location_code || 'TBD';
            const timeStr = event.time || 'TBD';
            const dateStr = event.date || 'TBD';
            const locationFull = event.location_name && event.location_address
                ? `${event.location_name}, ${event.location_address}`
                : event.location_name || '';

            // Title format: "Liza @MICC 5:00 - 6:00 pm"
            const eventTitle = event.title || `${childName} @${locationCode} ${timeStr}`;

            return `
            <div class="event-item" data-child="${escapeHtml(childName)}">
                <input type="checkbox" id="event-${index}" checked data-index="${index}">
                <div class="event-details">
                    <div class="event-title">${escapeHtml(eventTitle)}</div>
                    <div class="event-info">
                        <div class="event-date"><strong>Date:</strong> ${escapeHtml(dateStr)}</div>
                        <div class="event-time-detail"><strong>Time:</strong> ${escapeHtml(timeStr)}</div>
                        ${locationFull ? `<div class="event-location"><strong>Location:</strong> ${escapeHtml(locationFull)}</div>` : ''}
                    </div>
                </div>
            </div>
        `}).join('');
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
