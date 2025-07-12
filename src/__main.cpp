#include <WiFi.h>
#include <HTTPClient.h>
#include <Update.h>
#include <ArduinoJson.h>
#include <MD5Builder.h>
#include <esp_partition.h>
#include <esp_ota_ops.h>
#include "version.h"

// WiFi settings
const char *ssid = "tcutestnet";
const char *password = "tcutestpass";

// OTA server settings
const char *otaServerURL = "http://192.168.1.120:5005"; // Your server IP
const unsigned long checkInterval = 5000;              // Check every 30 seconds

// Global variables
String currentFirmwareVersion = "";
unsigned long lastCheck = 0;

void performOTAUpdate(int firmwareSize);
void otaProgressCallback(int progress);
void otaProgressCallback(int progress);
String getCurrentFirmwareMD5() {
    // Use built-in ESP32 function to get current sketch MD5
    String md5 = ESP.getSketchMD5();
    Serial.printf("Current firmware MD5: %s\n", md5.c_str());
    return md5;
}

void checkForUpdates() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi not connected");
        return;
    }
    
    HTTPClient http;
    http.begin(String(otaServerURL) + "/version");
    
    int httpCode = http.GET();
    if (httpCode == HTTP_CODE_OK) {
        String payload = http.getString();
        
        // Parse JSON response
        DynamicJsonDocument doc(1024);
        DeserializationError error = deserializeJson(doc, payload);
        
        if (error) {
            Serial.println("Failed to parse JSON response");
            http.end();
            return;
        }
        
        String serverVersion = doc["version"];
        int firmwareSize = doc["size"];
        String filename = doc["filename"];
        
        Serial.println("Server response:");
        Serial.println("  Server MD5: " + serverVersion);
        Serial.println("  Current MD5: " + currentFirmwareVersion);
        Serial.println("  Size: " + String(firmwareSize));
        Serial.println("  Filename: " + filename);
        
        // Compare versions
        if (serverVersion != currentFirmwareVersion) {
            Serial.println("MD5 mismatch detected! Starting update...");
            Serial.println("  Server:  " + serverVersion);
            Serial.println("  Current: " + currentFirmwareVersion);
            performOTAUpdate(firmwareSize);
        } else {
            Serial.println("Firmware is up to date - MD5 match");
        }
    } else {
        Serial.printf("HTTP error: %d\n", httpCode);
    }
    
    http.end();
}

void performOTAUpdate(int firmwareSize) {
    HTTPClient http;
    http.begin(String(otaServerURL) + "/update");
    
    int httpCode = http.GET();
    if (httpCode != HTTP_CODE_OK) {
        Serial.printf("Failed to start download: %d\n", httpCode);
        http.end();
        return;
    }
    
    int contentLength = http.getSize();
    if (contentLength != firmwareSize) {
        Serial.println("Content length mismatch");
        http.end();
        return;
    }
    
    // Start OTA update
    if (!Update.begin(contentLength)) {
        Serial.println("Not enough space for update");
        http.end();
        return;
    }
    
    Serial.println("Starting OTA update...");
    Serial.printf("Firmware size: %d bytes\n", contentLength);
    
    WiFiClient* client = http.getStreamPtr();
    int written = 0;
    int progress = 0;
    int lastProgress = -1;
    
    uint8_t buffer[128];
    
    while (http.connected() && (written < contentLength)) {
        size_t available = client->available();
        if (available) {
            int readBytes = client->readBytes(buffer, min(available, sizeof(buffer)));
            
            if (readBytes > 0) {
                if (Update.write(buffer, readBytes) != readBytes) {
                    Serial.println("Write failed");
                    break;
                }
                written += readBytes;
                
                // Calculate and display progress
                progress = (written * 100) / contentLength;
                if (progress != lastProgress && progress % 5 == 0) {
                    otaProgressCallback(progress);
                    lastProgress = progress;
                }
            }
        }
        delay(1);
    }
    
    if (written == contentLength) {
        Serial.println("Update completed successfully");
        otaProgressCallback(100);
    } else {
        Serial.printf("Update failed. Written: %d, Expected: %d\n", written, contentLength);
    }
    
    if (Update.end()) {
        if (Update.isFinished()) {
            Serial.println("Update successfully finished. Rebooting...");
            delay(1000);
            ESP.restart();
        } else {
            Serial.println("Update failed to finish");
        }
    } else {
        Serial.printf("Update error: %d\n", Update.getError());
    }
    
    http.end();
}

