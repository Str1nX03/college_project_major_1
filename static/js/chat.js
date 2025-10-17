document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chatForm');
    const chatInput = document.getElementById('chatInput');
    const chatMessages = document.getElementById('chatMessages');
    const sendBtn = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');
    const lessonList = document.getElementById('lessonList');
    const lessonControls = document.getElementById('lessonControls');
    const nextLessonBtn = document.getElementById('nextLessonBtn');
    const replayLessonBtn = document.getElementById('replayLessonBtn');
    const progressCurrent = document.getElementById('progressCurrent');
    const progressTotal = document.getElementById('progressTotal');
    const progressFill = document.getElementById('progressFill');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const lessonSidebar = document.getElementById('lessonSidebar');
    const userMenuBtn = document.getElementById('userMenuBtn');
    const userDropdown = document.getElementById('userDropdown');
    const newSessionBtn = document.getElementById('newSessionBtn');
    const clearHistoryBtn = document.getElementById('clearHistoryBtn');
    const toast = document.getElementById('toast');

    let currentLessonPlan = [];
    let currentLessonIndex = 0;
    let isFirstMessage = true;

    loadSession();

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = chatInput.value.trim();
        if (!message) return;

        addUserMessage(message);
        chatInput.value = '';
        chatInput.disabled = true;
        sendBtn.disabled = true;
        showTypingIndicator();

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message })
            });

            const data = await response.json();
            hideTypingIndicator();

            if (data.error) {
                addSystemMessage('Error: ' + data.error);
            } else {
                if (data.lesson_plan && data.lesson_plan.length > 0) {
                    currentLessonPlan = data.lesson_plan;
                    updateLessonPlan(data.lesson_plan);
                }
                
                addAIMessage(data.message);

                if (data.is_finished) {
                    lessonControls.style.display = 'none';
                    showToast('Lesson plan completed! 🎉');
                } else {
                    if (isFirstMessage) {
                        lessonControls.style.display = 'flex';
                        isFirstMessage = false;
                    }
                }
            }
        } catch (error) {
            hideTypingIndicator();
            addSystemMessage('Failed to send message. Please try again.');
            console.error('Error:', error);
        } finally {
            chatInput.disabled = false;
            sendBtn.disabled = false;
            chatInput.focus();
        }
    });

    nextLessonBtn.addEventListener('click', async () => {
        await sendControlMessage('next');
    });

    replayLessonBtn.addEventListener('click', async () => {
        await sendControlMessage('replay');
    });

    async function sendControlMessage(action) {
        chatInput.disabled = true;
        sendBtn.disabled = true;
        nextLessonBtn.disabled = true;
        replayLessonBtn.disabled = true;
        showTypingIndicator();

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message: action })
            });

            const data = await response.json();
            hideTypingIndicator();

            if (data.error) {
                addSystemMessage('Error: ' + data.error);
            } else {
                addAIMessage(data.message);
                
                if (action === 'next') {
                    currentLessonIndex++;
                    updateLessonProgress();
                }

                if (data.is_finished) {
                    lessonControls.style.display = 'none';
                    showToast('Lesson plan completed! 🎉');
                }
            }
        } catch (error) {
            hideTypingIndicator();
            addSystemMessage('Failed to process request. Please try again.');
            console.error('Error:', error);
        } finally {
            chatInput.disabled = false;
            sendBtn.disabled = false;
            nextLessonBtn.disabled = false;
            replayLessonBtn.disabled = false;
        }
    }

    function addUserMessage(text) {
        const welcomeMsg = chatMessages.querySelector('.welcome-message');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        messageDiv.innerHTML = `
            <div class="message-avatar">👤</div>
            <div class="message-content">
                <div class="message-bubble">${escapeHtml(text)}</div>
                <div class="message-time">${getCurrentTime()}</div>
            </div>
        `;
        chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }

    function addAIMessage(text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ai';
        messageDiv.innerHTML = `
            <div class="message-avatar">🤖</div>
            <div class="message-content">
                <div class="message-bubble">${formatMessage(text)}</div>
                <div class="message-time">${getCurrentTime()}</div>
            </div>
        `;
        chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }

    function addSystemMessage(text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ai';
        messageDiv.innerHTML = `
            <div class="message-avatar">⚠️</div>
            <div class="message-content">
                <div class="message-bubble">${escapeHtml(text)}</div>
            </div>
        `;
        chatMessages.appendChild(messageDiv);
        scrollToBottom();
    }

    function formatMessage(text) {
        text = escapeHtml(text);
        text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
        text = text.replace(/\n/g, '<br>');
        return text;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function getCurrentTime() {
        const now = new Date();
        return now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }

    function showTypingIndicator() {
        typingIndicator.style.display = 'flex';
    }

    function hideTypingIndicator() {
        typingIndicator.style.display = 'none';
    }

    function scrollToBottom() {
        setTimeout(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 100);
    }

    function updateLessonPlan(lessons) {
        lessonList.innerHTML = '';
        lessons.forEach((lesson, index) => {
            const lessonItem = document.createElement('div');
            lessonItem.className = 'lesson-item';
            if (index === currentLessonIndex) {
                lessonItem.classList.add('active');
            } else if (index < currentLessonIndex) {
                lessonItem.classList.add('completed');
            }
            lessonItem.innerHTML = `
                <span class="lesson-number">${index < currentLessonIndex ? '' : index + 1}</span>
                <span class="lesson-text">${escapeHtml(lesson)}</span>
            `;
            lessonList.appendChild(lessonItem);
        });
        updateLessonProgress();
    }

    function updateLessonProgress() {
        if (currentLessonPlan.length > 0) {
            progressCurrent.textContent = currentLessonIndex + 1;
            progressTotal.textContent = currentLessonPlan.length;
            const percentage = ((currentLessonIndex + 1) / currentLessonPlan.length) * 100;
            progressFill.style.width = percentage + '%';

            const items = lessonList.querySelectorAll('.lesson-item');
            items.forEach((item, index) => {
                item.className = 'lesson-item';
                if (index === currentLessonIndex) {
                    item.classList.add('active');
                } else if (index < currentLessonIndex) {
                    item.classList.add('completed');
                }
            });
        }
    }

    async function loadSession() {
        try {
            const response = await fetch('/api/session');
            const data = await response.json();
            
            if (data.history && data.history.length > 0) {
                const welcomeMsg = chatMessages.querySelector('.welcome-message');
                if (welcomeMsg) {
                    welcomeMsg.remove();
                }

                data.history.forEach(msg => {
                    if (msg.sender === 'user') {
                        const messageDiv = document.createElement('div');
                        messageDiv.className = 'message user';
                        messageDiv.innerHTML = `
                            <div class="message-avatar">👤</div>
                            <div class="message-content">
                                <div class="message-bubble">${escapeHtml(msg.message)}</div>
                                <div class="message-time">${formatTimestamp(msg.timestamp)}</div>
                            </div>
                        `;
                        chatMessages.appendChild(messageDiv);
                    } else {
                        const messageDiv = document.createElement('div');
                        messageDiv.className = 'message ai';
                        messageDiv.innerHTML = `
                            <div class="message-avatar">🤖</div>
                            <div class="message-content">
                                <div class="message-bubble">${formatMessage(msg.message)}</div>
                                <div class="message-time">${formatTimestamp(msg.timestamp)}</div>
                            </div>
                        `;
                        chatMessages.appendChild(messageDiv);
                    }
                });

                isFirstMessage = false;
                lessonControls.style.display = 'flex';
                scrollToBottom();
            }
        } catch (error) {
            console.error('Failed to load session:', error);
        }
    }

    function formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }

    sidebarToggle.addEventListener('click', () => {
        lessonSidebar.classList.toggle('collapsed');
        const icon = sidebarToggle.querySelector('.toggle-icon');
        icon.textContent = lessonSidebar.classList.contains('collapsed') ? '▶' : '◀';
    });

    userMenuBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        userMenuBtn.classList.toggle('active');
        userDropdown.classList.toggle('show');
    });

    document.addEventListener('click', (e) => {
        if (!userMenuBtn.contains(e.target) && !userDropdown.contains(e.target)) {
            userMenuBtn.classList.remove('active');
            userDropdown.classList.remove('show');
        }
    });

    newSessionBtn.addEventListener('click', async () => {
        if (confirm('Are you sure you want to start a new session? This will clear your current conversation.')) {
            await clearSession();
            location.reload();
        }
    });

    clearHistoryBtn.addEventListener('click', async () => {
        if (confirm('Are you sure you want to clear all history? This cannot be undone.')) {
            await clearSession();
            showToast('History cleared successfully');
            setTimeout(() => location.reload(), 1000);
        }
    });

    async function clearSession() {
        try {
            await fetch('/api/session', {
                method: 'DELETE'
            });
        } catch (error) {
            console.error('Failed to clear session:', error);
        }
    }

    function showToast(message) {
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }

    const exampleChips = document.querySelectorAll('.example-chip');
    exampleChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const text = chip.textContent.replace(/['"]/g, '');
            chatInput.value = text;
            chatInput.focus();
        });
    });

    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });
});