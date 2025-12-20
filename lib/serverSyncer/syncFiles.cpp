#include <Arduino.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "PSRamFS.h"
#include <map>
#include "serverSync.h"

#ifdef _PSRAMFS_H_
#define SYNC_IGNORE_HASH    1
#else 
#define SYNC_IGNORE_HASH    0
#endif

const bool REMOVE_LOCAL_FILES_NOT_ON_SERVER = false; // Set to true to enable cleanup
ProgressCallback progressCallback = NULL;

// Function to update and report progress
bool updateProgress(SyncProgress &syncProgress, uint32_t bytesTransferred, bool isUpload = false)
{
    if (isUpload)
    {
        syncProgress.uploadedBytes += bytesTransferred;
    }
    else
    {
        syncProgress.downloadedBytes += bytesTransferred;
    }

    uint32_t totalTransferred = syncProgress.downloadedBytes + syncProgress.uploadedBytes;

    if (syncProgress.totalBytes > 0)
    {
        syncProgress.percentage = (totalTransferred * 100) / syncProgress.totalBytes;
    }

    // Call progress callback every second
    unsigned long currentTime = millis();
    if (currentTime - syncProgress.lastUpdateTime >= 1000)
    {
        syncProgress.lastUpdateTime = currentTime;

        if (progressCallback)
        {
            return progressCallback(totalTransferred, syncProgress.totalBytes, syncProgress.percentage);
        }
    }

    return true;
}

// Function to get list of files from PsRamFS
String getLocalFileList()
{
    JsonDocument doc;
    JsonArray files = doc["files"].to<JsonArray>();

    Serial.println("=== Local PsRamFS file list ===");

    File root = PSRamFS.open("/");
    File file = root.openNextFile();

    while (file)
    {
        if (!file.isDirectory())
        {
            String fullPath = file.name();
            String filename = fullPath;

            // Remove leading "/" for compatibility with server
            if (filename.startsWith("/"))
            {
                filename = filename.substring(1);
            }

            uint32_t fileSize = file.size();

            Serial.printf("Local file: %s, size: %d\n",
                          filename.c_str(), fileSize);

            JsonObject fileObj = files.add<JsonObject>();
            fileObj["name"] = filename;
            fileObj["size"] = fileSize;
            // Hash removed for RAM-drive
        }
        file = root.openNextFile();
    }

    Serial.println("=== End local file list ===");

    String result;
    serializeJson(doc, result);
    return result;
}

// Upload file to server - disabled for one-way sync
bool uploadFile(const char *serverAddress, const char *filename)
{
    Serial.printf("Upload disabled - one-way sync (server to ESP32 only)\n");
    return true; // Always return true to avoid breaking sync flow
}

