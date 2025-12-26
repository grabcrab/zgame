/**
 * @file syncFiles.cpp
 * @brief ESP32 File Synchronization Library with LittleFS persistence and PSRAM caching
 * 
 * This library synchronizes files from a server to the ESP32:
 * 1. Files are downloaded and stored permanently in LittleFS
 * 2. After sync, files are copied to PSRAM for fast runtime access
 * 3. On boot, files can be loaded from LittleFS to PSRAM (no network needed)
 * 
 * LittleFS provides persistence across reboots
 * PSRAM provides fast file access during runtime
 */

#include <Arduino.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
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
// LittleFS Initialization (internal use)
//=============================================================================

static bool initSpiffs()
{
    if (!LittleFS.begin(true)) // true = format if mount fails
    {
        Serial.println("ERROR: LittleFS initialization failed!");
        return false;
    }
    
    Serial.printf("LittleFS initialized: Total=%d, Used=%d, Free=%d bytes\n",
                  LittleFS.totalBytes(), LittleFS.usedBytes(), 
                  LittleFS.totalBytes() - LittleFS.usedBytes());
    return true;
}

static void endSpiffs()
{
    LittleFS.end();
    Serial.println("LittleFS unmounted");
}

//=============================================================================
// Server List Cache (for hash comparison)
//=============================================================================