void otaProgressCallback(int progress) {
    // Callback function for update progress display
    // You can add your own logic here:
    // - Send progress to server
    // - Update display
    // - LED blinking
    // - Send to MQTT
    
    Serial.printf("OTA Progress: %d%%\n", progress);
    
    // Example: blink built-in LED
    if (progress % 10 == 0) {
        digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    }
    
    // Example: send progress via Serial in JSON format
    Serial.printf("{\"ota_progress\": %d}\n", progress);
}

void setup() {
    Serial.begin(115200);
    delay(3000);
    Serial.println("Starting ESP32 OTA Client");
    Serial.println(VERSION_STR);
    delay(3000);
    
    // Connect to WiFi
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    Serial.print("Connected to WiFi. IP: ");
    Serial.println(WiFi.localIP());
    
    // Get current firmware MD5 using built-in function
    currentFirmwareVersion = getCurrentFirmwareMD5();
    Serial.print("Current firmware MD5: ");
    Serial.println(currentFirmwareVersion);
    
    // First update check
    checkForUpdates();
}

void loop() {
    // Check for updates with specified interval
    if (millis() - lastCheck > checkInterval) {
        checkForUpdates();
        lastCheck = millis();
    }
    
    // Your main code here
    delay(1000);
}


// #include <WiFi.h>
// #include <HTTPClient.h>
// #include <ArduinoJson.h>
// #include <SPIFFS.h>
// #include <FS.h>
// #include <map>

// const char *ssid = "tcutestnet";
// const char *password = "tcutestpass";
// const char *serverAddress = "http://192.168.1.120:5001"; // IP и порт сервера

// String calculateFileHash(const char *filename);

// // Sync configuration
// const bool REMOVE_LOCAL_FILES_NOT_ON_SERVER = false; // Set to true to enable cleanup

// // Sync progress structure
// struct SyncProgress
// {
//     uint32_t totalFiles;
//     uint32_t processedFiles;
//     uint32_t totalBytes;
//     uint32_t downloadedBytes;
//     uint32_t uploadedBytes;
//     uint8_t percentage;
//     unsigned long lastUpdateTime;
// };

// SyncProgress syncProgress = {0, 0, 0, 0, 0, 0, 0};

// // Callback function type for progress updates
// typedef bool (*ProgressCallback)(uint32_t downloaded, uint32_t total, uint8_t percentage);

// // Default progress callback (stub with print)
// bool defaultProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage)
// {
//     Serial.printf("Progress: %d/%d bytes (%d%%) downloaded\n", downloaded, total, percentage);

//     // Add your custom logic here
//     // Return false to cancel sync, true to continue
//     return true;
// }

// // Progress callback pointer
// ProgressCallback progressCallback = defaultProgressCallback;

// // Function to update and report progress
// bool updateProgress(uint32_t bytesTransferred, bool isUpload = false)
// {
//     if (isUpload)
//     {
//         syncProgress.uploadedBytes += bytesTransferred;
//     }
//     else
//     {
//         syncProgress.downloadedBytes += bytesTransferred;
//     }

//     uint32_t totalTransferred = syncProgress.downloadedBytes + syncProgress.uploadedBytes;

//     if (syncProgress.totalBytes > 0)
//     {
//         syncProgress.percentage = (totalTransferred * 100) / syncProgress.totalBytes;
//     }

