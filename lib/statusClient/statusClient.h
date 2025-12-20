#pragma once

#include <Arduino.h>

// ============== Configuration ==============
#define STATUS_UPDATE_INTERVAL_MS   5000    // How often to send status updates
#define STATUS_ACCEL_SAMPLE_MS      5000    // Accelerometer sampling window for activity calculation
#define STATUS_SERVER_PORT          5004    // Server port
#define STATUS_GAME_STATUS_MAX_LEN  32      // Maximum length of game status string

// ============== Device Status Enum ==============
typedef enum {
    DEVICE_STATUS_OPERATION = 0,
    DEVICE_STATUS_SLEEP,
    DEVICE_STATUS_REBOOT
} DeviceStatus_t;

// ============== Command Enum ==============
typedef enum {
    CMD_NONE = 0,
    CMD_REBOOT,
    CMD_SLEEP
} DeviceCommand_t;

// ============== Initialization ==============
/**
 * Initialize the status client
 * @param deviceName Human-readable device name (max 32 chars)
 * @param serverIP IP address of the status server
 * @return true if initialization successful
 */
bool statusClientInit(const char* deviceName, const char* serverIP);

/**
 * Start the status client task
 * Should be called after WiFi is connected
 * @return true if task started successfully
 */
bool statusClientStart(void);

/**
 * Stop the status client task
 */
void statusClientStop(void);

// ============== Status Setters ==============
/**
 * Set the game status string
 * @param status Status string (max 32 chars, will be truncated if longer)
 */
void statusClientSetGameStatus(const char* status);

/**
 * Set the device status
 * @param status Device status (OPERATION, SLEEP, REBOOT)
 */
void statusClientSetDeviceStatus(DeviceStatus_t status);

// ============== Getters ==============
/**
 * Check if the status client is running
 * @return true if running
 */
bool statusClientIsRunning(void);

/**
 * Get current accelerometer activity level (1-100)
 * @return Activity level
 */
uint8_t statusClientGetAccelActivity(void);

// ============== Internal - called by accel sampling ==============
/**
 * Feed accelerometer data for activity calculation
 * Should be called periodically with current accel values
 * @param x X-axis acceleration
 * @param y Y-axis acceleration  
 * @param z Z-axis acceleration
 */
void statusClientFeedAccelData(float x, float y, float z);

void statusClientPause(void);
void statusClientResume(void);
