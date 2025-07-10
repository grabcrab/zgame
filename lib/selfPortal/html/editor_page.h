#pragma once

const char* editor_page = R"rawliteral(
    <!DOCTYPE html>
    <html>
    <head>
        <title>JSON Editor</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            #fileList { margin: 20px 0; }
            #editor { width: 100%; height: 400px; }
            #status { color: green; margin: 10px 0; }
            .error { color: red; }
            .button-container { margin-top: 10px; }
            button { margin-right: 10px; }
        </style>
    </head>
    <body>
        <h2>JSON File Editor</h2>
        
        <select id="fileList" onchange="checkUnsavedChanges()">
            <option value="">Select a file</option>
        </select>
        
        <textarea id="editor" oninput="markAsModified()"></textarea>
        <div class="button-container">
            <button onclick="saveFile()">Save Changes</button>
            <button onclick="goBack()">Back</button>
        </div>
        <div id="status"></div>
    
        <script>
            const editor = document.getElementById('editor');
            const fileList = document.getElementById('fileList');
            const statusDiv = document.getElementById('status');
            let isModified = false;
            let originalContent = '';
            let lastLoadedFile = '';
    
            // Load file list on page load
            window.onload = function() {
                fetch('/listFiles')
                    .then(response => response.json())
                    .then(files => {
                        files.forEach(file => {
                            if(file.endsWith('.json')) {
                                let option = document.createElement('option');
                                option.value = file;
                                option.text = file;
                                fileList.appendChild(option);
                            }
                        });
                    })
                    .catch(err => showStatus('Error loading files: ' + err, true));
            };
    
            function checkUnsavedChanges() {
                if(isModified && fileList.value !== lastLoadedFile) {
                    if(!confirm('You have unsaved changes. Are you sure you want to load another file?')) {
                        fileList.value = lastLoadedFile;
                        return;
                    }
                }
                loadFile();
            }
    
            function loadFile() {
                const filename = fileList.value;
                if(!filename) return;
                
                fetch('/getFile?file=' + filename)
                    .then(response => response.text())
                    .then(data => {
                        try {
                            const formattedData = JSON.stringify(JSON.parse(data), null, 2);
                            editor.value = formattedData;
                            originalContent = formattedData;
                            lastLoadedFile = filename;
                            isModified = false;
                            showStatus('File loaded successfully');
                        } catch(e) {
                            editor.value = data;
                            originalContent = data;
                            lastLoadedFile = filename;
                            isModified = false;
                            showStatus('Invalid JSON format', true);
                        }
                    })
                    .catch(err => showStatus('Error loading file: ' + err, true));
            }
    
            function saveFile() {
                const filename = fileList.value;
                if(!filename) {
                    showStatus('Please select a file first', true);
                    return;
                }
    
                const content = editor.value;
                try {
                    JSON.parse(content);
                    fetch('/saveFile', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: 'file=' + encodeURIComponent(filename) + '&data=' + encodeURIComponent(content)
                    })
                    .then(response => response.text())
                    .then(data => {
                        originalContent = content;
                        isModified = false;
                        showStatus(data);
                    })
                    .catch(err => showStatus('Error saving file: ' + err, true));
                } catch(e) {
                    showStatus('Invalid JSON format', true);
                }
            }
    
            function markAsModified() {
                isModified = editor.value !== originalContent;
            }
    
            function goBack() {
                if(isModified) {
                    if(!confirm('You have unsaved changes. Are you sure you want to go back?')) {
                        return;
                    }
                }
                window.location.href = '/'; 
            }
    
            function showStatus(message, isError = false) {
                statusDiv.textContent = message;
                statusDiv.className = isError ? 'error' : '';
            }
        </script>
    </body>
    </html>
    )rawliteral";