static bool saveServerListCache(const String &serverListStr)
{
    File file = LittleFS.open(SERVER_LIST_CACHE_FILE, "w");
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
    if (!LittleFS.exists(SERVER_LIST_CACHE_FILE))
    {
        Serial.println("No cached server list found");
        return "";
    }
    
    File file = LittleFS.open(SERVER_LIST_CACHE_FILE, "r");
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
// LittleFS File Operations (Persistent Storage)
//=============================================================================

String getLocalFileList()
{
    JsonDocument doc;
    JsonArray files = doc["files"].to<JsonArray>();

    Serial.println("=== Local LittleFS file list ===");

    File root = LittleFS.open("/");
    if (!root || !root.isDirectory())
    {
        Serial.println("Failed to open LittleFS root");
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

    if (LittleFS.remove(spiffsPath))
    {
        Serial.printf("Deleted from LittleFS: %s\n", filename);
        return true;
    }
    else
    {
        Serial.printf("Error deleting from LittleFS: %s\n", filename);
        return false;
    }
}

bool fileExistsOnSpiffs(const char *filename)
{
    String spiffsPath = "/";
    spiffsPath += filename;
    return LittleFS.exists(spiffsPath);
}

size_t getSpiffsFreeSpace()
{
    return LittleFS.totalBytes() - LittleFS.usedBytes();
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
// Copy Files from LittleFS to PSRAM
//=============================================================================

static bool copyFileToPsram(const char *filename)
{
    String spiffsPath = "/";
    spiffsPath += filename;
    
    String psramPath = "/";
    psramPath += filename;

    // Open source file from LittleFS
    File srcFile = LittleFS.open(spiffsPath, "r");
    if (!srcFile)
    {
        Serial.printf("Failed to open LittleFS file: %s\n", filename);
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

// Internal version - LittleFS must already be initialized
static int loadFilesToPsramInternal()
{
    int filesLoaded = 0;
    int filesFailed = 0;

    File root = LittleFS.open("/");
    if (!root || !root.isDirectory())
    {
        Serial.println("Failed to open LittleFS root");
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
    Serial.println("=== Loading files from LittleFS to PSRAM ===");
    
    // Initialize LittleFS
    if (!initSpiffs())
    {
        Serial.println("ERROR: Failed to initialize LittleFS!");
        return 0;
    }

    int filesLoaded = loadFilesToPsramInternal();

    // End LittleFS
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
// Download File to LittleFS
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

    // Check LittleFS space
    size_t freeSpace = LittleFS.totalBytes() - LittleFS.usedBytes();
    if (contentLength > 0 && (size_t)contentLength > freeSpace)
    {
        Serial.printf("Not enough LittleFS space. Need: %d, Available: %d\n",
                      contentLength, freeSpace);
        http.end();
        return false;
    }

    // Prepare LittleFS path
    String spiffsPath = "/";
    spiffsPath += filename;

    // Remove existing file
    if (LittleFS.exists(spiffsPath))
    {
        LittleFS.remove(spiffsPath);
    }

    // Create file in LittleFS
    File file = LittleFS.open(spiffsPath, "w");
    if (!file)
    {
        Serial.printf("Error creating LittleFS file: %s\n", spiffsPath.c_str());
        http.end();
        return false;
    }

    WiFiClient *stream = http.getStreamPtr();
    stream->setTimeout(5000);  // 5 second timeout for reads
    
    int totalDownloaded = 0;
    bool shouldContinue = true;
    unsigned long lastProgressTime = millis();
    unsigned long downloadStartTime = millis();
    unsigned long totalNetworkTime = 0;
    unsigned long totalWriteTime = 0;

    // Download loop - read directly with timeout, no polling
    while (shouldContinue && (contentLength < 0 || totalDownloaded < contentLength))
    {
        if (!http.connected() && !stream->available())
        {
            if (totalDownloaded < contentLength)
            {
                Serial.println("HTTP connection lost during download");
            }
            break;
        }

        int bytesToRead = bufferSize;
        if (contentLength > 0)
        {
            bytesToRead = min((int)bufferSize, contentLength - totalDownloaded);
        }
        
        unsigned long networkStart = millis();
        int bytesRead = stream->readBytes(buffer, bytesToRead);
        totalNetworkTime += millis() - networkStart;

        if (bytesRead > 0)
        {
            unsigned long writeStart = millis();
            size_t bytesWritten = file.write(buffer, bytesRead);
            totalWriteTime += millis() - writeStart;
            
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
        }
        else
        {
            // No data received - timeout or end of stream
            break;
        }
        
        yield();
    }

    file.close();;;
    http.end();

    unsigned long downloadTime = millis() - downloadStartTime;

    if (!shouldContinue)
    {
        LittleFS.remove(spiffsPath);
        Serial.printf("Download cancelled or failed for: %s\n", filename);
        return false;
    }

    // Verify file
    if (LittleFS.exists(spiffsPath))
    {
        File verifyFile = LittleFS.open(spiffsPath, "r");
        uint32_t savedSize = verifyFile.size();
        verifyFile.close();

        if (contentLength > 0 && savedSize != (uint32_t)contentLength)
        {
            Serial.printf("Size mismatch! Expected: %d, Saved: %d\n", contentLength, savedSize);
            LittleFS.remove(spiffsPath);
            return false;
        }

        Serial.printf("Downloaded to LittleFS: %s (%d bytes, total: %lu ms, download: %lu ms, write: %lu ms)\n", 
                      filename, savedSize, downloadTime, totalNetworkTime, totalWriteTime);
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
            // File not on LittleFS - need to download
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

    // Initialize LittleFS for sync operation
    if (!initSpiffs())
    {
        Serial.println("ERROR: Failed to initialize LittleFS!");
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

    // End LittleFS after sync
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
    Serial.println("\n=== LittleFS Contents ===");
    
    if (!initSpiffs())
    {
        Serial.println("Failed to initialize LittleFS");
        return;
    }

    File root = LittleFS.open("/");
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
    Serial.printf("Total: %d bytes\n", LittleFS.totalBytes());
    Serial.printf("Used:  %d bytes\n", LittleFS.usedBytes());
    Serial.printf("Free:  %d bytes\n", LittleFS.totalBytes() - LittleFS.usedBytes());
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
//  * @brief ESP32 File Synchronization Library with LittleFS persistence and PSRAM caching
//  * 
//  * This library synchronizes files from a server to the ESP32:
//  * 1. Files are downloaded and stored permanently in LittleFS
//  * 2. After sync, files are copied to PSRAM for fast runtime access
//  * 3. On boot, files can be loaded from LittleFS to PSRAM (no network needed)
//  * 
//  * LittleFS provides persistence across reboots
//  * PSRAM provides fast file access during runtime
//  */

// #include <Arduino.h>
// #include <HTTPClient.h>
// #include <ArduinoJson.h>
// #include <LittleFS.h>
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
// // LittleFS Initialization (internal use)
// //=============================================================================

// static bool initSpiffs()
// {
//     if (!LittleFS.begin(true)) // true = format if mount fails
//     {
//         Serial.println("ERROR: LittleFS initialization failed!");
//         return false;
//     }
    
//     Serial.printf("LittleFS initialized: Total=%d, Used=%d, Free=%d bytes\n",
//                   LittleFS.totalBytes(), LittleFS.usedBytes(), 
//                   LittleFS.totalBytes() - LittleFS.usedBytes());
//     return true;
// }

// static void endSpiffs()
// {
//     LittleFS.end();
//     Serial.println("LittleFS unmounted");
// }

// //=============================================================================
// // Server List Cache (for hash comparison)
// //=============================================================================

// static bool saveServerListCache(const String &serverListStr)
// {
//     File file = LittleFS.open(SERVER_LIST_CACHE_FILE, "w");
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
//     if (!LittleFS.exists(SERVER_LIST_CACHE_FILE))
//     {
//         Serial.println("No cached server list found");
//         return "";
//     }
    
//     File file = LittleFS.open(SERVER_LIST_CACHE_FILE, "r");
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
// // LittleFS File Operations (Persistent Storage)
// //=============================================================================

// String getLocalFileList()
// {
//     JsonDocument doc;
//     JsonArray files = doc["files"].to<JsonArray>();

//     Serial.println("=== Local LittleFS file list ===");

//     File root = LittleFS.open("/");
//     if (!root || !root.isDirectory())
//     {
//         Serial.println("Failed to open LittleFS root");
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

//     if (LittleFS.remove(spiffsPath))
//     {
//         Serial.printf("Deleted from LittleFS: %s\n", filename);
//         return true;
//     }
//     else
//     {
//         Serial.printf("Error deleting from LittleFS: %s\n", filename);
//         return false;
//     }
// }

// bool fileExistsOnSpiffs(const char *filename)
// {
//     String spiffsPath = "/";
//     spiffsPath += filename;
//     return LittleFS.exists(spiffsPath);
// }

// size_t getSpiffsFreeSpace()
// {
//     return LittleFS.totalBytes() - LittleFS.usedBytes();
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
// // Copy Files from LittleFS to PSRAM
// //=============================================================================

// static bool copyFileToPsram(const char *filename)
// {
//     String spiffsPath = "/";
//     spiffsPath += filename;
    
//     String psramPath = "/";
//     psramPath += filename;

//     // Open source file from LittleFS
//     File srcFile = LittleFS.open(spiffsPath, "r");
//     if (!srcFile)
//     {
//         Serial.printf("Failed to open LittleFS file: %s\n", filename);
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

// // Internal version - LittleFS must already be initialized
// static int loadFilesToPsramInternal()
// {
//     int filesLoaded = 0;
//     int filesFailed = 0;

//     File root = LittleFS.open("/");
//     if (!root || !root.isDirectory())
//     {
//         Serial.println("Failed to open LittleFS root");
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
//     Serial.println("=== Loading files from LittleFS to PSRAM ===");
    
//     // Initialize LittleFS
//     if (!initSpiffs())
//     {
//         Serial.println("ERROR: Failed to initialize LittleFS!");
//         return 0;
//     }

//     int filesLoaded = loadFilesToPsramInternal();

//     // End LittleFS
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
// // Download File to LittleFS
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

//     // Check LittleFS space
//     size_t freeSpace = LittleFS.totalBytes() - LittleFS.usedBytes();
//     if (contentLength > 0 && (size_t)contentLength > freeSpace)
//     {
//         Serial.printf("Not enough LittleFS space. Need: %d, Available: %d\n",
//                       contentLength, freeSpace);
//         http.end();
//         return false;
//     }

//     // Prepare LittleFS path
//     String spiffsPath = "/";
//     spiffsPath += filename;

//     // Remove existing file
//     if (LittleFS.exists(spiffsPath))
//     {
//         LittleFS.remove(spiffsPath);
//     }

//     // Create file in LittleFS
//     File file = LittleFS.open(spiffsPath, "w");
//     if (!file)
//     {
//         Serial.printf("Error creating LittleFS file: %s\n", spiffsPath.c_str());
//         http.end();
//         return false;
//     }

//     WiFiClient *stream = http.getStreamPtr();
//     int totalDownloaded = 0;
//     bool shouldContinue = true;
//     unsigned long lastProgressTime = millis();
//     unsigned long downloadStartTime = millis();
//     unsigned long totalNetworkTime = 0;
//     unsigned long totalWriteTime = 0;
//     unsigned long totalWaitTime = 0;

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
            
//             unsigned long networkStart = millis();
//             int bytesRead = stream->readBytes(buffer, bytesToRead);
//             totalNetworkTime += millis() - networkStart;

//             if (bytesRead > 0)
//             {
//                 unsigned long writeStart = millis();
//                 size_t bytesWritten = file.write(buffer, bytesRead);
//                 totalWriteTime += millis() - writeStart;
                
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
//             unsigned long waitStart = millis();
//             delay(1);  // Reduced from 50ms to 1ms
//             totalWaitTime += millis() - waitStart;

//             // Timeout check (30 seconds without data)
//             if (millis() - lastProgressTime > 30000)
//             {
//                 Serial.println("Download timeout - no data received");
//                 shouldContinue = false;
//                 break;
//             }
//         }
//     }

//     file.close();;
//     http.end();

//     unsigned long downloadTime = millis() - downloadStartTime;

//     if (!shouldContinue)
//     {
//         LittleFS.remove(spiffsPath);
//         Serial.printf("Download cancelled or failed for: %s\n", filename);
//         return false;
//     }

//     // Verify file
//     if (LittleFS.exists(spiffsPath))
//     {
//         File verifyFile = LittleFS.open(spiffsPath, "r");
//         uint32_t savedSize = verifyFile.size();
//         verifyFile.close();

//         if (contentLength > 0 && savedSize != (uint32_t)contentLength)
//         {
//             Serial.printf("Size mismatch! Expected: %d, Saved: %d\n", contentLength, savedSize);
//             LittleFS.remove(spiffsPath);
//             return false;
//         }

//         Serial.printf("Downloaded to LittleFS: %s (%d bytes, total: %lu ms, download: %lu ms, write: %lu ms, wait: %lu ms)\n", 
//                       filename, savedSize, downloadTime, totalNetworkTime, totalWriteTime, totalWaitTime);
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
//             // File not on LittleFS - need to download
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

//     // Initialize LittleFS for sync operation
//     if (!initSpiffs())
//     {
//         Serial.println("ERROR: Failed to initialize LittleFS!");
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
//     bool serverListChanged = isServerListChanged(serverListStr);
    
//     if (!serverListChanged)
//     {
//         Serial.println("Files are up to date - no sync needed");
        
//         // Still load files to PSRAM
//         Serial.println("Loading files to PSRAM...");
//         loadFilesToPsramInternal();
        
//         endSpiffs();
//         return true;
//     }

//     // Server list changed - need to re-download ALL files from server
//     // (because we can't compute local hashes, we must trust server hashes)
//     Serial.println("Server list changed - re-downloading all files");

//     // Parse server JSON
//     JsonDocument serverDoc;
//     if (deserializeJson(serverDoc, serverListStr))
//     {
//         Serial.println("Error parsing server JSON");
//         endSpiffs();
//         return false;
//     }

//     JsonArray serverFiles = serverDoc["files"];

//     // Calculate total size for progress
//     syncProgress.totalBytes = 0;
//     syncProgress.totalFiles = 0;
//     for (JsonObject file : serverFiles)
//     {
//         syncProgress.totalBytes += file["size"].as<uint32_t>();
//         syncProgress.totalFiles++;
//     }

//     Serial.printf("Sync plan: %d files, %d bytes to download\n",
//                   syncProgress.totalFiles, syncProgress.totalBytes);

//     bool shouldContinue = true;
//     int filesDownloaded = 0;

//     // Download ALL files from server
//     for (JsonObject serverFile : serverFiles)
//     {
//         if (!shouldContinue)
//             break;

//         const char* filename = serverFile["name"].as<const char*>();

//         size_t bufferSize = min((size_t)10000, (size_t)ESP.getMaxAllocHeap());
//         uint8_t *buffer = new uint8_t[bufferSize];
        
//         if (buffer)
//         {
//             shouldContinue = downloadFileToSpiffs(serverAddress, filename, 
//                                                    syncProgress, bufferSize, buffer);
//             delete[] buffer;
            
//             if (shouldContinue)
//             {
//                 filesDownloaded++;
//                 syncProgress.processedFiles++;
//             }
//         }
//         else
//         {
//             Serial.println("Failed to allocate download buffer");
//             shouldContinue = false;
//         }
//     }

//     // Remove local files not on server (if enabled)
//     if (REMOVE_LOCAL_FILES_NOT_ON_SERVER && shouldContinue)
//     {
//         // Get local file list
//         String localListStr = getLocalFileList();
//         JsonDocument localDoc;
//         if (!deserializeJson(localDoc, localListStr))
//         {
//             JsonArray localFiles = localDoc["files"];
            
//             // Create server filename set
//             std::map<String, bool> serverFileNames;
//             for (JsonObject file : serverFiles)
//             {
//                 serverFileNames[file["name"].as<String>()] = true;
//             }
            
//             // Remove files not on server
//             for (JsonObject localFile : localFiles)
//             {
//                 String filename = localFile["name"].as<String>();
//                 if (serverFileNames.find(filename) == serverFileNames.end() && 
//                     filename != ".server_list.json")
//                 {
//                     Serial.printf("Removing: %s\n", filename.c_str());
//                     deleteFileFromSpiffs(filename.c_str());
//                 }
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

//     // End LittleFS after sync
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
//     Serial.println("\n=== LittleFS Contents ===");
    
//     if (!initSpiffs())
//     {
//         Serial.println("Failed to initialize LittleFS");
//         return;
//     }

//     File root = LittleFS.open("/");
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
//     Serial.printf("Total: %d bytes\n", LittleFS.totalBytes());
//     Serial.printf("Used:  %d bytes\n", LittleFS.usedBytes());
//     Serial.printf("Free:  %d bytes\n", LittleFS.totalBytes() - LittleFS.usedBytes());
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
// //  * @brief ESP32 File Synchronization Library with LittleFS persistence and PSRAM caching
// //  * 
// //  * This library synchronizes files from a server to the ESP32:
// //  * 1. Files are downloaded and stored permanently in LittleFS
// //  * 2. After sync, files are copied to PSRAM for fast runtime access
// //  * 3. On boot, files can be loaded from LittleFS to PSRAM (no network needed)
// //  * 
// //  * LittleFS provides persistence across reboots
// //  * PSRAM provides fast file access during runtime
// //  */

// // #include <Arduino.h>
// // #include <HTTPClient.h>
// // #include <ArduinoJson.h>
// // #include <LittleFS.h>
// // #include "PSRamFS.h"
// // #include <map>
// // #include "serverSync.h"

// // // Configuration
// // static const bool REMOVE_LOCAL_FILES_NOT_ON_SERVER = false;
// // static ProgressCallback progressCallback = nullptr;

// // // Buffer size for file operations
// // static const size_t COPY_BUFFER_SIZE = 4096;

// // // Cached server file list filename
// // static const char* SERVER_LIST_CACHE_FILE = "/.server_list.json";

// // //=============================================================================
// // // LittleFS Initialization (internal use)
// // //=============================================================================

// // static bool initSpiffs()
// // {
// //     if (!LittleFS.begin(true)) // true = format if mount fails
// //     {
// //         Serial.println("ERROR: LittleFS initialization failed!");
// //         return false;
// //     }
    
// //     Serial.printf("LittleFS initialized: Total=%d, Used=%d, Free=%d bytes\n",
// //                   LittleFS.totalBytes(), LittleFS.usedBytes(), 
// //                   LittleFS.totalBytes() - LittleFS.usedBytes());
// //     return true;
// // }

// // static void endSpiffs()
// // {
// //     LittleFS.end();
// //     Serial.println("LittleFS unmounted");
// // }

// // //=============================================================================
// // // Server List Cache (for hash comparison)
// // //=============================================================================

// // static bool saveServerListCache(const String &serverListStr)
// // {
// //     File file = LittleFS.open(SERVER_LIST_CACHE_FILE, "w");
// //     if (!file)
// //     {
// //         Serial.println("ERROR: Failed to create server list cache file");
// //         return false;
// //     }
    
// //     size_t written = file.print(serverListStr);
// //     file.close();
    
// //     if (written == serverListStr.length())
// //     {
// //         Serial.printf("Server list cached (%d bytes)\n", written);
// //         return true;
// //     }
// //     else
// //     {
// //         Serial.println("ERROR: Failed to write server list cache");
// //         return false;
// //     }
// // }

// // static String loadServerListCache()
// // {
// //     if (!LittleFS.exists(SERVER_LIST_CACHE_FILE))
// //     {
// //         Serial.println("No cached server list found");
// //         return "";
// //     }
    
// //     File file = LittleFS.open(SERVER_LIST_CACHE_FILE, "r");
// //     if (!file)
// //     {
// //         Serial.println("ERROR: Failed to open server list cache");
// //         return "";
// //     }
    
// //     String content = file.readString();
// //     file.close();
    
// //     Serial.printf("Loaded cached server list (%d bytes)\n", content.length());
// //     return content;
// // }

// // static bool isServerListChanged(const String &newServerList)
// // {
// //     String cachedList = loadServerListCache();
    
// //     if (cachedList.isEmpty())
// //     {
// //         Serial.println("No cache - sync required");
// //         return true;
// //     }
    
// //     if (cachedList == newServerList)
// //     {
// //         Serial.println("Server list unchanged (hash match)");
// //         return false;
// //     }
// //     else
// //     {
// //         Serial.println("Server list changed - sync required");
// //         return true;
// //     }
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
// // // LittleFS File Operations (Persistent Storage)
// // //=============================================================================

// // String getLocalFileList()
// // {
// //     JsonDocument doc;
// //     JsonArray files = doc["files"].to<JsonArray>();

// //     Serial.println("=== Local LittleFS file list ===");

// //     File root = LittleFS.open("/");
// //     if (!root || !root.isDirectory())
// //     {
// //         Serial.println("Failed to open LittleFS root");
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

// //     if (LittleFS.remove(spiffsPath))
// //     {
// //         Serial.printf("Deleted from LittleFS: %s\n", filename);
// //         return true;
// //     }
// //     else
// //     {
// //         Serial.printf("Error deleting from LittleFS: %s\n", filename);
// //         return false;
// //     }
// // }

// // bool fileExistsOnSpiffs(const char *filename)
// // {
// //     String spiffsPath = "/";
// //     spiffsPath += filename;
// //     return LittleFS.exists(spiffsPath);
// // }

// // size_t getSpiffsFreeSpace()
// // {
// //     return LittleFS.totalBytes() - LittleFS.usedBytes();
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
// // // Copy Files from LittleFS to PSRAM
// // //=============================================================================

// // static bool copyFileToPsram(const char *filename)
// // {
// //     String spiffsPath = "/";
// //     spiffsPath += filename;
    
// //     String psramPath = "/";
// //     psramPath += filename;

// //     // Open source file from LittleFS
// //     File srcFile = LittleFS.open(spiffsPath, "r");
// //     if (!srcFile)
// //     {
// //         Serial.printf("Failed to open LittleFS file: %s\n", filename);
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

// // // Internal version - LittleFS must already be initialized
// // static int loadFilesToPsramInternal()
// // {
// //     int filesLoaded = 0;
// //     int filesFailed = 0;

// //     File root = LittleFS.open("/");
// //     if (!root || !root.isDirectory())
// //     {
// //         Serial.println("Failed to open LittleFS root");
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

// //             // Skip the server list cache file
// //             if (filename != ".server_list.json")
// //             {
// //                 if (copyFileToPsram(filename.c_str()))
// //                 {
// //                     filesLoaded++;
// //                 }
// //                 else
// //                 {
// //                     filesFailed++;
// //                 }
// //             }
// //         }
// //         file = root.openNextFile();
// //     }

// //     Serial.printf("Loaded %d files to PSRAM (%d failed)\n", filesLoaded, filesFailed);
// //     return filesLoaded;
// // }

// // int loadFilesToPsram()
// // {
// //     Serial.println("=== Loading files from LittleFS to PSRAM ===");
    
// //     // Initialize LittleFS
// //     if (!initSpiffs())
// //     {
// //         Serial.println("ERROR: Failed to initialize LittleFS!");
// //         return 0;
// //     }

// //     int filesLoaded = loadFilesToPsramInternal();

// //     // End LittleFS
// //     endSpiffs();

// //     Serial.printf("=== Loaded %d files to PSRAM ===\n", filesLoaded);
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
// // // Download File to LittleFS
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

// //     // Check LittleFS space
// //     size_t freeSpace = LittleFS.totalBytes() - LittleFS.usedBytes();
// //     if (contentLength > 0 && (size_t)contentLength > freeSpace)
// //     {
// //         Serial.printf("Not enough LittleFS space. Need: %d, Available: %d\n",
// //                       contentLength, freeSpace);
// //         http.end();
// //         return false;
// //     }

// //     // Prepare LittleFS path
// //     String spiffsPath = "/";
// //     spiffsPath += filename;

// //     // Remove existing file
// //     if (LittleFS.exists(spiffsPath))
// //     {
// //         LittleFS.remove(spiffsPath);
// //     }

// //     // Create file in LittleFS
// //     File file = LittleFS.open(spiffsPath, "w");
// //     if (!file)
// //     {
// //         Serial.printf("Error creating LittleFS file: %s\n", spiffsPath.c_str());
// //         http.end();
// //         return false;
// //     }

// //     WiFiClient *stream = http.getStreamPtr();
// //     int totalDownloaded = 0;
// //     bool shouldContinue = true;
// //     unsigned long lastProgressTime = millis();
// //     unsigned long downloadStartTime = millis();
// //     unsigned long totalNetworkTime = 0;
// //     unsigned long totalWriteTime = 0;

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
            
// //             unsigned long networkStart = millis();
// //             int bytesRead = stream->readBytes(buffer, bytesToRead);
// //             totalNetworkTime += millis() - networkStart;

// //             if (bytesRead > 0)
// //             {
// //                 unsigned long writeStart = millis();
// //                 size_t bytesWritten = file.write(buffer, bytesRead);
// //                 totalWriteTime += millis() - writeStart;
                
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
// //         LittleFS.remove(spiffsPath);
// //         Serial.printf("Download cancelled or failed for: %s\n", filename);
// //         return false;
// //     }

// //     // Verify file
// //     if (LittleFS.exists(spiffsPath))
// //     {
// //         File verifyFile = LittleFS.open(spiffsPath, "r");
// //         uint32_t savedSize = verifyFile.size();
// //         verifyFile.close();

// //         if (contentLength > 0 && savedSize != (uint32_t)contentLength)
// //         {
// //             Serial.printf("Size mismatch! Expected: %d, Saved: %d\n", contentLength, savedSize);
// //             LittleFS.remove(spiffsPath);
// //             return false;
// //         }

// //         Serial.printf("Downloaded to LittleFS: %s (%d bytes, total: %lu ms, download: %lu ms, write: %lu ms)\n", 
// //                       filename, savedSize, downloadTime, totalNetworkTime, totalWriteTime);
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
// //             // File not on LittleFS - need to download
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

// //     // Initialize LittleFS for sync operation
// //     if (!initSpiffs())
// //     {
// //         Serial.println("ERROR: Failed to initialize LittleFS!");
// //         return false;
// //     }

// //     setProgressCallback(callback);

// //     SyncProgress syncProgress = {0, 0, 0, 0, 0, 0, millis()};

// //     // Get file list from server
// //     String serverListStr = getServerFileList(serverAddress);
// //     if (serverListStr.isEmpty())
// //     {
// //         Serial.println("Failed to get file list from server");
// //         endSpiffs();
// //         return false;
// //     }

// //     // Check if server list has changed (compares full JSON including hashes)
// //     bool serverListChanged = isServerListChanged(serverListStr);
    
// //     if (!serverListChanged)
// //     {
// //         Serial.println("Files are up to date - no sync needed");
        
// //         // Still load files to PSRAM
// //         Serial.println("Loading files to PSRAM...");
// //         loadFilesToPsramInternal();
        
// //         endSpiffs();
// //         return true;
// //     }

// //     // Server list changed - need to re-download ALL files from server
// //     // (because we can't compute local hashes, we must trust server hashes)
// //     Serial.println("Server list changed - re-downloading all files");

// //     // Parse server JSON
// //     JsonDocument serverDoc;
// //     if (deserializeJson(serverDoc, serverListStr))
// //     {
// //         Serial.println("Error parsing server JSON");
// //         endSpiffs();
// //         return false;
// //     }

// //     JsonArray serverFiles = serverDoc["files"];

// //     // Calculate total size for progress
// //     syncProgress.totalBytes = 0;
// //     syncProgress.totalFiles = 0;
// //     for (JsonObject file : serverFiles)
// //     {
// //         syncProgress.totalBytes += file["size"].as<uint32_t>();
// //         syncProgress.totalFiles++;
// //     }

// //     Serial.printf("Sync plan: %d files, %d bytes to download\n",
// //                   syncProgress.totalFiles, syncProgress.totalBytes);

// //     bool shouldContinue = true;
// //     int filesDownloaded = 0;

// //     // Download ALL files from server
// //     for (JsonObject serverFile : serverFiles)
// //     {
// //         if (!shouldContinue)
// //             break;

// //         const char* filename = serverFile["name"].as<const char*>();

// //         size_t bufferSize = min((size_t)10000, (size_t)ESP.getMaxAllocHeap());
// //         uint8_t *buffer = new uint8_t[bufferSize];
        
// //         if (buffer)
// //         {
// //             shouldContinue = downloadFileToSpiffs(serverAddress, filename, 
// //                                                    syncProgress, bufferSize, buffer);
// //             delete[] buffer;
            
// //             if (shouldContinue)
// //             {
// //                 filesDownloaded++;
// //                 syncProgress.processedFiles++;
// //             }
// //         }
// //         else
// //         {
// //             Serial.println("Failed to allocate download buffer");
// //             shouldContinue = false;
// //         }
// //     }

// //     // Remove local files not on server (if enabled)
// //     if (REMOVE_LOCAL_FILES_NOT_ON_SERVER && shouldContinue)
// //     {
// //         // Get local file list
// //         String localListStr = getLocalFileList();
// //         JsonDocument localDoc;
// //         if (!deserializeJson(localDoc, localListStr))
// //         {
// //             JsonArray localFiles = localDoc["files"];
            
// //             // Create server filename set
// //             std::map<String, bool> serverFileNames;
// //             for (JsonObject file : serverFiles)
// //             {
// //                 serverFileNames[file["name"].as<String>()] = true;
// //             }
            
// //             // Remove files not on server
// //             for (JsonObject localFile : localFiles)
// //             {
// //                 String filename = localFile["name"].as<String>();
// //                 if (serverFileNames.find(filename) == serverFileNames.end() && 
// //                     filename != ".server_list.json")
// //                 {
// //                     Serial.printf("Removing: %s\n", filename.c_str());
// //                     deleteFileFromSpiffs(filename.c_str());
// //                 }
// //             }
// //         }
// //     }

// //     // Save server list cache after successful sync
// //     if (shouldContinue)
// //     {
// //         saveServerListCache(serverListStr);
// //     }

// //     // Load files to PSRAM
// //     if (shouldContinue)
// //     {
// //         Serial.println("Loading files to PSRAM...");
// //         loadFilesToPsramInternal();
// //     }

// //     // End LittleFS after sync
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
// //     Serial.println("\n=== LittleFS Contents ===");
    
// //     if (!initSpiffs())
// //     {
// //         Serial.println("Failed to initialize LittleFS");
// //         return;
// //     }

// //     File root = LittleFS.open("/");
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
// //     Serial.printf("Total: %d bytes\n", LittleFS.totalBytes());
// //     Serial.printf("Used:  %d bytes\n", LittleFS.usedBytes());
// //     Serial.printf("Free:  %d bytes\n", LittleFS.totalBytes() - LittleFS.usedBytes());
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