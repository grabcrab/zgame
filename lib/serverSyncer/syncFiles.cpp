/**
 * @file syncFiles.cpp
 * @brief ESP32 File Synchronization Library with SPIFFS persistence and PSRAM caching
 * 
 * This library synchronizes files from a server to the ESP32:
 * 1. Files are downloaded and stored permanently in SPIFFS
 * 2. After sync, files are copied to PSRAM for fast runtime access
 * 3. On boot, files can be loaded from SPIFFS to PSRAM (no network needed)
 * 
 * SPIFFS provides persistence across reboots
 * PSRAM provides fast file access during runtime
 */

#include <Arduino.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPIFFS.h>
#include "PSRamFS.h"
#include <map>
#include "serverSync.h"

// Configuration
static const bool REMOVE_LOCAL_FILES_NOT_ON_SERVER = false;
static ProgressCallback progressCallback = nullptr;

// Buffer size for file operations
static const size_t COPY_BUFFER_SIZE = 4096;

// Cached server file list filename
static const char* SERVER_LIST_CACHE_FILE = "/.server_list.json";

//=============================================================================
// SPIFFS Initialization (internal use)
//=============================================================================

static bool initSpiffs()
{
    if (!SPIFFS.begin(true)) // true = format if mount fails
    {
        Serial.println("ERROR: SPIFFS initialization failed!");
        return false;
    }
    
    Serial.printf("SPIFFS initialized: Total=%d, Used=%d, Free=%d bytes\n",
                  SPIFFS.totalBytes(), SPIFFS.usedBytes(), 
                  SPIFFS.totalBytes() - SPIFFS.usedBytes());
    return true;
}

static void endSpiffs()
{
    SPIFFS.end();
    Serial.println("SPIFFS unmounted");
}

//=============================================================================
// Server List Cache (for hash comparison)
//=============================================================================

static bool saveServerListCache(const String &serverListStr)
{
    File file = SPIFFS.open(SERVER_LIST_CACHE_FILE, "w");
    if (!file)
    {
        Serial.println("ERROR: Failed to create server list cache file");
        return false;
    }
    
    size_t written = file.print(serverListStr);
    file.close();
    
    if (written == serverListStr.length())
    {
        Serial.printf("Server list cached (%d bytes)\n", written);
        return true;
    }
    else
    {
        Serial.println("ERROR: Failed to write server list cache");
        return false;
    }
}

static String loadServerListCache()
{
    if (!SPIFFS.exists(SERVER_LIST_CACHE_FILE))
    {
        Serial.println("No cached server list found");
        return "";
    }
    
    File file = SPIFFS.open(SERVER_LIST_CACHE_FILE, "r");
    if (!file)
    {
        Serial.println("ERROR: Failed to open server list cache");
        return "";
    }
    
    String content = file.readString();
    file.close();
    
    Serial.printf("Loaded cached server list (%d bytes)\n", content.length());
    return content;
}

static bool isServerListChanged(const String &newServerList)
{
    String cachedList = loadServerListCache();
    
    if (cachedList.isEmpty())
    {
        Serial.println("No cache - sync required");
        return true;
    }
    
    if (cachedList == newServerList)
    {
        Serial.println("Server list unchanged (hash match)");
        return false;
    }
    else
    {
        Serial.println("Server list changed - sync required");
        return true;
    }
}

//=============================================================================
// Progress Tracking
//=============================================================================

static bool updateProgress(SyncProgress &syncProgress, uint32_t bytesTransferred, bool isUpload = false)
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

void setProgressCallback(ProgressCallback callback)
{
    progressCallback = callback;
}

bool defaultProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage)
{
    Serial.printf("Progress: %d/%d bytes (%d%%)\n", downloaded, total, percentage);
    return true;
}

//=============================================================================
// SPIFFS File Operations (Persistent Storage)
//=============================================================================

String getLocalFileList()
{
    JsonDocument doc;
    JsonArray files = doc["files"].to<JsonArray>();

    Serial.println("=== Local SPIFFS file list ===");

    File root = SPIFFS.open("/");
    if (!root || !root.isDirectory())
    {
        Serial.println("Failed to open SPIFFS root");
        String result;
        serializeJson(doc, result);
        return result;
    }

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

            Serial.printf("  %s (%d bytes)\n", filename.c_str(), fileSize);

            JsonObject fileObj = files.add<JsonObject>();
            fileObj["name"] = filename;
            fileObj["size"] = fileSize;
        }
        file = root.openNextFile();
    }

    Serial.println("=== End local file list ===");

    String result;
    serializeJson(doc, result);
    return result;
}

bool deleteFileFromSpiffs(const char *filename)
{
    String spiffsPath = "/";
    spiffsPath += filename;

    if (SPIFFS.remove(spiffsPath))
    {
        Serial.printf("Deleted from SPIFFS: %s\n", filename);
        return true;
    }
    else
    {
        Serial.printf("Error deleting from SPIFFS: %s\n", filename);
        return false;
    }
}

bool fileExistsOnSpiffs(const char *filename)
{
    String spiffsPath = "/";
    spiffsPath += filename;
    return SPIFFS.exists(spiffsPath);
}

size_t getSpiffsFreeSpace()
{
    return SPIFFS.totalBytes() - SPIFFS.usedBytes();
}

//=============================================================================
// PSRAM File Operations (Fast Runtime Cache)
//=============================================================================

bool fileExistsOnPsram(const char *filename)
{
    String psramPath = "/";
    psramPath += filename;
    return PSRamFS.exists(psramPath);
}

size_t getPsramFreeSpace()
{
    return PSRamFS.totalBytes() - PSRamFS.usedBytes();
}

//=============================================================================
// Copy Files from SPIFFS to PSRAM
//=============================================================================

static bool copyFileToPsram(const char *filename)
{
    String spiffsPath = "/";
    spiffsPath += filename;
    
    String psramPath = "/";
    psramPath += filename;

    // Open source file from SPIFFS
    File srcFile = SPIFFS.open(spiffsPath, "r");
    if (!srcFile)
    {
        Serial.printf("Failed to open SPIFFS file: %s\n", filename);
        return false;
    }

    size_t fileSize = srcFile.size();

    // Check PSRAM space
    size_t freeSpace = PSRamFS.totalBytes() - PSRamFS.usedBytes();
    if (fileSize > freeSpace)
    {
        Serial.printf("Not enough PSRAM space for %s (need %d, have %d)\n",
                      filename, fileSize, freeSpace);
        srcFile.close();
        return false;
    }

    // Remove existing file in PSRAM
    if (PSRamFS.exists(psramPath))
    {
        PSRamFS.remove(psramPath);
    }

    // Create destination file in PSRAM
    File dstFile = PSRamFS.open(psramPath, "w");
    if (!dstFile)
    {
        Serial.printf("Failed to create PSRAM file: %s\n", filename);
        srcFile.close();
        return false;
    }

    // Copy data in chunks
    uint8_t buffer[COPY_BUFFER_SIZE];
    size_t totalCopied = 0;

    while (srcFile.available())
    {
        size_t bytesRead = srcFile.read(buffer, COPY_BUFFER_SIZE);
        size_t bytesWritten = dstFile.write(buffer, bytesRead);
        
        if (bytesWritten != bytesRead)
        {
            Serial.printf("Write error copying %s\n", filename);
            srcFile.close();
            dstFile.close();
            PSRamFS.remove(psramPath);
            return false;
        }
        
        totalCopied += bytesWritten;
        yield(); // Prevent watchdog timeout
    }

    srcFile.close();
    dstFile.close();

    Serial.printf("Loaded to PSRAM: %s (%d bytes)\n", filename, totalCopied);
    return true;
}

// Internal version - SPIFFS must already be initialized
static int loadFilesToPsramInternal()
{
    int filesLoaded = 0;
    int filesFailed = 0;

    File root = SPIFFS.open("/");
    if (!root || !root.isDirectory())
    {
        Serial.println("Failed to open SPIFFS root");
        return 0;
    }

    File file = root.openNextFile();
    while (file)
    {
        if (!file.isDirectory())
        {
            String filename = file.name();
            if (filename.startsWith("/"))
            {
                filename = filename.substring(1);
            }

            // Skip the server list cache file
            if (filename != ".server_list.json")
            {
                if (copyFileToPsram(filename.c_str()))
                {
                    filesLoaded++;
                }
                else
                {
                    filesFailed++;
                }
            }
        }
        file = root.openNextFile();
    }

    Serial.printf("Loaded %d files to PSRAM (%d failed)\n", filesLoaded, filesFailed);
    return filesLoaded;
}

int loadFilesToPsram()
{
    Serial.println("=== Loading files from SPIFFS to PSRAM ===");
    
    // Initialize SPIFFS
    if (!initSpiffs())
    {
        Serial.println("ERROR: Failed to initialize SPIFFS!");
        return 0;
    }

    int filesLoaded = loadFilesToPsramInternal();

    // End SPIFFS
    endSpiffs();

    Serial.printf("=== Loaded %d files to PSRAM ===\n", filesLoaded);
    return filesLoaded;
}

//=============================================================================
// Server Communication
//=============================================================================

