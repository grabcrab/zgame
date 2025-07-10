#include <SPIFFS.h>
#include <ESPAsyncWebServer.h>

void listFiles(AsyncWebServerRequest *request) 
{
    Serial.println(">>> listFiles");
    String json = "[";
    File root = SPIFFS.open("/");
    File file = root.openNextFile();
    bool first = true;
    
    while(file) {
        if(!first) json += ",";
        json += "\"" + String(file.name()) + "\"";
        first = false;
        file = root.openNextFile();
    }
    json += "]";
    
    request->send(200, "application/json", json);
}

void getFile(AsyncWebServerRequest *request) 
{
    Serial.println(">>> getFile");
    if(!request->hasParam("file")) {
        request->send(400, "text/plain", "Missing file parameter");
        return;
    }
    
    String filename = request->getParam("file")->value();
    if(!filename.startsWith("/")) filename = "/" + filename;
    
    if(SPIFFS.exists(filename)) {
        File file = SPIFFS.open(filename, "r");
        String content = file.readString();
        file.close();
        request->send(200, "application/json", content);
    } 
    else 
    {
        request->send(404, "text/plain", "File not found");
    }
}

void saveFile(AsyncWebServerRequest *request) 
{
    Serial.println(">>> saveFile");
    if(!request->hasParam("file", true) || !request->hasParam("data", true)) 
    {
        request->send(400, "text/plain", "Missing parameters");
        return;
    }
    
    String filename = request->getParam("file", true)->value();
    String data = request->getParam("data", true)->value();
    
    if(!filename.startsWith("/")) filename = "/" + filename;
    
    File file = SPIFFS.open(filename, "w");
    if(file) 
    {
        file.print(data);
        file.close();
        request->send(200, "text/plain", "File saved successfully");
    } 
    else 
    {
        request->send(500, "text/plain", "Error saving file");
    }
}

void handleFileManager(AsyncWebServerRequest *request) 
{
    Serial.println(">>> handleFileManager");
    String html = "<html><body><h1>File manager</h1>";
    html += "<p><a href='/'>Back to main</a></p>";

    // Получение информации о SPIFFS
    size_t totalBytes = SPIFFS.totalBytes();
    size_t usedBytes = SPIFFS.usedBytes();
    size_t freeBytes = totalBytes - usedBytes;
    size_t totalFileSize = 0;

    html += "<h2>File system info:</h2>";
    html += "<p>Total size: " + String(totalBytes) + " bytes</p>";

    html += "<h2>File list:</h2><ul>";

    File root = SPIFFS.open("/");
    File file = root.openNextFile();
    while (file) 
    {
        String fileName = file.name();
        size_t fileSize = file.size();
        totalFileSize += fileSize;
        html += "<li><a href='/download?file=" + fileName + "'>" + fileName + "</a> (";
        html += String(fileSize) + " byte(s))";
        html += "<a href='/delete?file=" + fileName + "' onclick='return confirm(\"Delete file " + fileName + "?\");'>[Delete]</a></li>";
        file = root.openNextFile();
    }
    html += "</ul>";

    html += "<p>Total file(s) size: " + String(totalFileSize) + " bytes</p>";
    html += "<p>Used space: " + String(usedBytes) + " bytes</p>";
    html += "<p>Free space: " + String(freeBytes) + " bytes</p>";

    html += "<h2>Upload file:</h2>";
    html += "<form method='POST' action='/upload' enctype='multipart/form-data'>";
    html += "<input type='file' name='file'><input type='submit' value='Upload'>";
    html += "</form>";

    html += "</body></html>";
    request->send(200, "text/html", html);
}

void handleDelete(AsyncWebServerRequest *request) 
{
    Serial.println(">>> handleDelete");
    if (request->hasParam("file")) 
    {
        String fileName = request->getParam("file")->value();
        String path = "/" + fileName;
        if (SPIFFS.exists(path)) 
        {
            if (SPIFFS.remove(path)) 
            {
                request->redirect("/files"); 
            } 
            else 
            {
                request->send(500, "text/plain", "Error while deleting the file");
            }
        } 
        else 
        {
            request->send(404, "text/plain", "File not found");
        }
    } 
    else 
    {
        request->send(400, "text/plain", "File for deleting is not selected");
    }
}

void handleDownload(AsyncWebServerRequest *request) 
{
    Serial.println(">>> handleDownload");
    if (request->hasParam("file")) 
    {
        String fileName = request->getParam("file")->value();
        String path = "/" + fileName;
        if (SPIFFS.exists(path)) 
        {
            request->send(SPIFFS, path, String(), true);
        } 
        else 
        {
            request->send(404, "text/plain", "File not found");
        }
    } 
    else 
    {
        request->send(400, "text/plain", "Specify file to download");
    }
}
  

void handleUploadResponse(AsyncWebServerRequest *request) 
{
    Serial.println(">>> handleUploadResponse");
    String html = "<html><body>";
    html += "<h2>File upload successfully</h2>";
    html += "<p><a href='/files'>BACK</a></p>";
    html += "</body></html>";
    request->send(200, "text/html", html);
}
  
  
void handleUploadProcess(AsyncWebServerRequest *request, String filename, size_t index, uint8_t *data, size_t len, bool final) 
{
    Serial.println(">>> handleUploadResponse");
    static File uploadFile;

    if (!index) 
    {  
        String path = "/" + filename;
        uploadFile = SPIFFS.open(path, FILE_WRITE);
        if (!uploadFile) 
        {
            Serial.println("!!! handleUploadProcess. file write ERROR: " + path);
            return;
        }
    }

    if (len) 
    {  
        uploadFile.write(data, len);
    }

    if (final) 
    {  
        uploadFile.close();
        Serial.println(">>> File uploaded: " + filename);
    }
}