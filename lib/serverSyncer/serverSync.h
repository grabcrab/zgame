#ifndef SERVER_SYNC_H
#define SERVER_SYNC_H

#include <Arduino.h>
#include <functional>

// Sync progress structure
struct SyncProgress {
    uint32_t totalBytes;
    uint32_t downloadedBytes;
    uint32_t uploadedBytes;
    uint32_t totalFiles;
    uint32_t processedFiles;
    uint8_t percentage;
    unsigned long lastUpdateTime;
};

// Progress callback type - return false to cancel sync
typedef std::function<bool(uint32_t transferred, uint32_t total, uint8_t percentage)> ProgressCallback;


// Main sync function - syncs from server to SPIFFS, then loads to PSRAM
// serverAddress: Base URL of sync server (e.g., "http://192.168.1.100:8080")
// callback: Optional progress callback
// Returns true on success
bool syncFiles(const char *serverAddress, ProgressCallback callback = nullptr);

// Load all files from SPIFFS to PSRAM (called automatically after sync)
// Can also be called manually at boot to restore files
// Returns number of files loaded
int loadFilesToPsram();

// Set progress callback for sync operations
void setProgressCallback(ProgressCallback callback);

// Default progress callback implementation
bool defaultProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage);

// Debug utilities
void printSpiffsFileSystem();
void printPsramFileSystem();
void printBothFileSystems();

// File operations on SPIFFS (persistent)
bool deleteFileFromSpiffs(const char *filename);
bool fileExistsOnSpiffs(const char *filename);
size_t getSpiffsFreeSpace();

// File operations on PSRAM (volatile, fast access)
bool fileExistsOnPsram(const char *filename);
size_t getPsramFreeSpace();

// Get file list as JSON string
String getLocalFileList();  // From SPIFFS
String getServerFileList(const char *serverAddress);

//OTA
bool performOTAUpdate(const char *otaServerURL, int firmwareSize);
bool syncOTA(const char *otaServerURL, int currentVersion);

#endif // SERVER_SYNC_H

// #pragma once

// #include <Arduino.h>

// //file sync
// String calculateFileHash(const char *filename);

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

// typedef bool (*ProgressCallback)(uint32_t downloaded, uint32_t total, uint8_t percentage);
// void setProgressCallback(ProgressCallback callback);
// bool defaultProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage);
// bool syncFiles(const char *serverAddress, ProgressCallback callback = defaultProgressCallback);
// void printPsramFileSystem(void);

// bool performOTAUpdate(const char *otaServerURL, int firmwareSize);
// bool syncOTA(const char *otaServerURL, int currentVersion);
