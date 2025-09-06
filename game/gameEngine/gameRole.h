#pragma once

#include <Arduino.h>

#define R2R_INT_MS  1000

enum tGameRole
{
    grNone = 0,
    grZombie = 1,
    grHuman = 2,
    grBase = 3,
    grServer = 4,
    grPinger = 5,    
    grApPortalBeacon = 55,
    grRssiMonitor = 100
};

inline const char *role2str(tGameRole r)
{
    switch(r)
    {
        case grNone:    return "grNone";
        case grZombie:  return "grZombie";
        case grHuman:   return "grHuman";
        case grBase:    return "grBase";
        case grServer:  return "grServer";
        case grPinger:  return "grPinger";    
        case grRssiMonitor: return "grRssiMonitor";
        case grApPortalBeacon: return ""; 
    }
    return "na";
}

inline tGameRole str2role(const char *roleStr)
{   
    if (strcmp(roleStr, "grZombie") == 0)
    {
        return grZombie;
    }
    else if (strcmp(roleStr, "grHuman") == 0)
    {
        return grHuman;
    }
    else if (strcmp(roleStr, "grBase") == 0)
    {
        return grBase;
    }
    else if (strcmp(roleStr, "grServer") == 0)
    {
        return grServer;
    }
    else if (strcmp(roleStr, "grPinger") == 0)
    {
        return grPinger;
    }
    else if (strcmp(roleStr, "grApPortalBeacon") == 0)
    {
        return grApPortalBeacon;
    } else if (strcmp(roleStr, "grRssiMonitor") == 0)
    {
        return grRssiMonitor;
    }        

    Serial.println("!!! str2role ERROR: bad role string!!!");
    return grNone;
}