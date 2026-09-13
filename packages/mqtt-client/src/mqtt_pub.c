/*
 * mqtt_pub.c - Lightweight MQTT Publish Client for ESP32-S3 Linux
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <netdb.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <time.h>

#define MQTT_PKT_CONNECT    1
#define MQTT_PKT_CONNACK    2
#define MQTT_PKT_PUBLISH    3
#define MQTT_PKT_PUBACK     4
#define MQTT_PKT_DISCONNECT 14

static int encode_rem_len(uint8_t *buf, int len) {
    int idx = 0;
    do {
        uint8_t d = len % 128;
        len /= 128;
        if (len > 0) d |= 128;
        buf[idx++] = d;
    } while (len > 0);
    return idx;
}

static int connect_tcp(const char *host, int port) {
    struct addrinfo hints, *res, *rp;
    char port_str[16];
    snprintf(port_str, sizeof(port_str), "%d", port);

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    if (getaddrinfo(host, port_str, &hints, &res) != 0) {
        return -1;
    }

    int fd = -1;
    for (rp = res; rp != NULL; rp = rp->ai_next) {
        fd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (fd == -1) continue;
        if (connect(fd, rp->ai_addr, rp->ai_addrlen) != -1) break;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    return fd;
}

int main(int argc, char **argv) {
    const char *host = "127.0.0.1";
    int port = 1883;
    const char *topic = NULL;
    char message_buf[4096] = {0};
    const char *message = NULL;
    int qos = 0;
    char client_id[32];
    snprintf(client_id, sizeof(client_id), "pub-%d", (int)getpid());

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-h") == 0 && i + 1 < argc) host = argv[++i];
        else if (strcmp(argv[i], "-p") == 0 && i + 1 < argc) port = atoi(argv[++i]);
        else if (strcmp(argv[i], "-t") == 0 && i + 1 < argc) topic = argv[++i];
        else if (strcmp(argv[i], "-m") == 0 && i + 1 < argc) message = argv[++i];
        else if (strcmp(argv[i], "-q") == 0 && i + 1 < argc) qos = atoi(argv[++i]);
        else if (strcmp(argv[i], "-i") == 0 && i + 1 < argc) snprintf(client_id, sizeof(client_id), "%s", argv[++i]);
        else if (strcmp(argv[i], "--help") == 0) {
            printf("Usage: mqtt-pub [-h host] [-p port] -t topic [-m message] [-q qos]\n");
            return 0;
        }
    }

    if (!topic) {
        fprintf(stderr, "Error: -t <topic> is required\n");
        return 1;
    }

    if (!message) {
        /* Read from stdin */
        int n = read(STDIN_FILENO, message_buf, sizeof(message_buf) - 1);
        if (n > 0) {
            message_buf[n] = '\0';
            message = message_buf;
        } else {
            message = "";
        }
    }

    int fd = connect_tcp(host, port);
    if (fd < 0) {
        fprintf(stderr, "Error: Could not connect to %s:%d\n", host, port);
        return 1;
    }

    /* 1. Send CONNECT packet */
    uint8_t connect_pkt[128];
    int cid_len = strlen(client_id);
    int var_len = 10 + 2 + cid_len;

    connect_pkt[0] = (MQTT_PKT_CONNECT << 4);
    int hlen = 1;
    hlen += encode_rem_len(&connect_pkt[hlen], var_len);

    /* Protocol name: "MQTT", level 4 (3.1.1) */
    connect_pkt[hlen++] = 0; connect_pkt[hlen++] = 4;
    connect_pkt[hlen++] = 'M'; connect_pkt[hlen++] = 'Q'; connect_pkt[hlen++] = 'T'; connect_pkt[hlen++] = 'T';
    connect_pkt[hlen++] = 4;   /* version 3.1.1 */
    connect_pkt[hlen++] = 2;   /* flags: Clean Session */
    connect_pkt[hlen++] = 0; connect_pkt[hlen++] = 60; /* Keep-Alive 60s */

    connect_pkt[hlen++] = (cid_len >> 8) & 0xFF;
    connect_pkt[hlen++] = cid_len & 0xFF;
    memcpy(&connect_pkt[hlen], client_id, cid_len);
    hlen += cid_len;

    write(fd, connect_pkt, hlen);

    /* Read CONNACK */
    uint8_t connack[4];
    int r = read(fd, connack, 4);
    if (r < 4 || (connack[0] >> 4) != MQTT_PKT_CONNACK || connack[3] != 0) {
        fprintf(stderr, "Error: MQTT connection refused\n");
        close(fd);
        return 1;
    }

    /* 2. Send PUBLISH packet */
    int topic_len = strlen(topic);
    int msg_len = strlen(message);
    int pub_rem_len = 2 + topic_len + (qos > 0 ? 2 : 0) + msg_len;

    uint8_t pub_hdr[16];
    pub_hdr[0] = (MQTT_PKT_PUBLISH << 4) | (qos > 0 ? 2 : 0);
    int phlen = 1;
    phlen += encode_rem_len(&pub_hdr[phlen], pub_rem_len);
    pub_hdr[phlen++] = (topic_len >> 8) & 0xFF;
    pub_hdr[phlen++] = topic_len & 0xFF;

    write(fd, pub_hdr, phlen);
    write(fd, topic, topic_len);
    if (qos > 0) {
        uint8_t pkt_id[2] = {0, 1};
        write(fd, pkt_id, 2);
    }
    if (msg_len > 0) {
        write(fd, message, msg_len);
    }

    if (qos == 1) {
        uint8_t puback[4];
        read(fd, puback, 4);
    }

    /* 3. Send DISCONNECT */
    uint8_t disc[2] = { (MQTT_PKT_DISCONNECT << 4), 0 };
    write(fd, disc, 2);

    close(fd);
    return 0;
}