//     // Call progress callback every second
//     unsigned long currentTime = millis();
//     if (currentTime - syncProgress.lastUpdateTime >= 1000)
//     {
//         syncProgress.lastUpdateTime = currentTime;

//         if (progressCallback)
//         {
//             return progressCallback(totalTransferred, syncProgress.totalBytes, syncProgress.percentage);
//         }
//     }

//     return true;
// }

// // Function to get list of files from SPIFFS
// String getLocalFileList()
// {
//     JsonDocument doc;
//     JsonArray files = doc["files"].to<JsonArray>();

//     Serial.println("=== Local SPIFFS file list ===");

//     File root = SPIFFS.open("/");
//     File file = root.openNextFile();

//     while (file)
//     {
//         if (!file.isDirectory())
//         {
//             String fullPath = file.name();
//             String filename = fullPath;

//             // Remove leading "/" for compatibility with server
//             if (filename.startsWith("/"))
//             {
//                 filename = filename.substring(1);
//             }

//             uint32_t fileSize = file.size();
//             String fileHash = calculateFileHash(filename.c_str());

//             Serial.printf("Local file: %s, size: %d, hash: %s\n",
//                           filename.c_str(), fileSize, fileHash.c_str());

//             JsonObject fileObj = files.add<JsonObject>();
//             fileObj["name"] = filename;
//             fileObj["size"] = fileSize;
//             fileObj["hash"] = fileHash;
//         }
//         file = root.openNextFile();
//     }

//     Serial.println("=== End local file list ===");

//     String result;
//     serializeJson(doc, result);
//     return result;
// }

// // Simple hash function for file
// String calculateFileHash(const char *filename)
// {
//     // Add "/" prefix for SPIFFS
//     String spiffsPath = "/";
//     spiffsPath += filename;

//     File file = SPIFFS.open(spiffsPath, "r");
//     if (!file)
//         return "";

//     uint32_t hash = 0;
//     while (file.available())
//     {
//         hash = hash * 31 + file.read();
//     }
//     file.close();

//     return String(hash, HEX);
// }

// // Upload file to server - disabled for one-way sync
// bool uploadFile(const char *filename)
// {
//     Serial.printf("Upload disabled - one-way sync (server to ESP32 only)\n");
//     return true; // Always return true to avoid breaking sync flow
// }

// // Download file from server with progress tracking
// bool downloadFile(const char *filename)
// {
//     HTTPClient http;
//     http.begin(String(serverAddress) + "/download?file=" + String(filename));
//     http.setTimeout(30000);        // 30 second timeout for large files
//     http.setConnectTimeout(10000); // 10 second connection timeout

//     int httpResponseCode = http.GET();

//     if (httpResponseCode == 200)
//     {
//         int contentLength = http.getSize();
//         Serial.printf("Downloading file: %s (%d bytes)\n", filename, contentLength);

//         // Check if we have enough space in SPIFFS
//         size_t freeSpace = SPIFFS.totalBytes() - SPIFFS.usedBytes();
//         if (contentLength > 0 && contentLength > freeSpace)
//         {
//             Serial.printf("Error: Not enough space in SPIFFS. Need: %d, Available: %d\n",
//                           contentLength, freeSpace);
//             http.end();
//             return false;
//         }

//         // Add "/" prefix for SPIFFS
//         String spiffsPath = "/";
//         spiffsPath += filename;

//         // Remove existing file first to avoid corruption
//         if (SPIFFS.exists(spiffsPath))
//         {
//             SPIFFS.remove(spiffsPath);
//             Serial.printf("Removed existing file: %s\n", spiffsPath.c_str());
//         }

//         File file = SPIFFS.open(spiffsPath, "w");
//         if (!file)
//         {
//             Serial.println("Error creating file: " + spiffsPath);
//             http.end();
//             return false;
//         }

