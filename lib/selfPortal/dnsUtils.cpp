#include <ESPAsyncWebServer.h>
#include <DNSServer.h>

static DNSServer dnsServer;
const byte DNS_PORT = 53; 

void webDnsInit(void)
{
    Serial.println(">>> DNS started");
    IPAddress myIP = WiFi.softAPIP();
    dnsServer.start(DNS_PORT, "*", myIP);
}


void webDnsLoop(void)
{
    dnsServer.processNextRequest();
}