#pragma once
#include <Arduino.h>
#include "gameRole.h"

struct tGameApiRequest
{
    String id = "NoID";
    String role = "neutral";
    String status = "idle";
    int health = 0;
    int battery = 0;
    String comment = "";

    tGameApiRequest();

    inline void setRole(tGameRole role)
    {
        switch(role) 
        {
            case grNone:
                this->role = "none";
                break;
            case grZombie:
                this->role = "zombie";
                break;
            case grHuman:
                this->role = "human";
                break;
            case grBase:
                this->role = "base";
                break;
            case grServer:
                this->role = "server";
                break;
            case grPinger:
                this->role = "pinger";
                break;
            case grApPortalBeacon:
                this->role = "apportalbeacon";
                break;
            default:
                this->role = "unknown";
                break;
        }    
    }
    inline void print(String url)
    {
        Serial.printf(">>> [GAME REQUEST] [%s] [%s] [%s] [%s] [health = %d] [bat = %d] [%s]\n", 
                    url.c_str(), id.c_str(), role.c_str(), status.c_str(), health, battery, comment.c_str());
    }
};

struct tGameApiResponse
{
    int game_duration = 0;
    int game_timeout = 0;
    String role;
    String status;
    uint32_t respTimeMs = 0;
    bool success;
    
    inline void print(void)
    {
        Serial.printf(">>> [GAME RESPONSE] [game_duration = %d] [game_timeout = %d] [role = %s] [status = %s] [time = %u] [success = %s]\n",
                     game_duration, game_timeout, role.c_str(), status.c_str(), respTimeMs, success ? "true" : "false");
    }

    inline tGameRole getRole(void)
    {
        if (role == "none") return grNone;
        if (role == "zombie") return grZombie;
        if (role == "human") return grHuman;
        if (role == "base") return grBase;
        if (role == "server") return grServer;
        if (role == "pinger") return grPinger;
        if (role == "apportalbeacon") return grApPortalBeacon;
        return grNone; // default fallback
    }
};

tGameRole waitGame(uint16_t &preTimeoutMs, uint32_t toMs = 0xffffffff);
void gameApiAsyncInit(void);
void gameApiAsyncStop(void);
tGameApiResponse updateGameStep(String role_, String status_, int health_);