//         WiFiClient *stream = http.getStreamPtr();
//         const size_t bufferSize = 512; // Smaller buffer for stability
//         uint8_t buffer[bufferSize];
//         int totalDownloaded = 0;
//         bool shouldContinue = true;
//         unsigned long lastProgressTime = millis();
//         unsigned long downloadStartTime = millis();

//         Serial.printf("Starting download of %d bytes...\n", contentLength);

//         // Download with improved error handling
//         while (shouldContinue && (contentLength < 0 || totalDownloaded < contentLength))
//         {
//             // Check if connection is still alive
//             if (!http.connected())
//             {
//                 Serial.println("HTTP connection lost during download");
//                 break;
//             }

//             size_t availableBytes = stream->available();
//             if (availableBytes > 0)
//             {
//                 size_t bytesToRead = min(availableBytes, bufferSize);
//                 int bytesRead = stream->readBytes(buffer, bytesToRead);

//                 if (bytesRead > 0)
//                 {
//                     size_t bytesWritten = file.write(buffer, bytesRead);
//                     if (bytesWritten != bytesRead)
//                     {
//                         Serial.printf("Write error: expected %d, written %d\n", bytesRead, bytesWritten);
//                         shouldContinue = false;
//                         break;
//                     }

//                     totalDownloaded += bytesRead;

//                     // Progress update every second or every 10KB
//                     unsigned long currentTime = millis();
//                     if (currentTime - lastProgressTime >= 1000 ||
//                         totalDownloaded % 10240 == 0)
//                     {
//                         Serial.printf("Downloaded: %d/%d bytes (%.1f%%)\n",
//                                       totalDownloaded,
//                                       contentLength > 0 ? contentLength : totalDownloaded,
//                                       contentLength > 0 ? (totalDownloaded * 100.0 / contentLength) : 0.0);
//                         lastProgressTime = currentTime;
//                     }

//                     shouldContinue = updateProgress(bytesRead, false);

//                     if (!shouldContinue)
//                     {
//                         Serial.println("Download cancelled by user");
//                         break;
//                     }

//                     // Watchdog reset for long downloads
//                     yield();
//                 }
//                 else
//                 {
//                     // No bytes read, wait a bit
//                     delay(10);
//                 }
//             }
//             else
//             {
//                 // No data available, check if we're done or connection lost
//                 if (contentLength > 0 && totalDownloaded >= contentLength)
//                 {
//                     break; // Download complete
//                 }

//                 // Wait for more data
//                 delay(10);

//                 // Timeout check (30 seconds without data)
//                 if (millis() - lastProgressTime > 30000)
//                 {
//                     Serial.println("Download timeout - no data received");
//                     shouldContinue = false;
//                     break;
//                 }
//             }
//         }

//         file.close();
//         http.end();

//         unsigned long downloadTime = millis() - downloadStartTime;
//         Serial.printf("Download finished in %lu ms\n", downloadTime);

//         if (!shouldContinue)
//         {
//             SPIFFS.remove(spiffsPath); // Remove incomplete file
//             return false;
//         }

//         // Verify file was saved correctly
//         if (SPIFFS.exists(spiffsPath))
//         {
//             File verifyFile = SPIFFS.open(spiffsPath, "r");
//             uint32_t savedSize = verifyFile.size();
//             verifyFile.close();

//             Serial.printf("File saved: %s, size: %d bytes\n", filename, savedSize);

//             if (contentLength > 0 && savedSize != contentLength)
//             {
//                 Serial.printf("WARNING: Size mismatch! Expected: %d, Saved: %d\n",
//                               contentLength, savedSize);
//                 SPIFFS.remove(spiffsPath); // Remove corrupted file
//                 return false;
//             }

//             // Calculate and log hash for verification
//             String savedHash = calculateFileHash(filename);
//             Serial.printf("File hash after save: %s\n", savedHash.c_str());
//         }
//         else
//         {
//             Serial.printf("ERROR: File was not saved: %s\n", filename);
//             return false;
//         }