// Download file from server with progress tracking
bool downloadFile(const char *serverAddress, const char *filename, SyncProgress &syncProgress)
{
    HTTPClient http;
    http.begin(String(serverAddress) + "/download?file=" + String(filename));
    http.setTimeout(30000);        // 30 second timeout for large files
    http.setConnectTimeout(10000); // 10 second connection timeout

    int httpResponseCode = http.GET();

    if (httpResponseCode == 200)
    {
        int contentLength = http.getSize();
        Serial.printf("Downloading file: %s (%d bytes)\n", filename, contentLength);

        // Check if we have enough space in PsRamFS
        size_t freeSpace = PSRamFS.totalBytes() - PSRamFS.usedBytes();
        if (contentLength > 0 && contentLength > freeSpace)
        {
            Serial.printf("Error: Not enough space in PsRamFS. Need: %d, Available: %d\n",
                          contentLength, freeSpace);
            http.end();
            return false;
        }

        // Add "/" prefix for PsRamFS
        String psramPath = "/";
        psramPath += filename;

        // Remove existing file first to avoid corruption
        if (PSRamFS.exists(psramPath))
        {
            PSRamFS.remove(psramPath);
            Serial.printf("Removed existing file: %s\n", psramPath.c_str());
        }

        File file = PSRamFS.open(psramPath, "w");
        if (!file)
        {
            Serial.println("Error creating file: " + psramPath);
            http.end();
            return false;
        }

        WiFiClient *stream = http.getStreamPtr();
        const size_t bufferSize = 512; // Smaller buffer for stability
        uint8_t buffer[bufferSize];
        int totalDownloaded = 0;
        bool shouldContinue = true;
        unsigned long lastProgressTime = millis();
        unsigned long downloadStartTime = millis();

        Serial.printf("Starting download of %d bytes...\n", contentLength);

        // Download with improved error handling
        while (shouldContinue && (contentLength < 0 || totalDownloaded < contentLength))
        {
            // Check if connection is still alive
            if (!http.connected())
            {
                Serial.println("HTTP connection lost during download");
                break;
            }

            size_t availableBytes = stream->available();
            if (availableBytes > 0)
            {
                size_t bytesToRead = min(availableBytes, bufferSize);
                int bytesRead = stream->readBytes(buffer, bytesToRead);

                if (bytesRead > 0)
                {
                    size_t bytesWritten = file.write(buffer, bytesRead);
                    if (bytesWritten != bytesRead)
                    {
                        Serial.printf("Write error: expected %d, written %d\n", bytesRead, bytesWritten);
                        shouldContinue = false;
                        break;
                    }

                    totalDownloaded += bytesRead;

                    // Progress update every second or every 10KB
                    unsigned long currentTime = millis();
                    if (currentTime - lastProgressTime >= 1000 ||
                        totalDownloaded % 10240 == 0)
                    {
                        Serial.printf("Downloaded: %d/%d bytes (%.1f%%)\n",
                                      totalDownloaded,
                                      contentLength > 0 ? contentLength : totalDownloaded,
                                      contentLength > 0 ? (totalDownloaded * 100.0 / contentLength) : 0.0);
                        lastProgressTime = currentTime;
                    }

                    shouldContinue = updateProgress(syncProgress, bytesRead, false);

                    if (!shouldContinue)
                    {
                        Serial.println("Download cancelled by user");
                        break;
                    }

                    // Watchdog reset for long downloads
                    yield();
                }
                else
                {
                    // No bytes read, wait a bit
                    delay(10);
                }
            }
            else
            {
                // No data available, check if we're done or connection lost
                if (contentLength > 0 && totalDownloaded >= contentLength)
                {
                    break; // Download complete
                }

                // Wait for more data
                delay(10);

                // Timeout check (30 seconds without data)
                if (millis() - lastProgressTime > 30000)
                {
                    Serial.println("Download timeout - no data received");
                    shouldContinue = false;
                    break;
                }
            }
        }

        file.close();
        http.end();

        unsigned long downloadTime = millis() - downloadStartTime;
        Serial.printf("Download finished in %lu ms\n", downloadTime);

        if (!shouldContinue)
        {
            PSRamFS.remove(psramPath); // Remove incomplete file
            return false;
        }

        // Verify file was saved correctly
        if (PSRamFS.exists(psramPath))
        {
            File verifyFile = PSRamFS.open(psramPath, "r");
            uint32_t savedSize = verifyFile.size();
            verifyFile.close();

            Serial.printf("File saved: %s, size: %d bytes\n", filename, savedSize);

            if (contentLength > 0 && savedSize != contentLength)
            {
                Serial.printf("WARNING: Size mismatch! Expected: %d, Saved: %d\n",
                              contentLength, savedSize);
                PSRamFS.remove(psramPath); // Remove corrupted file
                return false;
            }
        }
        else
        {
            Serial.printf("ERROR: File was not saved: %s\n", filename);
            return false;
        }

        Serial.println("File downloaded successfully: " + String(filename));
        return true;
    }
    else
    {
        Serial.printf("Download error for file: %s, code: %d\n", filename, httpResponseCode);
        http.end();
        return false;
    }
}

// Delete file
bool deleteFile(const char *filename)
{
    // Add "/" prefix for PsRamFS
    String psramPath = "/";
    psramPath += filename;

    if (PSRamFS.remove(psramPath))
    {
        Serial.println("File deleted: " + String(filename));
        return true;
    }
    else
    {
        Serial.println("Error deleting file: " + String(filename));
        return false;
    }
}

