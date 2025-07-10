#include "gameEngine.h"


uint32_t tGameRecord::rssi2hp(int rssi)
{
    if (rssi > closeRssi)
        return closePs;

    if (rssi > middleRssi)
        return middlePs;

    if (rssi > farRssi)
        return farHitPs;
    

    return 0;
}

