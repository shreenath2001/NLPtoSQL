document.addEventListener('DOMContentLoaded', () => {
    // --- Elements ---
    const form = document.getElementById('query-form');
    const input = document.getElementById('nl-input');
    const chatHistory = document.getElementById('chat-history');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = document.querySelector('.btn-text');
    const loader = document.querySelector('.loader');

    // Schema Elements
    const schemaDropdown = document.getElementById('schema-dropdown');
    const schemaTableList = document.getElementById('schema-table-list');
    
    // Modal Elements
    const addSchemaBtn = document.getElementById('add-schema-btn');
    const schemaModal = document.getElementById('schema-modal');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const cancelSchemaBtn = document.getElementById('cancel-schema-btn');
    const schemaForm = document.getElementById('schema-form');
    const schemaNameInput = document.getElementById('schema-name');
    const schemaScriptInput = document.getElementById('schema-script');
    const schemaError = document.getElementById('schema-error');
    const saveSchemaBtn = document.getElementById('save-schema-btn');
    const schemaLoader = document.getElementById('schema-loader');

    // Mobile Sidebar Elements
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    const sidebar = document.querySelector('.sidebar');

    function toggleSidebar() {
        if(sidebar && sidebarOverlay) {
            sidebar.classList.toggle('active');
            sidebarOverlay.classList.toggle('active');
        }
    }

    if (mobileMenuBtn && sidebarOverlay) {
        mobileMenuBtn.addEventListener('click', toggleSidebar);
        sidebarOverlay.addEventListener('click', toggleSidebar);
    }

    // --- Init ---
    loadSchemas();

    // --- Event Listeners ---
    schemaDropdown.addEventListener('change', () => {
        loadSchemaInfo(schemaDropdown.value);
    });

    addSchemaBtn.addEventListener('click', () => {
        schemaModal.classList.remove('hidden');
        schemaError.classList.add('hidden');
        schemaForm.reset();
    });

    closeModalBtn.addEventListener('click', () => {
        schemaModal.classList.add('hidden');
    });

    if (cancelSchemaBtn) {
        cancelSchemaBtn.addEventListener('click', () => {
            schemaModal.classList.add('hidden');
        });
    }

    schemaForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const name = schemaNameInput.value.trim();
        const sql_script = schemaScriptInput.value.trim();
        
        if (!name || !sql_script) return;

        // Set Loading
        saveSchemaBtn.disabled = true;
        schemaLoader.classList.remove('hidden');
        schemaError.classList.add('hidden');

        try {
            const res = await fetch('/api/schemas', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, sql_script })
            });

            const data = await res.json();

            if (res.ok) {
                schemaModal.classList.add('hidden');
                await loadSchemas(name); // reload list and select the new one
            } else {
                schemaError.textContent = data.detail || 'Failed to add schema';
                schemaError.classList.remove('hidden');
            }
        } catch (err) {
            schemaError.textContent = 'Network error while adding schema';
            schemaError.classList.remove('hidden');
        } finally {
            saveSchemaBtn.disabled = false;
            schemaLoader.classList.add('hidden');
        }
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const query = input.value.trim();
        const schema_name = schemaDropdown.value;
        if (!query || !schema_name) return;

        appendMessage('user', query);
        input.value = '';

        setLoadingState(true);

        try {
            const response = await fetch('/api/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ query, schema_name })
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

    // --- Helper Functions ---

    async function loadSchemas(selectedName = 'ecommerce') {
        try {
            const res = await fetch('/api/schemas');
            const data = await res.json();
            
            schemaDropdown.innerHTML = '';
            data.schemas.forEach(schema => {
                const opt = document.createElement('option');
                opt.value = schema;
                opt.textContent = schema;
                schemaDropdown.appendChild(opt);
            });

            if (data.schemas.includes(selectedName)) {
                schemaDropdown.value = selectedName;
            } else if (data.schemas.length > 0) {
                schemaDropdown.value = data.schemas[0];
            }

            if (schemaDropdown.value) {
                loadSchemaInfo(schemaDropdown.value);
            }
        } catch (e) {
            console.error("Failed to load schemas", e);
        }
    }

    async function loadSchemaInfo(name) {
        schemaTableList.innerHTML = '<div style="padding:10px;text-align:center;">Loading schema...</div>';
        try {
            const res = await fetch(`/api/schema/${name}`);
            const data = await res.json();
            
            if (res.ok) {
                renderSchemaSidebar(data.tables);
            } else {
                schemaTableList.innerHTML = `<div class="error-text">Failed to load schema</div>`;
            }
        } catch (e) {
            schemaTableList.innerHTML = `<div class="error-text">Network error</div>`;
        }
    }

    function renderSchemaSidebar(tables) {
        schemaTableList.innerHTML = '';
        if (!tables || tables.length === 0) {
            schemaTableList.innerHTML = '<div style="padding:10px;text-align:center;font-size:0.9rem;opacity:0.7">No tables found.</div>';
            return;
        }

        tables.forEach(table => {
            const card = document.createElement('div');
            card.className = 'table-card';
            
            const h4 = document.createElement('h4');
            h4.textContent = table.name;
            card.appendChild(h4);

            const ul = document.createElement('ul');
            table.columns.forEach(col => {
                const li = document.createElement('li');
                li.innerHTML = `<span class="type">${col.type}</span> ${col.name}`;
                ul.appendChild(li);
            });

            card.appendChild(ul);
            schemaTableList.appendChild(card);
        });
    }

    function appendMessage(role, contentHTML) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        
        const bubbleDiv = document.createElement('div');
        bubbleDiv.className = 'bubble';
        
        if (role === 'user') {
            bubbleDiv.textContent = contentHTML;
        } else {
            bubbleDiv.innerHTML = contentHTML;
        }
        
        msgDiv.appendChild(bubbleDiv);
        chatHistory.appendChild(msgDiv);
        scrollToBottom();
    }

    function renderAssistantResponse(data) {
        let htmlContent = '';

        if (data.chat_response) {
            htmlContent += `<div style="padding: 0.5rem 0; color: var(--text-primary); line-height: 1.5;">${data.chat_response.replace(/\n/g, '<br>')}</div>`;
            appendMessage('assistant', htmlContent);
            return;
        }

        htmlContent += `<div class="sql-query">${data.sql_query}</div>`;

        if (data.results && data.results.length > 0) {
            let tableHtml = `<div class="data-table-container"><table class="data-table"><thead><tr>`;
            
            data.columns.forEach(col => {
                tableHtml += `<th>${col}</th>`;
            });
            tableHtml += `</tr></thead><tbody>`;

            data.results.forEach(row => {
                tableHtml += `<tr>`;
                row.forEach(cell => {
                    const displayVal = cell === null ? '<i>NULL</i>' : String(cell);
                    tableHtml += `<td>${displayVal}</td>`;
                });
                tableHtml += `</tr>`;
            });

            tableHtml += `</tbody></table></div>`;
            htmlContent += tableHtml;
            
            if (data.analysis) {
                htmlContent += `<div class="analysis-block">
                    <div class="analysis-header">
                        <svg width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
                        Analysis
                    </div>
                    <div class="analysis-content">${data.analysis.replace(/\n/g, '<br>')}</div>
                </div>`;
            }
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