// Get file list from server
String getServerFileList(const char *serverAddress)
{
    HTTPClient http;
    http.begin(String(serverAddress) + "/list");

    int httpResponseCode = http.GET();

    if (httpResponseCode == 200)
    {
        String payload = http.getString();
        http.end();

        Serial.println("=== Server file list ===");

        // Parse and log server files for debugging
        JsonDocument serverDoc;
        DeserializationError error = deserializeJson(serverDoc, payload);

        if (!error)
        {
            JsonArray serverFiles = serverDoc["files"];
            for (JsonObject file : serverFiles)
            {
                String filename = file["name"].as<String>();
                uint32_t fileSize = file["size"].as<uint32_t>();

                Serial.printf("Server file: %s, size: %d\n",
                              filename.c_str(), fileSize);
            }
        }

        Serial.println("=== End server file list ===");

        return payload;
    }
    else
    {
        Serial.printf("Error getting file list from server, code: %d\n", httpResponseCode);
        http.end();
        return "";
    }
}

// Calculate total sync size (only downloads from server)
uint32_t calculateSyncSize(const std::map<String, JsonObject> &serverMap,
                           const std::map<String, JsonObject> &localMap)
{
    uint32_t totalSize = 0;

    // Files to download (on server but not local)
    for (auto &pair : serverMap)
    {
        String filename = pair.first;
        JsonObject serverFile = pair.second;

        if (localMap.find(filename) == localMap.end())
        {
            // File exists on server but not locally
            totalSize += serverFile["size"].as<uint32_t>();
        }
        // Hash comparison removed - always re-download existing files for RAM-drive
    }

    return totalSize;
}

// Count total files to sync (only downloads)
uint32_t countSyncFiles(const std::map<String, JsonObject> &serverMap,
                        const std::map<String, JsonObject> &localMap)
{
    uint32_t totalFiles = 0;

    // Files to download
    for (auto &pair : serverMap)
    {
        String filename = pair.first;

        if (localMap.find(filename) == localMap.end())
        {
            totalFiles++;
        }
        // Hash comparison removed - don't count existing files for re-download
    }

    return totalFiles;
}