//         Serial.println("File downloaded successfully: " + String(filename));
//         return true;
//     }
//     else
//     {
//         Serial.printf("Download error for file: %s, code: %d\n", filename, httpResponseCode);
//         http.end();
//         return false;
//     }
// }

// // Delete file
// bool deleteFile(const char *filename)
// {
//     // Add "/" prefix for SPIFFS
//     String spiffsPath = "/";
//     spiffsPath += filename;

//     if (SPIFFS.remove(spiffsPath))
//     {
//         Serial.println("File deleted: " + String(filename));
//         return true;
//     }
//     else
//     {
//         Serial.println("Error deleting file: " + String(filename));
//         return false;
//     }
// }

// // Get file list from server
// String getServerFileList()
// {
//     HTTPClient http;
//     http.begin(String(serverAddress) + "/list");

//     int httpResponseCode = http.GET();

//     if (httpResponseCode == 200)
//     {
//         String payload = http.getString();
//         http.end();

//         Serial.println("=== Server file list ===");

//         // Parse and log server files for debugging
//         JsonDocument serverDoc;
//         DeserializationError error = deserializeJson(serverDoc, payload);

//         if (!error)
//         {
//             JsonArray serverFiles = serverDoc["files"];
//             for (JsonObject file : serverFiles)
//             {
//                 String filename = file["name"].as<String>();
//                 uint32_t fileSize = file["size"].as<uint32_t>();
//                 String fileHash = file["hash"].as<String>();

//                 Serial.printf("Server file: %s, size: %d, hash: %s\n",
//                               filename.c_str(), fileSize, fileHash.c_str());
//             }
//         }

//         Serial.println("=== End server file list ===");

//         return payload;
//     }
//     else
//     {
//         Serial.printf("Error getting file list from server, code: %d\n", httpResponseCode);
//         http.end();
//         return "";
//     }
// }

// // Calculate total sync size (only downloads from server)
// uint32_t calculateSyncSize(const std::map<String, JsonObject> &serverMap,
//                            const std::map<String, JsonObject> &localMap)
// {
//     uint32_t totalSize = 0;

//     // Files to download (on server but not local, or different hash)
//     for (auto &pair : serverMap)
//     {
//         String filename = pair.first;
//         JsonObject serverFile = pair.second;

//         if (localMap.find(filename) == localMap.end())
//         {
//             // File exists on server but not locally
//             totalSize += serverFile["size"].as<uint32_t>();
//         }
//         else
//         {
//             // File exists both places, check if different
//             JsonObject localFile = localMap.at(filename);
//             String serverHash = serverFile["hash"].as<String>();
//             String localHash = localFile["hash"].as<String>();
//             serverHash.toLowerCase();
//             localHash.toLowerCase();

//             if (serverHash != localHash)
//             {
//                 totalSize += serverFile["size"].as<uint32_t>();
//             }
//         }
//     }

//     // Note: No upload size calculation for one-way sync

//     return totalSize;
// }

// // Count total files to sync (only downloads)
// uint32_t countSyncFiles(const std::map<String, JsonObject> &serverMap,
//                         const std::map<String, JsonObject> &localMap)
// {
//     uint32_t totalFiles = 0;

//     // Files to download
//     for (auto &pair : serverMap)
//     {
//         String filename = pair.first;
//         JsonObject serverFile = pair.second;

//         if (localMap.find(filename) == localMap.end())
//         {
//             totalFiles++;
//         }
//         else
//         {
//             JsonObject localFile = localMap.at(filename);
//             String serverHash = serverFile["hash"].as<String>();
//             String localHash = localFile["hash"].as<String>();
//             serverHash.toLowerCase();
//             localHash.toLowerCase();

//             if (serverHash != localHash)
//             {
//                 totalFiles++;
//             }
//         }
//     }

//     // Note: No upload file counting for one-way sync

//     return totalFiles;
// }

