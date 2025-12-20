#pragma once

#include <Arduino.h>

//file sync
String calculateFileHash(const char *filename);

// Sync progress structure
struct SyncProgress
{
    uint32_t totalFiles;
    uint32_t processedFiles;
    uint32_t totalBytes;
    uint32_t downloadedBytes;
    uint32_t uploadedBytes;
    uint8_t percentage;
    unsigned long lastUpdateTime;
};

typedef bool (*ProgressCallback)(uint32_t downloaded, uint32_t total, uint8_t percentage);
void setProgressCallback(ProgressCallback callback);
bool defaultProgressCallback(uint32_t downloaded, uint32_t total, uint8_t percentage);
bool syncFiles(const char *serverAddress, ProgressCallback callback = defaultProgressCallback);
void printPsramFileSystem(void);

bool performOTAUpdate(const char *otaServerURL, int firmwareSize);
bool syncOTA(const char *otaServerURL, int currentVersion);