// Main sync function
bool syncFiles(const char *serverAddress, ProgressCallback callback) 
{
    SyncProgress syncProgress = {0, 0, 0, 0, 0, 0, 0};
    Serial.print(">>> syncFiles: ");    
    Serial.println(serverAddress);
    setProgressCallback(callback);

    syncProgress = {0, 0, 0, 0, 0, 0, millis()};

    // Get file list from server
    String serverListStr = getServerFileList(serverAddress);
    if (serverListStr.isEmpty())
    {
        Serial.println("Failed to get file list from server");
        return false;
    }

    // Get local file list
    String localListStr = getLocalFileList();

    // Parse JSON
    JsonDocument serverDoc;
    JsonDocument localDoc;

    DeserializationError serverError = deserializeJson(serverDoc, serverListStr);
    DeserializationError localError = deserializeJson(localDoc, localListStr);

    if (serverError)
    {
        Serial.println("Error parsing server JSON: " + String(serverError.c_str()));
        return false;
    }

    if (localError)
    {
        Serial.println("Error parsing local JSON: " + String(localError.c_str()));
        return false;
    }

    JsonArray serverFiles = serverDoc["files"];
    JsonArray localFiles = localDoc["files"];

    // Create maps for quick lookup
    std::map<String, JsonObject> serverMap;
    std::map<String, JsonObject> localMap;

    // Fill server files map
    for (JsonObject file : serverFiles)
    {
        String filename = file["name"].as<String>();
        serverMap[filename] = file;
    }

    // Fill local files map
    for (JsonObject file : localFiles)
    {
        String filename = file["name"].as<String>();
        localMap[filename] = file;
    }

    // Calculate total sync size and file count
    syncProgress.totalBytes = calculateSyncSize(serverMap, localMap);
    syncProgress.totalFiles = countSyncFiles(serverMap, localMap);

    Serial.printf("One-way sync started (server → ESP32): %d files, %d bytes total\n",
                  syncProgress.totalFiles, syncProgress.totalBytes);

    if (syncProgress.totalFiles == 0)
    {
        Serial.println("No files to sync from server");
        return false;
    }

    bool shouldContinue = true;

    // Only download files from server (one-way sync)
    for (auto &pair : serverMap)
    {
        if (!shouldContinue)
            break;

        String filename = pair.first;

        if (localMap.find(filename) == localMap.end())
        {
            // File exists on server but not locally - download
            Serial.println("Downloading new file: " + filename);
            shouldContinue = downloadFile(serverAddress, filename.c_str(), syncProgress);
        }
        else
        {
            // File exists both places - skip hash check for RAM-drive
            Serial.println("File already exists locally (skipping): " + filename);
        }

        if (shouldContinue)
        {
            syncProgress.processedFiles++;
        }
    }

    // Remove local files that don't exist on server (configurable cleanup)
    if (REMOVE_LOCAL_FILES_NOT_ON_SERVER)
    {
        Serial.println("Checking for local files to remove...");
        for (auto &pair : localMap)
        {
            if (!shouldContinue)
                break;

            String filename = pair.first;

            if (serverMap.find(filename) == serverMap.end())
            {
                // File exists locally but not on server - remove it
                Serial.println("Removing local file not on server: " + filename);
                deleteFile(filename.c_str());
            }
        }
    }
    else
    {
        Serial.println("Local file cleanup disabled - keeping all local files");
    }

    if (shouldContinue)
    {
        Serial.println("Synchronization completed successfully");
    }
    else
    {
        Serial.println("Synchronization cancelled by user");
        return false;
    }

    // Final progress update
    if (progressCallback)
    {
        uint32_t totalTransferred = syncProgress.downloadedBytes + syncProgress.uploadedBytes;
        progressCallback(totalTransferred, syncProgress.totalBytes, 100);
    }
    return true;
}

// Function to set custom progress callback
void setProgressCallback(ProgressCallback callback)
{
    progressCallback = callback;
}

// Default progress callback (stub with print)
bool defaultProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage)
{
    Serial.printf("Progress: %d/%d bytes (%d%%) downloaded\n", downloaded, total, percentage);

    // Add your custom logic here
    // Return false to cancel sync, true to continue
    return true;
}

void printPsramFileSystem(void)
{
    File root = PSRamFS.open("/");
    File file = root.openNextFile();

    Serial.println("File system contents:");
    Serial.println("----------------------------");

    while (file)
    {
        if (file.isDirectory())
        {
            Serial.print("DIR: ");
            Serial.println(file.name());
        }
        else
        {
            Serial.print("FILE: ");
            Serial.print(file.name());
            Serial.print(" (");
            Serial.print(file.size());
            Serial.println(" bytes)");
        }
        file = root.openNextFile();
    }

    Serial.println("----------------------------");

    // File system information
    Serial.print("Total size: ");
    Serial.print(PSRamFS.totalBytes());
    Serial.println(" bytes");

    Serial.print("Used: ");
    Serial.print(PSRamFS.usedBytes());
    Serial.println(" bytes");

    Serial.print("Free: ");
    Serial.print(PSRamFS.totalBytes() - PSRamFS.usedBytes());
    Serial.println(" bytes");
}

// #include <Arduino.h>
// #include <HTTPClient.h>
// #include <ArduinoJson.h>
// #include "PSRamFS.h"
// #include <map>
// #include "serverSync.h"

// #ifdef _PSRAMFS_H_
// #define SYNC_IGNORE_HASH    1
// #else 
// #define SYNC_IGNORE_HASH    0
// #endif

// const bool REMOVE_LOCAL_FILES_NOT_ON_SERVER = false; // Set to true to enable cleanup
// ProgressCallback progressCallback = NULL;

// // Function to update and report progress
// bool updateProgress(SyncProgress &syncProgress, uint32_t bytesTransferred, bool isUpload = false)
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