// // Main sync function
// void syncFiles()
// {
//     Serial.println("Starting synchronization...");

//     // Reset progress
//     syncProgress = {0, 0, 0, 0, 0, 0, millis()};

//     // Get file list from server
//     String serverListStr = getServerFileList();
//     if (serverListStr.isEmpty())
//     {
//         Serial.println("Failed to get file list from server");
//         return;
//     }

//     // Get local file list
//     String localListStr = getLocalFileList();

//     // Parse JSON
//     JsonDocument serverDoc;
//     JsonDocument localDoc;

//     DeserializationError serverError = deserializeJson(serverDoc, serverListStr);
//     DeserializationError localError = deserializeJson(localDoc, localListStr);

//     if (serverError)
//     {
//         Serial.println("Error parsing server JSON: " + String(serverError.c_str()));
//         return;
//     }

//     if (localError)
//     {
//         Serial.println("Error parsing local JSON: " + String(localError.c_str()));
//         return;
//     }

//     JsonArray serverFiles = serverDoc["files"];
//     JsonArray localFiles = localDoc["files"];

//     // Create maps for quick lookup
//     std::map<String, JsonObject> serverMap;
//     std::map<String, JsonObject> localMap;

//     // Fill server files map
//     for (JsonObject file : serverFiles)
//     {
//         String filename = file["name"].as<String>();
//         serverMap[filename] = file;
//     }

//     // Fill local files map
//     for (JsonObject file : localFiles)
//     {
//         String filename = file["name"].as<String>();
//         localMap[filename] = file;
//     }

//     // Calculate total sync size and file count
//     syncProgress.totalBytes = calculateSyncSize(serverMap, localMap);
//     syncProgress.totalFiles = countSyncFiles(serverMap, localMap);

//     Serial.printf("One-way sync started (server → ESP32): %d files, %d bytes total\n",
//                   syncProgress.totalFiles, syncProgress.totalBytes);

//     if (syncProgress.totalFiles == 0)
//     {
//         Serial.println("No files to sync from server");
//         return;
//     }

//     bool shouldContinue = true;

//     // Only download files from server (one-way sync)
//     for (auto &pair : serverMap)
//     {
//         if (!shouldContinue)
//             break;

//         String filename = pair.first;
//         JsonObject serverFile = pair.second;

//         if (localMap.find(filename) == localMap.end())
//         {
//             // File exists on server but not locally - download
//             Serial.println("Downloading new file: " + filename);
//             shouldContinue = downloadFile(filename.c_str());
//         }
//         else
//         {
//             // File exists both places - check hash
//             JsonObject localFile = localMap[filename];
//             String serverHash = serverFile["hash"].as<String>();
//             String localHash = localFile["hash"].as<String>();
//             serverHash.toLowerCase();
//             localHash.toLowerCase();

//             Serial.printf("Comparing file: %s\n", filename.c_str());
//             Serial.printf("  Server hash: %s\n", serverHash.c_str());
//             Serial.printf("  Local hash:  %s\n", localHash.c_str());

//             if (serverHash != localHash)
//             {
//                 // Hashes don't match - download newer version from server
//                 Serial.println("Hash mismatch - updating file from server: " + filename);
//                 shouldContinue = downloadFile(filename.c_str());
//             }
//             else
//             {
//                 Serial.println("File up to date: " + filename);
//             }
//         }

//         if (shouldContinue)
//         {
//             syncProgress.processedFiles++;
//         }
//     }

//     // Remove local files that don't exist on server (configurable cleanup)
//     if (REMOVE_LOCAL_FILES_NOT_ON_SERVER)
//     {
//         Serial.println("Checking for local files to remove...");
//         for (auto &pair : localMap)
//         {
//             if (!shouldContinue)
//                 break;

//             String filename = pair.first;