String getServerFileList(const char *serverAddress)
{
    HTTPClient http;
    http.begin(String(serverAddress) + "/list");
    http.setTimeout(10000);

    int httpResponseCode = http.GET();

    if (httpResponseCode == 200)
    {
        String payload = http.getString();
        http.end();

        Serial.println("=== Server file list ===");

        JsonDocument serverDoc;
        DeserializationError error = deserializeJson(serverDoc, payload);

        if (!error)
        {
            JsonArray serverFiles = serverDoc["files"];
            for (JsonObject file : serverFiles)
            {
                String filename = file["name"].as<String>();
                uint32_t fileSize = file["size"].as<uint32_t>();
                Serial.printf("  %s (%d bytes)\n", filename.c_str(), fileSize);
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

//=============================================================================
// Download File to SPIFFS
//=============================================================================

static bool downloadFileToSpiffs(const char *serverAddress, const char *filename, 
                                  SyncProgress &syncProgress, const size_t bufferSize, uint8_t *buffer)
{
    HTTPClient http;
    http.begin(String(serverAddress) + "/download?file=" + String(filename));
    http.setTimeout(30000);
    http.setConnectTimeout(10000);

    int httpResponseCode = http.GET();

    if (httpResponseCode != 200)
    {
        Serial.printf("Download error for file: %s, code: %d\n", filename, httpResponseCode);
        http.end();
        return false;
    }

    int contentLength = http.getSize();
    Serial.printf("Downloading: %s (%d bytes)\n", filename, contentLength);

    // Check SPIFFS space
    size_t freeSpace = SPIFFS.totalBytes() - SPIFFS.usedBytes();
    if (contentLength > 0 && (size_t)contentLength > freeSpace)
    {
        Serial.printf("Not enough SPIFFS space. Need: %d, Available: %d\n",
                      contentLength, freeSpace);
        http.end();
        return false;
    }

    // Prepare SPIFFS path
    String spiffsPath = "/";
    spiffsPath += filename;

    // Remove existing file
    if (SPIFFS.exists(spiffsPath))
    {
        SPIFFS.remove(spiffsPath);
    }

    // Create file in SPIFFS
    File file = SPIFFS.open(spiffsPath, "w");
    if (!file)
    {
        Serial.printf("Error creating SPIFFS file: %s\n", spiffsPath.c_str());
        http.end();
        return false;
    }

    WiFiClient *stream = http.getStreamPtr();
    int totalDownloaded = 0;
    bool shouldContinue = true;
    unsigned long lastProgressTime = millis();
    unsigned long downloadStartTime = millis();

    // Download loop
    while (shouldContinue && (contentLength < 0 || totalDownloaded < contentLength))
    {
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
                if (bytesWritten != (size_t)bytesRead)
                {
                    Serial.printf("Write error: expected %d, written %d\n", bytesRead, bytesWritten);
                    shouldContinue = false;
                    break;
                }

                totalDownloaded += bytesRead;

                // Progress update every second
                unsigned long currentTime = millis();
                if (currentTime - lastProgressTime >= 1000)
                {
                    Serial.printf("  Downloaded: %d/%d bytes (%.1f%%)\n",
                                  totalDownloaded,
                                  contentLength > 0 ? contentLength : totalDownloaded,
                                  contentLength > 0 ? (totalDownloaded * 100.0 / contentLength) : 0.0);
                    lastProgressTime = currentTime;
                }

                shouldContinue = updateProgress(syncProgress, bytesRead, false);
                yield();
            }
        }
        else
        {
            if (contentLength > 0 && totalDownloaded >= contentLength)
            {
                break;
            }
            delay(50);

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

    if (!shouldContinue)
    {
        SPIFFS.remove(spiffsPath);
        Serial.printf("Download cancelled or failed for: %s\n", filename);
        return false;
    }

    // Verify file
    if (SPIFFS.exists(spiffsPath))
    {
        File verifyFile = SPIFFS.open(spiffsPath, "r");
        uint32_t savedSize = verifyFile.size();
        verifyFile.close();

        if (contentLength > 0 && savedSize != (uint32_t)contentLength)
        {
            Serial.printf("Size mismatch! Expected: %d, Saved: %d\n", contentLength, savedSize);
            SPIFFS.remove(spiffsPath);
            return false;
        }

        Serial.printf("Downloaded to SPIFFS: %s (%d bytes, %lu ms)\n", 
                      filename, savedSize, downloadTime);
        return true;
    }
    else
    {
        Serial.printf("ERROR: File was not saved: %s\n", filename);
        return false;
    }
}

//=============================================================================
// Sync Size Calculation
//=============================================================================

static uint32_t calculateSyncSize(const std::map<String, JsonObject> &serverMap,
                                   const std::map<String, JsonObject> &localMap)
{
    uint32_t totalSize = 0;

    for (const auto &pair : serverMap)
    {
        const String &filename = pair.first;
        JsonObject serverFile = pair.second;

        auto localIt = localMap.find(filename);
        if (localIt == localMap.end())
        {
            // File not on SPIFFS - need to download
            totalSize += serverFile["size"].as<uint32_t>();
        }
        else
        {
            // File exists - check if size differs (simple sync check)
            uint32_t serverSize = serverFile["size"].as<uint32_t>();
            uint32_t localSize = localIt->second["size"].as<uint32_t>();
            
            if (serverSize != localSize)
            {
                totalSize += serverSize;
            }
        }
    }

    return totalSize;
}

static uint32_t countSyncFiles(const std::map<String, JsonObject> &serverMap,
                                const std::map<String, JsonObject> &localMap)
{
    uint32_t totalFiles = 0;

    for (const auto &pair : serverMap)
    {
        const String &filename = pair.first;
        JsonObject serverFile = pair.second;

        auto localIt = localMap.find(filename);
        if (localIt == localMap.end())
        {
            totalFiles++;
        }
        else
        {
            uint32_t serverSize = serverFile["size"].as<uint32_t>();
            uint32_t localSize = localIt->second["size"].as<uint32_t>();
            
            if (serverSize != localSize)
            {
                totalFiles++;
            }
        }
    }

    return totalFiles;
}

//=============================================================================
// Main Sync Function
//=============================================================================

bool syncFiles(const char *serverAddress, ProgressCallback callback)
{
    Serial.println("=== Starting File Sync ===");
    Serial.printf("Server: %s\n", serverAddress);

    // Initialize SPIFFS for sync operation
    if (!initSpiffs())
    {
        Serial.println("ERROR: Failed to initialize SPIFFS!");
        return false;
    }

    setProgressCallback(callback);

    SyncProgress syncProgress = {0, 0, 0, 0, 0, 0, millis()};

    // Get file list from server
    String serverListStr = getServerFileList(serverAddress);
    if (serverListStr.isEmpty())
    {
        Serial.println("Failed to get file list from server");
        endSpiffs();
        return false;
    }

    // Check if server list has changed (compares full JSON including hashes)
    bool serverListChanged = isServerListChanged(serverListStr);
    
    if (!serverListChanged)
    {
        Serial.println("Files are up to date - no sync needed");
        
        // Still load files to PSRAM
        Serial.println("Loading files to PSRAM...");
        loadFilesToPsramInternal();
        
        endSpiffs();
        return true;
    }

    // Server list changed - need to re-download ALL files from server
    // (because we can't compute local hashes, we must trust server hashes)
    Serial.println("Server list changed - re-downloading all files");

    // Parse server JSON
    JsonDocument serverDoc;
    if (deserializeJson(serverDoc, serverListStr))
    {
        Serial.println("Error parsing server JSON");
        endSpiffs();
        return false;
    }

    JsonArray serverFiles = serverDoc["files"];

    // Calculate total size for progress
    syncProgress.totalBytes = 0;
    syncProgress.totalFiles = 0;
    for (JsonObject file : serverFiles)
    {
        syncProgress.totalBytes += file["size"].as<uint32_t>();
        syncProgress.totalFiles++;
    }

    Serial.printf("Sync plan: %d files, %d bytes to download\n",
                  syncProgress.totalFiles, syncProgress.totalBytes);

    bool shouldContinue = true;
    int filesDownloaded = 0;

    // Download ALL files from server
    for (JsonObject serverFile : serverFiles)
    {
        if (!shouldContinue)
            break;

        const char* filename = serverFile["name"].as<const char*>();

        size_t bufferSize = min((size_t)10000, (size_t)ESP.getMaxAllocHeap());
        uint8_t *buffer = new uint8_t[bufferSize];
        
        if (buffer)
        {
            shouldContinue = downloadFileToSpiffs(serverAddress, filename, 
                                                   syncProgress, bufferSize, buffer);
            delete[] buffer;
            
            if (shouldContinue)
            {
                filesDownloaded++;
                syncProgress.processedFiles++;
            }
        }
        else
        {
            Serial.println("Failed to allocate download buffer");
            shouldContinue = false;
        }
    }

    // Remove local files not on server (if enabled)
    if (REMOVE_LOCAL_FILES_NOT_ON_SERVER && shouldContinue)
    {
        // Get local file list
        String localListStr = getLocalFileList();
        JsonDocument localDoc;
        if (!deserializeJson(localDoc, localListStr))
        {
            JsonArray localFiles = localDoc["files"];
            
            // Create server filename set
            std::map<String, bool> serverFileNames;
            for (JsonObject file : serverFiles)
            {
                serverFileNames[file["name"].as<String>()] = true;
            }
            
            // Remove files not on server
            for (JsonObject localFile : localFiles)
            {
                String filename = localFile["name"].as<String>();
                if (serverFileNames.find(filename) == serverFileNames.end() && 
                    filename != ".server_list.json")
                {
                    Serial.printf("Removing: %s\n", filename.c_str());
                    deleteFileFromSpiffs(filename.c_str());
                }
            }
        }
    }

    // Save server list cache after successful sync
    if (shouldContinue)
    {
        saveServerListCache(serverListStr);
    }

    // Load files to PSRAM
    if (shouldContinue)
    {
        Serial.println("Loading files to PSRAM...");
        loadFilesToPsramInternal();
    }

    // End SPIFFS after sync
    endSpiffs();

    // Final progress update
    if (progressCallback)
    {
        uint32_t totalTransferred = syncProgress.downloadedBytes + syncProgress.uploadedBytes;
        progressCallback(totalTransferred, syncProgress.totalBytes, 100);
    }

    if (shouldContinue)
    {
        Serial.printf("=== Sync completed: %d files downloaded ===\n", filesDownloaded);
        return true;
    }
    else
    {
        Serial.println("=== Sync cancelled ===");
        return false;
    }
}

//=============================================================================
// Debug Utilities
//=============================================================================

void printSpiffsFileSystem()
{
    Serial.println("\n=== SPIFFS Contents ===");
    
    if (!initSpiffs())
    {
        Serial.println("Failed to initialize SPIFFS");
        return;
    }

    File root = SPIFFS.open("/");
    File file = root.openNextFile();

    size_t totalUsed = 0;
    int fileCount = 0;

    while (file)
    {
        if (!file.isDirectory())
        {
            Serial.printf("  %s (%d bytes)\n", file.name(), file.size());
            totalUsed += file.size();
            fileCount++;
        }
        file = root.openNextFile();
    }

    Serial.println("------------------------");
    Serial.printf("Files: %d\n", fileCount);
    Serial.printf("Total: %d bytes\n", SPIFFS.totalBytes());
    Serial.printf("Used:  %d bytes\n", SPIFFS.usedBytes());
    Serial.printf("Free:  %d bytes\n", SPIFFS.totalBytes() - SPIFFS.usedBytes());
    Serial.println("========================\n");

    endSpiffs();
}

void printPsramFileSystem()
{
    Serial.println("\n=== PSRamFS Contents ===");
    
    File root = PSRamFS.open("/");
    File file = root.openNextFile();

    int fileCount = 0;

    while (file)
    {
        if (!file.isDirectory())
        {
            Serial.printf("  %s (%d bytes)\n", file.name(), file.size());
            fileCount++;
        }
        file = root.openNextFile();
    }

    Serial.println("------------------------");
    Serial.printf("Files: %d\n", fileCount);
    Serial.printf("Total: %d bytes\n", PSRamFS.totalBytes());
    Serial.printf("Used:  %d bytes\n", PSRamFS.usedBytes());
    Serial.printf("Free:  %d bytes\n", PSRamFS.totalBytes() - PSRamFS.usedBytes());
    Serial.println("========================\n");
}

void printBothFileSystems()
{
    printSpiffsFileSystem();
    printPsramFileSystem();
}

// /**
//  * @file syncFiles.cpp
//  * @brief ESP32 File Synchronization Library with SPIFFS persistence and PSRAM caching
//  * 
//  * This library synchronizes files from a server to the ESP32:
//  * 1. Files are downloaded and stored permanently in SPIFFS
//  * 2. After sync, files are copied to PSRAM for fast runtime access
//  * 3. On boot, files can be loaded from SPIFFS to PSRAM (no network needed)
//  * 
//  * SPIFFS provides persistence across reboots
//  * PSRAM provides fast file access during runtime
//  */

// #include <Arduino.h>
// #include <HTTPClient.h>
// #include <ArduinoJson.h>
// #include <SPIFFS.h>
// #include "PSRamFS.h"
// #include <map>
// #include "serverSync.h"

// // Configuration
// static const bool REMOVE_LOCAL_FILES_NOT_ON_SERVER = false;
// static ProgressCallback progressCallback = nullptr;

// // Buffer size for file operations
// static const size_t COPY_BUFFER_SIZE = 4096;

// // Cached server file list filename
// static const char* SERVER_LIST_CACHE_FILE = "/.server_list.json";

// //=============================================================================
// // SPIFFS Initialization (internal use)
// //=============================================================================

// static bool initSpiffs()
// {
//     if (!SPIFFS.begin(true)) // true = format if mount fails
//     {
//         Serial.println("ERROR: SPIFFS initialization failed!");
//         return false;
//     }
    
//     Serial.printf("SPIFFS initialized: Total=%d, Used=%d, Free=%d bytes\n",
//                   SPIFFS.totalBytes(), SPIFFS.usedBytes(), 
//                   SPIFFS.totalBytes() - SPIFFS.usedBytes());
//     return true;
// }

// static void endSpiffs()
// {
//     SPIFFS.end();
//     Serial.println("SPIFFS unmounted");
// }

// //=============================================================================
// // Server List Cache (for hash comparison)
// //=============================================================================

// static bool saveServerListCache(const String &serverListStr)
// {
//     File file = SPIFFS.open(SERVER_LIST_CACHE_FILE, "w");
//     if (!file)
//     {
//         Serial.println("ERROR: Failed to create server list cache file");
//         return false;
//     }
    
//     size_t written = file.print(serverListStr);
//     file.close();
    
//     if (written == serverListStr.length())
//     {
//         Serial.printf("Server list cached (%d bytes)\n", written);
//         return true;
//     }
//     else
//     {
//         Serial.println("ERROR: Failed to write server list cache");
//         return false;
//     }
// }

// static String loadServerListCache()
// {
//     if (!SPIFFS.exists(SERVER_LIST_CACHE_FILE))
//     {
//         Serial.println("No cached server list found");
//         return "";
//     }
    
//     File file = SPIFFS.open(SERVER_LIST_CACHE_FILE, "r");
//     if (!file)
//     {
//         Serial.println("ERROR: Failed to open server list cache");
//         return "";
//     }
    
//     String content = file.readString();
//     file.close();
    
//     Serial.printf("Loaded cached server list (%d bytes)\n", content.length());
//     return content;
// }

// static bool isServerListChanged(const String &newServerList)
// {
//     String cachedList = loadServerListCache();
    
//     if (cachedList.isEmpty())
//     {
//         Serial.println("No cache - sync required");
//         return true;
//     }
    
//     if (cachedList == newServerList)
//     {
//         Serial.println("Server list unchanged (hash match)");
//         return false;
//     }
//     else
//     {
//         Serial.println("Server list changed - sync required");
//         return true;
//     }
// }

// //=============================================================================
// // Progress Tracking
// //=============================================================================

// static bool updateProgress(SyncProgress &syncProgress, uint32_t bytesTransferred, bool isUpload = false)
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

// void setProgressCallback(ProgressCallback callback)
// {
//     progressCallback = callback;
// }

// bool defaultProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage)
// {
//     Serial.printf("Progress: %d/%d bytes (%d%%)\n", downloaded, total, percentage);
//     return true;
// }

// //=============================================================================
// // SPIFFS File Operations (Persistent Storage)
// //=============================================================================

// String getLocalFileList()
// {
//     JsonDocument doc;
//     JsonArray files = doc["files"].to<JsonArray>();

//     Serial.println("=== Local SPIFFS file list ===");

//     File root = SPIFFS.open("/");
//     if (!root || !root.isDirectory())
//     {
//         Serial.println("Failed to open SPIFFS root");
//         String result;
//         serializeJson(doc, result);
//         return result;
//     }

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

//             Serial.printf("  %s (%d bytes)\n", filename.c_str(), fileSize);

//             JsonObject fileObj = files.add<JsonObject>();
//             fileObj["name"] = filename;
//             fileObj["size"] = fileSize;
//         }
//         file = root.openNextFile();
//     }

//     Serial.println("=== End local file list ===");

//     String result;
//     serializeJson(doc, result);
//     return result;
// }

// bool deleteFileFromSpiffs(const char *filename)
// {
//     String spiffsPath = "/";
//     spiffsPath += filename;

//     if (SPIFFS.remove(spiffsPath))
//     {
//         Serial.printf("Deleted from SPIFFS: %s\n", filename);
//         return true;
//     }
//     else
//     {
//         Serial.printf("Error deleting from SPIFFS: %s\n", filename);
//         return false;
//     }
// }

// bool fileExistsOnSpiffs(const char *filename)
// {
//     String spiffsPath = "/";
//     spiffsPath += filename;
//     return SPIFFS.exists(spiffsPath);
// }

// size_t getSpiffsFreeSpace()
// {
//     return SPIFFS.totalBytes() - SPIFFS.usedBytes();
// }

// //=============================================================================
// // PSRAM File Operations (Fast Runtime Cache)
// //=============================================================================

// bool fileExistsOnPsram(const char *filename)
// {
//     String psramPath = "/";
//     psramPath += filename;
//     return PSRamFS.exists(psramPath);
// }

// size_t getPsramFreeSpace()
// {
//     return PSRamFS.totalBytes() - PSRamFS.usedBytes();
// }

// //=============================================================================
// // Copy Files from SPIFFS to PSRAM
// //=============================================================================

// static bool copyFileToPsram(const char *filename)
// {
//     String spiffsPath = "/";
//     spiffsPath += filename;
    
//     String psramPath = "/";
//     psramPath += filename;

//     // Open source file from SPIFFS
//     File srcFile = SPIFFS.open(spiffsPath, "r");
//     if (!srcFile)
//     {
//         Serial.printf("Failed to open SPIFFS file: %s\n", filename);
//         return false;
//     }

//     size_t fileSize = srcFile.size();

//     // Check PSRAM space
//     size_t freeSpace = PSRamFS.totalBytes() - PSRamFS.usedBytes();
//     if (fileSize > freeSpace)
//     {
//         Serial.printf("Not enough PSRAM space for %s (need %d, have %d)\n",
//                       filename, fileSize, freeSpace);
//         srcFile.close();
//         return false;
//     }

//     // Remove existing file in PSRAM
//     if (PSRamFS.exists(psramPath))
//     {
//         PSRamFS.remove(psramPath);
//     }

//     // Create destination file in PSRAM
//     File dstFile = PSRamFS.open(psramPath, "w");
//     if (!dstFile)
//     {
//         Serial.printf("Failed to create PSRAM file: %s\n", filename);
//         srcFile.close();
//         return false;
//     }

//     // Copy data in chunks
//     uint8_t buffer[COPY_BUFFER_SIZE];
//     size_t totalCopied = 0;

//     while (srcFile.available())
//     {
//         size_t bytesRead = srcFile.read(buffer, COPY_BUFFER_SIZE);
//         size_t bytesWritten = dstFile.write(buffer, bytesRead);
        
//         if (bytesWritten != bytesRead)
//         {
//             Serial.printf("Write error copying %s\n", filename);
//             srcFile.close();
//             dstFile.close();
//             PSRamFS.remove(psramPath);
//             return false;
//         }
        
//         totalCopied += bytesWritten;
//         yield(); // Prevent watchdog timeout
//     }

//     srcFile.close();
//     dstFile.close();

//     Serial.printf("Loaded to PSRAM: %s (%d bytes)\n", filename, totalCopied);
//     return true;
// }

// // Internal version - SPIFFS must already be initialized
// static int loadFilesToPsramInternal()
// {
//     int filesLoaded = 0;
//     int filesFailed = 0;

//     File root = SPIFFS.open("/");
//     if (!root || !root.isDirectory())
//     {
//         Serial.println("Failed to open SPIFFS root");
//         return 0;
//     }

//     File file = root.openNextFile();
//     while (file)
//     {
//         if (!file.isDirectory())
//         {
//             String filename = file.name();
//             if (filename.startsWith("/"))
//             {
//                 filename = filename.substring(1);
//             }

//             // Skip the server list cache file
//             if (filename != ".server_list.json")
//             {
//                 if (copyFileToPsram(filename.c_str()))
//                 {
//                     filesLoaded++;
//                 }
//                 else
//                 {
//                     filesFailed++;
//                 }
//             }
//         }
//         file = root.openNextFile();
//     }

//     Serial.printf("Loaded %d files to PSRAM (%d failed)\n", filesLoaded, filesFailed);
//     return filesLoaded;
// }

// int loadFilesToPsram()
// {
//     Serial.println("=== Loading files from SPIFFS to PSRAM ===");
    
//     // Initialize SPIFFS
//     if (!initSpiffs())
//     {
//         Serial.println("ERROR: Failed to initialize SPIFFS!");
//         return 0;
//     }

//     int filesLoaded = loadFilesToPsramInternal();

//     // End SPIFFS
//     endSpiffs();

//     Serial.printf("=== Loaded %d files to PSRAM ===\n", filesLoaded);
//     return filesLoaded;
// }

// //=============================================================================
// // Server Communication
// //=============================================================================

// String getServerFileList(const char *serverAddress)
// {
//     HTTPClient http;
//     http.begin(String(serverAddress) + "/list");
//     http.setTimeout(10000);

//     int httpResponseCode = http.GET();

//     if (httpResponseCode == 200)
//     {
//         String payload = http.getString();
//         http.end();

//         Serial.println("=== Server file list ===");

//         JsonDocument serverDoc;
//         DeserializationError error = deserializeJson(serverDoc, payload);

//         if (!error)
//         {
//             JsonArray serverFiles = serverDoc["files"];
//             for (JsonObject file : serverFiles)
//             {
//                 String filename = file["name"].as<String>();
//                 uint32_t fileSize = file["size"].as<uint32_t>();
//                 Serial.printf("  %s (%d bytes)\n", filename.c_str(), fileSize);
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

// //=============================================================================
// // Download File to SPIFFS
// //=============================================================================

// static bool downloadFileToSpiffs(const char *serverAddress, const char *filename, 
//                                   SyncProgress &syncProgress, const size_t bufferSize, uint8_t *buffer)
// {
//     HTTPClient http;
//     http.begin(String(serverAddress) + "/download?file=" + String(filename));
//     http.setTimeout(30000);
//     http.setConnectTimeout(10000);

//     int httpResponseCode = http.GET();

//     if (httpResponseCode != 200)
//     {
//         Serial.printf("Download error for file: %s, code: %d\n", filename, httpResponseCode);
//         http.end();
//         return false;
//     }

//     int contentLength = http.getSize();
//     Serial.printf("Downloading: %s (%d bytes)\n", filename, contentLength);

//     // Check SPIFFS space
//     size_t freeSpace = SPIFFS.totalBytes() - SPIFFS.usedBytes();
//     if (contentLength > 0 && (size_t)contentLength > freeSpace)
//     {
//         Serial.printf("Not enough SPIFFS space. Need: %d, Available: %d\n",
//                       contentLength, freeSpace);
//         http.end();
//         return false;
//     }

//     // Prepare SPIFFS path
//     String spiffsPath = "/";
//     spiffsPath += filename;

//     // Remove existing file
//     if (SPIFFS.exists(spiffsPath))
//     {
//         SPIFFS.remove(spiffsPath);
//     }

//     // Create file in SPIFFS
//     File file = SPIFFS.open(spiffsPath, "w");
//     if (!file)
//     {
//         Serial.printf("Error creating SPIFFS file: %s\n", spiffsPath.c_str());
//         http.end();
//         return false;
//     }

//     WiFiClient *stream = http.getStreamPtr();
//     int totalDownloaded = 0;
//     bool shouldContinue = true;
//     unsigned long lastProgressTime = millis();
//     unsigned long downloadStartTime = millis();

//     // Download loop
//     while (shouldContinue && (contentLength < 0 || totalDownloaded < contentLength))
//     {
//         if (!http.connected())
//         {
//             Serial.println("HTTP connection lost during download");
//             break;
//         }

//         size_t availableBytes = stream->available();
//         if (availableBytes > 0)
//         {
//             size_t bytesToRead = min(availableBytes, bufferSize);
//             int bytesRead = stream->readBytes(buffer, bytesToRead);

//             if (bytesRead > 0)
//             {
//                 size_t bytesWritten = file.write(buffer, bytesRead);
//                 if (bytesWritten != (size_t)bytesRead)
//                 {
//                     Serial.printf("Write error: expected %d, written %d\n", bytesRead, bytesWritten);
//                     shouldContinue = false;
//                     break;
//                 }

//                 totalDownloaded += bytesRead;

//                 // Progress update every second
//                 unsigned long currentTime = millis();
//                 if (currentTime - lastProgressTime >= 1000)
//                 {
//                     Serial.printf("  Downloaded: %d/%d bytes (%.1f%%)\n",
//                                   totalDownloaded,
//                                   contentLength > 0 ? contentLength : totalDownloaded,
//                                   contentLength > 0 ? (totalDownloaded * 100.0 / contentLength) : 0.0);
//                     lastProgressTime = currentTime;
//                 }

//                 shouldContinue = updateProgress(syncProgress, bytesRead, false);
//                 yield();
//             }
//         }
//         else
//         {
//             if (contentLength > 0 && totalDownloaded >= contentLength)
//             {
//                 break;
//             }
//             delay(50);

//             // Timeout check (30 seconds without data)
//             if (millis() - lastProgressTime > 30000)
//             {
//                 Serial.println("Download timeout - no data received");
//                 shouldContinue = false;
//                 break;
//             }
//         }
//     }

//     file.close();
//     http.end();

//     unsigned long downloadTime = millis() - downloadStartTime;

//     if (!shouldContinue)
//     {
//         SPIFFS.remove(spiffsPath);
//         Serial.printf("Download cancelled or failed for: %s\n", filename);
//         return false;
//     }

//     // Verify file
//     if (SPIFFS.exists(spiffsPath))
//     {
//         File verifyFile = SPIFFS.open(spiffsPath, "r");
//         uint32_t savedSize = verifyFile.size();
//         verifyFile.close();

//         if (contentLength > 0 && savedSize != (uint32_t)contentLength)
//         {
//             Serial.printf("Size mismatch! Expected: %d, Saved: %d\n", contentLength, savedSize);
//             SPIFFS.remove(spiffsPath);
//             return false;
//         }

//         Serial.printf("Downloaded to SPIFFS: %s (%d bytes, %lu ms)\n", 
//                       filename, savedSize, downloadTime);
//         return true;
//     }
//     else
//     {
//         Serial.printf("ERROR: File was not saved: %s\n", filename);
//         return false;
//     }
// }

// //=============================================================================
// // Sync Size Calculation
// //=============================================================================

// static uint32_t calculateSyncSize(const std::map<String, JsonObject> &serverMap,
//                                    const std::map<String, JsonObject> &localMap)
// {
//     uint32_t totalSize = 0;

//     for (const auto &pair : serverMap)
//     {
//         const String &filename = pair.first;
//         JsonObject serverFile = pair.second;

//         auto localIt = localMap.find(filename);
//         if (localIt == localMap.end())
//         {
//             // File not on SPIFFS - need to download
//             totalSize += serverFile["size"].as<uint32_t>();
//         }
//         else
//         {
//             // File exists - check if size differs (simple sync check)
//             uint32_t serverSize = serverFile["size"].as<uint32_t>();
//             uint32_t localSize = localIt->second["size"].as<uint32_t>();
            
//             if (serverSize != localSize)
//             {
//                 totalSize += serverSize;
//             }
//         }
//     }

//     return totalSize;
// }

// static uint32_t countSyncFiles(const std::map<String, JsonObject> &serverMap,
//                                 const std::map<String, JsonObject> &localMap)
// {
//     uint32_t totalFiles = 0;

//     for (const auto &pair : serverMap)
//     {
//         const String &filename = pair.first;
//         JsonObject serverFile = pair.second;

//         auto localIt = localMap.find(filename);
//         if (localIt == localMap.end())
//         {
//             totalFiles++;
//         }
//         else
//         {
//             uint32_t serverSize = serverFile["size"].as<uint32_t>();
//             uint32_t localSize = localIt->second["size"].as<uint32_t>();
            
//             if (serverSize != localSize)
//             {
//                 totalFiles++;
//             }
//         }
//     }

//     return totalFiles;
// }

// //=============================================================================
// // Main Sync Function
// //=============================================================================

// bool syncFiles(const char *serverAddress, ProgressCallback callback)
// {
//     Serial.println("=== Starting File Sync ===");
//     Serial.printf("Server: %s\n", serverAddress);

//     // Initialize SPIFFS for sync operation
//     if (!initSpiffs())
//     {
//         Serial.println("ERROR: Failed to initialize SPIFFS!");
//         return false;
//     }

//     setProgressCallback(callback);

//     SyncProgress syncProgress = {0, 0, 0, 0, 0, 0, millis()};

//     // Get file list from server
//     String serverListStr = getServerFileList(serverAddress);
//     if (serverListStr.isEmpty())
//     {
//         Serial.println("Failed to get file list from server");
//         endSpiffs();
//         return false;
//     }

//     // Check if server list has changed (compares full JSON including hashes)
//     if (!isServerListChanged(serverListStr))
//     {
//         Serial.println("Files are up to date - no sync needed");
        
//         // Still load files to PSRAM
//         Serial.println("Loading files to PSRAM...");
//         loadFilesToPsramInternal();
        
//         endSpiffs();
//         return true;
//     }

//     // Parse server JSON
//     JsonDocument serverDoc;
//     if (deserializeJson(serverDoc, serverListStr))
//     {
//         Serial.println("Error parsing server JSON");
//         endSpiffs();
//         return false;
//     }

//     // Get local file list for size comparison
//     String localListStr = getLocalFileList();
//     JsonDocument localDoc;
//     if (deserializeJson(localDoc, localListStr))
//     {
//         Serial.println("Error parsing local JSON");
//         endSpiffs();
//         return false;
//     }

//     Serial.println("========================= LOCAL LIST ==========================");
//     Serial.println(localListStr);
//     Serial.println("======================== SERVER LIST ==========================");
//     Serial.println(serverListStr);
//     Serial.println("===============================================================");
//     delay(2000);

//     JsonArray serverFiles = serverDoc["files"];
//     JsonArray localFiles = localDoc["files"];

//     // Create lookup maps
//     std::map<String, JsonObject> serverMap;
//     std::map<String, JsonObject> localMap;

//     for (JsonObject file : serverFiles)
//     {
//         serverMap[file["name"].as<String>()] = file;
//     }

//     for (JsonObject file : localFiles)
//     {
//         localMap[file["name"].as<String>()] = file;
//     }

//     // Calculate sync requirements
//     syncProgress.totalBytes = calculateSyncSize(serverMap, localMap);
//     syncProgress.totalFiles = countSyncFiles(serverMap, localMap);

//     Serial.printf("Sync plan: %d files, %d bytes to download\n",
//                   syncProgress.totalFiles, syncProgress.totalBytes);

//     bool shouldContinue = true;
//     int filesDownloaded = 0;

//     // Download files to SPIFFS
//     for (const auto &pair : serverMap)
//     {
//         if (!shouldContinue)
//             break;

//         const String &filename = pair.first;
//         JsonObject serverFile = pair.second;
        
//         bool needsDownload = false;
        
//         auto localIt = localMap.find(filename);
//         if (localIt == localMap.end())
//         {
//             needsDownload = true;
//         }
//         else
//         {
//             uint32_t serverSize = serverFile["size"].as<uint32_t>();
//             uint32_t localSize = localIt->second["size"].as<uint32_t>();
//             needsDownload = (serverSize != localSize);
//         }

//         if (needsDownload)
//         {
//             size_t bufferSize = min((size_t)10000, (size_t)ESP.getMaxAllocHeap());
//             uint8_t *buffer = new uint8_t[bufferSize];
            
//             if (buffer)
//             {
//                 shouldContinue = downloadFileToSpiffs(serverAddress, filename.c_str(), 
//                                                        syncProgress, bufferSize, buffer);
//                 delete[] buffer;
                
//                 if (shouldContinue)
//                 {
//                     filesDownloaded++;
//                     syncProgress.processedFiles++;
//                 }
//             }
//             else
//             {
//                 Serial.println("Failed to allocate download buffer");
//                 shouldContinue = false;
//             }
//         }
//         else
//         {
//             Serial.printf("Up to date: %s\n", filename.c_str());
//         }
//     }

//     // Remove local files not on server (if enabled)
//     if (REMOVE_LOCAL_FILES_NOT_ON_SERVER && shouldContinue)
//     {
//         Serial.println("Checking for files to remove...");
//         for (const auto &pair : localMap)
//         {
//             if (serverMap.find(pair.first) == serverMap.end())
//             {
//                 Serial.printf("Removing: %s\n", pair.first.c_str());
//                 deleteFileFromSpiffs(pair.first.c_str());
//             }
//         }
//     }

//     // Save server list cache after successful sync
//     if (shouldContinue)
//     {
//         saveServerListCache(serverListStr);
//     }

//     // Load files to PSRAM
//     if (shouldContinue)
//     {
//         Serial.println("Loading files to PSRAM...");
//         loadFilesToPsramInternal();
//     }

//     // End SPIFFS after sync
//     endSpiffs();

//     // Final progress update
//     if (progressCallback)
//     {
//         uint32_t totalTransferred = syncProgress.downloadedBytes + syncProgress.uploadedBytes;
//         progressCallback(totalTransferred, syncProgress.totalBytes, 100);
//     }

//     if (shouldContinue)
//     {
//         Serial.printf("=== Sync completed: %d files downloaded ===\n", filesDownloaded);
//         return true;
//     }
//     else
//     {
//         Serial.println("=== Sync cancelled ===");
//         return false;
//     }
// }

// //=============================================================================
// // Debug Utilities
// //=============================================================================

// void printSpiffsFileSystem()
// {
//     Serial.println("\n=== SPIFFS Contents ===");
    
//     if (!initSpiffs())
//     {
//         Serial.println("Failed to initialize SPIFFS");
//         return;
//     }

//     File root = SPIFFS.open("/");
//     File file = root.openNextFile();

//     size_t totalUsed = 0;
//     int fileCount = 0;

//     while (file)
//     {
//         if (!file.isDirectory())
//         {
//             Serial.printf("  %s (%d bytes)\n", file.name(), file.size());
//             totalUsed += file.size();
//             fileCount++;
//         }
//         file = root.openNextFile();
//     }

//     Serial.println("------------------------");
//     Serial.printf("Files: %d\n", fileCount);
//     Serial.printf("Total: %d bytes\n", SPIFFS.totalBytes());
//     Serial.printf("Used:  %d bytes\n", SPIFFS.usedBytes());
//     Serial.printf("Free:  %d bytes\n", SPIFFS.totalBytes() - SPIFFS.usedBytes());
//     Serial.println("========================\n");

//     endSpiffs();
// }

// void printPsramFileSystem()
// {
//     Serial.println("\n=== PSRamFS Contents ===");
    
//     File root = PSRamFS.open("/");
//     File file = root.openNextFile();

//     int fileCount = 0;

//     while (file)
//     {
//         if (!file.isDirectory())
//         {
//             Serial.printf("  %s (%d bytes)\n", file.name(), file.size());
//             fileCount++;
//         }
//         file = root.openNextFile();
//     }

//     Serial.println("------------------------");
//     Serial.printf("Files: %d\n", fileCount);
//     Serial.printf("Total: %d bytes\n", PSRamFS.totalBytes());
//     Serial.printf("Used:  %d bytes\n", PSRamFS.usedBytes());
//     Serial.printf("Free:  %d bytes\n", PSRamFS.totalBytes() - PSRamFS.usedBytes());
//     Serial.println("========================\n");
// }

// void printBothFileSystems()
// {
//     printSpiffsFileSystem();
//     printPsramFileSystem();
// }

// // /**
// //  * @file syncFiles.cpp
// //  * @brief ESP32 File Synchronization Library with SPIFFS persistence and PSRAM caching
// //  * 
// //  * This library synchronizes files from a server to the ESP32:
// //  * 1. Files are downloaded and stored permanently in SPIFFS
// //  * 2. After sync, files are copied to PSRAM for fast runtime access
// //  * 3. On boot, files can be loaded from SPIFFS to PSRAM (no network needed)
// //  * 
// //  * SPIFFS provides persistence across reboots
// //  * PSRAM provides fast file access during runtime
// //  */

// // #include <Arduino.h>
// // #include <HTTPClient.h>
// // #include <ArduinoJson.h>
// // #include <SPIFFS.h>
// // #include "PSRamFS.h"
// // #include <map>
// // #include "serverSync.h"

// // // Configuration
// // static const bool REMOVE_LOCAL_FILES_NOT_ON_SERVER = false;
// // static ProgressCallback progressCallback = nullptr;

// // // Buffer size for file operations
// // static const size_t COPY_BUFFER_SIZE = 4096;

// // //=============================================================================
// // // SPIFFS Initialization (internal use)
// // //=============================================================================

// // static bool initSpiffs()
// // {
// //     if (!SPIFFS.begin(true)) // true = format if mount fails
// //     {
// //         Serial.println("ERROR: SPIFFS initialization failed!");
// //         return false;
// //     }
    
// //     Serial.printf("SPIFFS initialized: Total=%d, Used=%d, Free=%d bytes\n",
// //                   SPIFFS.totalBytes(), SPIFFS.usedBytes(), 
// //                   SPIFFS.totalBytes() - SPIFFS.usedBytes());
// //     return true;
// // }

// // static void endSpiffs()
// // {
// //     SPIFFS.end();
// //     Serial.println("SPIFFS unmounted");
// // }

// // //=============================================================================
// // // Progress Tracking
// // //=============================================================================

// // static bool updateProgress(SyncProgress &syncProgress, uint32_t bytesTransferred, bool isUpload = false)
// // {
// //     if (isUpload)
// //     {
// //         syncProgress.uploadedBytes += bytesTransferred;
// //     }
// //     else
// //     {
// //         syncProgress.downloadedBytes += bytesTransferred;
// //     }

// //     uint32_t totalTransferred = syncProgress.downloadedBytes + syncProgress.uploadedBytes;

// //     if (syncProgress.totalBytes > 0)
// //     {
// //         syncProgress.percentage = (totalTransferred * 100) / syncProgress.totalBytes;
// //     }

// //     // Call progress callback every second
// //     unsigned long currentTime = millis();
// //     if (currentTime - syncProgress.lastUpdateTime >= 1000)
// //     {
// //         syncProgress.lastUpdateTime = currentTime;

// //         if (progressCallback)
// //         {
// //             return progressCallback(totalTransferred, syncProgress.totalBytes, syncProgress.percentage);
// //         }
// //     }

// //     return true;
// // }

// // void setProgressCallback(ProgressCallback callback)
// // {
// //     progressCallback = callback;
// // }

// // bool defaultProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage)
// // {
// //     Serial.printf("Progress: %d/%d bytes (%d%%)\n", downloaded, total, percentage);
// //     return true;
// // }

// // //=============================================================================
// // // SPIFFS File Operations (Persistent Storage)
// // //=============================================================================

// // String getLocalFileList()
// // {
// //     JsonDocument doc;
// //     JsonArray files = doc["files"].to<JsonArray>();

// //     Serial.println("=== Local SPIFFS file list ===");

// //     File root = SPIFFS.open("/");
// //     if (!root || !root.isDirectory())
// //     {
// //         Serial.println("Failed to open SPIFFS root");
// //         String result;
// //         serializeJson(doc, result);
// //         return result;
// //     }

// //     File file = root.openNextFile();
// //     while (file)
// //     {
// //         if (!file.isDirectory())
// //         {
// //             String fullPath = file.name();
// //             String filename = fullPath;

// //             // Remove leading "/" for compatibility with server
// //             if (filename.startsWith("/"))
// //             {
// //                 filename = filename.substring(1);
// //             }

// //             uint32_t fileSize = file.size();

// //             Serial.printf("  %s (%d bytes)\n", filename.c_str(), fileSize);

// //             JsonObject fileObj = files.add<JsonObject>();
// //             fileObj["name"] = filename;
// //             fileObj["size"] = fileSize;
// //         }
// //         file = root.openNextFile();
// //     }

// //     Serial.println("=== End local file list ===");

// //     String result;
// //     serializeJson(doc, result);
// //     return result;
// // }

// // bool deleteFileFromSpiffs(const char *filename)
// // {
// //     String spiffsPath = "/";
// //     spiffsPath += filename;

// //     if (SPIFFS.remove(spiffsPath))
// //     {
// //         Serial.printf("Deleted from SPIFFS: %s\n", filename);
// //         return true;
// //     }
// //     else
// //     {
// //         Serial.printf("Error deleting from SPIFFS: %s\n", filename);
// //         return false;
// //     }
// // }

// // bool fileExistsOnSpiffs(const char *filename)
// // {
// //     String spiffsPath = "/";
// //     spiffsPath += filename;
// //     return SPIFFS.exists(spiffsPath);
// // }

// // size_t getSpiffsFreeSpace()
// // {
// //     return SPIFFS.totalBytes() - SPIFFS.usedBytes();
// // }

// // //=============================================================================
// // // PSRAM File Operations (Fast Runtime Cache)
// // //=============================================================================

// // bool fileExistsOnPsram(const char *filename)
// // {
// //     String psramPath = "/";
// //     psramPath += filename;
// //     return PSRamFS.exists(psramPath);
// // }

// // size_t getPsramFreeSpace()
// // {
// //     return PSRamFS.totalBytes() - PSRamFS.usedBytes();
// // }

// // //=============================================================================
// // // Copy Files from SPIFFS to PSRAM
// // //=============================================================================

// // static bool copyFileToPsram(const char *filename)
// // {
// //     String spiffsPath = "/";
// //     spiffsPath += filename;
    
// //     String psramPath = "/";
// //     psramPath += filename;

// //     // Open source file from SPIFFS
// //     File srcFile = SPIFFS.open(spiffsPath, "r");
// //     if (!srcFile)
// //     {
// //         Serial.printf("Failed to open SPIFFS file: %s\n", filename);
// //         return false;
// //     }

// //     size_t fileSize = srcFile.size();

// //     // Check PSRAM space
// //     size_t freeSpace = PSRamFS.totalBytes() - PSRamFS.usedBytes();
// //     if (fileSize > freeSpace)
// //     {
// //         Serial.printf("Not enough PSRAM space for %s (need %d, have %d)\n",
// //                       filename, fileSize, freeSpace);
// //         srcFile.close();
// //         return false;
// //     }

// //     // Remove existing file in PSRAM
// //     if (PSRamFS.exists(psramPath))
// //     {
// //         PSRamFS.remove(psramPath);
// //     }

// //     // Create destination file in PSRAM
// //     File dstFile = PSRamFS.open(psramPath, "w");
// //     if (!dstFile)
// //     {
// //         Serial.printf("Failed to create PSRAM file: %s\n", filename);
// //         srcFile.close();
// //         return false;
// //     }

// //     // Copy data in chunks
// //     uint8_t buffer[COPY_BUFFER_SIZE];
// //     size_t totalCopied = 0;

// //     while (srcFile.available())
// //     {
// //         size_t bytesRead = srcFile.read(buffer, COPY_BUFFER_SIZE);
// //         size_t bytesWritten = dstFile.write(buffer, bytesRead);
        
// //         if (bytesWritten != bytesRead)
// //         {
// //             Serial.printf("Write error copying %s\n", filename);
// //             srcFile.close();
// //             dstFile.close();
// //             PSRamFS.remove(psramPath);
// //             return false;
// //         }
        
// //         totalCopied += bytesWritten;
// //         yield(); // Prevent watchdog timeout
// //     }

// //     srcFile.close();
// //     dstFile.close();

// //     Serial.printf("Loaded to PSRAM: %s (%d bytes)\n", filename, totalCopied);
// //     return true;
// // }

// // int loadFilesToPsram()
// // {
// //     Serial.println("=== Loading files from SPIFFS to PSRAM ===");
    
// //     // Initialize SPIFFS
// //     if (!initSpiffs())
// //     {
// //         Serial.println("ERROR: Failed to initialize SPIFFS!");
// //         return 0;
// //     }

// //     int filesLoaded = 0;
// //     int filesFailed = 0;

// //     File root = SPIFFS.open("/");
// //     if (!root || !root.isDirectory())
// //     {
// //         Serial.println("Failed to open SPIFFS root");
// //         endSpiffs();
// //         return 0;
// //     }

// //     File file = root.openNextFile();
// //     while (file)
// //     {
// //         if (!file.isDirectory())
// //         {
// //             String filename = file.name();
// //             if (filename.startsWith("/"))
// //             {
// //                 filename = filename.substring(1);
// //             }

// //             if (copyFileToPsram(filename.c_str()))
// //             {
// //                 filesLoaded++;
// //             }
// //             else
// //             {
// //                 filesFailed++;
// //             }
// //         }
// //         file = root.openNextFile();
// //     }

// //     // End SPIFFS
// //     endSpiffs();

// //     Serial.printf("=== Loaded %d files to PSRAM (%d failed) ===\n", filesLoaded, filesFailed);
// //     return filesLoaded;
// // }

// // //=============================================================================
// // // Server Communication
// // //=============================================================================

// // String getServerFileList(const char *serverAddress)
// // {
// //     HTTPClient http;
// //     http.begin(String(serverAddress) + "/list");
// //     http.setTimeout(10000);

// //     int httpResponseCode = http.GET();

// //     if (httpResponseCode == 200)
// //     {
// //         String payload = http.getString();
// //         http.end();

// //         Serial.println("=== Server file list ===");

// //         JsonDocument serverDoc;
// //         DeserializationError error = deserializeJson(serverDoc, payload);

// //         if (!error)
// //         {
// //             JsonArray serverFiles = serverDoc["files"];
// //             for (JsonObject file : serverFiles)
// //             {
// //                 String filename = file["name"].as<String>();
// //                 uint32_t fileSize = file["size"].as<uint32_t>();
// //                 Serial.printf("  %s (%d bytes)\n", filename.c_str(), fileSize);
// //             }
// //         }

// //         Serial.println("=== End server file list ===");
// //         return payload;
// //     }
// //     else
// //     {
// //         Serial.printf("Error getting file list from server, code: %d\n", httpResponseCode);
// //         http.end();
// //         return "";
// //     }
// // }

// // //=============================================================================
// // // Download File to SPIFFS
// // //=============================================================================

// // static bool downloadFileToSpiffs(const char *serverAddress, const char *filename, 
// //                                   SyncProgress &syncProgress, const size_t bufferSize, uint8_t *buffer)
// // {
// //     HTTPClient http;
// //     http.begin(String(serverAddress) + "/download?file=" + String(filename));
// //     http.setTimeout(30000);
// //     http.setConnectTimeout(10000);

// //     int httpResponseCode = http.GET();

// //     if (httpResponseCode != 200)
// //     {
// //         Serial.printf("Download error for file: %s, code: %d\n", filename, httpResponseCode);
// //         http.end();
// //         return false;
// //     }

// //     int contentLength = http.getSize();
// //     Serial.printf("Downloading: %s (%d bytes)\n", filename, contentLength);

// //     // Check SPIFFS space
// //     size_t freeSpace = SPIFFS.totalBytes() - SPIFFS.usedBytes();
// //     if (contentLength > 0 && (size_t)contentLength > freeSpace)
// //     {
// //         Serial.printf("Not enough SPIFFS space. Need: %d, Available: %d\n",
// //                       contentLength, freeSpace);
// //         http.end();
// //         return false;
// //     }

// //     // Prepare SPIFFS path
// //     String spiffsPath = "/";
// //     spiffsPath += filename;

// //     // Remove existing file
// //     if (SPIFFS.exists(spiffsPath))
// //     {
// //         SPIFFS.remove(spiffsPath);
// //     }

// //     // Create file in SPIFFS
// //     File file = SPIFFS.open(spiffsPath, "w");
// //     if (!file)
// //     {
// //         Serial.printf("Error creating SPIFFS file: %s\n", spiffsPath.c_str());
// //         http.end();
// //         return false;
// //     }

// //     WiFiClient *stream = http.getStreamPtr();
// //     int totalDownloaded = 0;
// //     bool shouldContinue = true;
// //     unsigned long lastProgressTime = millis();
// //     unsigned long downloadStartTime = millis();

// //     // Download loop
// //     while (shouldContinue && (contentLength < 0 || totalDownloaded < contentLength))
// //     {
// //         if (!http.connected())
// //         {
// //             Serial.println("HTTP connection lost during download");
// //             break;
// //         }

// //         size_t availableBytes = stream->available();
// //         if (availableBytes > 0)
// //         {
// //             size_t bytesToRead = min(availableBytes, bufferSize);
// //             int bytesRead = stream->readBytes(buffer, bytesToRead);

// //             if (bytesRead > 0)
// //             {
// //                 size_t bytesWritten = file.write(buffer, bytesRead);
// //                 if (bytesWritten != (size_t)bytesRead)
// //                 {
// //                     Serial.printf("Write error: expected %d, written %d\n", bytesRead, bytesWritten);
// //                     shouldContinue = false;
// //                     break;
// //                 }

// //                 totalDownloaded += bytesRead;

// //                 // Progress update every second
// //                 unsigned long currentTime = millis();
// //                 if (currentTime - lastProgressTime >= 1000)
// //                 {
// //                     Serial.printf("  Downloaded: %d/%d bytes (%.1f%%)\n",
// //                                   totalDownloaded,
// //                                   contentLength > 0 ? contentLength : totalDownloaded,
// //                                   contentLength > 0 ? (totalDownloaded * 100.0 / contentLength) : 0.0);
// //                     lastProgressTime = currentTime;
// //                 }

// //                 shouldContinue = updateProgress(syncProgress, bytesRead, false);
// //                 yield();
// //             }
// //         }
// //         else
// //         {
// //             if (contentLength > 0 && totalDownloaded >= contentLength)
// //             {
// //                 break;
// //             }
// //             delay(50);

// //             // Timeout check (30 seconds without data)
// //             if (millis() - lastProgressTime > 30000)
// //             {
// //                 Serial.println("Download timeout - no data received");
// //                 shouldContinue = false;
// //                 break;
// //             }
// //         }
// //     }

// //     file.close();
// //     http.end();

// //     unsigned long downloadTime = millis() - downloadStartTime;

// //     if (!shouldContinue)
// //     {
// //         SPIFFS.remove(spiffsPath);
// //         Serial.printf("Download cancelled or failed for: %s\n", filename);
// //         return false;
// //     }

// //     // Verify file
// //     if (SPIFFS.exists(spiffsPath))
// //     {
// //         File verifyFile = SPIFFS.open(spiffsPath, "r");
// //         uint32_t savedSize = verifyFile.size();
// //         verifyFile.close();

// //         if (contentLength > 0 && savedSize != (uint32_t)contentLength)
// //         {
// //             Serial.printf("Size mismatch! Expected: %d, Saved: %d\n", contentLength, savedSize);
// //             SPIFFS.remove(spiffsPath);
// //             return false;
// //         }

// //         Serial.printf("Downloaded to SPIFFS: %s (%d bytes, %lu ms)\n", 
// //                       filename, savedSize, downloadTime);
// //         return true;
// //     }
// //     else
// //     {
// //         Serial.printf("ERROR: File was not saved: %s\n", filename);
// //         return false;
// //     }
// // }

// // //=============================================================================
// // // Sync Size Calculation
// // //=============================================================================

// // static uint32_t calculateSyncSize(const std::map<String, JsonObject> &serverMap,
// //                                    const std::map<String, JsonObject> &localMap)
// // {
// //     uint32_t totalSize = 0;

// //     for (const auto &pair : serverMap)
// //     {
// //         const String &filename = pair.first;
// //         JsonObject serverFile = pair.second;

// //         auto localIt = localMap.find(filename);
// //         if (localIt == localMap.end())
// //         {
// //             // File not on SPIFFS - need to download
// //             totalSize += serverFile["size"].as<uint32_t>();
// //         }
// //         else
// //         {
// //             // File exists - check if size differs (simple sync check)
// //             uint32_t serverSize = serverFile["size"].as<uint32_t>();
// //             uint32_t localSize = localIt->second["size"].as<uint32_t>();
            
// //             if (serverSize != localSize)
// //             {
// //                 totalSize += serverSize;
// //             }
// //         }
// //     }

// //     return totalSize;
// // }

// // static uint32_t countSyncFiles(const std::map<String, JsonObject> &serverMap,
// //                                 const std::map<String, JsonObject> &localMap)
// // {
// //     uint32_t totalFiles = 0;

// //     for (const auto &pair : serverMap)
// //     {
// //         const String &filename = pair.first;
// //         JsonObject serverFile = pair.second;

// //         auto localIt = localMap.find(filename);
// //         if (localIt == localMap.end())
// //         {
// //             totalFiles++;
// //         }
// //         else
// //         {
// //             uint32_t serverSize = serverFile["size"].as<uint32_t>();
// //             uint32_t localSize = localIt->second["size"].as<uint32_t>();
            
// //             if (serverSize != localSize)
// //             {
// //                 totalFiles++;
// //             }
// //         }
// //     }

// //     return totalFiles;
// // }

// // //=============================================================================
// // // Main Sync Function
// // //=============================================================================

// // bool syncFiles(const char *serverAddress, ProgressCallback callback)
// // {
// //     Serial.println("=== Starting File Sync ===");
// //     Serial.printf("Server: %s\n", serverAddress);

// //     // Initialize SPIFFS for sync operation
// //     if (!initSpiffs())
// //     {
// //         Serial.println("ERROR: Failed to initialize SPIFFS!");
// //         return false;
// //     }

// //     setProgressCallback(callback);

// //     SyncProgress syncProgress = {0, 0, 0, 0, 0, 0, millis()};

// //     // Get file lists
// //     String serverListStr = getServerFileList(serverAddress);
// //     if (serverListStr.isEmpty())
// //     {
// //         Serial.println("Failed to get file list from server");
// //         endSpiffs();
// //         return false;
// //     }

// //     String localListStr = getLocalFileList();

// //     Serial.println("========================= LOCAL LIST ==========================");
// //     Serial.println(localListStr);
// //     Serial.println("======================== SERVER LIST ==========================");
// //     Serial.println(serverListStr);
// //     Serial.println("===============================================================");
// //     delay(2000);

// //     // Parse JSON
// //     JsonDocument serverDoc;
// //     JsonDocument localDoc;

// //     if (deserializeJson(serverDoc, serverListStr))
// //     {
// //         Serial.println("Error parsing server JSON");
// //         endSpiffs();
// //         return false;
// //     }

// //     if (deserializeJson(localDoc, localListStr))
// //     {
// //         Serial.println("Error parsing local JSON");
// //         endSpiffs();
// //         return false;
// //     }

// //     JsonArray serverFiles = serverDoc["files"];
// //     JsonArray localFiles = localDoc["files"];

// //     // Create lookup maps
// //     std::map<String, JsonObject> serverMap;
// //     std::map<String, JsonObject> localMap;

// //     for (JsonObject file : serverFiles)
// //     {
// //         serverMap[file["name"].as<String>()] = file;
// //     }

// //     for (JsonObject file : localFiles)
// //     {
// //         localMap[file["name"].as<String>()] = file;
// //     }

// //     // Calculate sync requirements
// //     syncProgress.totalBytes = calculateSyncSize(serverMap, localMap);
// //     syncProgress.totalFiles = countSyncFiles(serverMap, localMap);

// //     Serial.printf("Sync plan: %d files, %d bytes to download\n",
// //                   syncProgress.totalFiles, syncProgress.totalBytes);

// //     bool shouldContinue = true;
// //     int filesDownloaded = 0;

// //     // Download files to SPIFFS
// //     for (const auto &pair : serverMap)
// //     {
// //         if (!shouldContinue)
// //             break;

// //         const String &filename = pair.first;
// //         JsonObject serverFile = pair.second;
        
// //         bool needsDownload = false;
        
// //         auto localIt = localMap.find(filename);
// //         if (localIt == localMap.end())
// //         {
// //             needsDownload = true;
// //         }
// //         else
// //         {
// //             uint32_t serverSize = serverFile["size"].as<uint32_t>();
// //             uint32_t localSize = localIt->second["size"].as<uint32_t>();
// //             needsDownload = (serverSize != localSize);
// //         }

// //         if (needsDownload)
// //         {
// //             size_t bufferSize = min((size_t)10000, (size_t)ESP.getMaxAllocHeap());
// //             uint8_t *buffer = new uint8_t[bufferSize];
            
// //             if (buffer)
// //             {
// //                 shouldContinue = downloadFileToSpiffs(serverAddress, filename.c_str(), 
// //                                                        syncProgress, bufferSize, buffer);
// //                 delete[] buffer;
                
// //                 if (shouldContinue)
// //                 {
// //                     filesDownloaded++;
// //                     syncProgress.processedFiles++;
// //                 }
// //             }
// //             else
// //             {
// //                 Serial.println("Failed to allocate download buffer");
// //                 shouldContinue = false;
// //             }
// //         }
// //         else
// //         {
// //             Serial.printf("Up to date: %s\n", filename.c_str());
// //         }
// //     }

// //     // Remove local files not on server (if enabled)
// //     if (REMOVE_LOCAL_FILES_NOT_ON_SERVER && shouldContinue)
// //     {
// //         Serial.println("Checking for files to remove...");
// //         for (const auto &pair : localMap)
// //         {
// //             if (serverMap.find(pair.first) == serverMap.end())
// //             {
// //                 Serial.printf("Removing: %s\n", pair.first.c_str());
// //                 deleteFileFromSpiffs(pair.first.c_str());
// //             }
// //         }
// //     }

// //     // Load files to PSRAM
// //     if (shouldContinue)
// //     {
// //         Serial.println("Loading files to PSRAM...");
// //         loadFilesToPsram();
// //     }

// //     // End SPIFFS after sync
// //     endSpiffs();

// //     // Final progress update
// //     if (progressCallback)
// //     {
// //         uint32_t totalTransferred = syncProgress.downloadedBytes + syncProgress.uploadedBytes;
// //         progressCallback(totalTransferred, syncProgress.totalBytes, 100);
// //     }

// //     if (shouldContinue)
// //     {
// //         Serial.printf("=== Sync completed: %d files downloaded ===\n", filesDownloaded);
// //         return true;
// //     }
// //     else
// //     {
// //         Serial.println("=== Sync cancelled ===");
// //         return false;
// //     }
// // }

// // //=============================================================================
// // // Debug Utilities
// // //=============================================================================

// // void printSpiffsFileSystem()
// // {
// //     Serial.println("\n=== SPIFFS Contents ===");
    
// //     if (!initSpiffs())
// //     {
// //         Serial.println("Failed to initialize SPIFFS");
// //         return;
// //     }

// //     File root = SPIFFS.open("/");
// //     File file = root.openNextFile();

// //     size_t totalUsed = 0;
// //     int fileCount = 0;

// //     while (file)
// //     {
// //         if (!file.isDirectory())
// //         {
// //             Serial.printf("  %s (%d bytes)\n", file.name(), file.size());
// //             totalUsed += file.size();
// //             fileCount++;
// //         }
// //         file = root.openNextFile();
// //     }

// //     Serial.println("------------------------");
// //     Serial.printf("Files: %d\n", fileCount);
// //     Serial.printf("Total: %d bytes\n", SPIFFS.totalBytes());
// //     Serial.printf("Used:  %d bytes\n", SPIFFS.usedBytes());
// //     Serial.printf("Free:  %d bytes\n", SPIFFS.totalBytes() - SPIFFS.usedBytes());
// //     Serial.println("========================\n");

// //     endSpiffs();
// // }

// // void printPsramFileSystem()
// // {
// //     Serial.println("\n=== PSRamFS Contents ===");
    
// //     File root = PSRamFS.open("/");
// //     File file = root.openNextFile();

// //     int fileCount = 0;

// //     while (file)
// //     {
// //         if (!file.isDirectory())
// //         {
// //             Serial.printf("  %s (%d bytes)\n", file.name(), file.size());
// //             fileCount++;
// //         }
// //         file = root.openNextFile();
// //     }

// //     Serial.println("------------------------");
// //     Serial.printf("Files: %d\n", fileCount);
// //     Serial.printf("Total: %d bytes\n", PSRamFS.totalBytes());
// //     Serial.printf("Used:  %d bytes\n", PSRamFS.usedBytes());
// //     Serial.printf("Free:  %d bytes\n", PSRamFS.totalBytes() - PSRamFS.usedBytes());
// //     Serial.println("========================\n");
// // }

// // void printBothFileSystems()
// // {
// //     printSpiffsFileSystem();
// //     printPsramFileSystem();
// // }

// // // #include <Arduino.h>
// // // #include <HTTPClient.h>
// // // #include <ArduinoJson.h>
// // // #include "PSRamFS.h"
// // // #include <map>
// // // #include "serverSync.h"

// // // #ifdef _PSRAMFS_H_
// // // #define SYNC_IGNORE_HASH    1
// // // #else 
// // // #define SYNC_IGNORE_HASH    0
// // // #endif

// // // const bool REMOVE_LOCAL_FILES_NOT_ON_SERVER = false; // Set to true to enable cleanup
// // // ProgressCallback progressCallback = NULL;

// // // // Function to update and report progress
// // // bool updateProgress(SyncProgress &syncProgress, uint32_t bytesTransferred, bool isUpload = false)
// // // {
// // //     if (isUpload)
// // //     {
// // //         syncProgress.uploadedBytes += bytesTransferred;
// // //     }
// // //     else
// // //     {
// // //         syncProgress.downloadedBytes += bytesTransferred;
// // //     }

// // //     uint32_t totalTransferred = syncProgress.downloadedBytes + syncProgress.uploadedBytes;

// // //     if (syncProgress.totalBytes > 0)
// // //     {
// // //         syncProgress.percentage = (totalTransferred * 100) / syncProgress.totalBytes;
// // //     }

// // //     // Call progress callback every second
// // //     unsigned long currentTime = millis();
// // //     if (currentTime - syncProgress.lastUpdateTime >= 1000)
// // //     {
// // //         syncProgress.lastUpdateTime = currentTime;

// // //         if (progressCallback)
// // //         {
// // //             return progressCallback(totalTransferred, syncProgress.totalBytes, syncProgress.percentage);
// // //         }
// // //     }

// // //     return true;
// // // }

// // // // Function to get list of files from PsRamFS
// // // String getLocalFileList()
// // // {
// // //     JsonDocument doc;
// // //     JsonArray files = doc["files"].to<JsonArray>();

// // //     Serial.println("=== Local PsRamFS file list ===");

// // //     File root = PSRamFS.open("/");
// // //     File file = root.openNextFile();

// // //     while (file)
// // //     {
// // //         if (!file.isDirectory())
// // //         {
// // //             String fullPath = file.name();
// // //             String filename = fullPath;

// // //             // Remove leading "/" for compatibility with server
// // //             if (filename.startsWith("/"))
// // //             {
// // //                 filename = filename.substring(1);
// // //             }

// // //             uint32_t fileSize = file.size();

// // //             Serial.printf("Local file: %s, size: %d\n",
// // //                           filename.c_str(), fileSize);

// // //             JsonObject fileObj = files.add<JsonObject>();
// // //             fileObj["name"] = filename;
// // //             fileObj["size"] = fileSize;
// // //             // Hash removed for RAM-drive
// // //         }
// // //         file = root.openNextFile();
// // //     }

// // //     Serial.println("=== End local file list ===");

// // //     String result;
// // //     serializeJson(doc, result);
// // //     return result;
// // // }

// // // // Upload file to server - disabled for one-way sync
// // // bool uploadFile(const char *serverAddress, const char *filename)
// // // {
// // //     Serial.printf("Upload disabled - one-way sync (server to ESP32 only)\n");
// // //     return true; // Always return true to avoid breaking sync flow
// // // }

// // // // Download file from server with progress tracking
// // // bool downloadFile(const char *serverAddress, const char *filename, SyncProgress &syncProgress, const size_t bufferSize, uint8_t *buffer)
// // // {    
// // //     HTTPClient http;
// // //     http.begin(String(serverAddress) + "/download?file=" + String(filename));
// // //     http.setTimeout(30000);        // 30 second timeout for large files
// // //     http.setConnectTimeout(10000); // 10 second connection timeout

// // //     int httpResponseCode = http.GET();

// // //     if (httpResponseCode == 200)
// // //     {
// // //         int contentLength = http.getSize();
// // //         Serial.printf("Downloading file: %s (%d bytes)\n", filename, contentLength);

// // //         // Check if we have enough space in PsRamFS
// // //         size_t freeSpace = PSRamFS.totalBytes() - PSRamFS.usedBytes();
// // //         if (contentLength > 0 && contentLength > freeSpace)
// // //         {
// // //             Serial.printf("Error: Not enough space in PsRamFS. Need: %d, Available: %d\n",
// // //                           contentLength, freeSpace);
// // //             http.end();
// // //             return false;
// // //         }

// // //         // Add "/" prefix for PsRamFS
// // //         String psramPath = "/";
// // //         psramPath += filename;

// // //         // Remove existing file first to avoid corruption
// // //         if (PSRamFS.exists(psramPath))
// // //         {
// // //             PSRamFS.remove(psramPath);
// // //             Serial.printf("Removed existing file: %s\n", psramPath.c_str());
// // //         }

// // //         File file = PSRamFS.open(psramPath, "w");
// // //         if (!file)
// // //         {
// // //             Serial.println("Error creating file: " + psramPath);
// // //             http.end();
// // //             return false;
// // //         }

// // //         WiFiClient *stream = http.getStreamPtr();
// // //         int totalDownloaded = 0;
// // //         bool shouldContinue = true;
// // //         unsigned long lastProgressTime = millis();
// // //         unsigned long downloadStartTime = millis();

// // //         Serial.printf("Starting download of %d bytes...\n", contentLength);

// // //         // Download with improved error handling
// // //         while (shouldContinue && (contentLength < 0 || totalDownloaded < contentLength))
// // //         {
// // //             // Check if connection is still alive
// // //             if (!http.connected())
// // //             {
// // //                 Serial.println("HTTP connection lost during download");
// // //                 break;
// // //             }

// // //             size_t availableBytes = stream->available();
// // //             if (availableBytes > 0)
// // //             {
// // //                 size_t bytesToRead = min(availableBytes, bufferSize);

// // //                 Serial.printf("\t\tto read: %d bytes\r\n", bytesToRead);

// // //                 int bytesRead = stream->readBytes(buffer, bytesToRead);

// // //                 if (bytesRead > 0)
// // //                 {
// // //                     size_t bytesWritten = file.write(buffer, bytesRead);
// // //                     if (bytesWritten != bytesRead)
// // //                     {
// // //                         Serial.printf("Write error: expected %d, written %d\n", bytesRead, bytesWritten);
// // //                         shouldContinue = false;
// // //                         break;
// // //                     }

// // //                     totalDownloaded += bytesRead;

// // //                     // Progress update every second or every 10KB
// // //                     unsigned long currentTime = millis();
// // //                     if (currentTime - lastProgressTime >= 1000 ||
// // //                         totalDownloaded % 10240 == 0)
// // //                     {
// // //                         Serial.printf("Downloaded: %d/%d bytes (%.1f%%)\n",
// // //                                       totalDownloaded,
// // //                                       contentLength > 0 ? contentLength : totalDownloaded,
// // //                                       contentLength > 0 ? (totalDownloaded * 100.0 / contentLength) : 0.0);
// // //                         lastProgressTime = currentTime;
// // //                     }
                    
// // //                     shouldContinue = updateProgress(syncProgress, bytesRead, false);                    

// // //                     if (!shouldContinue)
// // //                     {
// // //                         Serial.println("Download cancelled by user");
// // //                         break;
// // //                     }

// // //                     // Watchdog reset for long downloads
// // //                     yield();
// // //                 }
// // //                 else
// // //                 {
// // //                     // No bytes read, wait a bit
// // //                     delay(10);
// // //                 }
// // //             }
// // //             else
// // //             {
// // //                 // No data available, check if we're done or connection lost
// // //                 if (contentLength > 0 && totalDownloaded >= contentLength)
// // //                 {
// // //                     break; // Download complete
// // //                 }

// // //                 // Wait for more data
// // //                 delay(50);

// // //                 // Timeout check (30 seconds without data)
// // //                 if (millis() - lastProgressTime > 30000)
// // //                 {
// // //                     Serial.println("Download timeout - no data received");
// // //                     shouldContinue = false;
// // //                     break;
// // //                 }
// // //             }
// // //         }

// // //         file.close();
// // //         http.end();

// // //         unsigned long downloadTime = millis() - downloadStartTime;
// // //         Serial.printf("Download finished in %lu ms\n", downloadTime);

// // //         if (!shouldContinue)
// // //         {
// // //             PSRamFS.remove(psramPath); // Remove incomplete file
// // //             return false;
// // //         }

// // //         // Verify file was saved correctly
// // //         if (PSRamFS.exists(psramPath))
// // //         {
// // //             File verifyFile = PSRamFS.open(psramPath, "r");
// // //             uint32_t savedSize = verifyFile.size();
// // //             verifyFile.close();

// // //             Serial.printf("File saved: %s, size: %d bytes\n", filename, savedSize);

// // //             if (contentLength > 0 && savedSize != contentLength)
// // //             {
// // //                 Serial.printf("WARNING: Size mismatch! Expected: %d, Saved: %d\n",
// // //                               contentLength, savedSize);
// // //                 PSRamFS.remove(psramPath); // Remove corrupted file
// // //                 return false;
// // //             }
// // //         }
// // //         else
// // //         {
// // //             Serial.printf("ERROR: File was not saved: %s\n", filename);
// // //             return false;
// // //         }

// // //         Serial.println("File downloaded successfully: " + String(filename));
// // //         return true;
// // //     }
// // //     else
// // //     {
// // //         Serial.printf("Download error for file: %s, code: %d\n", filename, httpResponseCode);
// // //         http.end();
// // //         return false;
// // //     }
// // // }

// // // // Delete file
// // // bool deleteFile(const char *filename)
// // // {
// // //     // Add "/" prefix for PsRamFS
// // //     String psramPath = "/";
// // //     psramPath += filename;

// // //     if (PSRamFS.remove(psramPath))
// // //     {
// // //         Serial.println("File deleted: " + String(filename));
// // //         return true;
// // //     }
// // //     else
// // //     {
// // //         Serial.println("Error deleting file: " + String(filename));
// // //         return false;
// // //     }
// // // }

// // // // Get file list from server
// // // String getServerFileList(const char *serverAddress)
// // // {
// // //     HTTPClient http;
// // //     http.begin(String(serverAddress) + "/list");

// // //     int httpResponseCode = http.GET();

// // //     if (httpResponseCode == 200)
// // //     {
// // //         String payload = http.getString();
// // //         http.end();

// // //         Serial.println("=== Server file list ===");

// // //         // Parse and log server files for debugging
// // //         JsonDocument serverDoc;
// // //         DeserializationError error = deserializeJson(serverDoc, payload);

// // //         if (!error)
// // //         {
// // //             JsonArray serverFiles = serverDoc["files"];
// // //             for (JsonObject file : serverFiles)
// // //             {
// // //                 String filename = file["name"].as<String>();
// // //                 uint32_t fileSize = file["size"].as<uint32_t>();

// // //                 Serial.printf("Server file: %s, size: %d\n",
// // //                               filename.c_str(), fileSize);
// // //             }
// // //         }

// // //         Serial.println("=== End server file list ===");

// // //         return payload;
// // //     }
// // //     else
// // //     {
// // //         Serial.printf("Error getting file list from server, code: %d\n", httpResponseCode);
// // //         http.end();
// // //         return "";
// // //     }
// // // }

// // // // Calculate total sync size (only downloads from server)
// // // uint32_t calculateSyncSize(const std::map<String, JsonObject> &serverMap,
// // //                            const std::map<String, JsonObject> &localMap)
// // // {
// // //     uint32_t totalSize = 0;

// // //     // Files to download (on server but not local)
// // //     for (auto &pair : serverMap)
// // //     {
// // //         String filename = pair.first;
// // //         JsonObject serverFile = pair.second;

// // //         if (localMap.find(filename) == localMap.end())
// // //         {
// // //             // File exists on server but not locally
// // //             totalSize += serverFile["size"].as<uint32_t>();
// // //         }
// // //         // Hash comparison removed - always re-download existing files for RAM-drive
// // //     }

// // //     return totalSize;
// // // }

// // // // Count total files to sync (only downloads)
// // // uint32_t countSyncFiles(const std::map<String, JsonObject> &serverMap,
// // //                         const std::map<String, JsonObject> &localMap)
// // // {
// // //     uint32_t totalFiles = 0;

// // //     // Files to download
// // //     for (auto &pair : serverMap)
// // //     {
// // //         String filename = pair.first;

// // //         if (localMap.find(filename) == localMap.end())
// // //         {
// // //             totalFiles++;
// // //         }
// // //         // Hash comparison removed - don't count existing files for re-download
// // //     }

// // //     return totalFiles;
// // // }

// // // // Main sync function
// // // bool syncFiles(const char *serverAddress, ProgressCallback callback) 
// // // {
// // //     SyncProgress syncProgress = {0, 0, 0, 0, 0, 0, 0};
// // //     Serial.print(">>> syncFiles: ");    
// // //     Serial.println(serverAddress);
// // //     setProgressCallback(callback);

// // //     syncProgress = {0, 0, 0, 0, 0, 0, millis()};

// // //     // Get file list from server
// // //     String serverListStr = getServerFileList(serverAddress);
// // //     if (serverListStr.isEmpty())
// // //     {
// // //         Serial.println("Failed to get file list from server");
// // //         return false;
// // //     }

// // //     // Get local file list
// // //     String localListStr = getLocalFileList();

// // //     // Parse JSON
// // //     JsonDocument serverDoc;
// // //     JsonDocument localDoc;

// // //     DeserializationError serverError = deserializeJson(serverDoc, serverListStr);
// // //     DeserializationError localError = deserializeJson(localDoc, localListStr);

// // //     if (serverError)
// // //     {
// // //         Serial.println("Error parsing server JSON: " + String(serverError.c_str()));
// // //         return false;
// // //     }

// // //     if (localError)
// // //     {
// // //         Serial.println("Error parsing local JSON: " + String(localError.c_str()));
// // //         return false;
// // //     }

// // //     JsonArray serverFiles = serverDoc["files"];
// // //     JsonArray localFiles = localDoc["files"];

// // //     // Create maps for quick lookup
// // //     std::map<String, JsonObject> serverMap;
// // //     std::map<String, JsonObject> localMap;

// // //     // Fill server files map
// // //     for (JsonObject file : serverFiles)
// // //     {
// // //         String filename = file["name"].as<String>();
// // //         serverMap[filename] = file;
// // //     }

// // //     // Fill local files map
// // //     for (JsonObject file : localFiles)
// // //     {
// // //         String filename = file["name"].as<String>();
// // //         localMap[filename] = file;
// // //     }

// // //     // Calculate total sync size and file count
// // //     syncProgress.totalBytes = calculateSyncSize(serverMap, localMap);
// // //     syncProgress.totalFiles = countSyncFiles(serverMap, localMap);

// // //     Serial.printf("One-way sync started (server → ESP32): %d files, %d bytes total\n",
// // //                   syncProgress.totalFiles, syncProgress.totalBytes);

// // //     if (syncProgress.totalFiles == 0)
// // //     {
// // //         Serial.println("No files to sync from server");
// // //         return false;
// // //     }

// // //     bool shouldContinue = true;

// // //     // Only download files from server (one-way sync)
// // //     for (auto &pair : serverMap)
// // //     {
// // //         if (!shouldContinue)
// // //             break;

// // //         String filename = pair.first;

// // //         if (localMap.find(filename) == localMap.end())
// // //         {
// // //             // File exists on server but not locally - download            
// // //             size_t bufferSize = 10000;
// // //             if (bufferSize > ESP.getMaxAllocHeap())
// // //             {
// // //                 bufferSize = ESP.getMaxAllocHeap();
// // //             }
// // //             Serial.printf(">>> Downloading new file [%s] [%u bytes buf]\r\n", filename.c_str(), bufferSize);
// // //             uint8_t *buffer = new uint8_t[bufferSize];
// // //             shouldContinue = downloadFile(serverAddress, filename.c_str(), syncProgress, bufferSize, buffer);
// // //             delete buffer;
// // //         }
// // //         else
// // //         {
// // //             // File exists both places - skip hash check for RAM-drive
// // //             Serial.println("File already exists locally (skipping): " + filename);
// // //         }

// // //         if (shouldContinue)
// // //         {
// // //             syncProgress.processedFiles++;
// // //         }
// // //     }

// // //     // Remove local files that don't exist on server (configurable cleanup)
// // //     if (REMOVE_LOCAL_FILES_NOT_ON_SERVER)
// // //     {
// // //         Serial.println("Checking for local files to remove...");
// // //         for (auto &pair : localMap)
// // //         {
// // //             if (!shouldContinue)
// // //                 break;

// // //             String filename = pair.first;

// // //             if (serverMap.find(filename) == serverMap.end())
// // //             {
// // //                 // File exists locally but not on server - remove it
// // //                 Serial.println("Removing local file not on server: " + filename);
// // //                 deleteFile(filename.c_str());
// // //             }
// // //         }
// // //     }
// // //     else
// // //     {
// // //         Serial.println("Local file cleanup disabled - keeping all local files");
// // //     }

// // //     if (shouldContinue)
// // //     {
// // //         Serial.println("Synchronization completed successfully");
// // //     }
// // //     else
// // //     {
// // //         Serial.println("Synchronization cancelled by user");
// // //         return false;
// // //     }

// // //     // Final progress update
// // //     if (progressCallback)
// // //     {
// // //         uint32_t totalTransferred = syncProgress.downloadedBytes + syncProgress.uploadedBytes;
// // //         progressCallback(totalTransferred, syncProgress.totalBytes, 100);
// // //     }
// // //     return true;
// // // }

// // // // Function to set custom progress callback
// // // void setProgressCallback(ProgressCallback callback)
// // // {
// // //     progressCallback = callback;
// // // }

// // // // Default progress callback (stub with print)
// // // bool defaultProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage)
// // // {
// // //     Serial.printf("Progress: %d/%d bytes (%d%%) downloaded\n", downloaded, total, percentage);

// // //     // Add your custom logic here
// // //     // Return false to cancel sync, true to continue
// // //     return true;
// // // }

// // // void printPsramFileSystem(void)
// // // {
// // //     File root = PSRamFS.open("/");
// // //     File file = root.openNextFile();

// // //     Serial.println("File system contents:");
// // //     Serial.println("----------------------------");

// // //     while (file)
// // //     {
// // //         if (file.isDirectory())
// // //         {
// // //             Serial.print("DIR: ");
// // //             Serial.println(file.name());
// // //         }
// // //         else
// // //         {
// // //             Serial.print("FILE: ");
// // //             Serial.print(file.name());
// // //             Serial.print(" (");
// // //             Serial.print(file.size());
// // //             Serial.println(" bytes)");
// // //         }
// // //         file = root.openNextFile();
// // //     }

// // //     Serial.println("----------------------------");

// // //     // File system information
// // //     Serial.print("Total size: ");
// // //     Serial.print(PSRamFS.totalBytes());
// // //     Serial.println(" bytes");

// // //     Serial.print("Used: ");
// // //     Serial.print(PSRamFS.usedBytes());
// // //     Serial.println(" bytes");

// // //     Serial.print("Free: ");
// // //     Serial.print(PSRamFS.totalBytes() - PSRamFS.usedBytes());
// // //     Serial.println(" bytes");
// // // }
