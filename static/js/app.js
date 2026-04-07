document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('query-form');
    const input = document.getElementById('nl-input');
    const chatHistory = document.getElementById('chat-history');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = document.querySelector('.btn-text');
    const loader = document.querySelector('.loader');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const query = input.value.trim();
        if (!query) return;

        // 1. Add User Message
        appendMessage('user', query);
        input.value = '';

        // 2. Disable input & show loading
        setLoadingState(true);

        // 3. Make API call
        try {
            const response = await fetch('/api/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ query })
            });

            const data = await response.json();

            if (response.ok) {
                renderAssistantResponse(data);
            } else {
                appendMessage('system', `<div class="error-text">❌ Error: ${data.detail || 'Failed to execute query.'}</div>`);
            }
        } catch (error) {
            appendMessage('system', `<div class="error-text">❌ Network Error: Could not connect to backend.</div>`);
        } finally {
            setLoadingState(false);
            scrollToBottom();
        }
    });

    function appendMessage(role, contentHTML) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        
        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = 'bubble';
        
        if (role === 'user') {
            bubbleDiv.textContent = contentHTML; // Plain text
        } else {
            bubbleDiv.innerHTML = contentHTML; // HTML for tables/formatted SQL
        }
        
        msgDiv.appendChild(bubbleDiv);
        chatHistory.appendChild(msgDiv);
        scrollToBottom();
    }

    function renderAssistantResponse(data) {
        let htmlContent = '';

        // Add SQL snippet
        htmlContent += `<div class="sql-query">${data.sql_query}</div>`;

        // Add Datatable
        if (data.results && data.results.length > 0) {
            let tableHtml = `<div class="data-table-container"><table class="data-table"><thead><tr>`;
            
            // Headers
            data.columns.forEach(col => {
                tableHtml += `<th>${col}</th>`;
            });
            tableHtml += `</tr></thead><tbody>`;

            // Rows
            data.results.forEach(row => {
                tableHtml += `<tr>`;
                row.forEach(cell => {
                    // format appropriately if it's null
                    const displayVal = cell === null ? '<i>NULL</i>' : String(cell);
                    tableHtml += `<td>${displayVal}</td>`;
                });
                tableHtml += `</tr>`;
            });

            tableHtml += `</tbody></table></div>`;
            htmlContent += tableHtml;
        } else {
             htmlContent += `<div><strong>No data found</strong> for your query.</div>`;
        }

        appendMessage('assistant', htmlContent);
    }

    function setLoadingState(isLoading) {
        if (isLoading) {
            submitBtn.disabled = true;
            btnText.classList.add('hidden');
            loader.classList.remove('hidden');
            input.disabled = true;
        } else {
            submitBtn.disabled = false;
            btnText.classList.remove('hidden');
            loader.classList.add('hidden');
            input.disabled = false;
            input.focus();
        }
    }

    function scrollToBottom() {
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
});