//             if (serverMap.find(filename) == serverMap.end())
//             {
//                 // File exists locally but not on server - remove it
//                 Serial.println("Removing local file not on server: " + filename);
//                 deleteFile(filename.c_str());
//             }
//         }
//     }
//     else
//     {
//         Serial.println("Local file cleanup disabled - keeping all local files");
//     }

//     if (shouldContinue)
//     {
//         Serial.println("Synchronization completed successfully");
//     }
//     else
//     {
//         Serial.println("Synchronization cancelled by user");
//     }

//     // Final progress update
//     if (progressCallback)
//     {
//         uint32_t totalTransferred = syncProgress.downloadedBytes + syncProgress.uploadedBytes;
//         progressCallback(totalTransferred, syncProgress.totalBytes, 100);
//     }
// }

// // Function to set custom progress callback
// void setProgressCallback(ProgressCallback callback)
// {
//     progressCallback = callback;
// }

// void setup()
// {
//     Serial.begin(115200);
//     delay(1000);

//     Serial.println("=== ESP32 SPIFFS Sync Client ===");

//     // Initialize SPIFFS
//     if (!SPIFFS.begin(true))
//     {
//         Serial.println("SPIFFS initialization error");
//         return;
//     }

//     // Show SPIFFS info
//     Serial.printf("SPIFFS Total: %d bytes\n", SPIFFS.totalBytes());
//     Serial.printf("SPIFFS Used: %d bytes\n", SPIFFS.usedBytes());
//     Serial.printf("SPIFFS Free: %d bytes\n", SPIFFS.totalBytes() - SPIFFS.usedBytes());

//     // Connect to WiFi
//     WiFi.begin(ssid, password);
//     Serial.print("Connecting to WiFi");

//     while (WiFi.status() != WL_CONNECTED)
//     {
//         delay(1000);
//         Serial.print(".");
//     }

//     Serial.println();
//     Serial.println("WiFi connected!");
//     Serial.print("IP address: ");
//     Serial.println(WiFi.localIP());

// }

// void printFileSystem()
// {
//     File root = SPIFFS.open("/");
//     File file = root.openNextFile();

//     Serial.println("File system contents:");
//     Serial.println("----------------------------");

//     while (file)
//     {
//         if (file.isDirectory())
//         {
//             Serial.print("DIR: ");
//             Serial.println(file.name());
//         }
//         else
//         {
//             Serial.print("FILE: ");
//             Serial.print(file.name());
//             Serial.print(" (");
//             Serial.print(file.size());
//             Serial.println(" bytes)");
//         }
//         file = root.openNextFile();
//     }

//     Serial.println("----------------------------");

//     // File system information
//     Serial.print("Total size: ");
//     Serial.print(SPIFFS.totalBytes());
//     Serial.println(" bytes");

//     Serial.print("Used: ");
//     Serial.print(SPIFFS.usedBytes());
//     Serial.println(" bytes");

//     Serial.print("Free: ");
//     Serial.print(SPIFFS.totalBytes() - SPIFFS.usedBytes());
//     Serial.println(" bytes");
// }

// void loop()
// {
//     if (WiFi.status() == WL_CONNECTED)
//     {
//         syncFiles();
//     }
//     else
//     {
//         Serial.println("WiFi not connected");
//     }
//     Serial.println("========================");
//     printFileSystem();
//     Serial.println("========================\r\n\n\n");
//     delay(20000);
// }

// // #include <Arduino.h>
// // #include <WiFi.h>

// // #include "espRadio.h"
// // #include "serialCommander.h"
// // #include "gameEngine.h"

// // void setup()
// // {
// //     Serial.begin(115200);
// //     delay(500);
// //     Serial.println(">>> BOOT");
// //     delay(10);
// //     prepareWiFi();
// //     rssiReaderInit();
// //     initRadio();
// //     testGameHuman();
// //     //testGameZombie();
// //     //testGameBase();
// //     serialCommInit();
// // }

// // void loop()
// // {
// //     serialCommLoop();
// //     delay(50);
// // }