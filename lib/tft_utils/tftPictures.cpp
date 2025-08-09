#include "tft_utils.h"

void bazaLogo(void)
{
    tftDrawBmp("/xgamelogo.bmp", 0, 0, 536, 240);
    delay(3000);
}

void gameWaitLogo(void)
{
    tftDrawBmp("/xhat.bmp", 0, 0, 536, 240);    
}

void zombiPreWaitPicture(void)
{
    tftDrawBmp("/xzomb.bmp", 0, 0, 536, 240);    
}

void humanPreWaitPicture(void)
{
    tftDrawBmp("/xhum.bmp", 0, 0, 536, 240);    
}