// // Function to get list of files from PsRamFS
// String getLocalFileList()
// {
//     JsonDocument doc;
//     JsonArray files = doc["files"].to<JsonArray>();

//     Serial.println("=== Local PsRamFS file list ===");

//     File root = PSRamFS.open("/");
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
//     // Add "/" prefix for PsRamFS
//     String psramPath = "/";
//     psramPath += filename;

//     File file = PSRamFS.open(psramPath, "r");
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
// bool uploadFile(const char *serverAddress, const char *filename)
// {
//     Serial.printf("Upload disabled - one-way sync (server to ESP32 only)\n");
//     return true; // Always return true to avoid breaking sync flow
// }

// // Download file from server with progress tracking
// bool downloadFile(const char *serverAddress, const char *filename, SyncProgress &syncProgress)
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

//         // Check if we have enough space in PsRamFS
//         size_t freeSpace = PSRamFS.totalBytes() - PSRamFS.usedBytes();
//         if (contentLength > 0 && contentLength > freeSpace)
//         {
//             Serial.printf("Error: Not enough space in PsRamFS. Need: %d, Available: %d\n",
//                           contentLength, freeSpace);
//             http.end();
//             return false;
//         }

//         // Add "/" prefix for PsRamFS
//         String psramPath = "/";
//         psramPath += filename;

//         // Remove existing file first to avoid corruption
//         if (PSRamFS.exists(psramPath))
//         {
//             PSRamFS.remove(psramPath);
//             Serial.printf("Removed existing file: %s\n", psramPath.c_str());
//         }

//         File file = PSRamFS.open(psramPath, "w");
//         if (!file)
//         {
//             Serial.println("Error creating file: " + psramPath);
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

//                     shouldContinue = updateProgress(syncProgress, bytesRead, false);

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
//             PSRamFS.remove(psramPath); // Remove incomplete file
//             return false;
//         }

//         // Verify file was saved correctly
//         if (PSRamFS.exists(psramPath))
//         {
//             File verifyFile = PSRamFS.open(psramPath, "r");
//             uint32_t savedSize = verifyFile.size();
//             verifyFile.close();

//             Serial.printf("File saved: %s, size: %d bytes\n", filename, savedSize);

//             if (contentLength > 0 && savedSize != contentLength)
//             {
//                 Serial.printf("WARNING: Size mismatch! Expected: %d, Saved: %d\n",
//                               contentLength, savedSize);
//                 PSRamFS.remove(psramPath); // Remove corrupted file
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
//     // Add "/" prefix for PsRamFS
//     String psramPath = "/";
//     psramPath += filename;

//     if (PSRamFS.remove(psramPath))
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
// String getServerFileList(const char *serverAddress)
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
// bool syncFiles(const char *serverAddress, ProgressCallback callback) 
// {
//     SyncProgress syncProgress = {0, 0, 0, 0, 0, 0, 0};
//     Serial.print("Starting synchronization: ");    
//     Serial.println(serverAddress);
//     setProgressCallback(callback);

//     syncProgress = {0, 0, 0, 0, 0, 0, millis()};

//     // Get file list from server
//     String serverListStr = getServerFileList(serverAddress);
//     if (serverListStr.isEmpty())
//     {
//         Serial.println("Failed to get file list from server");
//         return false;
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
//         return false;
//     }

//     if (localError)
//     {
//         Serial.println("Error parsing local JSON: " + String(localError.c_str()));
//         return false;
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
//         return false;
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
//             shouldContinue = downloadFile(serverAddress, filename.c_str(), syncProgress);
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
//                 shouldContinue = downloadFile(serverAddress, filename.c_str(), syncProgress);
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
//     return true;
// }

// // Function to set custom progress callback
// void setProgressCallback(ProgressCallback callback)
// {
//     progressCallback = callback;
// }

// // Default progress callback (stub with print)
// bool defaultProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage)
// {
//     Serial.printf("Progress: %d/%d bytes (%d%%) downloaded\n", downloaded, total, percentage);

//     // Add your custom logic here
//     // Return false to cancel sync, true to continue
//     return true;
// }