#pragma once

#include <Arduino.h>

enum tGameRole
{
    grNone = 0,
    grZombie = 1,
    grHuman = 2,
    grBase = 3,
    grServer = 4,
    grPinger = 5,
    grApPortalBeacon = 55
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
        case grApPortalBeacon: return ""; 
    }
    return "na";
}